import sys
import requests
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QTableWidget, QTableWidgetItem, 
    QTabWidget, QHeaderView, QMessageBox, QComboBox,
    QLabel
)
from PyQt5.QtCore import Qt

class AdminWindow(QMainWindow):
    def __init__(self, current_user, server_url):
        super().__init__()
        self.current_user = current_user
        self.server_url = server_url
        self.setWindowTitle("Admin Dashboard")
        self.resize(800, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Tabs
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        # Users Tab
        self.users_tab = QWidget()
        self.init_users_tab()
        self.tabs.addTab(self.users_tab, "Users Management")

        # History Tab
        self.history_tab = QWidget()
        self.init_history_tab()
        self.tabs.addTab(self.history_tab, "User History")

        # Settings Tab
        self.settings_tab = QWidget()
        self.init_settings_tab()
        self.tabs.addTab(self.settings_tab, "System Settings")

        self.load_users()
        self.load_history()
        self.load_settings()

    def init_users_tab(self):
        layout = QVBoxLayout(self.users_tab)

        # Table
        self.users_table = QTableWidget()
        self.users_table.setColumnCount(3)
        self.users_table.setHorizontalHeaderLabels(["Username", "Is Blocked", "Is Admin"])
        self.users_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.users_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.users_table.setSelectionMode(QTableWidget.SingleSelection)
        layout.addWidget(self.users_table)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_block = QPushButton("Block Selected")
        self.btn_block.clicked.connect(self.block_user)
        self.btn_unblock = QPushButton("Unblock Selected")
        self.btn_unblock.clicked.connect(self.unblock_user)
        self.btn_refresh_users = QPushButton("Refresh")
        self.btn_refresh_users.clicked.connect(self.load_users)

        btn_layout.addWidget(self.btn_block)
        btn_layout.addWidget(self.btn_unblock)
        btn_layout.addWidget(self.btn_refresh_users)
        layout.addLayout(btn_layout)

    def init_history_tab(self):
        layout = QVBoxLayout(self.history_tab)

        # Controls
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Filter by User:"))
        self.combo_users = QComboBox()
        self.combo_users.addItem("All Users")
        self.combo_users.currentIndexChanged.connect(self.load_history)
        ctrl_layout.addWidget(self.combo_users)
        
        self.btn_refresh_history = QPushButton("Refresh History")
        self.btn_refresh_history.clicked.connect(self.load_history)
        ctrl_layout.addWidget(self.btn_refresh_history)
        
        layout.addLayout(ctrl_layout)

        # Table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["Time", "User", "Action", "Details"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.history_table)

    def init_settings_tab(self):
        from PyQt5.QtWidgets import QSpinBox, QFormLayout
        layout = QFormLayout(self.settings_tab)
        
        self.spin_max_downloads = QSpinBox()
        self.spin_max_downloads.setRange(0, 1000)
        self.spin_max_downloads.setValue(5)
        
        layout.addRow(QLabel("Global Max Downloads per File:"), self.spin_max_downloads)
        
        self.btn_save_settings = QPushButton("Save Settings")
        self.btn_save_settings.clicked.connect(self.save_settings)
        layout.addRow(self.btn_save_settings)
        
        self.lbl_settings_status = QLabel("")
        layout.addRow(self.lbl_settings_status)

    def load_users(self):
        try:
            url = f"{self.server_url}/admin/users"
            resp = requests.post(url, json={"admin_user": self.current_user})
            data = resp.json()

            if data.get("status") == "OK":
                users = data.get("users", [])
                self.users_table.setRowCount(0)
                
                # Update combo box in history tab as well
                current_combo_text = self.combo_users.currentText()
                self.combo_users.blockSignals(True)
                self.combo_users.clear()
                self.combo_users.addItem("All Users")

                for row_idx, user in enumerate(users):
                    self.users_table.insertRow(row_idx)
                    self.users_table.setItem(row_idx, 0, QTableWidgetItem(user["username"]))
                    
                    blocked_item = QTableWidgetItem("Yes" if user["is_blocked"] else "No")
                    if user["is_blocked"]:
                        blocked_item.setBackground(Qt.red)
                    self.users_table.setItem(row_idx, 1, blocked_item)
                    
                    admin_item = QTableWidgetItem("Yes" if user["is_admin"] else "No")
                    self.users_table.setItem(row_idx, 2, admin_item)
                    
                    self.combo_users.addItem(user["username"])

                # Restore combo selection if possible
                index = self.combo_users.findText(current_combo_text)
                if index >= 0:
                    self.combo_users.setCurrentIndex(index)
                self.combo_users.blockSignals(False)

            else:
                QMessageBox.warning(self, "Error", f"Failed to load users: {data.get('status')}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Connection error: {e}")

    def load_history(self):
        target = self.combo_users.currentText()
        if target == "All Users":
            target_user = None
        else:
            target_user = target

        try:
            url = f"{self.server_url}/admin/history"
            resp = requests.post(url, json={"admin_user": self.current_user, "target_user": target_user})
            data = resp.json()

            if data.get("status") == "OK":
                history = data.get("history", [])
                self.history_table.setRowCount(0)
                for row_idx, h in enumerate(history):
                    self.history_table.insertRow(row_idx)
                    self.history_table.setItem(row_idx, 0, QTableWidgetItem(str(h["timestamp"])))
                    self.history_table.setItem(row_idx, 1, QTableWidgetItem(h["username"]))
                    self.history_table.setItem(row_idx, 2, QTableWidgetItem(h["action"]))
                    self.history_table.setItem(row_idx, 3, QTableWidgetItem(h["details"]))
            else:
                 QMessageBox.warning(self, "Error", f"Failed to load history: {data.get('status')}")

        except Exception as e:
            print(f"History load error: {e}")

    def load_settings(self):
        try:
            url = f"{self.server_url}/admin/get_settings"
            resp = requests.post(url, json={"admin_user": self.current_user})
            data = resp.json()
            if data.get("status") == "OK":
                self.spin_max_downloads.setValue(int(data.get("max_downloads", 5)))
                self.lbl_settings_status.setText("Settings loaded.")
            else:
                self.lbl_settings_status.setText(f"Error: {data.get('status')}")
        except Exception as e:
             self.lbl_settings_status.setText(f"Connection Error: {e}")
             
    def save_settings(self):
        val = self.spin_max_downloads.value()
        try:
            url = f"{self.server_url}/admin/update_settings"
            resp = requests.post(url, json={"admin_user": self.current_user, "max_downloads": val})
            data = resp.json()
            if data.get("status") == "OK":
                QMessageBox.information(self, "Success", "Settings saved successfully.")
                self.lbl_settings_status.setText("Settings saved.")
            else:
                QMessageBox.warning(self, "Error", data.get("status"))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def block_user(self):
        self._set_block_status(True)

    def unblock_user(self):
        self._set_block_status(False)

    def _set_block_status(self, block):
        row = self.users_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Info", "Please select a user first.")
            return

        username = self.users_table.item(row, 0).text()
        
        try:
            url = f"{self.server_url}/admin/block_user"
            resp = requests.post(url, json={
                "admin_user": self.current_user,
                "target_user": username,
                "block": block
            })
            data = resp.json()
            
            if data.get("status") == "OK":
                QMessageBox.information(self, "Success", f"User {username} {'blocked' if block else 'unblocked'} successfully.")
                self.load_users()
            else:
                QMessageBox.warning(self, "Error", data.get("status"))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
