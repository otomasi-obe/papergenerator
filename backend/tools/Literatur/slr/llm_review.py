"""LLM-assisted title-abstract review untuk SLR screening.

Pendekatan LLM-screening bersifat emerging — belum sevalidasi active learning.
Gunakan sebagai reviewer KEDUA untuk flag disagreement antara prediksi model & LLM.

Rambu ketat:
- LLM bukan pengganti reviewer manusia
- Hanya flag disagreement → yang konflik dibaca manusia
- Output LLM wajib terstruktur (relevan/tidak + alasan + kutipan kriteria)
- Jangan biarkan LLM "mengarang" kelayakan — kunci ke abstrak nyata

Model: VIOLA-CHAT (via model_config / LLM proxy user)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class LLMReviewResult:
    """Hasil review LLM untuk satu paper."""

    paper_id: str
    title: str
    is_relevant: bool | None        # None = LLM tidak yakin
    reason: str = ""
    criteria_match: list[str] = None  # kriteria inklusi/eksklusi yang match
    quoted_evidence: str = ""         # kutipan dari abstrak
    confidence: float = 0.0
    error: str = ""

    def __post_init__(self):
        if self.criteria_match is None:
            self.criteria_match = []


@dataclass
class LLMDisagreement:
    """Disagreement antara model classifier dan LLM."""

    paper_id: str
    title: str
    abstract: str
    model_prediction: float     # P(relevant) dari SVM
    llm_prediction: bool | None
    llm_reason: str
    requires_human: bool = True  # selalu True — conflict selalu butuh manusia


class LLMReviewer:
    """LLM-assisted screening reviewer.

    Hanya flag disagreement antara prediksi model & LLM.
    Paper yang agreement (keduanya setuju relevant/irrelevant) tidak perlu
    dibaca manusia — ini menghemat waktu screening.

    Model: VIOLA-CHAT (via get_primary_generate_model dari model_config)
    """

    # Kriteria inklusi/eksklusi default (bisa di-override)
    DEFAULT_INCLUSION = [
        "Membahas metode atau framework SLR/systematic review",
        "Menggunakan machine learning atau AI untuk automasi literature review",
        "Menyajikan pendekatan screening atau ekstraksi data terstruktur",
        "Publikasi peer-reviewed (journal/conference)",
        "Tersedia abstrak dalam bahasa Inggris atau Indonesia",
    ]
    DEFAULT_EXCLUSION = [
        "Bukan artikel penelitian (editorial, book review, letter)",
        "Tidak membahas literature review atau SLR",
        "Duplikat dari paper yang sudah di-include",
        "Abstrak tidak tersedia atau terlalu pendek (<50 kata)",
        "Diterbitkan sebelum tahun 2010 (kecuali paper seminal)",
    ]

    def __init__(self, llm_fn=None, model_name: str = "V-OPUS"):
        """
        Args:
            llm_fn: Callable LLM function (optional)
            model_name: Model LLM untuk review
        """
        self.llm_fn = llm_fn
        self.model_name = model_name
        self.inclusion_criteria: list[str] = list(self.DEFAULT_INCLUSION)
        self.exclusion_criteria: list[str] = list(self.DEFAULT_EXCLUSION)
        self._stats = {"reviewed": 0, "disagreements": 0, "agreements": 0, "errors": 0}

    def set_criteria(
        self,
        inclusion: list[str] | None = None,
        exclusion: list[str] | None = None,
    ) -> None:
        """Override kriteria inklusi/eksklusi."""
        if inclusion:
            self.inclusion_criteria = inclusion
        if exclusion:
            self.exclusion_criteria = exclusion

    def review(
        self,
        paper_id: str,
        title: str,
        abstract: str,
        model_probability: float | None = None,
        year: int | None = None,
    ) -> LLMReviewResult:
        """Review satu paper dengan LLM.

        Args:
            paper_id: ID paper
            title: Judul
            abstract: Abstrak
            model_probability: P(relevant) dari classifier SVM (kalau ada)
            year: Tahun publikasi

        Returns:
            LLMReviewResult
        """
        if not self.llm_fn:
            return LLMReviewResult(
                paper_id=paper_id,
                title=title,
                is_relevant=None,
                reason="LLM function not available",
                error="No LLM function configured",
            )

        prompt = self._build_review_prompt(title, abstract, year)
        self._stats["reviewed"] += 1

        try:
            response = self.llm_fn(prompt)
            result = self._parse_response(response, paper_id, title)
            return result
        except Exception as e:
            self._stats["errors"] += 1
            return LLMReviewResult(
                paper_id=paper_id,
                title=title,
                is_relevant=None,
                error=str(e),
            )

    def check_disagreement(
        self,
        model_probability: float,
        llm_result: LLMReviewResult,
        uncertainty_threshold: float = 0.3,
        probability_threshold: float = 0.5,
    ) -> LLMDisagreement | None:
        """Deteksi disagreement antara model classifier dan LLM.

        Disagreement terjadi kalau:
        - Model yakin relevant (proba > 0.7) tapi LLM bilang irrelevant
        - Model yakin irrelevant (proba < 0.3) tapi LLM bilang relevant
        - Model uncertain (0.3-0.7) dan LLM punya confidence rendah → perlu manusia

        Args:
            model_probability: P(relevant) dari classifier
            llm_result: Hasil review LLM
            uncertainty_threshold: Range uncertainty (0.3 berarti 0.2-0.8 uncertain)
            probability_threshold: Threshold untuk relevant

        Returns:
            LLMDisagreement kalau ada konflik, None kalau agreement
        """
        if llm_result.is_relevant is None:
            # LLM tidak yakin → anggap sebagai disagreement
            self._stats["disagreements"] += 1
            return LLMDisagreement(
                paper_id=llm_result.paper_id,
                title=llm_result.title,
                abstract="",
                model_prediction=model_probability,
                llm_prediction=None,
                llm_reason=llm_result.reason or "LLM uncertain",
            )

        model_relevant = model_probability >= probability_threshold
        model_uncertain = (
            probability_threshold - uncertainty_threshold
            <= model_probability
            <= probability_threshold + uncertainty_threshold
        )

        # Agreement → no conflict
        if model_relevant == llm_result.is_relevant and not model_uncertain:
            self._stats["agreements"] += 1
            return None

        # Disagreement
        self._stats["disagreements"] += 1
        return LLMDisagreement(
            paper_id=llm_result.paper_id,
            title=llm_result.title,
            abstract="",
            model_prediction=model_probability,
            llm_prediction=llm_result.is_relevant,
            llm_reason=llm_result.reason,
        )

    def batch_review(
        self,
        papers: list[dict[str, Any]],
        model_probabilities: dict[str, float] | None = None,
        max_concurrent: int = 5,
    ) -> list[LLMDisagreement]:
        """Batch review — hanya return disagreements.

        Args:
            papers: List dict dengan 'id', 'title', 'abstract'
            model_probabilities: Dict[id → P(relevant)] dari classifier
            max_concurrent: Maksimum concurrent LLM calls

        Returns:
            List LLMDisagreement — hanya paper yang perlu review manusia
        """
        disagreements: list[LLMDisagreement] = []

        for paper in papers:
            pid = paper.get("id", "")
            proba = (model_probabilities or {}).get(pid, 0.5)
            result = self.review(
                paper_id=pid,
                title=paper.get("title", ""),
                abstract=paper.get("abstract", ""),
                model_probability=proba,
                year=paper.get("year"),
            )
            conflict = self.check_disagreement(proba, result)
            if conflict:
                conflict.abstract = paper.get("abstract", "")[:500]
                conflict.title = paper.get("title", "")
                disagreements.append(conflict)

        log.info(
            "LLM batch review: %d papers, %d agreements, %d disagreements, %d errors",
            self._stats["reviewed"],
            self._stats["agreements"],
            self._stats["disagreements"],
            self._stats["errors"],
        )
        return disagreements

    def get_stats(self) -> dict:
        return dict(self._stats)

    # ── Internal ───────────────────────────────────────────────────────

    def _build_review_prompt(
        self,
        title: str,
        abstract: str,
        year: int | None = None,
    ) -> str:
        """Build structured review prompt."""
        inc = "\n".join(f"  [{i+1}] {c}" for i, c in enumerate(self.inclusion_criteria))
        exc = "\n".join(f"  [{i+1}] {c}" for i, c in enumerate(self.exclusion_criteria))
        year_str = f" ({year})" if year else ""

        return f"""Review this academic paper for inclusion in a systematic literature review.

