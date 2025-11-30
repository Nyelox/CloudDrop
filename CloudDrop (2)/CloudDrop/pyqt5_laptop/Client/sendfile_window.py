import os
import base64
import requests

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QMainWindow, QFileDialog, QListWidgetItem, QMessageBox
)
from PyQt5.uic import loadUi


class SendFileWindow(QMainWindow):
    def __init__(self, current_user, users_list, server_url="http://127.0.0.1:5000"):
        super().__init__()


        ui_path = os.path.join(os.path.dirname(__file__), "sendfile_window.ui")
        loadUi(ui_path, self)

        self.current_user = current_user
        self.server_url = server_url
        self.users_list = [u for u in users_list if u != current_user]
        self._online_users_cache = []

        self.selected_file_path = None

        #  עדכון תווית משתמש
        self.label_current_user.setText(f"Connected as: {current_user}")

        # מילוי רשימת משתמשים
        self.combo_receiver.addItems(self.users_list)

        #  חיבור הכפתורים
        self.btn_select.clicked.connect(self.select_file)
        self.btn_send.clicked.connect(self.send_file)
        self.btn_refresh.clicked.connect(self.refresh_incoming)
        self.btn_download.clicked.connect(self.download_selected)
        self.input_filter.textChanged.connect(self.apply_filter)
        self.input_filter.textChanged.connect(self.filter_users_combo)

        #  טיימר heartbeat
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self.send_heartbeat)
        self.heartbeat_timer.start(5000)

        #  טיימר משתמשים אונליין
        self.users_refresh_timer = QTimer(self)
        self.users_refresh_timer.timeout.connect(self.refresh_users_online)
        self.users_refresh_timer.start(7000)

        # טען קבצים נכנסים בהתחלה
        self.refresh_incoming()

    #
    # בחירת קובץ
    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            self.selected_file_path = path
            self.lbl_file.setText(os.path.basename(path))
            self.btn_send.setEnabled(True)

    # שליחת קובץ
    def send_file(self):
        if not self.selected_file_path:
            QMessageBox.warning(self, "Error", "No file selected")
            return

        receiver = self.combo_receiver.currentText()
        minutes = int(self.spin_minutes.value())
        filename = os.path.basename(self.selected_file_path)

        with open(self.selected_file_path, "rb") as f:
            raw = f.read()

        encoded = base64.b64encode(raw).decode()

        payload = {
            "sender": self.current_user,
            "receiver": receiver,
            "filename": filename,
            "filedata": encoded,
            "minutes": minutes
        }

        r = requests.post(f"{self.server_url}/upload_file", json=payload)
        data = r.json()

        if data["status"] == "OK":
            QMessageBox.information(self, "Success", "The file was sent successfully")
            self.lbl_file.setText("No ")
            self.btn_send.setEnabled(False)
        else:
            QMessageBox.warning(self, "Error", str(data))

    # heartbeat לשרת (משתמש אונליין)
    def send_heartbeat(self):
        try:
            requests.post(
                f"{self.server_url}/user_online",
                json={"username": self.current_user},
                timeout=2
            )
        except:
            pass

    # רענון קבצים נכנסים
    def refresh_incoming(self):
        self.list_incoming.clear()

        payload = {"receiver": self.current_user}
        r = requests.post(f"{self.server_url}/incoming_files", json=payload)
        data = r.json()

        if data.get("status") != "OK":
            return

        self.incoming_raw = data["files"]

        for f in self.incoming_raw:
            txt = f"{f['filename']} | From: {f['sender']} | Expires: {f['expires_at']}"
            item = QListWidgetItem(txt)
            item.setData(Qt.UserRole, f["id"])
            self.list_incoming.addItem(item)

        self.apply_filter()

    # רענון רשימת משתמשים אונליין
    def refresh_users_online(self):
        try:
            r = requests.get(f"{self.server_url}/online_users", timeout=2)
            data = r.json()
            if data.get("status") != "OK":
                return

            online_users = data.get("online", [])
            self._online_users_cache = [u for u in online_users if u != self.current_user]

            self.rebuild_receivers()

        except:
            pass

    #סינון רשימת המשתמשים
    def rebuild_receivers(self):
        filter_text = self.input_filter.text().lower()

        self.combo_receiver.blockSignals(True)
        self.combo_receiver.clear()

        for u in self._online_users_cache:
            if filter_text in u.lower():
                self.combo_receiver.addItem(u)

        self.combo_receiver.blockSignals(False)

    def filter_users_combo(self):
        self.rebuild_receivers()

    # סינון קבצים
    def apply_filter(self):
        filter_text = self.input_filter.text().lower()
        for i in range(self.list_incoming.count()):
            item = self.list_incoming.item(i)
            item.setHidden(filter_text not in item.text().lower())

    # הורדת קובץ
    def download_selected(self):
        item = self.list_incoming.currentItem()
        if not item:
            QMessageBox.information(self, "No Selection", "Please select a file from the list")
            return

        file_id = item.data(Qt.UserRole)
        payload = {"receiver": self.current_user, "file_id": file_id}

        r = requests.post(f"{self.server_url}/get_file", json=payload)
        data = r.json()

        if data.get("status") != "OK":
            QMessageBox.warning(self, "Error", data["status"])
            return

        raw = base64.b64decode(data["filedata"])
        save_path, _ = QFileDialog.getSaveFileName(self, "Save File", data["filename"])

        if save_path:
            with open(save_path, "wb") as f:
                f.write(raw)
            QMessageBox.information(self, "Sucess", "The file has been saved successfully")
