#!/usr/bin/env python3
"""Generate hasil.json dengan 7 working fetchers (termasuk ArXiv)"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from slr.fetchers import arxiv, openalex, crossref, pubmed, europepmc, dblp, sinta
from slr.http_client import get_client

# All 7 working fetchers
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
        "authors": paper.authors,
        "abstract": paper.abstract,
        "year": paper.year,
        "venue": paper.venue,
        "venue_type": paper.venue_type,
        "doi": paper.doi,
        "url": paper.url,
        "citations": paper.citations,
        "is_open_access": paper.is_open_access,
        "type": paper.type,
        "publisher": paper.publisher,
    }

def search_keyword(keyword: str, limit_per_fetcher: int = 10):
    """Search keyword dengan semua fetchers"""
    print(f"\n{'='*70}")
    print(f"🔍 Searching: {keyword}")
    print(f"{'='*70}")
    
    results = {
        "keyword": keyword,
        "timestamp": datetime.now().isoformat(),
        "fetchers": {},
        "summary": {
            "total_papers": 0,
            "total_with_pdf": 0,
            "total_open_access": 0,
            "fetchers_success": 0,
            "fetchers_failed": 0,
        }
    }
    
    client = get_client()
    
    for fetcher_name, fetcher_module in FETCHERS.items():
        print(f"\n  📚 {fetcher_name.upper()}...", end=" ", flush=True)
        
        try:
            papers = list(fetcher_module.search(client, keyword, limit=limit_per_fetcher))
            
            papers_data = [paper_to_dict(p) for p in papers]
            
            # Count statistics
            papers_with_pdf = sum(1 for p in papers if p.url)
            open_access = sum(1 for p in papers if p.is_open_access)
            
            results["fetchers"][fetcher_name] = {
                "status": "success",
                "papers_found": len(papers),
                "papers_with_pdf": papers_with_pdf,
                "open_access_count": open_access,
                "papers": papers_data,
            }
            
            results["summary"]["total_papers"] += len(papers)
            results["summary"]["total_with_pdf"] += papers_with_pdf
            results["summary"]["total_open_access"] += open_access
            results["summary"]["fetchers_success"] += 1
            
            print(f"✅ {len(papers)} papers")
            
        except Exception as e:
            results["fetchers"][fetcher_name] = {
                "status": "error",
                "error": str(e),
                "papers_found": 0,
                "papers": [],
            }
            results["summary"]["fetchers_failed"] += 1
            print(f"❌ Error: {str(e)[:50]}")
    
    return results

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║           GENERATE HASIL.JSON - 7 WORKING FETCHERS                   ║
║           Including ArXiv (now working!)                             ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    
    # Keywords to search
    keywords = [
        "robot agv",
        "kesehatan manusia",
    ]
    
    # Limit per fetcher per keyword
    limit_per_fetcher = 10
    
    # Main results structure
    hasil = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_keywords": len(keywords),
            "total_fetchers": len(FETCHERS),
            "limit_per_fetcher": limit_per_fetcher,
            "fetchers_used": list(FETCHERS.keys()),
        },
        "keywords": []
    }
    
    # Search each keyword
    for keyword in keywords:
        keyword_results = search_keyword(keyword, limit_per_fetcher)
        hasil["keywords"].append(keyword_results)
    
    # Calculate overall summary
    total_papers = sum(k["summary"]["total_papers"] for k in hasil["keywords"])
    total_with_pdf = sum(k["summary"]["total_with_pdf"] for k in hasil["keywords"])
    total_open_access = sum(k["summary"]["total_open_access"] for k in hasil["keywords"])
    
    hasil["overall_summary"] = {
        "total_papers_all_keywords": total_papers,
        "total_with_pdf_links": total_with_pdf,
        "total_open_access": total_open_access,
        "keywords_searched": len(keywords),
        "fetchers_used": len(FETCHERS),
    }
    
    # Save to hasil.json
    output_dir = Path(__file__).parent / "hasil"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "hasil.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(hasil, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*70}")
    print(f"✅ HASIL.JSON GENERATED SUCCESSFULLY!")
    print(f"{'='*70}")
    print(f"\n📁 File: {output_file}")
    print(f"📊 Total Papers: {total_papers}")
    print(f"📄 With PDF Links: {total_with_pdf}")
    print(f"🔓 Open Access: {total_open_access}")
    print(f"🔍 Keywords: {len(keywords)}")
    print(f"📚 Fetchers: {len(FETCHERS)}")
    print(f"\n{'='*70}\n")
    
    # Print summary per keyword
    for kw_result in hasil["keywords"]:
        print(f"Keyword: {kw_result['keyword']}")
        print(f"  Total papers: {kw_result['summary']['total_papers']}")
        print(f"  With PDF: {kw_result['summary']['total_with_pdf']}")
        print(f"  Open Access: {kw_result['summary']['total_open_access']}")
        print(f"  Success: {kw_result['summary']['fetchers_success']}/{len(FETCHERS)} fetchers")
        print()

if __name__ == "__main__":
    main()
