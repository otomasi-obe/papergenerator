"""
SLR auto-fetch new topics — extract keywords from SLR results and queue
for background fetching via bulk_fetch_v2.py.
"""

import re
import logging
from collections import Counter

log = logging.getLogger(__name__)

# Common stopwords + academic boilerplate words to filter out
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "shall", "this",
    "that", "these", "those", "it", "its", "we", "they", "he", "she",
    "them", "their", "our", "your", "my", "his", "her", "about", "into",
    "through", "during", "before", "after", "above", "below", "between",
    "under", "over", "each", "all", "both", "few", "more", "most", "other",
    "some", "such", "no", "not", "only", "own", "same", "so", "than",
    "too", "very", "just", "also", "now", "new", "based", "using",
    "study", "research", "analysis", "approach", "method", "model",
    "system", "data", "results", "paper", "review", "survey",
    "application", "implementation", "evaluation", "performance",
    "comparison", "framework", "design", "development", "case",
    "effect", "impact", "role", "use", "towards", "toward",
    "dan", "yang", "di", "ke", "dari", "pada", "untuk", "dengan",
    "ini", "itu", "tersebut", "adalah", "merupakan", "dalam",
    "sebagai", "atau", "tidak", "akan", "telah", "sudah",
    "studi", "penelitian", "analisis", "metode", "model",
    "sistem", "data", "hasil", "implementasi", "pengaruh",
    "terhadap", "antara", "hubungan", "literatur",
}

_MIN_KEYWORD_LEN = 4


def _extract_title_phrases(titles: list[str], min_count: int = 1) -> list[tuple[str, int]]:
    """Extract significant 2-4 word phrases from paper titles."""
    word_counter: Counter = Counter()

    for title in titles:
        title = (title or "").lower().strip()
        words = re.findall(r"[a-z0-9]+", title)
        words = [w for w in words if len(w) >= _MIN_KEYWORD_LEN and w not in _STOPWORDS]

        for i in range(len(words) - 1):
            phrase = f"{words[i]} {words[i+1]}"
            word_counter[phrase] += 1
        for i in range(len(words) - 2):
            phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
            word_counter[phrase] += 1
        for i in range(len(words) - 3):
            phrase = f"{words[i]} {words[i+1]} {words[i+2]} {words[i+3]}"
            word_counter[phrase] += 1

    return sorted(
        [(p, c) for p, c in word_counter.items() if c >= min_count],
        key=lambda x: (-x[1], x[0]),
    )


def _extract_keywords_from_slr_result(payload: dict) -> list[str]:
    """Extract significant keyword phrases from SLR pipeline results."""
    papers = payload.get("papers") or payload.get("top_k") or []
    if not papers:
        return []

    titles = [p.get("title", "") for p in papers if p.get("title")]
    if not titles:
        return []

    phrases = _extract_title_phrases(titles, min_count=2)
    log.info(
        "slr.auto_fetch: extracted %d phrases from %d titles",
        len(phrases), len(titles),
    )

    return [p for p, _ in phrases[:15]]


def _queue_new_topics_to_mega_fetch(
    keywords: list[str],
    slr_query: str,
    slr_job_id: str,
) -> int:
    """Insert new keyword topics into mega_fetch_progress for background
    fetching. Uses batch INSERT with ON CONFLICT DO NOTHING — single
    transaction, no per-row rollback hazard.
    """
    if not keywords:
        return 0

    from . import db_cache
    from psycopg2.extras import execute_values

    conn = None
    queued = 0

    try:
        conn = db_cache.get_connection()

        # Detect field_name from SLR query using orchestrator
        from .orchestrator import _detect_topics
        detected = _detect_topics(slr_query or "")
        field_name = (
            next(iter(detected - {"any"}), None)
            or "SLR Auto-Discovery"
        )

        # Build unique keyword list (dedup in Python first)
        seen: set[str] = set()
        rows: list[tuple[str, str, int]] = []
        for kw in keywords:
            kw_clean = kw.lower().strip()
            if not kw_clean or kw_clean in seen:
                continue
            seen.add(kw_clean)
            rows.append((field_name, kw_clean, 3000))

        if not rows:
            return 0

        with conn.cursor() as cur:
            # Single batch INSERT — ON CONFLICT handles DB-level dedup
            execute_values(
                cur,
                """
                INSERT INTO mega_fetch_progress
                    (field_name, topic, target_count, status)
                VALUES %s
                ON CONFLICT (field_name, topic) DO NOTHING
                """,
                rows,
            )
            queued = cur.rowcount or 0
            conn.commit()

        if queued > 0:
            log.info(
                "slr.auto_fetch: queued %d new topics for mega_fetch "
                "(job=%s, field=%s)",
                queued, slr_job_id, field_name,
            )

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        log.warning("slr.auto_fetch: mega_fetch insert failed: %s", e)
    finally:
        if conn:
            try:
                db_cache.put_connection(conn)
            except Exception:
                pass

    return queued


def auto_fetch_new_topics_from_slr(payload: dict, slr_query: str, slr_job_id: str) -> int:
    """Top-level: extract keywords from SLR results and queue new topics.
    Returns number of new topics queued for background fetching.
    Should be called after SLR job is marked done. Does NOT raise.
    """
    try:
        keywords = _extract_keywords_from_slr_result(payload)
        if not keywords:
            log.info("slr.auto_fetch: no significant keywords extracted")
            return 0
        queued = _queue_new_topics_to_mega_fetch(
            keywords, slr_query, slr_job_id,
        )
        return queued
    except Exception as e:
        log.exception("slr.auto_fetch: unexpected error: %s", e)
        return 0
