import pymysql
from Server.auth import userauth

auth = userauth()


def handle_login(username, password):
    # Check if account is locked
    locked, lock_message = auth.is_locked(username)
    if locked:
        return lock_message

    con = pymysql.connect(
        host='localhost',
        user='root',
        password='Data230308data',
        database='userdata',
    )
    cursor = con.cursor()

    query = 'SELECT password FROM data WHERE username=%s'
    cursor.execute(query, (username,))
    result = cursor.fetchone()
    con.close()

    if result:
        stored_hash = result[0]
        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode('utf-8')
        if auth.check_password(password, stored_hash):
            if username in auth.login_attempts:
                del auth.login_attempts[username]
            return "Login successful"
        else:
            auth.track_failed_attempt(username)
            return "Invalid username or password"
    else:
        auth.track_failed_attempt(username)
        return "Invalid username or password"


def handle_signup(username, password):

    con = pymysql.connect(
        host='localhost',
        user='root',
        password='Data230308data',
        database='userdata',
    )
    mycursor = con.cursor()

    mycursor.execute('SELECT * FROM data WHERE username=%s', (username,))
    if mycursor.fetchone():
        response = "Username already exists"
    else:
        pwd_hash = auth.hash_password(password)

        if isinstance(pwd_hash, bytes):
            pwd_hash = pwd_hash.decode('utf-8')

        mycursor.execute('INSERT INTO data(username, password) VALUES (%s, %s)', (username, pwd_hash))
        con.commit()
        response = "Sign Up successful"

    con.close()
    return response
