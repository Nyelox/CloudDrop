import os
import base64
import uuid
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
import pymysql
from werkzeug.utils import secure_filename

from Server.Database_connection import handle_login, handle_signup
from supabase import create_client, Client

SUPABASE_URL = "https://trgaimvzokzrtapgkxsd.supabase.co"
# TODO: REPLACE WITH SERVICE ROLE KEY (from Project Settings -> API -> service_role)
# The 'anon' key will NOT work if you disable Public Access.
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRyZ2FpbXZ6b2t6cnRhcGdreHNkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTQ3MDQ2NSwiZXhwIjoyMDgxMDQ2NDY1fQ.8VFdJPQEmCsMqnnAUBGYFuG0tUtPzOroSx6hnKEF2og"
SUPABASE_BUCKET = "Files"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

APP_HOST = "0.0.0.0"
APP_PORT = 5000

UPLOAD_DIR = "uploaded_files"
MAX_FILE_MB = 50

online_users = {}
ONLINE_TIMEOUT_SECONDS = 20

DB_CONFIG = dict(
    host='localhost',
    user='root',
    password='Data230308data',
    database='userdata',
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)

app = Flask(__name__)
# Max content length applies to the request body, still relevant for upload limit
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_MB * 1024 * 1024




def get_db():
    return pymysql.connect(**DB_CONFIG)


def init_db():
    con = get_db()
    cur = con.cursor()
    
    # Shared files table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS shared_files (
            id INT AUTO_INCREMENT PRIMARY KEY,
            file_uid VARCHAR(64) NOT NULL,
            sender VARCHAR(255) NOT NULL,
            receiver VARCHAR(255) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            path VARCHAR(500) NOT NULL,
            expires_at DATETIME NOT NULL,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # History table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            action VARCHAR(255) NOT NULL,
            details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # System Settings table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            setting_key VARCHAR(50) PRIMARY KEY,
            setting_value VARCHAR(255)
        );
    """)
    
    # Insert default global max downloads if not exists
    cur.execute("SELECT setting_value FROM system_settings WHERE setting_key='global_max_downloads'")
    if not cur.fetchone():
        cur.execute("INSERT INTO system_settings (setting_key, setting_value) VALUES ('global_max_downloads', '5')")

    # Print jobs table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS print_jobs (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            file_id       INT NOT NULL,
            sender        VARCHAR(255) NOT NULL,
            filename      VARCHAR(255) NOT NULL,
            file_type     VARCHAR(20) NOT NULL,
            print_allowed BOOLEAN DEFAULT 0,
            print_status  ENUM('pending','printed') DEFAULT 'pending',
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Update 'data' table with new columns if they don't exist
    def add_column(table, col, defi):
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defi}")
        except Exception:
            pass # Column likely exists

    add_column("data", "is_blocked", "BOOLEAN DEFAULT 0")
    add_column("data", "is_admin", "BOOLEAN DEFAULT 0")

    add_column("shared_files", "message", "TEXT")

    con.commit()
    con.close()


def log_history(username, action, details=""):
    try:
        con = get_db()
        cur = con.cursor()
        cur.execute("INSERT INTO history (username, action, details) VALUES (%s, %s, %s)", 
                    (username, action, details))
        con.commit()
        con.close()
    except Exception as e:
        print(f"Failed to log history: {e}")


def cleanup_expired_files():
    # ... existing cleanup code ...
    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT id, path FROM shared_files WHERE expires_at < NOW()")
    expired = cur.fetchall()

    for row in expired:
        # Remove from Supabase
        try:
            supabase.storage.from_(SUPABASE_BUCKET).remove([row["path"]])
        except Exception as e:
            print(f"Error removing file from Supabase: {e}")

        # Also try local cleanup in case mixed usage or migration
        try:
            if os.path.exists(row["path"]):
                os.remove(row["path"])
        except Exception:
            pass

        cur.execute("DELETE FROM shared_files WHERE id=%s", (row["id"],))

    con.commit()
    con.close()


@app.before_request
def before_any_request():
    cleanup_expired_files()


@app.route("/signup", methods=["POST"])
def api_signup():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"status": "Missing fields"}), 400

    res = handle_signup(username, password)
    # res is now a dict
    if res.get("status") == "success":
        log_history(username, "SIGNUP", "User created account")
        return jsonify({"status": res["message"]})
    
    return jsonify({"status": res.get("message", "Error")})


@app.route("/login", methods=["POST"])
def api_login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"status": "Missing fields"}), 400

    res = handle_login(username, password)
    
    if res.get("status") == "success":
        log_history(username, "LOGIN", "User logged in")
        return jsonify({
            "status": res["message"], 
            "is_admin": res.get("is_admin", False),
            "is_blocked": res.get("is_blocked", False)
        })
    
    return jsonify({"status": res.get("message", "Login failed")})


@app.route("/upload_file", methods=["POST"])
def upload_file():
    data = request.json
    sender = data.get("sender", "").strip()
    receiver = data.get("receiver", "").strip()
    filename = data.get("filename", "").strip()
    filedata_b64 = data.get("filedata", "")
    minutes = int(data.get("minutes", 10))

    message = data.get("message", "").strip()

    if not all([sender, receiver, filename]) or "filedata" not in data:
        return jsonify({"status": "Missing fields"}), 400

    safe_name = secure_filename(filename)
    if not safe_name:
        return jsonify({"status": "Bad filename"}), 400

    try:
        raw_bytes = base64.b64decode(filedata_b64)
    except Exception:
        return jsonify({"status": "Invalid base64"}), 400

    file_uid = uuid.uuid4().hex
    server_filename = f"{file_uid}_{safe_name}"
    path = server_filename

    try:
        supabase.storage.from_(SUPABASE_BUCKET).upload(path, raw_bytes, {"content-type": "application/octet-stream"})
    except Exception as e:
        print(f"Supabase upload error: {e}")
        return jsonify({"status": "Storage Error"}), 500

    expires_at = datetime.now() + timedelta(minutes=minutes)

    con = get_db()
    cur = con.cursor()
    # Explicitly save message
    cur.execute("""
        INSERT INTO shared_files(file_uid, sender, receiver, filename, path, expires_at, message)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (file_uid, sender, receiver, safe_name, path, expires_at, message))
    con.commit()
    con.close()

    log_history(sender, "UPLOAD", f"Sent file '{safe_name}' to {receiver}")

    return jsonify({"status": "OK"})


