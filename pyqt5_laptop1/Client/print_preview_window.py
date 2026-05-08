"""
print_preview_window.py  ←  loads print_preview_window.ui

Two print modes:
  • Windows Printer  — QPrinter with the chosen printer name (no dialog,
                       the user already picked it in the UI)
  • Network Printer  — raw TCP socket → port 9100 (JetDirect/AppSocket)
                       sends the PDF bytes directly to the printer IP

After a successful print, calls /update_print_status on the server.
"""
import os
import socket as _socket

import requests
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QPainter
from PyQt5.QtPrintSupport import QPrinter, QPrinterInfo
from PyQt5.QtWidgets import (
    QDialog, QLabel, QFrame, QMessageBox, QSizePolicy
)
from PyQt5.uic import loadUi

DPI_PREVIEW = 120
DPI_PRINT   = 300

# ── Stylesheet ───────────────────────────────────────────────────────────────

STYLE = """
QDialog, QWidget {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #0f0c29, stop:0.5 #1a1a2e, stop:1 #16213e);
    color: #e0d7ff;
    font-family: "Segoe UI", Arial, sans-serif;
}
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical {
    background: #1a1a2e; width: 8px; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #7c4dff; border-radius: 4px; min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QLabel#label_title { color: #e0d7ff; font-size: 16px; font-weight: bold; }
QLabel#label_pages { color: #9e86d8; font-size: 10px; }

QFrame#line_sep1, QFrame#line_sep2, QFrame#line_sep3 {
    color: rgba(124,77,255,0.35);
}

QGroupBox#group_printer {
    color: #b39ddb;
    border: 1px solid rgba(124,77,255,0.35);
    border-radius: 10px;
    margin-top: 8px;
    font-size: 12px;
    font-weight: bold;
    padding: 10px 8px 8px 8px;
}
QGroupBox#group_printer::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #9c6dff;
}

QRadioButton { color: #d4c9ff; font-size: 12px; spacing: 6px; }
QRadioButton::indicator { width: 16px; height: 16px; }
QRadioButton::indicator:checked {
    background: #7c4dff; border-radius: 8px; border: 2px solid #9c6dff;
}
QRadioButton::indicator:unchecked {
    background: rgba(255,255,255,0.08);
    border-radius: 8px; border: 2px solid rgba(124,77,255,0.4);
}

QComboBox {
    background: rgba(255,255,255,0.08); color: #e0d7ff;
    border: 1px solid rgba(124,77,255,0.4); border-radius: 7px;
    padding: 5px 10px; font-size: 12px;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #1a1a2e; color: #e0d7ff;
    selection-background-color: #7c4dff;
    border: 1px solid rgba(124,77,255,0.5);
}

QLineEdit {
    background: rgba(255,255,255,0.08); color: #e0d7ff;
    border: 1px solid rgba(124,77,255,0.4); border-radius: 7px;
    padding: 5px 10px; font-size: 12px;
}
QLineEdit:disabled { color: rgba(255,255,255,0.3); }

QLabel#label_port { color: #9e86d8; font-size: 12px; }

QPushButton#btn_print {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #7c4dff, stop:1 #3d5afe);
    color: white; border: none; border-radius: 10px;
    font-size: 13px; font-weight: bold;
}
QPushButton#btn_print:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #9c6dff, stop:1 #5d7aff);
}
QPushButton#btn_print:pressed  { background: #5e35b1; }
QPushButton#btn_print:disabled {
    background: rgba(255,255,255,0.12); color: rgba(255,255,255,0.35);
}

QPushButton#btn_close {
    background: rgba(255,255,255,0.08); color: #b39ddb;
    border: 1px solid rgba(124,77,255,0.3); border-radius: 10px;
    font-size: 13px;
}
QPushButton#btn_close:hover {
    background: rgba(255,255,255,0.15); color: #e0d7ff;
}
"""

# ── Socket print thread ───────────────────────────────────────────────────────

