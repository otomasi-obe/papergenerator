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
