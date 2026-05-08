import os
import base64
import requests

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QMainWindow, QFileDialog, QListWidgetItem, QMessageBox
)
from PyQt5.uic import loadUi


# ── Background workers (keep UI thread free) ─────────────────────────────────

class HeartbeatThread(QThread):
    def __init__(self, server_url, username):
        super().__init__()
        self.server_url = server_url
        self.username   = username

    def run(self):
        try:
            requests.post(
                f"{self.server_url}/user_online",
                json={"username": self.username},
                timeout=3
            )
        except Exception:
            pass


class UsersRefreshThread(QThread):
    done = pyqtSignal(list)   # list of (display, username) tuples

    def __init__(self, server_url, current_user):
        super().__init__()
        self.server_url   = server_url
        self.current_user = current_user

    def run(self):
        try:
            r_all  = requests.get(f"{self.server_url}/all_users", timeout=5)
            all_users = r_all.json().get("users", [])
        except Exception:
            all_users = []

        try:
            r_on   = requests.get(f"{self.server_url}/online_users", timeout=3)
            online_set = set(r_on.json().get("online", []))
        except Exception:
            online_set = set()

        others       = [u for u in all_users if u != self.current_user]
        online_first = [u for u in others if u in online_set]
        offline_rest = [u for u in others if u not in online_set]

        result = [(u, u) for u in online_first] + [(u, u) for u in offline_rest]
        self.done.emit(result)


class IncomingFilesThread(QThread):
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, server_url, receiver):
        super().__init__()
        self.server_url = server_url
        self.receiver   = receiver

    def run(self):
        try:
            r    = requests.post(
                f"{self.server_url}/incoming_files",
                json={"receiver": self.receiver},
                timeout=8
            )
            data = r.json()
            if data.get("status") == "OK":
                self.done.emit(data.get("files", []))
            else:
                self.error.emit(data.get("status", "Error"))
        except Exception as e:
            self.error.emit(str(e))


class SendFileThread(QThread):
    success = pyqtSignal()
    error   = pyqtSignal(str)

    def __init__(self, server_url, payload):
        super().__init__()
        self.server_url = server_url
        self.payload    = payload

    def run(self):
        try:
            r    = requests.post(f"{self.server_url}/upload_file",
                                 json=self.payload, timeout=30)
            data = r.json()
            if data.get("status") == "OK":
                self.success.emit()
            else:
                self.error.emit(data.get("status", "Upload failed"))
        except Exception as e:
            self.error.emit(str(e))


class DownloadFileThread(QThread):
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, server_url, receiver, file_id):
        super().__init__()
        self.server_url = server_url
        self.receiver   = receiver
        self.file_id    = file_id

    def run(self):
        try:
            r    = requests.post(
                f"{self.server_url}/get_file",
                json={"receiver": self.receiver, "file_id": self.file_id},
                timeout=30
            )
            data = r.json()
            if data.get("status") == "OK":
                self.done.emit(data)
            else:
                self.error.emit(data.get("status", "Error"))
        except Exception as e:
            self.error.emit(str(e))


# ── Main window ───────────────────────────────────────────────────────────────

