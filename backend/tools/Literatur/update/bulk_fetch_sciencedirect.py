#!/usr/bin/env python3
"""
Bulk Fetcher: ScienceDirect API (Elsevier)
===========================================
Dedicated standalone fetcher — searches ALL topics via ScienceDirect Search API.
Requires ELSEVIER_API_KEY with ScienceDirect Search entitlement.
Falls back to Scopus Search API if SD Search returns 401 (no entitlement).
Writes to paper_database PG via Unix socket.

Usage:
    cd /home/sirobo/papergenerator/backend
    .venv/bin/python tools/Literatur/update/bulk_fetch_sciencedirect.py [--limit N]

Config:
    ELSEVIER_API_KEY      API key from https://dev.elsevier.com
    PAPERS_PER_TOPIC      Max papers to fetch per topic (default: 200)

Note: Most institutional Elsevier keys do NOT have ScienceDirect Search entitlement.
If your key gets 401, this fetcher automatically falls back to Scopus Search API
(which has broader coverage including non-Elsevier content).
"""

import json
import os
import sys
import time
import logging

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".env"))

from db_utils import get_conn, upsert_papers, load_all_topics, log_progress

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY = os.getenv("ELSEVIER_API_KEY")
if not API_KEY:
    print("ERROR: ELSEVIER_API_KEY not set in .env or environment")
    sys.exit(1)

SD_URL = "https://api.elsevier.com/content/search/sciencedirect"
SCOPUS_URL = "https://api.elsevier.com/content/search/scopus"
HEADERS = {"X-ELS-APIKey": API_KEY, "Accept": "application/json"}
DELAY = 0.5
OA_DELAY = 0.2
PER_PAGE = 25
MAX_FAILS = 5
MAX_START = 5000

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("sciencedirect_fetcher")

_sd_entitlement = None  # None=unknown, True=has SD, False=must use Scopus


def _check_sd_entitlement(client: httpx.Client) -> bool:
    """Test if API key has ScienceDirect Search entitlement."""
    global _sd_entitlement
    if _sd_entitlement is not None:
        return _sd_entitlement

    try:
        r = client.get(SD_URL, params={"query": "test", "count": 1}, headers=HEADERS, timeout=15.0)
        _sd_entitlement = (r.status_code == 200)
        if _sd_entitlement:
            log.info("ScienceDirect Search entitlement: YES")
        else:
            log.info(f"ScienceDirect Search entitlement: NO (HTTP {r.status_code}). Falling back to Scopus.")
    except Exception:
        _sd_entitlement = False
        log.info("ScienceDirect Search: connection failed. Falling back to Scopus.")

    return _sd_entitlement


def fetch_sd_page(client: httpx.Client, topic: str, start: int, count: int) -> list[dict]:
    """Fetch from ScienceDirect Search API."""
    try:
        r = client.get(SD_URL, params={
            "query": topic,
            "count": min(PER_PAGE, count),
            "start": start,
            "sort": "-pubyear",  # newest papers first
        }, headers=HEADERS, timeout=30.0)

        if r.status_code == 401:
            global _sd_entitlement
            _sd_entitlement = False
            return []

        if r.status_code != 200:
            log.error(f"SD API error {r.status_code}: {r.text[:200]}")
            return []

        data = r.json()
        entries = data.get("search-results", {}).get("entry", [])
        papers = []

        for entry in entries:
            if entry.get("error"):
                continue
            title = entry.get("dc:title", "")
            if not title:
                continue

            doi = entry.get("prism:doi", "")
            pii = entry.get("pii", "")

            # Authors
            authors_data = entry.get("authors", {}).get("author", [])
            if isinstance(authors_data, dict):
                authors_data = [authors_data]
            authors = [a.get("$", "").strip() for a in authors_data if a.get("$", "").strip()]

            year = None
            cover_date = entry.get("prism:coverDate", "")
            if cover_date:
                try:
                    year = int(cover_date.split("-")[0])
                except (ValueError, IndexError):
                    pass

            papers.append({
                "doi": (doi or "")[:1000],
                "title": title[:2000],
                "authors": json.dumps(authors)[:5000],
                "year": year,
                "venue": (entry.get("prism:publicationName") or "")[:500],
                "venue_type": "journal",
                "abstract": (entry.get("dc:description") or "")[:5000],
                "citations": 0,
                "is_open_access": entry.get("openaccess") == "1",
                "url": entry.get("prism:url") or (f"https://doi.org/{doi}" if doi else ""),
                "pdf_url": "",
                "source": "sciencedirect",
                "source_id": (pii or doi or "")[:255],
                "paper_type": (entry.get("prism:aggregationType") or "")[:100],
                "publisher": "Elsevier",
            })

        return papers

    except Exception as e:
        log.error(f"SD fetch error: {e}")
        return []