@app.route("/incoming_files", methods=["POST"])
def incoming_files():
    data = request.json
    receiver = data.get("receiver", "").strip()
    if not receiver:
        return jsonify({"status": "Missing receiver"}), 400

    con = get_db()
    cur = con.cursor()
    # We can also fetch max_downloads setting to show user how many left, ideally
    # But for now just basic list
    cur.execute("""
        SELECT id, sender, filename, uploaded_at, expires_at, message
        FROM shared_files
        WHERE receiver=%s AND expires_at >= NOW()
        ORDER BY uploaded_at DESC
    """, (receiver,))
    rows = cur.fetchall()
    con.close()

    return jsonify({"status": "OK", "files": rows})


@app.route("/get_file", methods=["POST"])
def get_file():
    """
    JSON: { receiver, file_id }
    """
    data = request.json
    receiver = data.get("receiver", "").strip()
    file_id = data.get("file_id")

    if not receiver or not file_id:
        return jsonify({"status": "Missing fields"}), 400

    con = get_db()
    cur = con.cursor()
    
    # 1. Get Global Limit
    cur.execute("SELECT setting_value FROM system_settings WHERE setting_key='global_max_downloads'")
    # 2. Get File Info
    cur.execute("""
        SELECT filename, path, expires_at
        FROM shared_files
        WHERE id=%s AND receiver=%s
    """, (file_id, receiver))
    row = cur.fetchone()

    if not row:
        con.close()
        return jsonify({"status": "Not found"}), 404

    if datetime.now() > row["expires_at"]:
        con.close()
        return jsonify({"status": "File expired"}), 403
    
    con.close()

    # Download from Supabase
    try:
        response = supabase.storage.from_(SUPABASE_BUCKET).download(row["path"])
        raw = response
    except Exception as e:
        print(f"Supabase download error: {e}")
        if os.path.exists(row["path"]):
            with open(row["path"], "rb") as f:
                raw = f.read()
        else:
            return jsonify({"status": "File not found"}), 404

    encoded = base64.b64encode(raw).decode()
    
    log_history(receiver, "DOWNLOAD", f"Downloaded file '{row['filename']}'")

    return jsonify({"status": "OK", "filename": row["filename"], "filedata": encoded})



