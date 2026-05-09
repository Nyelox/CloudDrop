# Sent Files Viewer + Print System Implementation

## Overview

Implement a "Sended Files" window that lets the operator see all files sent through the app (fetched from the server), with PDF/DOCX print capability. This includes a new MySQL table, server endpoint for print status, DOCX→PDF conversion, and a custom PDF preview/print window.

---

## Proposed Changes

### 1. Server — `server_app.py`

#### [MODIFY] [server_app.py](file:///c:/Users/דניאל שומונוב/OneDrive/שולחן העבודה/pyqt5_laptop/Server/server_app.py)

- **`init_db()`** — add `CREATE TABLE IF NOT EXISTS print_jobs (...)` for tracking print records.
- **`GET /all_sent_files`** — new endpoint: returns ALL shared_files rows (sender, receiver, filename, uploaded_at, path, id) for the operator view. No receiver filter.
- **`POST /request_print`** — new endpoint: receives `{file_id, operator}`, downloads the file bytes from Supabase, returns them base64-encoded + inserts a `pending` print_jobs record.
- **`POST /update_print_status`** — new endpoint: receives `{job_id, status}` and updates `print_jobs.print_status`.

**New `print_jobs` table:**
```sql
CREATE TABLE IF NOT EXISTS print_jobs (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    file_id       INT NOT NULL,
    sender        VARCHAR(255) NOT NULL,
    filename      VARCHAR(255) NOT NULL,
    file_type     VARCHAR(20) NOT NULL,
    print_allowed BOOLEAN DEFAULT 0,
    print_status  ENUM('pending','printed') DEFAULT 'pending',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

### 2. Client — New `sended_files_window.py`

#### [NEW] [sended_files_window.py](file:///c:/Users/דניאל שומונוב/OneDrive/שולחן העבודה/pyqt5_laptop/Client/sended_files_window.py)

A pure-code PyQt5 `QMainWindow` (no `.ui` file needed) with:

- `QScrollArea` + `QVBoxLayout` to list all sent files.
- Each row: `QLabel` (Sender + Filename) + optional `QPushButton("🖨 Print")` for PDF/DOCX.
- On "Print": calls `/request_print` on the server → receives base64 file bytes → if DOCX converts to PDF → opens `PrintPreviewWindow`.
- Styled with a dark glassmorphism theme consistent with the app.

---

### 3. Client — New `print_preview_window.py`

#### [NEW] [print_preview_window.py](file:///c:/Users/דניאל שומונוב/OneDrive/שולחן העבודה/pyqt5_laptop/Client/print_preview_window.py)

A `QDialog` that:

- Uses `QPdfView` (from `PyQt5.QtPdf`) OR falls back to rendering PDF pages as `QPixmap` via `fitz` (PyMuPDF) for preview.
- Shows a "🖨 Print" button that uses `QPrinter` + `QPrintDialog` for actual system printing.
- Calls `/update_print_status` on the server after successful print.

> **Note on PDF rendering:** PyMuPDF (`fitz`) is the most reliable cross-platform option and doesn't require Qt PDF modules. We'll use it with a `QLabel` + `QScrollArea` for the preview.

---

### 4. Client — `home.py`

#### [MODIFY] [home.py](file:///c:/Users/דניאל שומונוב/OneDrive/שולחן העבודה/pyqt5_laptop/Client/home.py)

- Implement `open_sended_files()` to instantiate and show `SendedFilesWindow`.

---

### 5. Dependencies — `requirements.txt`

#### [MODIFY] [requirements.txt](file:///c:/Users/דניאל שומונוב/OneDrive/שולחן העבודה/pyqt5_laptop/requirements.txt)

Add:
- `PyMuPDF` — PDF rendering for preview
- `python-docx` — read DOCX files
- `reportlab` — convert DOCX content to PDF

---

## Design Decisions

> [!IMPORTANT]
> **DOCX→PDF conversion strategy:** LibreOffice requires a system install and subprocess calls, which is fragile in production. Instead, we use `python-docx` to extract text/paragraphs + `reportlab` to render a PDF — this is pure-Python, no system dependencies. Complex formatting won't be perfectly preserved, but it works reliably for printing purposes.

> [!NOTE]
> **Operator-only view:** `/all_sent_files` returns ALL files in the system (not filtered by receiver). This is an operator/admin view. In production you may want to gate this behind `is_admin` check — I'll add an optional `admin_user` param for it.

> [!NOTE]
> **No new `.ui` file:** `SendedFilesWindow` is built entirely in code (no Qt Designer) to keep it self-contained and avoid needing a `.ui` file.

---

## Verification Plan

### Automated
- Run server with `python -m Server.server_app` and confirm new tables created.
- Hit `/all_sent_files` with curl/Postman to verify response.
- Hit `/request_print` with a valid `file_id` to verify base64 bytes returned.

### Manual
1. Start server, log in as a user, send a PDF file.
2. Click "Sended Files" → verify the file appears with a "Print" button.
3. Click "Print" → verify PDF preview window opens.
4. Click Print in the dialog → verify system print dialog appears.
5. Check MySQL `print_jobs` table for a `printed` record.
