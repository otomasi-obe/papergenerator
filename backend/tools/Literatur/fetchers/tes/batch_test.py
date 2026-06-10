#!/usr/bin/env python3
"""Batch test semua fetcher dengan hasil lengkap"""

import os
import sys
import json
import time
import signal
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.Literatur.fetchers import ALL
from tools.Literatur.http_client import get_client

TEST_QUERY = "machine learning"
TEST_LIMIT = 5
TIMEOUT = 20
DELAY_BETWEEN = 3

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Timeout")

def test_fetcher(name: str, module):
    """Test single fetcher dengan timeout"""
    result = {
        "name": name,
        "status": "unknown",
        "papers_found": 0,
        "papers_with_url": 0,
        "papers_with_doi": 0,
        "papers_with_pdf": 0,
        "sample_papers": [],
        "error": None,
        "timestamp": datetime.now().isoformat()
    }
    
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(TIMEOUT)
    
    try:
        client = get_client()
        papers = list(module.search(client, TEST_QUERY, limit=TEST_LIMIT))
        result["papers_found"] = len(papers)
        
        if papers:
            result["status"] = "success"
            
            for paper in papers:
                if paper.url:
                    result["papers_with_url"] += 1
                if paper.doi:
                    result["papers_with_doi"] += 1
                if paper.is_open_access:
                    result["papers_with_pdf"] += 1
                
                if len(result["sample_papers"]) < 2:
                    result["sample_papers"].append({
                        "title": paper.title[:100] if paper.title else None,
                        "authors": paper.authors[:3] if paper.authors else [],
                        "year": paper.year,
                        "url": paper.url,
                        "doi": paper.doi,
                        "is_open_access": paper.is_open_access,
                        "venue": paper.venue[:50] if paper.venue else None,
                    })
            
            print(f"✓ {name:20s} {len(papers)} papers, {result['papers_with_url']} URL, {result['papers_with_doi']} DOI")
        else:
            result["status"] = "no_results"
            print(f"⚠ {name:20s} No results")
            
    except TimeoutError:
        result["status"] = "timeout"
        result["error"] = f"Timeout after {TIMEOUT}s"
        print(f"✗ {name:20s} Timeout")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
        print(f"✗ {name:20s} Error: {str(e)[:50]}")
    finally:
        signal.alarm(0)
    
    return result

def main():
    print(f"Testing {len(ALL)} fetchers")
    print(f"Query: '{TEST_QUERY}', Limit: {TEST_LIMIT}, Timeout: {TIMEOUT}s")
    print("=" * 80)
    
    results = []
    
    for i, name in enumerate(sorted(ALL.keys())):
        module = ALL[name]
        result = test_fetcher(name, module)
        results.append(result)
        
        if i < len(ALL) - 1:
            time.sleep(DELAY_BETWEEN)
    
    # Summary
    print("=" * 80)
    success = [r for r in results if r["status"] == "success"]
    no_results = [r for r in results if r["status"] == "no_results"]
    timeout = [r for r in results if r["status"] == "timeout"]
    errors = [r for r in results if r["status"] == "error"]
    
    print(f"\nSUMMARY:")
    print(f"  ✓ Success:    {len(success)}")
    print(f"  ⚠ No results: {len(no_results)}")
    print(f"  ⏱ Timeout:    {len(timeout)}")
    print(f"  ✗ Errors:     {len(errors)}")
    
    # Save reports
    report_dir = Path(__file__).parent / "laporan"
    report_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON report
    json_file = report_dir / f"batch_test_{timestamp}.json"
    with open(json_file, "w") as f:
        json.dump({
            "test_query": TEST_QUERY,
            "test_limit": TEST_LIMIT,
            "timeout": TIMEOUT,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": len(results),
                "success": len(success),
                "no_results": len(no_results),
                "timeout": len(timeout),
                "errors": len(errors)
            },
            "results": results
        }, f, indent=2)
    
    print(f"\n✓ JSON report: {json_file}")
    
    # Markdown report
    md_file = report_dir / f"batch_test_{timestamp}.md"
    with open(md_file, "w") as f:
        f.write(f"# SLR Fetchers Test Report\n\n")
        f.write(f"**Test Query:** `{TEST_QUERY}`\n")
        f.write(f"**Test Limit:** {TEST_LIMIT} papers per fetcher\n")
        f.write(f"**Timeout:** {TIMEOUT}s per fetcher\n")
        f.write(f"**Timestamp:** {datetime.now().isoformat()}\n\n")
        
        f.write(f"## Summary\n\n")
        f.write(f"| Status | Count |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| ✓ Success | {len(success)} |\n")
        f.write(f"| ⚠ No Results | {len(no_results)} |\n")
        f.write(f"| ⏱ Timeout | {len(timeout)} |\n")
        f.write(f"| ✗ Errors | {len(errors)} |\n")
        f.write(f"| **Total** | **{len(results)}** |\n\n")
        
        f.write(f"## ✓ Successful Fetchers ({len(success)})\n\n")
        f.write("These fetchers successfully retrieved papers with download links:\n\n")
        for r in success:
            f.write(f"### {r['name']}\n\n")
            f.write(f"- **Papers found:** {r['papers_found']}\n")
            f.write(f"- **Papers with URL:** {r['papers_with_url']}\n")
            f.write(f"- **Papers with DOI:** {r['papers_with_doi']}\n")
            f.write(f"- **Open Access:** {r['papers_with_pdf']}\n\n")
            
            if r['sample_papers']:
                f.write(f"**Sample Papers:**\n\n")
                for i, p in enumerate(r['sample_papers'], 1):
                    f.write(f"{i}. **{p['title']}**\n")
                    if p['authors']:
                        f.write(f"   - Authors: {', '.join(p['authors'])}\n")
                    if p['year']:
                        f.write(f"   - Year: {p['year']}\n")
                    if p['venue']:
                        f.write(f"   - Venue: {p['venue']}\n")
                    if p['url']:
                        f.write(f"   - URL: {p['url']}\n")
                    if p['doi']:
                        f.write(f"   - DOI: https://doi.org/{p['doi']}\n")
                    if p['is_open_access']:
                        f.write(f"   - 🔓 Open Access\n")
                    f.write(f"\n")
            f.write(f"\n")
        
        f.write(f"## ⚠ No Results ({len(no_results)})\n\n")
        f.write("These fetchers require API keys or institutional subscriptions:\n\n")
        for r in no_results:
            f.write(f"- **{r['name']}**\n")
        f.write(f"\n")
        
        if timeout:
            f.write(f"## ⏱ Timeout ({len(timeout)})\n\n")
            f.write("These fetchers timed out (likely rate limiting):\n\n")
            for r in timeout:
                f.write(f"- **{r['name']}**\n")
            f.write(f"\n")
        
        if errors:
            f.write(f"## ✗ Errors ({len(errors)})\n\n")
            for r in errors:
                f.write(f"### {r['name']}\n\n")
                f.write(f"```\n{r['error']}\n```\n\n")
    
    print(f"✓ Markdown report: {md_file}")
    
    return 0 if not errors else 1

if __name__ == "__main__":
    sys.exit(main())
