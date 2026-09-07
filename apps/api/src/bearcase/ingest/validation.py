"""Upload validation. Every upload is untrusted; nothing here executes document content."""

from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO

ALLOWED_EXTENSIONS = {"pdf", "xlsx", "csv"}
MIME_BY_EXT = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}
# A workbook is a zip archive, and a small archive can expand to a very large one. Both budgets are checked
# from the archive directory before any part is decompressed. A real statement workbook has tens of parts and
# expands to a few megabytes; these limits leave room for large models without allowing a decompression bomb.
XLSX_MAX_ENTRIES = 10_000
XLSX_MAX_EXPANDED_BYTES = 100 * 1024 * 1024


class UploadRejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedUpload:
    display_name: str
    extension: str
    mime_declared: str | None
    mime_detected: str
    sha256: str
    size_bytes: int
    data: bytes


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ ()-]+")


def sanitize_display_name(name: str, extension: str) -> str:
    base = name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = base.rsplit(".", 1)[0] if "." in base else base
    base = _SAFE_NAME.sub("-", base).strip(" .-") or "document"
    return f"{base[:120]}.{extension}"


def detect_type(data: bytes) -> str | None:
    """Magic-byte detection for the three accepted formats."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                entries = zf.infolist()
                if len(entries) > XLSX_MAX_ENTRIES:
                    raise UploadRejected(
                        "archive_entries",
                        f"The workbook archive has {len(entries):,} parts; the limit is {XLSX_MAX_ENTRIES:,}.",
                    )
                expanded = sum(e.file_size for e in entries)
                if expanded > XLSX_MAX_EXPANDED_BYTES:
                    raise UploadRejected(
                        "expanded_size",
                        f"The workbook expands to {expanded // (1024 * 1024):,} MB when opened; "
                        f"the limit is {XLSX_MAX_EXPANDED_BYTES // (1024 * 1024)} MB.",
                    )
                names = {e.filename for e in entries}
                if "[Content_Types].xml" in names and any(n.startswith("xl/") for n in names):
                    if any(n.startswith("xl/vbaProject") for n in names):
                        raise UploadRejected("macro_workbook", "Workbooks containing VBA macros are not accepted.")
                    return "xlsx"
        except zipfile.BadZipFile:
            return None
        return None
    head = data[:4096]
    if b"\x00" in head:
        return None
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        try:
            head.decode("latin-1")
        except UnicodeDecodeError:
            return None
    if b"," in head or b";" in head or b"\t" in head:
        return "csv"
    return None


def validate_upload(filename: str, declared_mime: str | None, data: bytes, max_bytes: int) -> ValidatedUpload:
    if not data:
        raise UploadRejected("empty_file", "The uploaded file is empty.")
    if len(data) > max_bytes:
        raise UploadRejected("too_large", f"File exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadRejected("extension", f"Unsupported file extension '.{ext or '?'}'. Accepted: PDF, XLSX, CSV.")
    detected = detect_type(data)
    if detected is None:
        raise UploadRejected("content_type", "The file content does not match a supported format.")
    if detected != ext:
        raise UploadRejected("extension_mismatch", f"The file is named .{ext} but its content looks like {detected.upper()}.")
    if declared_mime and declared_mime not in {
        MIME_BY_EXT[ext],
        "application/octet-stream",
        "text/plain",
        "application/vnd.ms-excel",
    }:
        raise UploadRejected("declared_type", f"Declared content type '{declared_mime}' does not match a {ext.upper()} file.")
    sha = hashlib.sha256(data).hexdigest()
    return ValidatedUpload(sanitize_display_name(filename, ext), ext, declared_mime, MIME_BY_EXT[ext], sha, len(data), data)
