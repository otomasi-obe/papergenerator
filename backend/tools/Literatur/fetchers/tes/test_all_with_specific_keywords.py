#!/usr/bin/env python3
"""Test all fetchers dengan keyword yang sesuai untuk domain masing-masing"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.Literatur.fetchers import arxiv, openalex, crossref, pubmed, europepmc, dblp, sinta
from tools.Literatur.http_client import get_client

# Keyword yang sesuai untuk setiap fetcher berdasarkan coverage
FETCHER_KEYWORDS = {
    "arxiv": [
        "neural networks",           # CS
        "quantum computing",         # Physics
        "deep learning",            # CS/AI
    ],
    "openalex": [
        "machine learning",         # Broad
        "climate change",           # Science
        "artificial intelligence",  # CS
    ],
    "crossref": [
        "machine learning",         # Broad
        "cancer treatment",         # Medical
        "renewable energy",         # Engineering
    ],
    "pubmed": [
        "cancer",                   # Medical
        "diabetes",                 # Medical
        "covid-19",                 # Medical
    ],
    "europepmc": [
        "cancer treatment",         # Medical
        "diabetes mellitus",        # Medical
        "cardiovascular disease",   # Medical
    ],
    "dblp": [
        "machine learning",         # CS
        "neural networks",          # CS
        "algorithms",               # CS
    ],
    "sinta": [
        "pendidikan",               # Indonesian
        "kesehatan",                # Indonesian
        "teknologi informasi",      # Indonesian
    ],
}

FETCHERS = {
    "arxiv": arxiv,
    "openalex": openalex,
    "crossref": crossref,
    "pubmed": pubmed,
    "europepmc": europepmc,
    "dblp": dblp,
    "sinta": sinta,
}

def paper_to_dict(paper):
    """Convert Paper object to dict"""
    return {
        "source": paper.source,
        "source_id": paper.source_id,
        "title": paper.title,
        "authors": paper.authors[:3] if paper.authors else [],  # Limit authors
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "url": paper.url,
        "is_open_access": paper.is_open_access,
    }

def test_fetcher_with_keywords(fetcher_name: str, fetcher_module, keywords: list, limit: int = 5):
    """Test fetcher dengan multiple keywords sampai dapat hasil"""
    print(f"\n{'='*70}")
    print(f"Testing: {fetcher_name.upper()}")
    print(f"{'='*70}")
    
    client = get_client()
    results = {
        "fetcher": fetcher_name,
        "keywords_tested": [],
        "total_papers": 0,
        "status": "failed",
    }
    
    for keyword in keywords:
        print(f"\n  Keyword: '{keyword}'...", end=" ", flush=True)
        
        try:
            start = time.time()
            papers = list(fetcher_module.search(client, keyword, limit=limit))
            elapsed = time.time() - start
            
            if papers:
                papers_data = [paper_to_dict(p) for p in papers]
                
                results["keywords_tested"].append({
                    "keyword": keyword,
                    "papers_found": len(papers),
                    "time": round(elapsed, 2),
                    "papers": papers_data,
                })
                results["total_papers"] += len(papers)
                results["status"] = "success"
                
                print(f"✅ {len(papers)} papers ({elapsed:.1f}s)")
                
                # Show first paper
                if papers:
                    p = papers[0]
                    print(f"      Sample: {p.title[:50]}...")
                    print(f"      URL: {p.url}")
                
                # Stop after first successful keyword
                break
            else:
                print(f"⚠️  0 papers")
                results["keywords_tested"].append({
                    "keyword": keyword,
                    "papers_found": 0,
                    "time": round(elapsed, 2),
                    "papers": [],
                })
                
        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}")
            results["keywords_tested"].append({
                "keyword": keyword,
                "error": str(e),
                "papers_found": 0,
                "papers": [],
            })
    
    if results["status"] == "success":
        print(f"\n  ✅ SUCCESS: {results['total_papers']} papers total")
    else:
        print(f"\n  ❌ FAILED: No papers found with any keyword")
    
    return results

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║        TEST ALL FETCHERS WITH DOMAIN-SPECIFIC KEYWORDS               ║
║        Ensuring ALL fetchers return results                          ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    
    all_results = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_fetchers": len(FETCHERS),
        },
        "fetchers": []
    }
    
    for fetcher_name in FETCHERS.keys():
        fetcher_module = FETCHERS[fetcher_name]
        keywords = FETCHER_KEYWORDS[fetcher_name]
        
        result = test_fetcher_with_keywords(fetcher_name, fetcher_module, keywords, limit=5)
        all_results["fetchers"].append(result)
        
        # Delay between fetchers
        time.sleep(2)
    
    # Summary
    print(f"\n{'='*70}")
    print("FINAL SUMMARY")
    print(f"{'='*70}\n")
    
    success_count = sum(1 for r in all_results["fetchers"] if r["status"] == "success")
    total_papers = sum(r["total_papers"] for r in all_results["fetchers"])
    
    print(f"✅ Success: {success_count}/{len(FETCHERS)} fetchers")
    print(f"📄 Total papers: {total_papers}")
    print()
    
    print("Fetcher Results:")
    for r in all_results["fetchers"]:
        status_icon = "✅" if r["status"] == "success" else "❌"
        print(f"  {status_icon} {r['fetcher']:12s}: {r['total_papers']:3d} papers")
    
    # Save results
    output_dir = Path(__file__).parent / "hasil"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "all_fetchers_working.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n📁 Results saved to: {output_file}")
    
    if success_count == len(FETCHERS):
        print(f"\n🎉 SUCCESS! All {len(FETCHERS)} fetchers are working!")
        return 0
    else:
        print(f"\n⚠️  {len(FETCHERS) - success_count} fetchers failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
