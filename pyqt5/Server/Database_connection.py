import pymysql


def handle_login(username, password):

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
        stored_password = result[0]
        if password == stored_password:
            return "Login successful"
        else:
            return "Invalid username or password"
    else:
        return "Invalid username or password"


def handle_signup(username, password):

    con = pymysql.connect(
        host='localhost',
        user='root',
        password='Data230308data',
        database='userdata',
    )
    cursor = con.cursor()

    cursor.execute('SELECT * FROM data WHERE username=%s', (username,))
    if cursor.fetchone():
        response = "Username already exists"
    else:
        cursor.execute('INSERT INTO data(username, password) VALUES (%s, %s)', (username, password))
        con.commit()
        response = "Sign Up successful"

    con.close()
    return response