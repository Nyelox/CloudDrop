"""
sended_files_window.py  ←  loads sended_files_window.ui
Operator view: every file ever sent through CloudDrop.
PDF / DOCX rows get a 🖨 Print button.
"""
import base64
import os

import requests
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QMessageBox, QSizePolicy
)
from PyQt5.uic import loadUi

PRINTABLE_EXTS = {"pdf", "docx"}

ICON_MAP = {
    "pdf": "📄", "docx": "📝", "doc": "📝",
    "png": "🖼", "jpg": "🖼", "jpeg": "🖼",
    "mp4": "🎬", "zip": "📦", "xlsx": "📊", "txt": "📃",
}

# ── Stylesheet ──────────────────────────────────────────────────────────────

STYLE = """
QMainWindow, QWidget {
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

QLabel#label_title   { color: #e0d7ff; font-size: 20px; font-weight: bold; }
QLabel#label_subtitle{ color: #9e86d8; font-size: 11px; }
QLabel#label_status  { color: #9e86d8; font-size: 12px; }

QFrame#line_sep { color: rgba(124,77,255,0.35); }

QPushButton#btn_refresh {
    background: rgba(124,77,255,0.15); color: #b39ddb;
    border: 1px solid rgba(124,77,255,0.4); border-radius: 8px;
    padding: 6px 18px; font-size: 12px;
}
QPushButton#btn_refresh:hover { background: rgba(124,77,255,0.30); color: #e0d7ff; }

/* Dynamic card frames */
QFrame[objectName^="card_"] {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(124,77,255,0.22);
    border-radius: 12px;
}
QFrame[objectName^="card_"]:hover {
    background: rgba(255,255,255,0.10);
    border: 1px solid rgba(124,77,255,0.55);
}
"""

BTN_PRINT_STYLE = """
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #7c4dff, stop:1 #3d5afe);
    color: white; border: none; border-radius: 8px;
    padding: 6px 16px; font-size: 12px; font-weight: bold;
}
QPushButton:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #9c6dff, stop:1 #5d7aff);
}
QPushButton:pressed  { background: #5e35b1; }
QPushButton:disabled { background: rgba(255,255,255,0.12); color: rgba(255,255,255,0.35); }
"""

# ── Background threads ───────────────────────────────────────────────────────

class FetchFilesThread(QThread):
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, server_url):
        super().__init__()
        self.server_url = server_url

    def run(self):
        try:
            r = requests.get(f"{self.server_url}/all_sent_files", timeout=10)
            data = r.json()
            if data.get("status") == "OK":
                self.done.emit(data.get("files", []))
            else:
                self.error.emit(data.get("status", "Unknown error"))
        except Exception as e:
            self.error.emit(str(e))


class PrintRequestThread(QThread):
    done  = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, server_url, file_id, operator):
        super().__init__()
        self.server_url = server_url
        self.file_id    = file_id
        self.operator   = operator

    def run(self):
        try:
            r = requests.post(
                f"{self.server_url}/request_print",
                json={"file_id": self.file_id, "operator": self.operator},
                timeout=30,
            )
            data = r.json()
            if data.get("status") == "OK":
                self.done.emit(data)
            else:
                self.error.emit(data.get("status", "Unknown error"))
        except Exception as e:
            self.error.emit(str(e))

# ── Main window ──────────────────────────────────────────────────────────────