class SendFileWindow(QMainWindow):
    def __init__(self, current_user, users_list, server_url="http://127.0.0.1:5000"):
        super().__init__()

        ui_path = os.path.join(os.path.dirname(__file__), "sendfile_window.ui")
        loadUi(ui_path, self)

        self.current_user     = current_user
        self.server_url       = server_url
        self._all_users_cache = []
        self._threads: list   = []   # keep refs so threads aren't GC'd
        self.selected_file_path = None
        self.incoming_raw       = []

        self.label_current_user.setText(f"Connected as: {current_user}")

        # buttons
        self.btn_select.clicked.connect(self.select_file)
        self.btn_send.clicked.connect(self.send_file)
        self.btn_refresh.clicked.connect(self.refresh_incoming)
        self.btn_download.clicked.connect(self.download_selected)
        self.input_filter.textChanged.connect(self.apply_filter)
        self.input_filter.textChanged.connect(self.rebuild_receivers)

        # heartbeat timer — fires thread, never blocks UI
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self._send_heartbeat)
        self.heartbeat_timer.start(8000)

        # users refresh timer
        self.users_refresh_timer = QTimer(self)
        self.users_refresh_timer.timeout.connect(self.refresh_users_online)
        self.users_refresh_timer.start(15000)

        # initial load (non-blocking)
        self.refresh_incoming()
        self.refresh_users_online()

    # ── file selection ────────────────────────────────────────────────────────

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            self.selected_file_path = path
            self.lbl_file.setText(os.path.basename(path))
            self.btn_send.setEnabled(True)

    # ── send file ─────────────────────────────────────────────────────────────

    def send_file(self):
        if not self.selected_file_path:
            QMessageBox.warning(self, "Error", "No file selected")
            return

        receiver = self.combo_receiver.currentData()
        if not receiver:
            receiver = self.combo_receiver.currentText().strip()
        if not receiver:
            QMessageBox.warning(self, "Error", "Please select a recipient")
            return

        filename = os.path.basename(self.selected_file_path)
        with open(self.selected_file_path, "rb") as f:
            raw = f.read()

        payload = {
            "sender":   self.current_user,
            "receiver": receiver,
            "filename": filename,
            "filedata": base64.b64encode(raw).decode(),
            "minutes":  int(self.spin_minutes.value()),
            "message":  self.input_file_message.text().strip(),
        }

        self.btn_send.setEnabled(False)
        self.btn_send.setText("Sending...")

        t = SendFileThread(self.server_url, payload)
        t.success.connect(self._on_send_success)
        t.error.connect(self._on_send_error)
        self._threads.append(t)
        t.start()

    def _on_send_success(self):
        self.btn_send.setText("Send")
        self.btn_send.setEnabled(True)
        QMessageBox.information(self, "Success", "File sent successfully")
        self.lbl_file.setText("No file selected")
        self.input_file_message.clear()
        self.selected_file_path = None

    def _on_send_error(self, msg):
        self.btn_send.setText("Send")
        self.btn_send.setEnabled(True)
        QMessageBox.warning(self, "Error", msg)

    # ── heartbeat ─────────────────────────────────────────────────────────────

    def _send_heartbeat(self):
        t = HeartbeatThread(self.server_url, self.current_user)
        self._threads.append(t)
        t.start()

    # ── incoming files ────────────────────────────────────────────────────────

    def refresh_incoming(self):
        t = IncomingFilesThread(self.server_url, self.current_user)
        t.done.connect(self._on_incoming_loaded)
        t.error.connect(lambda _: None)   # silent fail on background refresh
        self._threads.append(t)
        t.start()

    def _on_incoming_loaded(self, files):
        self.list_incoming.clear()
        self.incoming_raw = files
        for f in files:
            msg_part = f" | Msg: {f['message']}" if f.get("message") else ""
            txt  = (f"{f['filename']} | From: {f['sender']} "
                    f"| Expires: {f['expires_at']}{msg_part}")
            item = QListWidgetItem(txt)
            item.setData(Qt.UserRole, f["id"])
            self.list_incoming.addItem(item)
        self.apply_filter()

    # ── users refresh ─────────────────────────────────────────────────────────

    def refresh_users_online(self):
        t = UsersRefreshThread(self.server_url, self.current_user)
        t.done.connect(self._on_users_loaded)
        self._threads.append(t)
        t.start()

    def _on_users_loaded(self, users):
        self._all_users_cache = users
        self.rebuild_receivers()

    def rebuild_receivers(self):
        filter_text = self.input_filter.text().lower()
        self.combo_receiver.blockSignals(True)
        self.combo_receiver.clear()
        for display, username in self._all_users_cache:
            if filter_text in username.lower():
                self.combo_receiver.addItem(display, userData=username)
        self.combo_receiver.blockSignals(False)

    def filter_users_combo(self):
        self.rebuild_receivers()

    # ── filter incoming list ──────────────────────────────────────────────────

    def apply_filter(self):
        filter_text = self.input_filter.text().lower()
        for i in range(self.list_incoming.count()):
            item = self.list_incoming.item(i)
            item.setHidden(filter_text not in item.text().lower())

    # ── download ──────────────────────────────────────────────────────────────

    def download_selected(self):
        item = self.list_incoming.currentItem()
        if not item:
            QMessageBox.information(self, "No Selection",
                                    "Please select a file from the list")
            return

        file_id = item.data(Qt.UserRole)
        self.btn_download.setEnabled(False)
        self.btn_download.setText("Downloading...")

        t = DownloadFileThread(self.server_url, self.current_user, file_id)
        t.done.connect(self._on_download_done)
        t.error.connect(self._on_download_error)
        self._threads.append(t)
        t.start()

    def _on_download_done(self, data):
        self.btn_download.setEnabled(True)
        self.btn_download.setText("Download")

        raw       = base64.b64decode(data["filedata"])
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save File", data["filename"])
        if save_path:
            with open(save_path, "wb") as f:
                f.write(raw)
            QMessageBox.information(self, "Success",
                                    "File saved successfully")

    def _on_download_error(self, msg):
        self.btn_download.setEnabled(True)
        self.btn_download.setText("Download")
        QMessageBox.warning(self, "Error", msg)
