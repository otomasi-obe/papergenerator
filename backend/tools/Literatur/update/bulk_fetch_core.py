#!/usr/bin/env python3
"""
Bulk Fetcher: CORE API
========================
Dedicated standalone fetcher — searches ALL topics via CORE API (core.ac.uk).
Requires CORE_API_KEY in .env or environment.
Writes to paper_database PG via Unix socket.

Usage:
    cd /home/sirobo/papergenerator/backend
    .venv/bin/python tools/Literatur/update/bulk_fetch_core.py [--limit N]

Config:
    CORE_API_KEY          API key from https://core.ac.uk/services/api
    PAPERS_PER_TOPIC      Max papers to fetch per topic (default: 200)
"""

import json
import os
import sys
import time
import logging

import httpx
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".env"))

from db_utils import get_conn, upsert_papers, load_all_topics, log_progress

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY = os.getenv("CORE_API_KEY")
if not API_KEY:
    print("ERROR: CORE_API_KEY not set in .env or environment")
    sys.exit(1)

BASE = "https://api.core.ac.uk/v3/search/works"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
DELAY = 1.0  # seconds between requests (CORE Azure backend throttle)
PER_PAGE = 100
MAX_FAILS = 5

DATA_DIR = os.path.dirname(os.path.abspath(__file__))  # update/

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("core_fetcher")


def fetch_core_page(client: httpx.Client, topic: str, offset: int, limit: int) -> list[dict]:
    """Fetch one page from CORE API, return list of paper dicts."""
    try:
        r = client.post(BASE, json={
            "q": topic,
            "limit": min(PER_PAGE, limit),
            "offset": offset,
            "sort": ["dateNewest"],
        }, headers=HEADERS, timeout=30.0)

        if r.status_code != 200:
            log.error(f"CORE API error {r.status_code}: {r.text[:200]}")
            return []

        data = r.json()
        results = data.get("results", [])
        papers = []

        for item in results:
            title = item.get("title", "")
            if not title:
                continue

            # DOI extraction
            doi = item.get("doi")
            identifiers = item.get("identifiers")
            if not doi and isinstance(identifiers, list):
                for ident in identifiers:
                    if isinstance(ident, dict) and ident.get("type") == "doi":
                        doi = ident.get("identifier")
                        break

            # PDF URL
            pdf_url = item.get("downloadUrl")
            if not pdf_url:
                sft = item.get("sourceFulltextUrls")
                if isinstance(sft, list) and sft:
                    pdf_url = sft[0]

            # Landing URL
            landing = ""
            urls = item.get("urls")
            if isinstance(urls, list) and urls:
                landing = urls[0]
            if not landing and doi:
                landing = f"https://doi.org/{doi}"

            # Authors
            authors = [a.get("name", "") for a in (item.get("authors") or [])[:20]]

            # Year
            year = None
            y = item.get("yearPublished")
            if y:
                try:
                    year = int(str(y)[:4])
                except (ValueError, TypeError):
                    pass

            papers.append({
                "doi": (doi or "")[:1000],
                "title": title[:2000],
                "authors": json.dumps(authors)[:5000],
                "year": year,
                "venue": (item.get("publisher") or "")[:500],
                "venue_type": "",
                "abstract": (item.get("abstract") or "")[:5000],
                "citations": 0,
                "is_open_access": True,
                "url": (landing or "")[:1000],
                "pdf_url": (pdf_url or "")[:1000],
                "source": "core",
                "source_id": str(item.get("id", "")),
                "paper_type": "",
                "publisher": (item.get("publisher") or "")[:500],
            })

        return papers

    except Exception as e:
        log.error(f"CORE fetch error: {e}")
        return []


def main():
    limit_per_topic = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--limit" else 200

    topics = load_all_topics(DATA_DIR)
    log.info(f"CORE fetcher starting: {len(topics)} topics, {limit_per_topic}/topic")

    conn = get_conn()
    client = httpx.Client(timeout=30.0)

    total_fetched = 0
    total_inserted = 0
    t_start = time.time()

    for i, t in enumerate(topics):
        topic = t["topic"]
        field = t["field"]
        print(f"\n[{i+1}/{len(topics)}] [{field}] {topic}")

        topic_fetched = 0
        topic_inserted = 0
        offset = 0
        fails = 0

        while topic_fetched < limit_per_topic:
            time.sleep(DELAY)
            papers = fetch_core_page(client, topic, offset, limit_per_topic - topic_fetched)

            if not papers:
                fails += 1
                if fails >= MAX_FAILS:
                    log.warning(f"Too many failures for '{topic}', moving on")
                    break
                continue

            fails = 0
            inserted = upsert_papers(conn, papers)
            topic_fetched += len(papers)
            topic_inserted += inserted
            offset += len(papers)

            if offset >= 10000:  # CORE max depth
                break

        total_fetched += topic_fetched
        total_inserted += topic_inserted
        log_progress("CORE", topic, topic_fetched, topic_inserted, time.time() - t_start)

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"CORE FETCHER DONE: {total_fetched} fetched, {total_inserted} new in {elapsed:.1f}s")
    print(f"Rate: {total_fetched / max(elapsed, 0.1):.0f} rec/s")

    client.close()
    conn.close()


if __name__ == "__main__":
    main()