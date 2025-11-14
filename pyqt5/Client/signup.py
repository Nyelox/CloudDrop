import sys
import threading
import queue
import time

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QLabel
from PyQt5.uic import loadUi
from PyQt5.QtCore import Qt, QObject, pyqtSignal
import pymysql


# --- Worker Thread Class ---
class WorkerThread(threading.Thread):
    def __init__(self, task_queue, signals):
        super().__init__(daemon=True)
        self.task_queue = task_queue
        self.signals = signals

    def run(self):
        while True:
            try:
                task_name, data = self.task_queue.get()
                if task_name == "signup":
                    self.handle_signup(data)
            except Exception as e:
                print(f"Error in worker: {e}")

    def handle_signup(self, data):
        username, password = data

        print(f"🔍 Checking if username '{username}' exists...")
        time.sleep(1)  # Simulate network delay

        try:
            connection = pymysql.connect(
                host="localhost",
                user="root",
                password="Data230308data",
                database="userdata",
            )
            cursor = connection.cursor()

            # First check if username exists
            check_query = "SELECT username FROM data WHERE username = %s"
            cursor.execute(check_query, (username,))
            result = cursor.fetchone()

            if result:
                cursor.close()
                connection.close()
                self.signals.error.emit(f"Username '{username}' already exists!")
                return

            print(f"✅ Username available, creating account...")
            time.sleep(1)  # Simulate processing time

            # Insert new user
            query = "INSERT INTO data (username, password) VALUES (%s, %s)"
            cursor.execute(query, (username, password))
            connection.commit()

            cursor.close()
            connection.close()

            # Send success signal
            self.signals.success.emit("Signup successful!")

        except pymysql.Error as e:
            self.signals.error.emit(f"Database error: {str(e)}")
        except Exception as e:
            self.signals.error.emit(f"Error: {str(e)}")


# --- Signals Class ---
class WorkerSignals(QObject):
    success = pyqtSignal(str)
    error = pyqtSignal(str)


# --- Main Application Class ---
class Signup(QMainWindow):
    def __init__(self):
        super(Signup, self).__init__()
        loadUi('signup.ui', self)

        # Create queue
        self.task_queue = queue.Queue()

        # Create signals
        self.signals = WorkerSignals()
        self.signals.success.connect(self.on_signup_success)
        self.signals.error.connect(self.show_message)

        # Start background thread
        self.worker = WorkerThread(self.task_queue, self.signals)
        self.worker.start()

        # Connect button events
        self.pushButton_signUp.clicked.connect(self.signup_function)
        self.lineEdit_password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.lineEdit_confirmPassword.setEchoMode(QtWidgets.QLineEdit.Password)

        self.label_login = QLabel('<a href="#" style="text-decoration: none; color: #0066cc;">Click here!</a>', self)
        self.label_login.setTextFormat(Qt.RichText)
        self.label_login.setOpenExternalLinks(False)
        self.label_login.linkActivated.connect(self.go_to_login)
        self.label_login.setGeometry(152, 174, 80, 14)

    def signup_function(self):
        username = self.lineEdit_userName.text().strip()
        password = self.lineEdit_password.text()
        confirm_password = self.lineEdit_confirmPassword.text()

        if not username or not password or not confirm_password:
            self.show_message("All fields are required")
            return

        if password != confirm_password:
            self.show_message("Passwords do not match")
            return

        # Send task to queue
        self.task_queue.put(("signup", (username, password)))
        print("🔄 Starting signup process...")

    def on_signup_success(self, message):
        self.show_message(message)
        self.go_to_login()

    def show_message(self, text):
        QMessageBox.information(self, "Signup", text)

    def go_to_login(self):
        try:
            from Login import Login
            self.login_window = Login()
            self.login_window.show()
            self.close()
        except ImportError:
            self.show_message("Login module not found")
        except Exception as e:
            self.show_message(f"Could not open login: {str(e)}")
