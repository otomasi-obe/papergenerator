#!/usr/bin/env python3
"""Comprehensive test of all 29 SLR fetchers.

Tests each fetcher to determine:
- Working status (functional/needs-credentials/stub)
- Metadata completeness
- Ability to return results
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from slr.fetchers import ALL
from slr.http_client import get_client
from slr.paper import Paper


def check_metadata_completeness(paper: Paper) -> dict:
    """Check which metadata fields are present."""
    return {
        "title": bool(paper.title),
        "authors": bool(paper.authors),
        "year": paper.year is not None,
        "doi": bool(paper.doi),
        "abstract": bool(paper.abstract),
        "citations": paper.citations is not None,
        "venue": bool(paper.venue),
        "url": bool(paper.url),
    }


def test_fetcher(name: str, module, test_query: str = "machine learning") -> dict:
    """Test a single fetcher and return status report."""
    result = {
        "name": name,
        "status": "unknown",
        "error": None,
        "papers_found": 0,
        "sample_paper": None,
        "metadata_completeness": {},
    }

    try:
        with get_client() as client:
            papers = list(module.search(client, test_query, limit=5))
            
            if not papers:
                result["status"] = "no-results"
                result["papers_found"] = 0
            else:
                result["status"] = "working"
                result["papers_found"] = len(papers)
                
                # Check first paper for metadata completeness
                first_paper = papers[0]
                result["sample_paper"] = {
                    "title": first_paper.title[:80] + "..." if len(first_paper.title) > 80 else first_paper.title,
                    "authors": first_paper.authors[:3] if first_paper.authors else [],
                    "year": first_paper.year,
                    "doi": first_paper.doi,
                    "has_abstract": bool(first_paper.abstract),
                    "citations": first_paper.citations,
                    "venue": first_paper.venue,
                }
                
                # Calculate metadata completeness across all papers
                completeness_counts = {
                    "title": 0,
                    "authors": 0,
                    "year": 0,
                    "doi": 0,
                    "abstract": 0,
                    "citations": 0,
                    "venue": 0,
                    "url": 0,
                }
                
                for paper in papers:
                    meta = check_metadata_completeness(paper)
                    for field, present in meta.items():
                        if present:
                            completeness_counts[field] += 1
                
                # Calculate percentages
                total = len(papers)
                result["metadata_completeness"] = {
                    field: f"{count}/{total} ({count*100//total}%)"
                    for field, count in completeness_counts.items()
                }
                
    except Exception as e:
        error_msg = str(e)
        
        # Categorize the error
        if "API" in error_msg or "api_key" in error_msg.lower() or "key" in error_msg.lower():
            result["status"] = "needs-credentials"
        elif "not set" in error_msg.lower() or "skipped" in error_msg.lower():
            result["status"] = "needs-credentials"
        else:
            result["status"] = "error"
        
        result["error"] = error_msg[:200]
    
    return result


def main():
    """Test all fetchers and generate report."""
    print("=" * 80)
    print("COMPREHENSIVE SLR FETCHER TEST")
    print("=" * 80)
    print()
    
    # Check for API keys
    print("Environment Variables Check:")
    api_keys = {
        "IEEE_API_KEY": os.getenv("IEEE_API_KEY"),
        "ELSEVIER_API_KEY": os.getenv("ELSEVIER_API_KEY"),
        "SPRINGER_API_KEY": os.getenv("SPRINGER_API_KEY"),
        "S2_API_KEY": os.getenv("S2_API_KEY"),
        "NCBI_API_KEY": os.getenv("NCBI_API_KEY"),
        "OPENALEX_API_KEY": os.getenv("OPENALEX_API_KEY"),
    }
    
    for key, value in api_keys.items():
        status = "✓ SET" if value else "✗ NOT SET"
        print(f"  {key}: {status}")
    print()
    
    # Test queries for different domains
    test_queries = {
        "general": "machine learning",
        "medical": "covid-19 treatment",
        "cs": "neural networks",
    }
    
    results = {}
    
    print("Testing fetchers...")
    print("-" * 80)
    
    for name, module in ALL.items():
        print(f"Testing {name}...", end=" ", flush=True)
        
        # Choose appropriate test query
        query = test_queries["general"]
        if name in ["pubmed", "europepmc", "embase", "clinicalkey"]:
            query = test_queries["medical"]
        elif name in ["dblp", "ieee", "arxiv"]:
            query = test_queries["cs"]
        
        result = test_fetcher(name, module, query)
        results[name] = result
        
        # Print immediate status
        status_symbol = {
            "working": "✓",
            "no-results": "○",
            "needs-credentials": "⚠",
            "error": "✗",
            "unknown": "?",
        }.get(result["status"], "?")
        
        print(f"{status_symbol} {result['status'].upper()}")
    
    print()
    print("=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)
    print()
    
    # Categorize results
    working = []
    needs_credentials = []
    no_results = []
    errors = []
    
    for name, result in results.items():
        if result["status"] == "working":
            working.append((name, result))
        elif result["status"] == "needs-credentials":
            needs_credentials.append((name, result))
        elif result["status"] == "no-results":
            no_results.append((name, result))
        else:
            errors.append((name, result))
    
    # Print working fetchers
    print(f"✓ WORKING FETCHERS ({len(working)}):")
    print("-" * 80)
    for name, result in working:
        print(f"\n{name}:")
        print(f"  Papers found: {result['papers_found']}")
        if result['sample_paper']:
            print(f"  Sample: {result['sample_paper']['title']}")
            print(f"  Authors: {', '.join(result['sample_paper']['authors'])}")
            print(f"  Year: {result['sample_paper']['year']}")
            print(f"  DOI: {result['sample_paper']['doi']}")
            print(f"  Abstract: {'Yes' if result['sample_paper']['has_abstract'] else 'No'}")
            print(f"  Citations: {result['sample_paper']['citations']}")
        print(f"  Metadata completeness:")
        for field, pct in result['metadata_completeness'].items():
            print(f"    {field}: {pct}")
    
    # Print needs credentials
    print(f"\n\n⚠ NEEDS CREDENTIALS ({len(needs_credentials)}):")
    print("-" * 80)
    for name, result in needs_credentials:
        print(f"  {name}: {result.get('error', 'API key required')}")
    
    # Print no results (stubs)
    print(f"\n\n○ STUB IMPLEMENTATIONS ({len(no_results)}):")
    print("-" * 80)
    for name, result in no_results:
        print(f"  {name}: No public API available")
    
    # Print errors
    if errors:
        print(f"\n\n✗ ERRORS ({len(errors)}):")
        print("-" * 80)
        for name, result in errors:
            print(f"  {name}: {result.get('error', 'Unknown error')}")
    
    # Final statistics
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)
    print(f"Total fetchers: {len(ALL)}")
    print(f"Working (no credentials needed): {len(working)}")
    print(f"Needs credentials: {len(needs_credentials)}")
    print(f"Stub implementations: {len(no_results)}")
    print(f"Errors: {len(errors)}")
    print()
    
    # Recommendations
    print("=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    print()
    print("1. Core working fetchers (no API key needed):")
    print("   - openalex, crossref, arxiv, dblp, semantic_scholar")
    print("   - pubmed, europepmc, sinta")
    print()
    print("2. To enable additional fetchers, set these API keys:")
    print("   - IEEE_API_KEY for IEEE Xplore")
    print("   - ELSEVIER_API_KEY for Scopus & ScienceDirect")
    print("   - SPRINGER_API_KEY for Springer/Nature")
    print()
    print("3. Stub fetchers are intentional - their content is available")
    print("   through crossref/openalex aggregators")
    print()


if __name__ == "__main__":
    main()