class SocketPrintThread(QThread):
    """Sends raw PDF bytes to a network printer via TCP (port 9100 JetDirect)."""
    success  = pyqtSignal()
    error    = pyqtSignal(str)
    progress = pyqtSignal(int, int)   # sent, total

    def __init__(self, host: str, port: int, pdf_bytes: bytes):
        super().__init__()
        self.host      = host
        self.port      = port
        self.pdf_bytes = pdf_bytes

    def run(self):
        try:
            sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            sock.settimeout(15)
            sock.connect((self.host, self.port))

            total      = len(self.pdf_bytes)
            chunk_size = 8192
            sent       = 0
            while sent < total:
                chunk = self.pdf_bytes[sent:sent + chunk_size]
                sock.sendall(chunk)
                sent += len(chunk)
                self.progress.emit(sent, total)

            sock.close()
            self.success.emit()
        except Exception as e:
            self.error.emit(str(e))

# ── Main dialog ───────────────────────────────────────────────────────────────

class PrintPreviewWindow(QDialog):
    def __init__(self, pdf_bytes: bytes, filename: str,
                 job_id: int, server_url: str, operator: str,
                 parent=None):
        super().__init__(parent)
        self.pdf_bytes  = pdf_bytes
        self.filename   = filename
        self.job_id     = job_id
        self.server_url = server_url
        self.operator   = operator
        self._threads: list = []

        ui_path = os.path.join(os.path.dirname(__file__), "print_preview_window.ui")
        loadUi(ui_path, self)

        self.setStyleSheet(STYLE)
        self.setWindowTitle(f"Print Preview — {filename}")
        self.setModal(True)

        self._setup_ui()
        self._render_pages()

    # ── initial setup ────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.label_title.setText(f"🖨  {self.filename}")

        # populate Windows printers
        self.combo_printers.clear()
        for info in QPrinterInfo.availablePrinters():
            self.combo_printers.addItem(info.printerName())
        default = QPrinterInfo.defaultPrinter()
        if default and not default.isNull():
            idx = self.combo_printers.findText(default.printerName())
            if idx >= 0:
                self.combo_printers.setCurrentIndex(idx)

        # radio button logic
        self.radio_windows.toggled.connect(self._on_radio_changed)
        self.radio_network.toggled.connect(self._on_radio_changed)
        self._on_radio_changed()

        # buttons
        self.btn_close.clicked.connect(self.reject)
        self.btn_print.clicked.connect(self._do_print)

    def _on_radio_changed(self):
        win_mode = self.radio_windows.isChecked()
        self.combo_printers.setEnabled(win_mode)
        self.input_ip.setEnabled(not win_mode)
        self.input_port.setEnabled(not win_mode)

    # ── PDF rendering ────────────────────────────────────────────────────────

    def _render_pages(self):
        try:
            import fitz
        except ImportError:
            self.label_pages.setText("⚠  Install PyMuPDF for preview: pip install PyMuPDF")
            return

        layout = self.scroll_content.layout()
        doc  = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        zoom = DPI_PREVIEW / 72.0
        mat  = fitz.Matrix(zoom, zoom)
        n    = len(doc)
        self.label_pages.setText(f"{n} page(s)  ·  PDF preview")

        for page in doc:
            pix   = page.get_pixmap(matrix=mat, alpha=False)
            img   = QImage(pix.samples, pix.width, pix.height,
                           pix.stride, QImage.Format_RGB888)
            qpix  = QPixmap.fromImage(img)

            frame = QFrame()
            frame.setStyleSheet(
                "QFrame { background: white; border-radius: 4px; }"
            )
            from PyQt5.QtWidgets import QVBoxLayout as _VBox
            fl = _VBox(frame)
            fl.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel()
            lbl.setPixmap(qpix.scaledToWidth(
                min(qpix.width(), 640), Qt.SmoothTransformation))
            lbl.setAlignment(Qt.AlignCenter)
            fl.addWidget(lbl)

            # insert before the spacer
            layout.insertWidget(layout.count() - 1, frame,
                                alignment=Qt.AlignHCenter)
        doc.close()

    # ── print dispatch ────────────────────────────────────────────────────────

    def _do_print(self):
        self.btn_print.setEnabled(False)

        if self.radio_windows.isChecked():
            printer_name = self.combo_printers.currentText()
            if not printer_name:
                QMessageBox.warning(self, "No Printer",
                                    "No Windows printer is available on this machine.")
                self.btn_print.setEnabled(True)
                return
            self._print_windows(printer_name)
        else:
            ip   = self.input_ip.text().strip()
            port_txt = self.input_port.text().strip()
            if not ip:
                QMessageBox.warning(self, "Missing IP",
                                    "Please enter the printer's IP address.")
                self.btn_print.setEnabled(True)
                return
            try:
                port = int(port_txt)
            except ValueError:
                port = 9100
            self._print_socket(ip, port)

    # ── Windows printer ───────────────────────────────────────────────────────

    def _print_windows(self, printer_name: str):
        self.btn_print.setText("Printing…")
        try:
            # Find the QPrinterInfo for this name
            target = None
            for info in QPrinterInfo.availablePrinters():
                if info.printerName() == printer_name:
                    target = info
                    break

            printer = QPrinter(target, QPrinter.HighResolution) if target \
                      else QPrinter(QPrinter.HighResolution)
            printer.setPrinterName(printer_name)
            printer.setDocName(self.filename)

            self._render_to_printer(printer)
            self._mark_printed()
            QMessageBox.information(self, "Print",
                                    f"Document sent to '{printer_name}'.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Print Error", str(e))
        finally:
            self.btn_print.setEnabled(True)
            self.btn_print.setText("🖨  Print")

    def _render_to_printer(self, printer: QPrinter):
        try:
            import fitz
        except ImportError:
            raise RuntimeError("PyMuPDF required — pip install PyMuPDF")

        doc  = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        zoom = DPI_PRINT / 72.0
        mat  = fitz.Matrix(zoom, zoom)

        painter = QPainter()
        if not painter.begin(printer):
            raise RuntimeError("Failed to start painter on printer device.")

        for i, page in enumerate(doc):
            if i > 0:
                printer.newPage()
            pix   = page.get_pixmap(matrix=mat, alpha=False)
            img   = QImage(pix.samples, pix.width, pix.height,
                           pix.stride, QImage.Format_RGB888)
            qpix  = QPixmap.fromImage(img)
            rect  = painter.viewport()
            scaled = qpix.scaled(rect.size(), Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
            x = (rect.width()  - scaled.width())  // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        painter.end()
        doc.close()

    # ── Network / Socket printer ──────────────────────────────────────────────

    def _print_socket(self, host: str, port: int):
        self.btn_print.setText(f"Connecting to {host}:{port}…")

        t = SocketPrintThread(host, port, self.pdf_bytes)
        t.progress.connect(self._on_socket_progress)
        t.success.connect(self._on_socket_success)
        t.error.connect(self._on_socket_error)
        self._threads.append(t)
        t.start()

    def _on_socket_progress(self, sent: int, total: int):
        pct = int(sent / total * 100)
        self.btn_print.setText(f"Sending… {pct}%")

    def _on_socket_success(self):
        self.btn_print.setEnabled(True)
        self.btn_print.setText("🖨  Print")
        self._mark_printed()
        QMessageBox.information(self, "Print",
                                "Document sent to printer via network socket.")
        self.accept()

    def _on_socket_error(self, msg: str):
        self.btn_print.setEnabled(True)
        self.btn_print.setText("🖨  Print")
        QMessageBox.critical(self, "Socket Error",
                             f"Could not connect to printer:\n{msg}")

    # ── status update ─────────────────────────────────────────────────────────

    def _mark_printed(self):
        try:
            requests.post(
                f"{self.server_url}/update_print_status",
                json={"job_id": self.job_id, "status": "printed"},
                timeout=5,
            )
        except Exception:
            pass
