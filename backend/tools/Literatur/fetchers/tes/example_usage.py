#!/usr/bin/env python3
"""
Quick example: Search multiple databases and combine results
"""

import httpx
from tools.Literatur.fetchers import ALL


def search_multiple_sources(query: str, sources: list[str], limit_per_source: int = 5):
    """Search multiple academic databases and combine results"""
    client = httpx.Client(timeout=30.0)
    all_papers = []

    print(f"Searching for: '{query}'")
    print(f"Sources: {', '.join(sources)}\n")

    for source_name in sources:
        if source_name not in ALL:
            print(f"⚠️  Unknown source: {source_name}")
            continue

        print(f"Searching {source_name}...", end=" ")
        try:
            papers = list(ALL[source_name].search(client, query, limit=limit_per_source))
            print(f"✓ Found {len(papers)} papers")
            all_papers.extend(papers)
        except Exception as e:
            print(f"❌ Error: {e}")

    client.close()

    # Remove duplicates by DOI
    seen_dois = set()
    unique_papers = []
    for paper in all_papers:
        if paper.doi:
            if paper.doi not in seen_dois:
                seen_dois.add(paper.doi)
                unique_papers.append(paper)
        else:
            unique_papers.append(paper)

    print(f"\n{'='*60}")
    print(f"Total: {len(all_papers)} papers, {len(unique_papers)} unique")
    print(f"{'='*60}\n")

    # Display results
    for i, paper in enumerate(unique_papers[:10], 1):
        print(f"{i}. {paper.title}")
        print(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
        print(f"   Year: {paper.year} | Venue: {paper.venue}")
        print(f"   Source: {paper.source}")
        if paper.doi:
            print(f"   DOI: {paper.doi}")
        print()

    return unique_papers


if __name__ == "__main__":
    # Example 1: Computer Science research
    print("\n" + "="*60)
    print("Example 1: Computer Science Research")
    print("="*60 + "\n")
    cs_sources = ["openalex", "arxiv", "dblp", "semantic_scholar"]
    papers = search_multiple_sources("deep learning", cs_sources, limit_per_source=3)

    # Example 2: Medical research
    print("\n" + "="*60)
    print("Example 2: Medical Research")
    print("="*60 + "\n")
    med_sources = ["pubmed", "europepmc", "openalex"]
    papers = search_multiple_sources("CRISPR gene editing", med_sources, limit_per_source=3)
