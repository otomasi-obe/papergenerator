"""Pre-cleaning abstract sebelum embedding / scoring.

Port dari PROMPTHEUS/cleaner.py (MDPI Information 2025) dengan tambahan:
- normalisasi whitespace + JATS tag stripping (warisan Crossref)
- penghapusan boilerplate "we / our / in this paper" yang bikin
  cosine similarity bias ke kalimat self-reference, bukan substansi.
"""

from __future__ import annotations

import re
import unicodedata

_BOILERPLATE = {
    " we ": " ",
    " our ": " ",
    " us ": " ",
    " i ": " ",
    "in this study,": "studies",
    "in this study": "studies",
    "in this paper,": "studies",
    "in this paper": "studies",
    "in this work,": "studies",
    "in this work": "studies",
    "this paper": "studies",
    "this work": "studies",
    "in this section,": "studies",
    "in this section": "studies",
    "in this article,": "studies",
    "in this article": "studies",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_NON_PRINTABLE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_tags(text: str) -> str:
    return _TAG_RE.sub(" ", text)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _NON_PRINTABLE_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def clean_abstract(text: str | None) -> str:
    if not text:
        return ""
    t = normalize(strip_tags(text))
    if not t:
        return ""
    lower = " " + t.lower() + " "
    for k, v in _BOILERPLATE.items():
        lower = lower.replace(k, v)
    return _WS_RE.sub(" ", lower).strip()


def clean_title(text: str | None) -> str:
    if not text:
        return ""
    return normalize(strip_tags(text))


# ─── Mojibake / Garbled Text Detection ──────────────────────────────────
#
# Paper dengan teks mojibake (UTF-8→Latin-1 decode error) tetap bisa
# dapat skor SBERT tinggi karena embedding model membaca karakter rusak
# sebagai token valid. Deteksi ini dipakai untuk PENALTY berat di scoring.
#
# Deteksi:
# 1. Replacement character U+FFFD () → pasti mojibake
# 2. Rasio karakter Latin-1 Supplement (U+0080–U+00BF) terhadap total 
#    non-ASCII. Karakter di range ini muncul saat byte UTF-8 Russian/
#    Chinese/Japanese di-decode sebagai Latin-1.
#    — Rasio > 0.8 → 100% mojibake
#    — Rasio > 0.5 → berat
#    — Rasio > 0.2 → ringan
# 3. Marker spesifik: ÐÑÒÓÔÕÖ×ØÙÚÛÜ (byte D0-DF) — sangat umum di
#    Cyrillic→Latin-1 mojibake

_MOJIBIKE_LATIN1_HIGH = re.compile(r'[\u0080-\u00BF]')
_MOJIBIKE_CYRILLIC_MARKERS = re.compile(
    r'[\u00D0\u00D1\u00D2\u00D3\u00D4\u00D5\u00D6\u00D7\u00D8\u00D9\u00DA\u00DB\u00DC]'
)
_MOJIBIKE_REPLACEMENT = '\ufffd'


def detect_mojibake(text: str | None) -> float:
    """Return 0.0 (clean) to 1.0 (completely garbled).
    
    Digunakan sebagai penalty multiplier di scoring pipeline.
    Paper dengan score > 0.7 akan di-exclude dari AI rerank.
    """
    if not text or len(text) < 15:
        return 0.0
    
    # Replacement char = pasti mojibake
    if _MOJIBIKE_REPLACEMENT in text:
        return 1.0
    
    non_ascii = [c for c in text if ord(c) > 0x7F]
    if not non_ascii:
        return 0.0  # Pure ASCII = clean English paper
    
    total = len(text)
    non_ascii_count = len(non_ascii)
    non_ascii_ratio = non_ascii_count / total
    
    # Count Latin-1 Supplement high bytes (U+0080–U+00BF)
    # These are the hallmark of UTF-8→Latin-1 mojibake
    mojibake_chars = len(_MOJIBIKE_LATIN1_HIGH.findall(text))
    mojibake_ratio = mojibake_chars / non_ascii_count if non_ascii_count else 0
    
    # Count D0-DC markers (Cyrillic mojibake signature)
    cyrillic_mojo = len(_MOJIBIKE_CYRILLIC_MARKERS.findall(text))
    cyrillic_ratio = cyrillic_mojo / non_ascii_count if non_ascii_count else 0
    
    # Decision logic
    if mojibake_ratio > 0.7 or cyrillic_ratio > 0.6:
        return 1.0  # Definitely mojibake
    if mojibake_ratio > 0.4 or cyrillic_ratio > 0.3:
        return 0.8  # Heavy mojibake
    if mojibake_ratio > 0.2 or cyrillic_ratio > 0.15:
        return 0.5  # Moderate mojibake
    if non_ascii_ratio > 0.4 and mojibake_ratio > 0.1:
        return 0.3  # Suspicious
    
    return 0.0  # Clean
