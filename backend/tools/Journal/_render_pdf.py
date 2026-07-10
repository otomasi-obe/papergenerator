"""
Shared PDF rendering utility for all journal generators.

Each gen's ``build_document()`` produces a .docx; this module converts
that .docx to a .pdf via LibreOffice headless mode.  All 49 gens share
the identical conversion pipeline — only the docx layout differs.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def convert_docx_to_pdf(docx_path: Path, pdf_path: Path, timeout: int = 120) -> Path:
    """Convert a .docx file to .pdf via ``soffice --headless --convert-to pdf``.

    Args:
        docx_path: Path to the source .docx file.
        pdf_path:  Desired output .pdf path.
        timeout:   Seconds before the subprocess is killed.

    Returns:
        The *pdf_path* that was written.

    Raises:
        RuntimeError: If LibreOffice returns non-zero or times out.
    """
    output_dir = pdf_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", str(output_dir),
                str(docx_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"LibreOffice PDF conversion timed out ({timeout}s)")

    # soffice names the output after the source stem
    expected_pdf = output_dir / (docx_path.stem + ".pdf")

    # soffice may return non-zero with a harmless javaldx warning but still produce
    # a valid PDF. Check the output file first before raising.
    if expected_pdf.exists() and expected_pdf.stat().st_size > 0:
        if expected_pdf != pdf_path:
            if pdf_path.exists():
                pdf_path.unlink()
            expected_pdf.replace(pdf_path)
        return pdf_path

    if result.returncode != 0:
        raise RuntimeError(
            f"LibreOffice PDF conversion failed (rc={result.returncode}): "
            f"{result.stderr.decode('utf-8', errors='ignore')}"
        )

    # Edge case: returncode 0 but no file (shouldn't happen)
    if not expected_pdf.exists():
        raise RuntimeError("LibreOffice completed but no PDF file was produced")

    if expected_pdf != pdf_path:
        if pdf_path.exists():
            pdf_path.unlink()
        expected_pdf.replace(pdf_path)

    return pdf_path


def build_pdf_from_builder(
    builder_fn,
    json_path: Path,
    pdf_path: Path,
    template_path: Path | None = None,
) -> Path:
    """Build a .pdf from a JSON paper using a ``build_document``-style builder.

    Steps:
    1. Write a temporary .docx via ``builder_fn``.
    2. Convert the .docx to .pdf via LibreOffice.
    3. Clean up the temporary .docx.

    Args:
        builder_fn:    ``build_document(json_path, docx_path, template_path)`` callable.
        json_path:     Path to the paper JSON.
        pdf_path:      Desired output .pdf path.
        template_path: Optional .docx template path.

    Returns:
        The *pdf_path* that was written.
    """
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_docx = Path(tmp.name)

    try:
        # Build the DOCX
        kwargs = {"json_path": json_path, "output_path": tmp_docx}
        if template_path is not None:
            kwargs["template_path"] = template_path
        builder_fn(**kwargs)

        # Convert to PDF
        return convert_docx_to_pdf(tmp_docx, pdf_path)
    finally:
        tmp_docx.unlink(missing_ok=True)