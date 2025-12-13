import os
from PyQt5.QtWidgets import QMainWindow, QLabel
from PyQt5.uic import loadUi
from PyQt5.QtCore import Qt

class Home(QMainWindow):
    def __init__(self, current_user="", users_list=None, server_url="http://127.0.0.1:5000"):
        super().__init__()
        ui_path = os.path.join(os.path.dirname(__file__), "home.ui")
        loadUi(ui_path, self)

        self.current_user = current_user or ""
        self.users_list = users_list or []
        self.server_url = server_url

        self.button_sendfile.clicked.connect(self.open_send_file)
        self.button_sendedfile.clicked.connect(self.open_sended_files)

        self.label_logout = QLabel(
            '<a href="#" style="text-decoration: none; color: #0066cc;">Logout</a>',
            self
        )
        self.label_logout.setTextFormat(Qt.RichText)
        self.label_logout.linkActivated.connect(self.go_to_login)
        self.label_logout.setGeometry(340, 10, 47, 16)

        self.sendfile_window = None
        self.login_window = None

    def open_send_file(self):
        from Client.sendfile_window import SendFileWindow

        users = self.users_list if self.users_list else [self.current_user]

        self.sendfile_window = SendFileWindow(
            current_user=self.current_user,
            users_list=users,
            server_url=self.server_url
        )

        self.sendfile_window.destroyed.connect(self._return_from_sendfile)
        self.sendfile_window.show()
        self.hide()

    def _return_from_sendfile(self):
        self.show()

    def open_sended_files(self):
        pass

    def go_to_login(self):
        from Login import Login
        self.login_window = Login()
        self.login_window.show()
        self.close()
