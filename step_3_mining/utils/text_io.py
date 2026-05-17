"""
PDF / DOCX / DOC text-extraction utilities for step_3_mining.

Exports
-------
read_pdf_text, read_docx_text, read_doc_text, read_any_text, safe_truncate
"""
from __future__ import annotations

import logging
import os
import warnings
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from pypdf.errors import PdfReadWarning
except Exception:
    class PdfReadWarning(Warning): ...  # type: ignore[no-redef]

logging.getLogger("pypdf").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=PdfReadWarning)


# ---------------------------------------------------------------------------
# File-type detection (magic bytes)
# ---------------------------------------------------------------------------

def _is_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(5).startswith(b"%PDF-")
    except Exception:
        return False


def _is_docx(path: str) -> bool:
    # DOCX is a ZIP containing word/document.xml
    try:
        with zipfile.ZipFile(path) as z:
            return "word/document.xml" in z.namelist()
    except Exception:
        return False


def _is_doc_binary(path: str) -> bool:
    # Legacy .doc is OLE Compound File: D0 CF 11 E0 A1 B1 1A E1
    try:
        with open(path, "rb") as f:
            return f.read(8) == b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Text readers
# ---------------------------------------------------------------------------

def read_pdf_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    if not _is_pdf(path):
        print(f"[SKIP NON-PDF] {path}")
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        chunks = []
        for p in reader.pages:
            try:
                chunks.append(p.extract_text() or "")
            except Exception:
                continue
        return "\n".join(chunks).strip()
    except Exception:
        return ""


def read_docx_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    if not _is_docx(path):
        print(f"[SKIP NON-DOCX] {path}")
        return ""
    try:
        with zipfile.ZipFile(path) as z:
            xml_bytes = z.read("word/document.xml")
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        root = ET.fromstring(xml_bytes)
        paras = []
        for p in root.findall(".//w:p", ns):
            texts = [t.text or "" for t in p.findall(".//w:t", ns)]
            line = "".join(texts).strip()
            if line:
                paras.append(line)
        return "\n".join(paras)
    except Exception:
        print(f"[SKIP BAD DOCX] {path}")
        return ""


def read_doc_text(path: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    if not _is_doc_binary(path):
        print(f"[SKIP NON-DOC] {path}")
        return ""
    try:
        import textract
        b = textract.process(path)  # requires antiword / catdoc on PATH
        return b.decode("utf-8", errors="ignore")
    except Exception:
        print(f"[SKIP .doc needs textract or antiword] {path}")
        return ""


def read_any_text(path: str) -> str:
    """Dispatch to the right reader by extension + magic bytes."""
    if not path or not os.path.exists(path):
        return ""
    ext = Path(path).suffix.lower()
    if ext == ".pdf" or _is_pdf(path):
        return read_pdf_text(path)
    if ext == ".docx" or _is_docx(path):
        return read_docx_text(path)
    if ext == ".doc" or _is_doc_binary(path):
        return read_doc_text(path)
    print(f"[SKIP UNSUPPORTED] {path}")
    return ""


def safe_truncate(txt: str, max_chars: int = 400_000) -> str:
    return txt[:max_chars] if txt and len(txt) > max_chars else (txt or "")
