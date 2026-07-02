"""Literatur module — SLR (Systematic Literature Review) tools.

Current system (v4 — 2026-06-29 refactor):
    slrOrchestrator.py → NEW unified pipeline: parallel fetch + dedup + rank + group.
    slrFetch.py        → Smart fetcher routing (keyword analysis, domain-based selection).
    slrSummarize.py    → Programmatic ranking, dedup, and method-grouping (no LLM required).
    slrFetchPrompt.txt → LLM prompt for fetcher selection.
    slrSummarizePrompt.txt → LLM prompt for result summarization.
    slr.py             → Legacy Flask blueprint orchestrator (kept for backward compat).

Usage:
    from tools.Literatur import run_slr
    result = run_slr(keyword="machine learning", top_n=20)
"""

try:
    from . import slr  # noqa: F401  (Flask blueprint, optional)
except Exception:
    slr = None  # type: ignore[assignment]

from .slrOrchestrator import run_slr  # NEW: unified pipeline

__all__ = ["slr", "run_slr"]
