"""
File Extractor Module - Extracts text from various file formats to Markdown.

Based on patterns from docling (https://github.com/docling-project/docling) and 
markitdown (https://github.com/microsoft/markitdown).

Supported formats:
- PDF (.pdf) - via PyMuPDF (fitz) with fallback to extract_pdfs.py
- DOCX (.docx) - via python-docx with fallback to XML parsing
- DOC (.doc) - via python-docx
- Excel (.xlsx, .xls) - via openpyxl for xlsx, xlrd for xls
- PowerPoint (.pptx) - via python-pptx
- CSV (.csv) - direct text read
- TXT/MD (.txt, .md) - direct text read

Output is Markdown-formatted text suitable for AI context injection.
"""

from __future__ import annotations

import logging
import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Magic bytes for file type detection
FILE_SIGNATURES = {
    b"%PDF": ".pdf",
    b"PK\x03\x04": ".zip",  # ZIP-based formats (DOCX, XLSX, PPTX, etc.)
    b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1": ".doc",  # OLE2 format (DOC, XLS, PPT)
}

# MIME type to extension mapping
MIME_TO_EXT = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-powerpoint": ".ppt",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "text/markdown": ".md",
}

# Maximum characters to extract per file
MAX_EXTRACT_CHARS = 50_000


def detect_file_type(data: bytes, filename: str | None = None) -> str | None:
    """
    Detect file type from magic bytes and filename extension.
    
    Returns extension (e.g., ".pdf", ".docx") or None if unknown.
    
    Priority:
    1. Magic bytes detection
    2. Filename extension
    """
    # Check magic bytes first
    for sig, ext in FILE_SIGNATURES.items():
        if data.startswith(sig):
            if ext == ".zip":
                # ZIP-based format — need to inspect contents
                return _detect_zip_format(data, filename)
            elif ext == ".doc":
                # OLE2 format — could be .doc, .xls, or .ppt
                return _detect_ole2_format(data, filename)
            return ext
    
    # Fallback to filename extension
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".csv", ".txt", ".md"}:
            return ext
    
    return None


def _detect_zip_format(data: bytes, filename: str | None = None) -> str:
    """Detect specific format within a ZIP file (DOCX, XLSX, PPTX, etc.)."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = set(zf.namelist())
            
            # Check for DOCX
            if "word/document.xml" in names:
                return ".docx"
            
            # Check for XLSX
            if any(n.startswith("xl/") and n.endswith(".xml") for n in names):
                return ".xlsx"
            
            # Check for PPTX
            if "ppt/presentation.xml" in names:
                return ".pptx"
            
            # Fallback: check for common patterns
            if any("word/" in n for n in names):
                return ".docx"
            if any("xl/" in n for n in names):
                return ".xlsx"
            if any("ppt/" in n for n in names):
                return ".pptx"
    except Exception as e:
        log.debug(f"ZIP detection failed: {e}")
    
    # Fallback to filename extension if provided
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in {".docx", ".xlsx", ".pptx"}:
            return ext
    
    return ".zip"


def _detect_ole2_format(data: bytes, filename: str | None = None) -> str:
    """Detect specific format within an OLE2 file (DOC, XLS, PPT)."""
    # OLE2 is complex — rely on filename extension as primary hint
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in {".doc", ".xls", ".ppt"}:
            return ext
    
    # Default to .doc for OLE2
    return ".doc"


def extract_to_markdown(
    filepath: Path | str,
    file_data: bytes | None = None,
    filename: str | None = None,
    max_chars: int = MAX_EXTRACT_CHARS,
) -> str:
    """
    Extract text from a file and return as Markdown.
    
    Args:
        filepath: Path to the file
        file_data: Raw file bytes (optional, will be read from filepath if not provided)
        filename: Original filename for type detection (optional)
        max_chars: Maximum characters to extract
    
    Returns:
        Markdown-formatted text, or empty string on failure.
    """
    filepath = Path(filepath)
    
    if file_data is None:
        try:
            file_data = filepath.read_bytes()
        except Exception as e:
            log.warning(f"Failed to read file {filepath}: {e}")
            return ""
    
    # Detect file type
    ext = detect_file_type(file_data, filename or filepath.name)
    if not ext:
        log.warning(f"Unknown file type: {filename or filepath.name}")
        return ""
    
    # Route to appropriate extractor
    extractors = {
        ".pdf": _extract_pdf,
        ".docx": _extract_docx,
        ".doc": _extract_doc,
        ".xlsx": _extract_xlsx,
        ".xls": _extract_xls,
        ".pptx": _extract_pptx,
        ".csv": _extract_csv,
        ".txt": _extract_text,
        ".md": _extract_text,
    }
    
    extractor = extractors.get(ext)
    if not extractor:
        log.warning(f"No extractor for format: {ext}")
        return ""
    
    try:
        text = extractor(filepath, file_data)
        return text[:max_chars] if text else ""
    except Exception as e:
        log.error(f"Extraction failed for {filepath}: {e}")
        return ""


def _extract_pdf(filepath: Path, file_data: bytes) -> str:
    """Extract text from PDF using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
        
        parts = []
        with fitz.open(str(filepath)) as doc:
            for i, page in enumerate(doc):
                text = page.get_text("text")
                if text.strip():
                    parts.append(f"<!-- Page {i+1} -->\n{text}")
                if sum(len(p) for p in parts) >= MAX_EXTRACT_CHARS:
                    break
        return "\n\n".join(parts)
    except Exception as e:
        log.warning(f"PyMuPDF failed: {e}")
        # Fallback to extract_pdfs.py
        try:
            from tools.File.extract_pdfs import extract_text_from_pdf
            return extract_text_from_pdf(BytesIO(file_data))
        except Exception as e2:
            log.error(f"PDF extraction failed: {e2}")
            return ""


