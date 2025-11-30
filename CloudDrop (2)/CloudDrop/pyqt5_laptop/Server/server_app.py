import os
import base64
import uuid
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
import pymysql
from werkzeug.utils import secure_filename

from Server.Database_connection import handle_login, handle_signup

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
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_MB * 1024 * 1024


def get_db():
    return pymysql.connect(**DB_CONFIG)


def init_db():
    con = get_db()
    cur = con.cursor()
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
    con.commit()
    con.close()


def cleanup_expired_files():

    con = get_db()
    cur = con.cursor()

    cur.execute("SELECT id, path FROM shared_files WHERE expires_at < NOW()")
    expired = cur.fetchall()

    for row in expired:
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
    return jsonify({"status": res})


@app.route("/login", methods=["POST"])
def api_login():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"status": "Missing fields"}), 400

    res = handle_login(username, password)
    return jsonify({"status": res})


@app.route("/upload_file", methods=["POST"])
def upload_file():

    data = request.json
    sender = data.get("sender", "").strip()
    receiver = data.get("receiver", "").strip()
    filename = data.get("filename", "").strip()
    filedata_b64 = data.get("filedata", "")
    minutes = int(data.get("minutes", 10))

    if not all([sender, receiver, filename, filedata_b64]):
        return jsonify({"status": "Missing fields"}), 400

    # שומר שם קובץ בטוח
    safe_name = secure_filename(filename)
    if not safe_name:
        return jsonify({"status": "Bad filename"}), 400

    # מפענח
    try:
        raw_bytes = base64.b64decode(filedata_b64)
    except Exception:
        return jsonify({"status": "Invalid base64"}), 400

    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)

    file_uid = uuid.uuid4().hex
    server_filename = f"{file_uid}_{safe_name}"
    path = os.path.join(UPLOAD_DIR, server_filename)

    with open(path, "wb") as f:
        f.write(raw_bytes)

    expires_at = datetime.now() + timedelta(minutes=minutes)

    con = get_db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO shared_files(file_uid, sender, receiver, filename, path, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (file_uid, sender, receiver, safe_name, path, expires_at))
    con.commit()
    con.close()

    return jsonify({"status": "OK"})


@app.route("/incoming_files", methods=["POST"])
def incoming_files():

    data = request.json
    receiver = data.get("receiver", "").strip()
    if not receiver:
        return jsonify({"status": "Missing receiver"}), 400

    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, sender, filename, uploaded_at, expires_at
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
    מחזיר filedata(base64) אם בתוקף.
    """
    data = request.json
    receiver = data.get("receiver", "").strip()
    file_id = data.get("file_id")

    if not receiver or not file_id:
        return jsonify({"status": "Missing fields"}), 400

    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT filename, path, expires_at
        FROM shared_files
        WHERE id=%s AND receiver=%s
    """, (file_id, receiver))
    row = cur.fetchone()
    con.close()

    if not row:
        return jsonify({"status": "Not found"}), 404

    if datetime.now() > row["expires_at"]:
        return jsonify({"status": "File expired"}), 403

    with open(row["path"], "rb") as f:
        raw = f.read()

    encoded = base64.b64encode(raw).decode()
    return jsonify({"status": "OK", "filename": row["filename"], "filedata": encoded})


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


if __name__ == "__main__":
    init_db()
    app.run(host=APP_HOST, port=APP_PORT, debug=True)
