"""
Preview package — reference normalization and formatting for paper exports.
"""

from .ref_normalize import normalize_references, style_for_journal
from .reference_formatter import format_reference

__all__ = [
    "normalize_references",
    "style_for_journal",
    "format_reference",
]
