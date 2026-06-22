"""Anti-hallucination data extraction untuk SLR synthesis.

Prinsip kunci:
- Setiap data point di-anchor ke DOI + lokasi teks asal
- Verifikasi tiap referensi via Crossref API sebelum masuk sintesis
- Gap analysis: LLM hanya menyimpulkan dari tabel ekstraksi terstruktur
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ExtractionPoint:
    """Satu data point hasil ekstraksi."""

    field: str                    # nama field (mis. "sample_size", "method")
    value: str                    # nilai terekstrak
    paper_id: str                 # ID paper sumber
    doi: str = ""                 # DOI paper sumber
    text_location: str = ""       # lokasi di teks (mis. "Section 3.2, paragraph 2")
    confidence: float = 1.0       # confidence score (0-1)
    verified: bool = False        # sudah diverifikasi Crossref?
    verification_note: str = ""


@dataclass
class ExtractionResult:
    """Hasil ekstraksi untuk satu paper."""

    paper_id: str
    doi: str
    title: str
    points: list[ExtractionPoint] = field(default_factory=list)
    verified: bool = False        # semua referensi terverifikasi?
    errors: list[str] = field(default_factory=list)

    def to_table_row(self) -> dict[str, str]:
        """Export ke format tabel (untuk sintesis)."""
        row = {"paper_id": self.paper_id, "doi": self.doi, "title": self.title}
        for p in self.points:
            row[p.field] = p.value
        return row


# ── Extractor ──────────────────────────────────────────────────────────────


class DataExtractor:
    """Ekstraksi data terstruktur dari abstrak + full-text.

    Anti-hallucination:
    - Anchor setiap extraction ke text span asli
    - Verifikasi referensi via Crossref
    - Simpan provenance (DOI + lokasi)
    """

    def __init__(self, llm_fn=None):
        """
        Args:
            llm_fn: Callable untuk LLM (optional, untuk ekstraksi dari full-text).
                   Signature: llm_fn(prompt: str) -> str
        """
        self.llm_fn = llm_fn
        self.extraction_schema: list[str] = []

    def set_schema(self, fields: list[str]) -> None:
        """Set extraction schema — field apa yang diekstrak.

        Contoh: ["population", "intervention", "outcome", "sample_size", "effect_size"]
        """
        self.extraction_schema = fields

    def extract_from_abstract(
        self,
        paper_id: str,
        doi: str,
        title: str,
        abstract: str,
    ) -> ExtractionResult:
        """Ekstraksi data dari abstrak (rule-based + regex patterns).

        Untuk ekstraksi dari full-text, gunakan extract_with_llm().
        """
        result = ExtractionResult(paper_id=paper_id, doi=doi, title=title)

        for field in self.extraction_schema:
            point = self._extract_field(field, abstract, paper_id, doi)
            if point:
                result.points.append(point)

        # Verifikasi referensi
        if doi:
            verified, note = verify_reference(doi, title)
            result.verified = verified
            if not verified:
                result.errors.append(note)

        return result

    def extract_with_llm(
        self,
        paper_id: str,
        doi: str,
        title: str,
        full_text: str,
    ) -> ExtractionResult:
        """Ekstraksi via LLM dengan anchor ke text span.

        LLM diminta output JSON terstruktur: untuk setiap field,
        berikan {value, text_location, confidence}.
        """
        result = ExtractionResult(paper_id=paper_id, doi=doi, title=title)

        if not self.llm_fn:
            # Fallback ke rule-based dari teks
            return self.extract_from_abstract(paper_id, doi, title, full_text)

        if not self.extraction_schema:
            return result

        # Prompt terstruktur
        prompt = self._build_extraction_prompt(full_text)
        try:
            response = self.llm_fn(prompt)
            parsed = self._parse_llm_response(response)
            for field, data in parsed.items():
                if isinstance(data, dict):
                    result.points.append(ExtractionPoint(
                        field=field,
                        value=str(data.get("value", "")),
                        paper_id=paper_id,
                        doi=doi,
                        text_location=str(data.get("text_location", "")),
                        confidence=float(data.get("confidence", 0.5)),
                    ))
        except Exception as e:
            result.errors.append(f"LLM extraction error: {e}")

        # Verifikasi referensi
        if doi:
            verified, note = verify_reference(doi, title)
            result.verified = verified
            if not verified:
                result.errors.append(note)

        return result

    def _extract_field(
        self,
        field: str,
        text: str,
        paper_id: str,
        doi: str,
    ) -> ExtractionPoint | None:
        """Ekstrak satu field dari teks menggunakan pattern matching."""
        patterns = {
            "sample_size": r'(?:n\s*[=:]\s*|sample\s*(?:size\s*)?(?:of\s*)?(?:was\s*)?|total\s*(?:of\s*)?)\s*(\d[\d,]*)',
            "method": r'(?:method\w*\s*(?:ology\s*)?(?:was|used|is|:)|approach\s*(?:was|used|is|:))\s*([A-Z][^.]{3,100})',
            "dataset": r'(?:dataset|corpus|data\s*(?:set\s*)?(?:was|used|is|:))\s*([A-Z][^.]{3,100})',
            "accuracy": r'(?:accuracy|acc\.?)\s*(?:of\s*)?\s*(\d+\.?\d*\s*%?)',
            "f1_score": r'(?:F1[-\s]?(?:score)?)\s*(?:of\s*)?\s*(\d+\.?\d*\s*%?)',
            "year": r'(?:20\d{2})',
        }

        if field not in patterns:
            # Generic extraction: cari field sebagai heading
            field_re = re.compile(
                rf'(?:{re.escape(field)})\s*[=:]\s*(.+?)(?:\.\s|\n|$)',
                re.IGNORECASE,
            )
            m = field_re.search(text)
            if m:
                return ExtractionPoint(
                    field=field,
                    value=m.group(1).strip(),
                    paper_id=paper_id,
                    doi=doi,
                    text_location=f"abstract (regex match for '{field}')",
                )
            return None

        m = re.search(patterns[field], text, re.IGNORECASE)
        if m:
            return ExtractionPoint(
                field=field,
                value=m.group(1).strip(),
                paper_id=paper_id,
                doi=doi,
                text_location=f"abstract (regex match at char {m.start()})",
            )

        return None

    def _build_extraction_prompt(self, text: str) -> str:
        """Build extraction prompt untuk LLM."""
        truncated = text[:8000] if len(text) > 8000 else text
        fields_str = "\n".join(f"  - {f}" for f in self.extraction_schema)

        return f"""Extract structured data from this academic paper. Output ONLY valid JSON.