@app.route("/all_sent_files", methods=["GET"])
def all_sent_files():
    """
    Operator view: returns ALL shared_files rows (no receiver filter).
    Optional query param ?admin_user=<username> for future auth gating.
    """
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, sender, receiver, filename, path, uploaded_at, expires_at, message
        FROM shared_files
        ORDER BY uploaded_at DESC
    """)
    rows = cur.fetchall()
    con.close()

    # Convert datetime objects to strings for JSON serialisation
    for r in rows:
        if r.get("uploaded_at"):
            r["uploaded_at"] = str(r["uploaded_at"])
        if r.get("expires_at"):
            r["expires_at"] = str(r["expires_at"])

    return jsonify({"status": "OK", "files": rows})


@app.route("/request_print", methods=["POST"])
def request_print():
    """
    JSON: { file_id, operator }
    Downloads file bytes from Supabase, returns base64,
    and inserts a 'pending' print_jobs record.
    """
    data = request.json
    file_id = data.get("file_id")
    operator = data.get("operator", "operator").strip()

    if not file_id:
        return jsonify({"status": "Missing file_id"}), 400

    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, sender, filename, path
        FROM shared_files
        WHERE id=%s
    """, (file_id,))
    row = cur.fetchone()

    if not row:
        con.close()
        return jsonify({"status": "File not found"}), 404

    filename = row["filename"]
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    print_allowed = ext in ("pdf", "docx")

    # Download from Supabase
    try:
        raw = supabase.storage.from_(SUPABASE_BUCKET).download(row["path"])
    except Exception as e:
        con.close()
        print(f"Supabase download error: {e}")
        return jsonify({"status": "Storage error"}), 500

    # Insert pending print job
    cur.execute("""
        INSERT INTO print_jobs (file_id, sender, filename, file_type, print_allowed, print_status)
        VALUES (%s, %s, %s, %s, %s, 'pending')
    """, (file_id, row["sender"], filename, ext, int(print_allowed)))
    job_id = cur.lastrowid
    con.commit()
    con.close()

    encoded = base64.b64encode(raw).decode()
    log_history(operator, "PRINT_REQUEST", f"Requested print of '{filename}' (job #{job_id})")

    return jsonify({
        "status": "OK",
        "job_id": job_id,
        "filename": filename,
        "file_type": ext,
        "filedata": encoded
    })


@app.route("/update_print_status", methods=["POST"])
def update_print_status():
    """
    JSON: { job_id, status }  where status is 'pending' or 'printed'
    """
    data = request.json
    job_id = data.get("job_id")
    status = data.get("status", "printed").strip()

    if not job_id or status not in ("pending", "printed"):
        return jsonify({"status": "Missing or invalid fields"}), 400

    con = get_db()
    cur = con.cursor()
    cur.execute("UPDATE print_jobs SET print_status=%s WHERE id=%s", (status, job_id))
    con.commit()
    con.close()

    return jsonify({"status": "OK"})


@app.route("/all_users", methods=["GET"])
def all_users():
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT username FROM data ORDER BY username")
    rows = cur.fetchall()
    con.close()

    users = [r["username"] for r in rows]
    return jsonify({"status": "OK", "users": users})


@app.route("/user_online", methods=["POST"])
def user_online():
    data = request.json
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"status": "Missing username"}), 400

    online_users[username] = datetime.now()
    return jsonify({"status": "OK"})


@app.route("/online_users", methods=["GET"])
def online_users_list():
    now = datetime.now()
    active = [
        u for u, t in online_users.items()
        if (now - t).total_seconds() < ONLINE_TIMEOUT_SECONDS
    ]
    return jsonify({"status": "OK", "online": active})

# --- Admin Endpoints ---

def is_admin(username):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT is_admin FROM data WHERE username=%s", (username,))
    res = cur.fetchone()
    con.close()
    return res and res["is_admin"]

@app.route("/admin/users", methods=["POST"])
def admin_users():
    data = request.json
    admin_user = data.get("admin_user", "")
    
    if not is_admin(admin_user):
        return jsonify({"status": "Forbidden"}), 403

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT username, is_blocked, is_admin FROM data ORDER BY username")
    rows = cur.fetchall()
    con.close()
    
    for r in rows:
        r["is_blocked"] = bool(r["is_blocked"])
        r["is_admin"] = bool(r["is_admin"])

    return jsonify({"status": "OK", "users": rows})

@app.route("/admin/block_user", methods=["POST"])
def admin_block_user():
    data = request.json
    admin_user = data.get("admin_user", "")
    target_user = data.get("target_user", "")
    block = data.get("block", False)

    if not is_admin(admin_user):
        return jsonify({"status": "Forbidden"}), 403
    
    if admin_user == target_user:
        return jsonify({"status": "Cannot block self"}), 400

    con = get_db()
    cur = con.cursor()
    cur.execute("UPDATE data SET is_blocked=%s WHERE username=%s", (1 if block else 0, target_user))
    con.commit()
    con.close()
    
    action = "BLOCKED" if block else "UNBLOCKED"
    log_history(admin_user, "ADMIN_ACTION", f"{action} user {target_user}")

    return jsonify({"status": "OK"})

@app.route("/admin/history", methods=["POST"])
def admin_history():
    data = request.json
    admin_user = data.get("admin_user", "")
    target_user = data.get("target_user", None)

    if not is_admin(admin_user):
        return jsonify({"status": "Forbidden"}), 403

    con = get_db()
    cur = con.cursor()
    
    if target_user:
        cur.execute("SELECT * FROM history WHERE username=%s ORDER BY timestamp DESC", (target_user,))
    else:
        cur.execute("SELECT * FROM history ORDER BY timestamp DESC")
        
    rows = cur.fetchall()
    con.close()

    return jsonify({"status": "OK", "history": rows})



if __name__ == "__main__":
    init_db()
    app.run(host=APP_HOST, port=APP_PORT, debug=True)