def fetch_scopus_page(client: httpx.Client, topic: str, start: int, count: int) -> list[dict]:
    """Fallback: fetch from Scopus API (same key, broader coverage)."""
    try:
        r = client.get(SCOPUS_URL, params={
            "query": topic,
            "count": min(PER_PAGE, count),
            "start": start,
            "sort": "-pubyear",  # newest first
        }, headers=HEADERS, timeout=30.0)

        if r.status_code != 200:
            log.error(f"Scopus fallback error {r.status_code}: {r.text[:200]}")
            return []

        data = r.json()
        entries = data.get("search-results", {}).get("entry", [])
        papers = []

        for entry in entries:
            if entry.get("error"):
                continue
            title = entry.get("dc:title", "")
            if not title:
                continue

            doi = entry.get("prism:doi", "")
            source_id = entry.get("dc:identifier", "").replace("SCOPUS_ID:", "")

            year = None
            cover_date = entry.get("prism:coverDate", "")
            if cover_date:
                try:
                    year = int(cover_date.split("-")[0])
                except (ValueError, IndexError):
                    pass

            agg_type = entry.get("prism:aggregationType", "")
            venue_type = ""
            if "journal" in agg_type.lower():
                venue_type = "journal"
            elif "conference" in agg_type.lower():
                venue_type = "conference"

            try:
                citations = int(entry.get("citedby-count", 0))
            except (ValueError, TypeError):
                citations = 0

            papers.append({
                "doi": (doi or "")[:1000],
                "title": title[:2000],
                "authors": json.dumps([entry.get("dc:creator", "")])[:5000],
                "year": year,
                "venue": (entry.get("prism:publicationName") or "")[:500],
                "venue_type": venue_type,
                "abstract": "",  # Scopus search doesn't return abstracts
                "citations": citations,
                "is_open_access": entry.get("openaccess") == "1",
                "url": f"https://doi.org/{doi}" if doi else "",
                "pdf_url": "",
                "source": "scopus",
                "source_id": source_id,
                "paper_type": agg_type[:100],
                "publisher": (entry.get("dc:publisher") or "")[:500],
            })

        return papers

    except Exception as e:
        log.error(f"Scopus fallback error: {e}")
        return []


def enrich_abstracts_oa(papers: list[dict]) -> int:
    """Enrich papers without abstracts via OpenAlex DOI lookup."""
    enriched = 0
    for p in papers:
        doi = p.get("doi", "")
        abstract = p.get("abstract", "")
        if not doi or abstract:
            continue
        try:
            time.sleep(OA_DELAY)
            r = httpx.get(f"https://api.openalex.org/works/doi:{doi}", timeout=15.0)
            if r.status_code != 200:
                continue
            oa = r.json()
            ai = oa.get("abstract_inverted_index")
            if ai and isinstance(ai, dict):
                word_positions = []
                for word, positions in ai.items():
                    for pos in positions:
                        word_positions.append((pos, word))
                word_positions.sort()
                abstract = " ".join(w for _, w in word_positions)
                if abstract:
                    p["abstract"] = abstract[:5000]
                    enriched += 1
        except Exception:
            continue
    return enriched


def main():
    limit_per_topic = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--limit" else 200

    topics = load_all_topics(DATA_DIR)
    log.info(f"ScienceDirect fetcher starting: {len(topics)} topics, {limit_per_topic}/topic")

    conn = get_conn()
    client = httpx.Client(timeout=30.0)

    # Check SD entitlement
    use_sd = _check_sd_entitlement(client)

    total_fetched = 0
    total_inserted = 0
    total_enriched = 0
    t_start = time.time()

    for i, t in enumerate(topics):
        topic = t["topic"]
        field = t["field"]
        source_name = "SD" if use_sd else "Scopus(fb)"
        print(f"\n[{i+1}/{len(topics)}] [{field}] [{source_name}] {topic}")

        topic_fetched = 0
        topic_inserted = 0
        topic_enriched = 0
        start = 0
        fails = 0
        all_papers = []

        while topic_fetched < limit_per_topic and start < MAX_START:
            time.sleep(DELAY)
            if use_sd:
                batch = fetch_sd_page(client, topic, start, limit_per_topic - topic_fetched)
            else:
                batch = fetch_scopus_page(client, topic, start, limit_per_topic - topic_fetched)

            if not batch:
                fails += 1
                if fails >= MAX_FAILS:
                    log.warning(f"Too many failures for '{topic}'")
                    break
                continue

            fails = 0
            all_papers.extend(batch)
            topic_fetched += len(batch)
            start += len(batch)

        if all_papers:
            topic_enriched = enrich_abstracts_oa(all_papers)
            total_enriched += topic_enriched
            topic_inserted = upsert_papers(conn, all_papers)

        total_fetched += topic_fetched
        total_inserted += topic_inserted
        log_progress("SD/Scopus", topic, topic_fetched, topic_inserted, time.time() - t_start)
        if topic_enriched:
            print(f"         enriched={topic_enriched} abstracts")

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"SCIENCEDIRECT/ELSEVIER FETCHER DONE: {total_fetched} fetched, {total_inserted} new, {total_enriched} enriched in {elapsed:.1f}s")
    print(f"Rate: {total_fetched / max(elapsed, 0.1):.0f} rec/s")

    client.close()
    conn.close()


if __name__ == "__main__":
    main()