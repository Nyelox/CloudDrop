
import base64
import os

import requests
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QMessageBox, QSizePolicy,
    QFileDialog
)
from PyQt5.uic import loadUi

PRINTABLE_EXTS = {"pdf", "docx", "doc"}

ICON_MAP = {
    "pdf": "PDF", "docx": "DOC", "doc": "DOC",
    "png": "IMG", "jpg": "IMG", "jpeg": "IMG",
    "mp4": "VID", "zip": "ZIP", "xlsx": "XLS", "txt": "TXT",
}



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

        # cards_layout is the VBoxLayout inside scroll_content (from .ui)
        self._cards_layout = self.scroll_content.layout()

        self.btn_refresh.clicked.connect(self._load_files)
        self.btn_upload_print.clicked.connect(self._on_upload_print)
        self.input_filter.textChanged.connect(self._apply_filter)
        self._load_files()

    # ── file upload for printing ─────────────────────────────────────────────

    def _on_upload_print(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File to Print",
            "", "Printable Files (*.pdf *.docx *.doc);;All Files (*)"
        )
        if not path:
            return

        filename = os.path.basename(path)
        ext = os.path.splitext(filename)[1].lower().lstrip(".")

        if ext not in PRINTABLE_EXTS:
            QMessageBox.warning(
                self, "Unsupported File",
                "Only PDF, DOCX and DOC files can be printed."
            )
            return

        try:
            with open(path, "rb") as f:
                raw = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read file:\n{e}")
            return

        if ext in ("docx", "doc"):
            try:
                raw = _docx_to_pdf_bytes(raw)
            except Exception as e:
                QMessageBox.critical(
                    self, "Conversion Error",
                    f"Word → PDF conversion failed:\n{e}"
                )
                return

        from Client.print_preview_window import PrintPreviewWindow
        dlg = PrintPreviewWindow(
            pdf_bytes  = raw,
            filename   = filename,
            job_id     = None,
            server_url = self.server_url,
            operator   = self.current_user,
            parent     = self,
        )
        dlg.exec_()

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

        row = QHBoxLayout(card)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(12)

        # icon
        icon_lbl = QLabel(ICON_MAP.get(ext, "FILE"))
        icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
        icon_lbl.setFixedWidth(36)
        row.addWidget(icon_lbl)

        # text
        col = QVBoxLayout()
        col.setSpacing(3)
        name_lbl = QLabel(filename)
        name_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        name_lbl.setStyleSheet("color: #222;")
        meta_lbl = QLabel(
            f"From: <b>{sender}</b>  →  To: <b>{receiver}</b>"
            + (f"   <span style='color:#999;'>{ts}</span>" if ts else "")
        )
        meta_lbl.setTextFormat(Qt.RichText)
        meta_lbl.setStyleSheet("color: #555; font-size: 11px;")
        col.addWidget(name_lbl)
        col.addWidget(meta_lbl)
        row.addLayout(col, stretch=1)

        # print button (PDF / DOCX only)
        if ext in PRINTABLE_EXTS:
            btn = QPushButton("Print")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedWidth(100)
            btn.clicked.connect(
                lambda _, fid=file_id, fn=filename, fe=ext, b=btn:
                    self._on_print_click(fid, fn, fe, b)
            )
            row.addWidget(btn)

        # Insert before the trailing spacer
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

    # ── filter ───────────────────────────────────────────────────────────────

    def _apply_filter(self):
        filter_text = self.input_filter.text().lower()
        layout = self._cards_layout
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget()
            if w and isinstance(w, QFrame) and w.objectName().startswith("card_"):
                # Check all labels inside the card
                labels = w.findChildren(QLabel)
                text = " ".join(lbl.text() for lbl in labels).lower()
                w.setVisible(filter_text in text)

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
        btn.setText("Print")

        raw    = base64.b64decode(data["filedata"])
        job_id = data.get("job_id")

        if ext in ("docx", "doc"):
            try:
                raw = _docx_to_pdf_bytes(raw)
            except Exception as e:
                QMessageBox.critical(self, "Conversion Error",
                                     f"Word → PDF failed:\n{e}")
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
        btn.setText("Print")
        QMessageBox.critical(self, "Print Error",
                             f"Could not fetch file for printing:\n{msg}")


# ── DOCX / DOC → PDF ────────────────────────────────────────────────────────
# Primary: docx2pdf (uses Microsoft Word via COM — perfect Hebrew/RTL support)
# Fallback: reportlab (basic, no Hebrew support)

def _docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    import os
    import tempfile

    # ── Try docx2pdf (requires Microsoft Word installed) ────────────────────
    try:
        from docx2pdf import convert

        suffix = ".docx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(docx_bytes)
            docx_path = tmp.name

        pdf_path = docx_path[:-len(suffix)] + ".pdf"
        try:
            convert(docx_path, pdf_path)
            with open(pdf_path, "rb") as f:
                return f.read()
        finally:
            try: os.unlink(docx_path)
            except: pass
            try: os.unlink(pdf_path)
            except: pass

    except Exception:
        pass  # Word not installed → fall through to reportlab

    # ── Fallback: reportlab (Latin text only, no Hebrew) ────────────────────
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
    h1   = ParagraphStyle("H1", parent=styles["Heading1"],
                          fontName="Helvetica-Bold", fontSize=16, spaceAfter=10)
    h2   = ParagraphStyle("H2", parent=styles["Heading2"],
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

