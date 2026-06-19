#!/usr/bin/env python3
"""
Bulk Fetcher: Scopus API (Elsevier)
====================================
Dedicated standalone fetcher — searches ALL topics via Scopus Search API.
Requires ELSEVIER_API_KEY in .env or environment.
Uses dual-phase: Scopus search → OpenAlex DOI enrichment for abstracts.
Writes to paper_database PG via Unix socket.

Usage:
    cd /home/sirobo/papergenerator/backend
    .venv/bin/python tools/Literatur/update/bulk_fetch_scopus.py [--limit N]

Config:
    ELSEVIER_API_KEY      API key from https://dev.elsevier.com
    PAPERS_PER_TOPIC      Max papers to fetch per topic (default: 500)
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

SCOPUS_URL = "https://api.elsevier.com/content/search/scopus"
SCOPUS_HEADERS = {"X-ELS-APIKey": API_KEY, "Accept": "application/json"}
SCOPUS_DELAY = 0.5  # ~2 req/sec (respect Scopus limit)
OA_DELAY = 0.2      # OpenAlex enrichment delay
PER_PAGE = 25       # Scopus max per page
MAX_FAILS = 5
MAX_START = 5000    # Scopus max offset

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("scopus_fetcher")


def fetch_scopus_page(client: httpx.Client, topic: str, start: int, count: int) -> list[dict]:
    """Fetch one page from Scopus API, return paper dicts (no abstracts)."""
    try:
        r = client.get(SCOPUS_URL, params={
            "query": topic,
            "count": min(PER_PAGE, count),
            "start": start,
            "sort": "-pubyear",
        }, headers=SCOPUS_HEADERS, timeout=30.0)

        if r.status_code != 200:
            log.error(f"Scopus API error {r.status_code}: {r.text[:200]}")
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

            scopus_citations = entry.get("citedby-count", "0")
            try:
                citations = int(scopus_citations)
            except (ValueError, TypeError):
                citations = 0

            papers.append({
                "doi": (doi or "")[:1000],
                "title": title[:2000],
                "authors": json.dumps([entry.get("dc:creator", "")])[:5000],
                "year": year,
                "venue": (entry.get("prism:publicationName") or "")[:500],
                "venue_type": venue_type,
                "abstract": "",  # Will be enriched via OpenAlex
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
        log.error(f"Scopus fetch error: {e}")
        return []


def enrich_abstracts_oa(papers: list[dict]) -> int:
    """Enrich Scopus papers with abstracts from OpenAlex DOI lookup."""
    enriched = 0
    for p in papers:
        doi = p.get("doi", "")
        if not doi or p.get("abstract", ""):
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
    limit_per_topic = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--limit" else 500

    topics = load_all_topics(DATA_DIR)
    log.info(f"Scopus fetcher starting: {len(topics)} topics, {limit_per_topic}/topic")

    conn = get_conn()
    client = httpx.Client(timeout=30.0)

    total_fetched = 0
    total_inserted = 0
    total_enriched = 0
    t_start = time.time()

    for i, t in enumerate(topics):
        topic = t["topic"]
        field = t["field"]
        print(f"\n[{i+1}/{len(topics)}] [{field}] {topic}")

        topic_fetched = 0
        topic_inserted = 0
        topic_enriched = 0
        start = 0
        fails = 0

        # Phase 1: Fetch from Scopus
        phase1_papers = []
        while topic_fetched < limit_per_topic and start < MAX_START:
            time.sleep(SCOPUS_DELAY)
            batch = fetch_scopus_page(client, topic, start, limit_per_topic - topic_fetched)

            if not batch:
                fails += 1
                if fails >= MAX_FAILS:
                    log.warning(f"Too many failures for '{topic}'")
                    break
                continue

            fails = 0
            phase1_papers.extend(batch)
            topic_fetched += len(batch)
            start += len(batch)

        if phase1_papers:
            # Phase 2: Enrich abstracts via OpenAlex
            topic_enriched = enrich_abstracts_oa(phase1_papers)
            total_enriched += topic_enriched

            # Phase 3: Upsert all to DB
            topic_inserted = upsert_papers(conn, phase1_papers)

        total_fetched += topic_fetched
        total_inserted += topic_inserted
        log_progress("Scopus", topic, topic_fetched, topic_inserted, time.time() - t_start)
        print(f"         enriched={topic_enriched} abstracts")

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"SCOPUS FETCHER DONE: {total_fetched} fetched, {total_inserted} new, {total_enriched} enriched in {elapsed:.1f}s")
    print(f"Rate: {total_fetched / max(elapsed, 0.1):.0f} rec/s")

    client.close()
    conn.close()


if __name__ == "__main__":
    main()