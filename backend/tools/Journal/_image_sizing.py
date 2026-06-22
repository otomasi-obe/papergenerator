"""
Shared image sizing utility for all journal generators.
Auto-detects page dimensions from template .docx, applies:
  - 2-column: 70% of column width
  - 1-column: 50% of text area (page - margins)
"""
from pathlib import Path
from docx import Document

DEFAULTS = {
    "page_width_cm": 21.0,
    "page_height_cm": 29.7,
    "margin_left_cm": 2.54,
    "margin_right_cm": 2.54,
    "columns": 1,
    "col_width_cm": 8.0,
}


def get_embedded_image_max_width(template_docx: Path,
                                 page_width_cm=None,
                                 margin_left_cm=None,
                                 margin_right_cm=None,
                                 columns=None,
                                 col_width_cm=None) -> float:
    """
    Returns max image width in cm for the given template.

    Priority: explicit CFG values > auto-detect from template .docx > fallback defaults.

    2-column: col_width_cm * 0.7
    1-column: (page_width_cm - margin_left_cm - margin_right_cm) * 0.5
    """
    # If all values explicitly given, use them directly
    if page_width_cm and margin_left_cm is not None and margin_right_cm is not None:
        text_w = page_width_cm - margin_left_cm - margin_right_cm
        if columns is not None and columns > 1 and col_width_cm:
            return round(col_width_cm * 0.5, 1)
        return round(text_w * 0.5, 1)

    # Auto-detect from template .docx
    if template_docx and Path(template_docx).exists():
        try:
            doc = Document(str(template_docx))
            section = doc.sections[0]
            pw_cm = section.page_width / 360000
            ml_cm = section.left_margin / 360000
            mr_cm = section.right_margin / 360000
            text_w = pw_cm - ml_cm - mr_cm
            return round(text_w * 0.5, 1)
        except Exception:
            pass

    # Fallback: A4 50%
    text_w = DEFAULTS["page_width_cm"] - DEFAULTS["margin_left_cm"] - DEFAULTS["margin_right_cm"]
    return round(text_w * 0.5, 1)