PAPER:
Title: {title}{year_str}
Abstract: {abstract[:3000]}

INCLUSION CRITERIA:
{inc}

EXCLUSION CRITERIA:
{exc}

OUTPUT ONLY THIS JSON (no other text):
{{
  "decision": "INCLUDE" or "EXCLUDE" or "UNCLEAR",
  "matched_criteria": ["I1", "E3"],
  "evidence": "Verbatim quote from abstract supporting decision",
  "confidence": 0.0_to_1.0
}}

CRITICAL RULES:
- Base your decision ONLY on the abstract text above.
- Do NOT use your training knowledge about this paper.
- If the abstract is insufficient to decide, use "UNCLEAR".
- The "evidence" field MUST be a verbatim quote from the abstract.
- Output ONLY the JSON — no markdown, no explanation."""

    def _parse_response(
        self,
        response: str,
        paper_id: str,
        title: str,
    ) -> LLMReviewResult:
        """Parse LLM JSON response."""
        # Extract JSON block
        json_match = re.search(r'\{[\s\S]*?\}', response)
        if not json_match:
            return LLMReviewResult(
                paper_id=paper_id,
                title=title,
                is_relevant=None,
                reason=f"Could not parse JSON from response: {response[:100]}",
                error="Parse error",
            )

        try:
            data = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            return LLMReviewResult(
                paper_id=paper_id,
                title=title,
                is_relevant=None,
                reason="JSON parse error",
                error="JSON decode failed",
            )

        decision = str(data.get("decision", "")).upper()
        is_relevant = None if decision == "UNCLEAR" else (decision == "INCLUDE")

        return LLMReviewResult(
            paper_id=paper_id,
            title=title,
            is_relevant=is_relevant,
            reason=str(data.get("evidence", "")),
            criteria_match=data.get("matched_criteria", []),
            quoted_evidence=str(data.get("evidence", "")),
            confidence=float(data.get("confidence", 0.0)),
        )


# ── Integration helper ────────────────────────────────────────────────────


def get_viola_chat_llm():
    """Dapatkan VIOLA-CHAT LLM function via model_config.

    Returns callable yang menerima prompt → response string.
    """
    try:
        import sys
        from pathlib import Path

        # Tambah papergenerator ke path
        pg_root = str(Path(__file__).resolve().parent.parent.parent.parent)
        if pg_root not in sys.path:
            sys.path.insert(0, pg_root)

        from utils.ai_tools.model_router import route_chat_call

        def llm_fn(prompt: str) -> str:
            messages = [{"role": "user", "content": prompt}]
            try:
                resp, _model = route_chat_call(
                    json={
                        "messages": messages,
                        "model": "V-OPUS",
                        "temperature": 0.1,
                        "max_tokens": 300,
                    },
                )
                data = resp.json() if hasattr(resp, 'json') else resp
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            except Exception as e:
                log.error("VIOLA-CHAT call failed: %s", e)
                return ""

        return llm_fn
    except ImportError:
        log.warning("model_router not available — LLM review disabled")
        return None