def _extract_docx(filepath: Path, file_data: bytes) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        from docx import Document
        
        doc = Document(str(filepath))
        chunks = []
        
        # Extract paragraphs
        for p in doc.paragraphs:
            if p.text.strip():
                chunks.append(p.text)
        
        # Extract tables
        for tbl in doc.tables:
            table_md = _table_to_markdown(tbl)
            if table_md:
                chunks.append(table_md)
        
        return "\n\n".join(chunks)
    except Exception as e:
        log.warning(f"python-docx failed: {e}")
        # Fallback: parse word/document.xml directly
        return _extract_docx_fallback(filepath, file_data)


def _extract_docx_fallback(filepath: Path, file_data: bytes) -> str:
    """Fallback DOCX extraction via XML parsing."""
    try:
        import defusedxml.ElementTree as ET
        
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        
        with zipfile.ZipFile(str(filepath)) as zf:
            candidates = [
                n for n in zf.namelist()
                if n.endswith("/document.xml") or n == "word/document.xml"
            ]
            if not candidates:
                return ""
            
            with zf.open(candidates[0]) as raw:
                tree = ET.parse(raw)
        
        lines = []
        for para in tree.iter(f"{{{ns['w']}}}p"):
            parts = [t.text or "" for t in para.iter(f"{{{ns['w']}}}t")]
            line = "".join(parts).strip()
            if line:
                lines.append(line)
        
        return "\n".join(lines)
    except Exception as e:
        log.error(f"DOCX fallback failed: {e}")
        return ""


