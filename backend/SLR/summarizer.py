"""Summarizer untuk SLR — extractive (gratis) + AI-augmented (V-OPUS).

Dua mode:

1. `summarize(text, query, n)` — extractive, tanpa API. TextRank-style:
   embed tiap kalimat (SBERT MiniLM) lalu score = 0.6 * cos(kalimat, dokumen)
   + 0.4 * cos(kalimat, query). Aman, no hallucination, dipakai untuk
   abstract yang gampang di-rangkum atau saat AI down.

2. `summarize_with_ai(papers, query, model)` — batch summarization via upstream
   chat-completions endpoint (default `V-OPUS`). Setiap batch berisi N paper;
   model diminta keluarkan JSON array `[{"id":..,"summary":".."}]`. Kalau JSON
   gagal di-parse, fallback ke extractive untuk paper di batch tersebut.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Iterable

import numpy as np
import requests

from .text_cleaner import clean_abstract

log = logging.getLogger(__name__)

_SBERT = None

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
_MIN_LEN = 25


def _sbert():
    global _SBERT
    if _SBERT is None:
        from sentence_transformers import SentenceTransformer
        _SBERT = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _SBERT


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    raw = _SENT_SPLIT_RE.split(text)
    return [s.strip() for s in raw if len(s.strip()) >= _MIN_LEN]


def summarize(text: str | None, query: str | None = None,
              n_sentences: int = 3) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    sents = split_sentences(cleaned)
    if not sents:
        return cleaned[:500]
    if len(sents) <= n_sentences:
        return " ".join(sents)

    try:
        model = _sbert()
        embs = model.encode(sents, normalize_embeddings=True, show_progress_bar=False,
                            convert_to_numpy=True)
        doc_emb = embs.mean(axis=0, keepdims=True)
        sims_doc = (embs @ doc_emb.T).flatten()

        if query:
            q_emb = model.encode([query], normalize_embeddings=True,
                                  show_progress_bar=False, convert_to_numpy=True)
            sims_q = (embs @ q_emb.T).flatten()
            scores = 0.6 * sims_doc + 0.4 * sims_q
        else:
            scores = sims_doc

        if len(scores) > 0:
            scores[0] += 0.05  # lead-sentence boost

        top_idx = np.argsort(-scores)[:n_sentences]
        chosen = sorted(top_idx.tolist())
        return " ".join(sents[i] for i in chosen)
    except Exception:
        return " ".join(sents[:n_sentences])


def batch_summarize(texts: Iterable[str | None], query: str | None = None,
                     n_sentences: int = 3) -> list[str]:
    return [summarize(t, query=query, n_sentences=n_sentences) for t in texts]


# ─── AI summarizer (upstream LLM) ───────────────────────────────────────────

_AI_BASE = (os.getenv("AIOTOMASI_API") or "").rstrip("/")
_AI_KEY = os.getenv("AIOTOMASI_APIKEY") or ""
_DEFAULT_MODEL = os.getenv("AIOTOMASI_MODEL") or "V-OPUS"


def _ai_chat(messages, model: str | None = None,
             max_tokens: int = 32000, timeout: int = 90) -> str | None:
    """Synchronous, non-streaming chat completion. Returns content or None."""
    if not (_AI_BASE and _AI_KEY):
        return None
    chosen = model or _DEFAULT_MODEL
    try:
        resp = requests.post(
            _AI_BASE + "/chat/completions",
            headers={
                "Authorization": f"Bearer {_AI_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": chosen,
                "messages": messages,
                "stream": False,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            log.warning("summarizer.ai_chat status=%s body=%s",
                        resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        return (choices[0].get("message", {}).get("content") or "").strip()
    except Exception as e:
        log.warning("summarizer.ai_chat error: %s", e)
        return None


_AI_SYS_PROMPT = (
    "You are an academic literature reviewer. For each paper, write a "
    "FAITHFUL 2-3 sentence summary in English that captures: (1) the problem "
    "or contribution, (2) the method/approach, (3) headline result if "
    "stated. NEVER invent numbers, datasets, or claims not present in the "
    "input. If the abstract is empty or too short, summarize from the title "
    "only and prefix the sentence with '[based on title]'. Respond with "
    'VALID JSON ONLY: an array of {"id": <int>, "summary": "<sentences>"} '
    "objects in the same order as the input. No prose, no markdown."
)


def _parse_json_array(text: str):
    """Parse text into a JSON array, tolerating preamble/postamble noise."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def summarize_with_ai(papers: list[dict],
                      query: str,
                      model: str | None = None,
                      batch_size: int = 8,
                      progress_cb=None) -> dict[int, str]:
    """Batch-summarize a list of paper dicts via the upstream LLM.

    Each item must carry at least `id` and `title`; `abstract`, `year`
    optional. Returns {id -> summary}. Items missing from the response fall
    back to the extractive `summarize`.
    """
    out: dict[int, str] = {}
    if not papers:
        return out

    chosen_model = model or _DEFAULT_MODEL
    total = len(papers)

    for i in range(0, total, batch_size):
        batch = papers[i:i + batch_size]
        body = []
        for p in batch:
            body.append({
                "id": p["id"],
                "title": (p.get("title") or "")[:400],
                "year": p.get("year"),
                "abstract": (p.get("abstract") or "")[:1500],
            })
        user = (
            f"Research query: {query}\n\n"
            f"Papers (JSON):\n{json.dumps(body, ensure_ascii=False)}\n\n"
            "Output JSON array only."
        )
        msgs = [
            {"role": "system", "content": _AI_SYS_PROMPT},
            {"role": "user", "content": user},
        ]
        content = _ai_chat(msgs, model=chosen_model, max_tokens=900)
        parsed = _parse_json_array(content) if content else None
        if not parsed:
            log.warning("summarizer batch %d-%d: AI failed/parse error; extractive fallback",
                        i, i + len(batch))
            for p in batch:
                out[p["id"]] = (
                    summarize(p.get("abstract"), query=query, n_sentences=3)
                    or (p.get("title") or "")[:280]
                )
        else:
            for item in parsed:
                try:
                    pid = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                summary = (item.get("summary") or "").strip()
                if summary:
                    out[pid] = summary[:1200]
            for p in batch:
                if p["id"] not in out:
                    out[p["id"]] = (
                        summarize(p.get("abstract"), query=query, n_sentences=3)
                        or (p.get("title") or "")[:280]
                    )

        if progress_cb:
            progress_cb("summarized", {"done": min(i + batch_size, total),
                                        "total": total})

        time.sleep(0.3)  # be polite to upstream

    return out
