#!/usr/bin/env python3
"""
Test script to verify fetchers are working correctly.
Run: python test_fetchers.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import httpx
from tools.Literatur.fetchers import ALL


def test_fetcher(name: str, module, query: str = "machine learning", limit: int = 3):
    """Test a single fetcher"""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")

    client = httpx.Client(timeout=30.0)

    try:
        papers = list(module.search(client, query, limit=limit))

        if not papers:
            print(f"⚠️  No results returned (may need API key or be unavailable)")
            return False

        print(f"✓ Found {len(papers)} papers")
        for i, paper in enumerate(papers, 1):
            print(f"\n{i}. {paper.title}")
            print(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
            print(f"   Year: {paper.year}")
            print(f"   Venue: {paper.venue}")
            if paper.doi:
                print(f"   DOI: {paper.doi}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        client.close()


def main():
    print("Academic Database Fetchers Test")
    print("="*60)

    # Test free fetchers first
    free_fetchers = [
        "openalex",
        "crossref",
        "arxiv",
        "dblp",
        "semantic_scholar",
    ]

    print("\n\n🔓 Testing FREE fetchers (no API key required):")
    print("="*60)

    results = {}
    for name in free_fetchers:
        if name in ALL:
            results[name] = test_fetcher(name, ALL[name])

    # Test fetchers that need API keys
    api_key_fetchers = {
        "ieee": "IEEE_API_KEY",
        "scopus": "ELSEVIER_API_KEY",
        "sciencedirect": "ELSEVIER_API_KEY",
        "springer": "SPRINGER_API_KEY",
        "pubmed": "NCBI_API_KEY (optional)",
    }

    print("\n\n🔑 Testing fetchers that need API keys:")
    print("="*60)

    for name, key_name in api_key_fetchers.items():
        if name in ALL:
            key_set = "NCBI_API_KEY" in os.environ if name == "pubmed" else any(
                k in os.environ for k in key_name.split()[0].split("/")
            )
            if key_set or name == "pubmed":
                results[name] = test_fetcher(name, ALL[name])
            else:
                print(f"\n⏭️  Skipping {name} (set {key_name} to test)")
                results[name] = None

    # Summary
    print("\n\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    working = [k for k, v in results.items() if v is True]
    failed = [k for k, v in results.items() if v is False]
    skipped = [k for k, v in results.items() if v is None]

    print(f"\n✓ Working: {len(working)}")
    for name in working:
        print(f"  - {name}")

    if failed:
        print(f"\n❌ Failed: {len(failed)}")
        for name in failed:
            print(f"  - {name}")

    if skipped:
        print(f"\n⏭️  Skipped: {len(skipped)}")
        for name in skipped:
            print(f"  - {name}")

    print(f"\n\nTotal fetchers available: {len(ALL)}")
    print(f"Tested: {len(results)}")
    print(f"Working: {len(working)}/{len(results)}")


if __name__ == "__main__":
    main()