def _extract_doc(filepath: Path, file_data: bytes) -> str:
    """Extract text from DOC (older Word format)."""
    # DOC files are OLE2-based — python-docx doesn't support them
    # Use antiword or similar if available, otherwise return empty
    try:
        import subprocess
        result = subprocess.run(
            ["antiword", str(filepath)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception as e:
        log.warning(f"antiword not available: {e}")
    
    return "[DOC format extraction requires antiword. Please convert to DOCX.]"


def _extract_xlsx(filepath: Path, file_data: bytes) -> str:
    """Extract text from XLSX using openpyxl."""
    try:
        from openpyxl import load_workbook
        
        wb = load_workbook(str(filepath), read_only=True, data_only=True)
        out = []
        
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            out.append(f"## {sheet_name}")
            
            # Extract as markdown table
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = ["" if v is None else str(v) for v in row]
                if any(cells):
                    rows.append(cells)
            
            if rows:
                table_md = _rows_to_markdown(rows)
                if table_md:
                    out.append(table_md)
            
            out.append("")
            
            if sum(len(s) for s in out) >= MAX_EXTRACT_CHARS:
                break
        
        return "\n".join(out)
    except Exception as e:
        log.error(f"XLSX extraction failed: {e}")
        return ""


def _extract_xls(filepath: Path, file_data: bytes) -> str:
    """Extract text from XLS (older Excel format) using xlrd."""
    try:
        import xlrd
        
        wb = xlrd.open_workbook(str(filepath))
        out = []
        
        for sheet in wb.sheets():
            out.append(f"## {sheet.name}")
            
            rows = []
            for row_idx in range(min(sheet.nrows, 500)):
                cells = [str(sheet.cell_value(row_idx, col_idx)) for col_idx in range(sheet.ncols)]
                if any(cells):
                    rows.append(cells)
            
            if rows:
                table_md = _rows_to_markdown(rows)
                if table_md:
                    out.append(table_md)
            
            out.append("")
            
            if sum(len(s) for s in out) >= MAX_EXTRACT_CHARS:
                break
        
        return "\n".join(out)
    except Exception as e:
        log.error(f"XLS extraction failed: {e}")
        return ""


def _extract_pptx(filepath: Path, file_data: bytes) -> str:
    """Extract text from PPTX using python-pptx."""
    try:
        import pptx
        
        presentation = pptx.Presentation(str(filepath))
        out = []
        
        for i, slide in enumerate(presentation.slides, 1):
            out.append(f"## Slide {i}")
            
            # Extract title
            if slide.shapes.title:
                out.append(f"**{slide.shapes.title.text}**")
                out.append("")
            
            # Extract text from all shapes
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    out.append(shape.text)
                
                # Extract tables
                if hasattr(shape, "has_table") and shape.has_table:
                    table = shape.table
                    rows = []
                    for row in table.rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        if any(cells):
                            rows.append(cells)
                    
                    if rows:
                        table_md = _rows_to_markdown(rows)
                        if table_md:
                            out.append(table_md)
            
            out.append("")
            
            if sum(len(s) for s in out) >= MAX_EXTRACT_CHARS:
                break
        
        return "\n".join(out)
    except Exception as e:
        log.error(f"PPTX extraction failed: {e}")
        return ""


def _extract_csv(filepath: Path, file_data: bytes) -> str:
    """Extract CSV as plain text."""
    # Try UTF-8 first, fallback to latin-1
    try:
        text = file_data.decode("utf-8", errors="replace")
    except Exception:
        text = file_data.decode("latin-1", errors="replace")
    
    return text


def _extract_text(filepath: Path, file_data: bytes) -> str:
    """Extract plain text file."""
    # Try UTF-8 first, fallback to latin-1
    try:
        return file_data.decode("utf-8", errors="replace")
    except Exception:
        return file_data.decode("latin-1", errors="replace")


def _table_to_markdown(table) -> str:
    """Convert a python-docx table to Markdown format."""
    rows = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        if any(cells):
            rows.append(cells)
    
    return _rows_to_markdown(rows)


def _rows_to_markdown(rows: list[list[str]]) -> str:
    """Convert a list of rows (each row is a list of strings) to Markdown table."""
    if not rows:
        return ""
    
    # Normalize column count
    max_cols = max(len(row) for row in rows)
    normalized = []
    for row in rows:
        padded = row + [""] * (max_cols - len(row))
        normalized.append(padded)
    
    # Calculate column widths
    col_widths = [max(len(str(cell)) for cell in col) for col in zip(*normalized)]
    
    # Build header
    header = normalized[0]
    header_line = "| " + " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(header)) + " |"
    
    # Build separator
    sep_line = "|" + "|".join("-" * (col_widths[i] + 2) for i in range(len(header))) + "|"
    
    # Build rows
    data_lines = []
    for row in normalized[1:]:
        row_line = "| " + " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)) + " |"
        data_lines.append(row_line)
    
    return "\n".join([header_line, sep_line] + data_lines)