Fields to extract:
{fields_str}

For each field, return:
- "value": the extracted value (string)
- "text_location": sentence/paragraph where this was found (copy verbatim from text)
- "confidence": 0.0-1.0, how confident you are in this extraction

Paper text:
---
{truncated}
---

Output JSON format:
{{"field_name": {{"value": "...", "text_location": "...", "confidence": 0.X}}, ...}}

CRITICAL: Only extract information that is EXPLICITLY stated in the text above.
Do NOT use your training knowledge. If a field is not found, omit it.
Anchors must be verbatim quotes from the text."""

    def _parse_llm_response(self, response: str) -> dict:
        """Parse LLM JSON response dengan error handling."""
        # Extract JSON block
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group(0))  # type: ignore[no-any-return]
            except json.JSONDecodeError:
                pass
        return {}


# ── Cross-verification ────────────────────────────────────────────────────


def verify_reference(doi: str, title: str) -> tuple[bool, str]:
    """Verifikasi referensi via Crossref API.

    Cek: DOI ditemukan, judul cocok, tahun tersedia.

    Args:
        doi: DOI paper
        title: Judul paper

    Returns:
        (verified: bool, note: str)
    """
    if not doi:
        return False, "No DOI provided"

    try:
        url = f"https://api.crossref.org/works/{doi}"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "SLR-Tool/1.0 (mailto:slr@example.com)")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        msg = data.get("message", {})
        if not msg:
            return False, f"DOI {doi} not found in Crossref"

        # Cek judul
        crossref_title = (msg.get("title") or [""])[0] if msg.get("title") else ""
        if crossref_title and title:
            from .dedup import _jaro_winkler_similarity, normalize_title

            sim = _jaro_winkler_similarity(
                normalize_title(title) or "",
                normalize_title(crossref_title) or "",
            )
            if sim < 0.70:
                return False, (
                    f"Title mismatch: '{title[:60]}...' vs Crossref "
                    f"'{crossref_title[:60]}...' (sim={sim:.2f})"
                )

        # Cek tahun
        year = msg.get("published-print", {}).get("date-parts", [[None]])[0][0]
        if year is None:
            year = msg.get("created", {}).get("date-parts", [[None]])[0][0]

        year_str = str(year) if year else "unknown"
        return True, f"Verified: {year_str}"

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, f"DOI {doi} not found (Crossref 404)"
        return False, f"Crossref API error: HTTP {e.code}"
    except Exception as e:
        return False, f"Crossref verification failed: {e}"


# ── Gap Analysis ───────────────────────────────────────────────────────────


def generate_gap_analysis(
    extraction_table: list[dict[str, str]],
    research_question: str,
    llm_fn=None,
) -> str:
    """Generate gap analysis dari tabel ekstraksi terstruktur.

    LLM hanya menyimpulkan dari data tabel — BUKAN dari memori model.
    """
    if not extraction_table or not llm_fn:
        return ""

    # Build text table
    if not extraction_table:
        return "No data for gap analysis"

    columns = list(extraction_table[0].keys())
    table_text = " | ".join(columns) + "\n"
    table_text += " | ".join(["---"] * len(columns)) + "\n"
    for row in extraction_table[:50]:
        table_text += " | ".join(str(row.get(c, ""))[:60] for c in columns) + "\n"

    prompt = f"""Analyze research gaps based ONLY on the extraction table below.
Do NOT use your training knowledge. Only reason from the table data.

Research Question: {research_question}

Extraction Table ({len(extraction_table)} papers):
{table_text}

Identify:
1. What patterns emerge from the extracted data?
2. What research questions remain unanswered?
3. What methodological gaps exist?
4. What are promising future directions?

CRITICAL: Base ALL conclusions on the table data above. Cite specific rows."""  # noqa: E501

    try:
        return llm_fn(prompt)
    except Exception as e:
        return f"Gap analysis failed: {e}"


# ── Self-test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test extraction
    extractor = DataExtractor()
    extractor.set_schema(["sample_size", "method", "accuracy"])

    abstract = (
        "We propose a novel approach to SLR automation. "
        "The method used was active learning with SVM. "
        "Our sample size was n=1,500 papers. "
        "The model achieved accuracy of 94.2%."
    )

    result = extractor.extract_from_abstract(
        paper_id="test_1",
        doi="10.1000/test.1",
        title="Active Learning for SLR Screening",
        abstract=abstract,
    )

    print(f"Paper: {result.title}")
    print(f"Verified: {result.verified}")
    for p in result.points:
        print(f"  {p.field}: {p.value} (confidence: {p.confidence})")
    if result.errors:
        print(f"  Errors: {result.errors}")

    # Test Crossref verification
    verified, note = verify_reference("10.1038/nature12373", "")
    print(f"\nCrossref test: {verified} — {note}")