#!/usr/bin/env python3
"""Test the orchestrator to ensure it properly aggregates results from multiple sources."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.Literatur.orchestrator import fetch_titles


def test_orchestrator():
    """Test orchestrator with a simple query."""
    print("=" * 80)
    print("ORCHESTRATOR TEST")
    print("=" * 80)
    print()
    
    query = "machine learning"
    print(f"Query: {query}")
    print(f"Requesting 50 results per source...")
    print()
    
    def progress_callback(event, data):
        if event == "fetching":
            print(f"Starting fetch from {len(data['sources'])} sources:")
            for src in data['sources']:
                print(f"  - {src}")
        elif event == "source_done":
            print(f"  ✓ {data['source']}: {data['count']} papers ({data['completed']}/{data['total']})")
        elif event == "dedup_done":
            print(f"\nDeduplication complete: {data['count']} unique papers")
    
    print("Fetching from all available sources...")
    print("-" * 80)
    
    papers = fetch_titles(
        query=query,
        sources=None,  # Use all available sources
        limit_per_source=50,
        max_total=100,
        progress_cb=progress_callback
    )
    
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Total unique papers: {len(papers)}")
    print()
    
    # Analyze by source
    by_source = {}
    for paper in papers:
        by_source.setdefault(paper.source, []).append(paper)
    
    print("Papers by source:")
    for source, source_papers in sorted(by_source.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {source}: {len(source_papers)}")
    print()
    
    # Check metadata completeness
    print("Metadata completeness across all papers:")
    completeness = {
        "title": sum(1 for p in papers if p.title),
        "authors": sum(1 for p in papers if p.authors),
        "year": sum(1 for p in papers if p.year),
        "doi": sum(1 for p in papers if p.doi),
        "abstract": sum(1 for p in papers if p.abstract),
        "citations": sum(1 for p in papers if p.citations is not None),
        "venue": sum(1 for p in papers if p.venue),
        "url": sum(1 for p in papers if p.url),
    }
    
    total = len(papers)
    for field, count in completeness.items():
        pct = count * 100 // total if total > 0 else 0
        print(f"  {field}: {count}/{total} ({pct}%)")
    print()
    
    # Show sample papers
    print("Sample papers (first 5):")
    print("-" * 80)
    for i, paper in enumerate(papers[:5], 1):
        print(f"\n{i}. {paper.title}")
        print(f"   Source: {paper.source}")
        print(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
        print(f"   Year: {paper.year}")
        print(f"   DOI: {paper.doi}")
        print(f"   Citations: {paper.citations}")
        print(f"   Abstract: {'Yes' if paper.abstract else 'No'}")
        print(f"   URL: {paper.url}")
    
    print()
    print("=" * 80)
    print("ORCHESTRATOR TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_orchestrator()
