import mysql.connector


def connect_database():
    # Establish the connection
    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password="Data230308data",
        database="userdata"
    )

    cursor = connection.cursor()
    return connection, cursor


def signup(cursor, connection, username, password):
    try:
        # MySQL uses %s for placeholders, not ?
        query = "INSERT INTO userdata (username, password) VALUES (%s, %s)"
        data = (username, password)

        cursor.execute(query, data)
        connection.commit()  # Save changes to database

        print(f"User '{username}' added successfully!")
        return True

    except mysql.connector.IntegrityError:
        print("Error: Username already exists!")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def login(cursor, username, password):

    try:
        query = "SELECT * FROM userdata WHERE username = %s AND password = %s"
        cursor.execute(query, (username, password))

        user = cursor.fetchone()

        if user:
            print(f"Login successful! Welcome, {username}!")
            return True
        else:
            print("Login failed: Invalid username or password")
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False