class SendedFilesWindow(QMainWindow):
    def __init__(self, current_user="operator", server_url="http://127.0.0.1:5000"):
        super().__init__()
        self.current_user = current_user
        self.server_url   = server_url
        self._threads: list = []
        self._card_index  = 0

        ui_path = os.path.join(os.path.dirname(__file__), "sended_files_window.ui")
        loadUi(ui_path, self)

        self.setStyleSheet(STYLE)

        # cards_layout is the VBoxLayout inside scroll_content (from .ui)
        self._cards_layout = self.scroll_content.layout()

        self.btn_refresh.clicked.connect(self._load_files)
        self._load_files()

    # ── data loading ─────────────────────────────────────────────────────────

    def _load_files(self):
        self.btn_refresh.setEnabled(False)
        self.label_status.setText("Loading…")
        self._clear_cards()

        t = FetchFilesThread(self.server_url)
        t.done.connect(self._on_files_loaded)
        t.error.connect(self._on_load_error)
        t.finished.connect(lambda: self.btn_refresh.setEnabled(True))
        self._threads.append(t)
        t.start()

    def _on_files_loaded(self, files):
        self._clear_cards()
        if not files:
            self.label_status.setText("No files found.")
            return
        self.label_status.setText(f"{len(files)} file(s) found")
        for f in files:
            self._add_file_card(f)

    def _on_load_error(self, msg):
        self.label_status.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Connection Error",
                             f"Could not fetch sent files:\n{msg}")

    def _clear_cards(self):
        layout = self._cards_layout
        # Remove everything except the trailing spacer (last item)
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._card_index = 0

    # ── card builder ─────────────────────────────────────────────────────────

    def _add_file_card(self, f):
        filename = f.get("filename", "unknown")
        sender   = f.get("sender",   "unknown")
        receiver = f.get("receiver", "?")
        ts       = str(f.get("uploaded_at", ""))[:16]
        file_id  = f.get("id")
        ext      = os.path.splitext(filename)[1].lower().lstrip(".")

        card = QFrame(objectName=f"card_{self._card_index}")
        self._card_index += 1
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.06); "
            "border: 1px solid rgba(124,77,255,0.22); border-radius: 12px; }"
            "QFrame:hover { background: rgba(255,255,255,0.10); "
            "border: 1px solid rgba(124,77,255,0.55); }"
        )

        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)

        # icon
        icon_lbl = QLabel(ICON_MAP.get(ext, "📎"))
        icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
        icon_lbl.setFixedWidth(36)
        row.addWidget(icon_lbl)

        # text
        col = QVBoxLayout()
        col.setSpacing(3)
        name_lbl = QLabel(filename)
        name_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        name_lbl.setStyleSheet("color: #e0d7ff;")
        meta_lbl = QLabel(
            f"From: <b>{sender}</b>  →  To: <b>{receiver}</b>"
            + (f"   <span style='color:#6e6a8a;'>{ts}</span>" if ts else "")
        )
        meta_lbl.setTextFormat(Qt.RichText)
        meta_lbl.setStyleSheet("color: #9e86d8; font-size: 11px;")
        col.addWidget(name_lbl)
        col.addWidget(meta_lbl)
        row.addLayout(col, stretch=1)

        # print button (PDF / DOCX only)
        if ext in PRINTABLE_EXTS:
            btn = QPushButton("🖨  Print")
            btn.setStyleSheet(BTN_PRINT_STYLE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedWidth(100)
            btn.clicked.connect(
                lambda _, fid=file_id, fn=filename, fe=ext, b=btn:
                    self._on_print_click(fid, fn, fe, b)
            )
            row.addWidget(btn)

        # Insert before the trailing spacer
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

    # ── print flow ───────────────────────────────────────────────────────────

    def _on_print_click(self, file_id, filename, ext, btn: QPushButton):
        btn.setEnabled(False)
        btn.setText("…")

        t = PrintRequestThread(self.server_url, file_id, self.current_user)
        t.done.connect(
            lambda data, b=btn, fn=filename, fe=ext:
                self._on_print_data(data, b, fn, fe)
        )
        t.error.connect(
            lambda msg, b=btn: self._on_print_error(msg, b)
        )
        self._threads.append(t)
        t.start()

    def _on_print_data(self, data, btn: QPushButton, filename, ext):
        btn.setEnabled(True)
        btn.setText("🖨  Print")

        raw    = base64.b64decode(data["filedata"])
        job_id = data.get("job_id")

        if ext == "docx":
            try:
                raw = _docx_to_pdf_bytes(raw)
            except Exception as e:
                QMessageBox.critical(self, "Conversion Error",
                                     f"DOCX → PDF failed:\n{e}")
                return

        from Client.print_preview_window import PrintPreviewWindow
        dlg = PrintPreviewWindow(
            pdf_bytes  = raw,
            filename   = filename,
            job_id     = job_id,
            server_url = self.server_url,
            operator   = self.current_user,
            parent     = self,
        )
        dlg.exec_()

    def _on_print_error(self, msg, btn: QPushButton):
        btn.setEnabled(True)
        btn.setText("🖨  Print")
        QMessageBox.critical(self, "Print Error",
                             f"Could not fetch file for printing:\n{msg}")


# ── DOCX → PDF (pure Python) ─────────────────────────────────────────────────

def _docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    import io
    from docx import Document
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    doc = Document(io.BytesIO(docx_bytes))
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=styles["Normal"],
                          fontName="Helvetica", fontSize=11, leading=16, spaceAfter=6)
    h1   = ParagraphStyle("H1",   parent=styles["Heading1"],
                          fontName="Helvetica-Bold", fontSize=16, spaceAfter=10)
    h2   = ParagraphStyle("H2",   parent=styles["Heading2"],
                          fontName="Helvetica-Bold", fontSize=13, spaceAfter=8)
    story = []
    for para in doc.paragraphs:
        if not para.text.strip():
            story.append(Spacer(1, 6))
            continue
        pname = para.style.name if para.style else ""
        ps = h1 if "Heading 1" in pname else (h2 if "Heading 2" in pname else body)
        rich = ""
        for run in para.runs:
            t = run.text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            if run.bold and run.italic: t = f"<b><i>{t}</i></b>"
            elif run.bold:              t = f"<b>{t}</b>"
            elif run.italic:            t = f"<i>{t}</i>"
            rich += t
        if not rich:
            rich = para.text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        story.append(Paragraph(rich, ps))
    pdf.build(story)
    return buf.getvalue()
