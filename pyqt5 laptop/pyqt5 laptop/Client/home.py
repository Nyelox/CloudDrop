from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QMainWindow, QLabel
from PyQt5.uic import loadUi
from PyQt5.QtCore import Qt

class Home(QMainWindow):
    def __init__(self):
        super().__init__()
        loadUi("home.ui", self)

        self.button_sendfile.clicked.connect(self.open_send_file)
        self.button_sendedfile.clicked.connect(self.open_sended_files)

        self.label_logout = QLabel('<a href="#" style="text-decoration: none; color: #0066cc;">Logout</a>', self)
        self.label_logout.setTextFormat(Qt.RichText)
        self.label_logout.linkActivated.connect(self.go_to_login)
        self.label_logout.setGeometry(340, 10, 47, 16)

    def open_send_file(self):
        from Sendfile import SendFile
        self.sendfile_window = SendFile()
        self.sendfile_window.show()
        self.close()

    def open_sended_files(self):
        pass

    def go_to_login(self):
        from Login import Login
        self.login_window = Login()
        self.login_window.show()
        self.close()
