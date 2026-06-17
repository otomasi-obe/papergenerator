#!/usr/bin/env python3
"""Retrofit PubMed abstracts for papers already in DB that have empty abstract.

Reads PMIDs from paper_database where source='pubmed' AND abstract is empty,
batch-fetches full XML from efetch, parses all AbstractText sections with
itertext(), and updates the DB.

Rate limits: PubMed free = 3 req/sec. With NCBI_API_KEY = 10 req/sec.
Batch size: 200 PMIDs per efetch call.

Usage:
    python retrofit_pubmed_abstracts.py [--batch 200] [--limit 0] [--dry-run]

    --batch   PMIDs per API call (default 200, max 10000)
    --limit   Max PMIDs to process (0 = all)
    --dry-run Only count, don't update DB
"""
import argparse
import os
import sys
import time
from xml.etree import ElementTree as ET

import httpx
import psycopg2

DB_DSN = os.getenv("PAPER_DB_DSN", "dbname=paper_database host=/var/run/postgresql")
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def get_pubmed_pmids(conn, limit=0):
    """Get PMIDs from papers where abstract is empty."""
    with conn.cursor() as cur:
        sql = """
            SELECT source_id FROM papers
            WHERE source = 'pubmed'
              AND (abstract IS NULL OR TRIM(abstract) = '')
        """
        if limit:
            sql += f" LIMIT {limit}"
        cur.execute(sql)
        return [row[0] for row in cur.fetchall()]


def parse_abstracts_from_xml(xml_content):
    """Parse efetch XML and return dict {pmid: abstract_text}."""
    root = ET.fromstring(xml_content)
    results = {}
    for article in root.findall('.//PubmedArticle'):
        pmid_elem = article.find('.//PMID')
        if pmid_elem is None or not pmid_elem.text:
            continue
        pmid = pmid_elem.text

        # Join ALL AbstractText sections with itertext (handles structured abstracts + inline tags)
        abstract_parts = []
        for at in article.findall('.//Abstract/AbstractText'):
            label = at.get('Label', '')
            full = ''.join(at.itertext())
            if label:
                abstract_parts.append(f'{label}: {full}')
            else:
                abstract_parts.append(full)
        abstract = ' '.join(abstract_parts)
        if abstract:
            results[pmid] = abstract[:5000]
    return results


def update_abstracts(conn, pmid_abstract_map):
    """Batch UPDATE abstracts by source_id."""
    if not pmid_abstract_map:
        return 0
    updated = 0
    with conn.cursor() as cur:
        for pmid, abstract in pmid_abstract_map.items():
            cur.execute("""
                UPDATE papers SET abstract = %s
                WHERE source = 'pubmed' AND source_id = %s
                  AND (abstract IS NULL OR TRIM(abstract) = '')
            """, (abstract, pmid))
            updated += cur.rowcount
    conn.commit()
    return updated


def main():
    parser = argparse.ArgumentParser(description="Retrofit PubMed abstracts from efetch XML")
    parser.add_argument("--batch", type=int, default=200, help="PMIDs per API call (default 200)")
    parser.add_argument("--limit", type=int, default=0, help="Max PMIDs to process (0=all)")
    parser.add_argument("--dry-run", action="store_true", help="Only count, don't update")
    args = parser.parse_args()

    api_key = os.getenv("NCBI_API_KEY")
    rate_delay = 0.1 if api_key else 0.35  # seconds between requests

    conn = psycopg2.connect(DB_DSN)
    try:
        pmids = get_pubmed_pmids(conn, args.limit)
        total = len(pmids)
        print(f"Found {total} PubMed papers without abstract")
        if args.dry_run:
            print("[DRY RUN] Would process", total, "PMIDs")
            return

        if not pmids:
            print("Nothing to do.")
            return

        processed = 0
        updated = 0
        batch_size = min(args.batch, 10000)

        for i in range(0, total, batch_size):
            batch_pmids = pmids[i:i + batch_size]
            time.sleep(rate_delay)

            params = {
                "db": "pubmed",
                "id": ",".join(batch_pmids),
                "retmode": "xml",
            }
            if api_key:
                params["api_key"] = api_key

            try:
                resp = httpx.get(EFETCH, params=params, timeout=60.0)
                if resp.status_code != 200:
                    print(f"  Batch {i//batch_size + 1}: HTTP {resp.status_code}, retrying...")
                    time.sleep(2.0)
                    resp = httpx.get(EFETCH, params=params, timeout=60.0)
                    if resp.status_code != 200:
                        print(f"  Batch {i//batch_size + 1}: FAILED permanently, skipping")
                        continue
            except Exception as e:
                print(f"  Batch {i//batch_size + 1}: Error: {e}")
                continue

            abstracts = parse_abstracts_from_xml(resp.content)
            batch_updated = update_abstracts(conn, abstracts)
            processed += len(batch_pmids)
            updated += batch_updated

            pct = processed * 100 / total
            print(f"  Batch {i//batch_size + 1}: processed {processed}/{total} ({pct:.1f}%), "
                  f"updated {batch_updated}/{len(batch_pmids)} in batch, "
                  f"total updated: {updated}")

        print(f"\nDone. Updated {updated}/{total} papers with abstracts.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
