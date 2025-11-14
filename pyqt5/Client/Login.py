import sys
import threading
import queue
import time

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QMessageBox
from PyQt5.uic import loadUi
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QTimer
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
                if task_name == "login":
                    self.handle_login(data)
            except Exception as e:
                print(f"Error in worker: {e}")

    def handle_login(self, data):
        username, password = data

        print(f"🔍 Checking credentials for '{username}'...")
        time.sleep(1)  # Simulate network delay

        try:
            connection = pymysql.connect(
                host="localhost",
                user="root",
                password="Data230308data",
                database="userdata",
                charset='utf8mb4'
            )
            cursor = connection.cursor()

            # Check if username and password match
            query = "SELECT * FROM data WHERE username = %s AND password = %s"
            cursor.execute(query, (username, password))
            user = cursor.fetchone()

            cursor.close()
            connection.close()

            if user:
                print(f"✅ Login successful for '{username}'")
                self.signals.success.emit(username)
            else:
                print(f"❌ Invalid credentials for '{username}'")
                self.signals.error.emit("Invalid username or password")

        except pymysql.Error as e:
            self.signals.error.emit(f"Database error: {str(e)}")
        except Exception as e:
            self.signals.error.emit(f"Error: {str(e)}")


# --- Signals Class ---
class WorkerSignals(QObject):
    success = pyqtSignal(str)
    error = pyqtSignal(str)


# --- Main Application Class ---
class Login(QMainWindow):
    def __init__(self):
        super(Login, self).__init__()
        loadUi("login.ui", self)

        # Create queue
        self.task_queue = queue.Queue()

        # Create signals
        self.signals = WorkerSignals()
        self.signals.success.connect(self.on_login_success)
        self.signals.error.connect(self.on_login_failed)

        # Start background thread
        self.worker = WorkerThread(self.task_queue, self.signals)
        self.worker.start()

        # Connect button events
        self.pushButton_login.clicked.connect(self.loginfunction)
        self.lineEdit_password.setEchoMode(QtWidgets.QLineEdit.Password)

        self.label_register = QLabel('<a href="#" style="text-decoration: none; color: #0066cc;">Register</a>', self)
        self.label_register.setTextFormat(Qt.RichText)
        self.label_register.linkActivated.connect(self.open_register)
        self.label_register.setGeometry(176, 172, 80, 14)

        self.home_window = None

    def loginfunction(self):
        username = self.lineEdit_userName.text().strip()
        password = self.lineEdit_password.text()

        if not username or not password:
            self.show_message("All fields are required", QMessageBox.Warning)
            return

        # Send task to queue
        self.task_queue.put(("login", (username, password)))
        print("🔄 Starting login process...")

    def on_login_success(self, username):
        # מציג הודעת הצלחה
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setText(f"Welcome, {username}!")
        msg.setWindowTitle("Login Success")
        msg.finished.connect(lambda: self.open_home_window())
        msg.exec_()

    def open_home_window(self):

        try:
            self.home_window = QtWidgets.QMainWindow()
            loadUi("home.ui", self.home_window)
            self.home_window.show()
            self.close()
        except Exception as e:
            print(f"Error opening home window: {e}")

    def on_login_failed(self, message):
        self.show_message(message, QMessageBox.Critical)

    def show_message(self, message, icon=QMessageBox.Information):
        msg = QMessageBox(self)
        msg.setIcon(icon)
        msg.setText(message)
        msg.setWindowTitle("Login")
        msg.exec_()

    def open_register(self):
        from signup import Signup
        self.signup_window = Signup()
        self.signup_window.show()
        self.close()