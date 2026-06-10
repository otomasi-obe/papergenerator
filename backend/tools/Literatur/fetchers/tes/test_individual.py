#!/usr/bin/env python3
"""Test individual fetcher dengan timeout"""

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
TIMEOUT = 15  # timeout per fetcher

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Fetcher timeout")

def test_fetcher(name: str, module):
    """Test single fetcher dengan timeout"""
    result = {
        "name": name,
        "status": "unknown",
        "papers_found": 0,
        "papers_with_url": 0,
        "papers_with_doi": 0,
        "sample_papers": [],
        "error": None,
        "timestamp": datetime.now().isoformat()
    }
    
    # Set timeout
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
                
                if len(result["sample_papers"]) < 2:
                    result["sample_papers"].append({
                        "title": paper.title,
                        "authors": paper.authors[:3] if paper.authors else [],
                        "year": paper.year,
                        "url": paper.url,
                        "doi": paper.doi,
                        "is_open_access": paper.is_open_access,
                        "venue": paper.venue,
                    })
            
            print(f"✓ {name}: {len(papers)} papers, {result['papers_with_url']} URL, {result['papers_with_doi']} DOI")
        else:
            result["status"] = "no_results"
            print(f"⚠ {name}: No results")
            
    except TimeoutError:
        result["status"] = "timeout"
        result["error"] = "Timeout after 15s"
        print(f"✗ {name}: Timeout")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"✗ {name}: {e}")
    finally:
        signal.alarm(0)  # Cancel alarm
    
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_individual.py <fetcher_name>")
        print(f"Available: {', '.join(sorted(ALL.keys()))}")
        sys.exit(1)
    
    name = sys.argv[1]
    if name not in ALL:
        print(f"Unknown fetcher: {name}")
        print(f"Available: {', '.join(sorted(ALL.keys()))}")
        sys.exit(1)
    
    result = test_fetcher(name, ALL[name])
    print(json.dumps(result, indent=2))
