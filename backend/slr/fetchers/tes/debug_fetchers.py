#!/usr/bin/env python3
"""Debug specific fetchers to understand why they return no results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from slr.fetchers import semantic_scholar, arxiv
from slr.http_client import get_client


def test_semantic_scholar():
    """Test semantic_scholar with different queries."""
    print("=" * 80)
    print("SEMANTIC SCHOLAR DEBUG")
    print("=" * 80)
    print()
    
    queries = [
        "machine learning",
        "neural networks",
        "deep learning",
    ]
    
    with get_client() as client:
        for query in queries:
            print(f"Query: '{query}'")
            try:
                papers = list(semantic_scholar.search(client, query, limit=5))
                print(f"  Results: {len(papers)}")
                if papers:
                    print(f"  Sample: {papers[0].title}")
            except Exception as e:
                print(f"  Error: {e}")
            print()


def test_arxiv():
    """Test arxiv with different queries."""
    print("=" * 80)
    print("ARXIV DEBUG")
    print("=" * 80)
    print()
    
    queries = [
        "machine learning",
        "neural networks",
        "deep learning",
    ]
    
    with get_client() as client:
        for query in queries:
            print(f"Query: '{query}'")
            try:
                papers = list(arxiv.search(client, query, limit=5))
                print(f"  Results: {len(papers)}")
                if papers:
                    print(f"  Sample: {papers[0].title}")
            except Exception as e:
                print(f"  Error: {e}")
            print()


if __name__ == "__main__":
    test_semantic_scholar()
    print()
    test_arxiv()
