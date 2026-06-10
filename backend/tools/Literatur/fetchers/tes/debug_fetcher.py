"""Debug script to see what's actually happening with fetchers"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tools.Literatur.http_client import get_client
import httpx


def debug_dblp():
    print("\n" + "="*60)
    print("DEBUG: DBLP")
    print("="*60)
    
    client = get_client()
    url = "https://dblp.org/search/publ/api"
    params = {
        "q": "machine learning",
        "format": "json",
        "h": 3,
        "f": 0,
    }
    
    print(f"URL: {url}")
    print(f"Params: {params}")
    
    try:
        response = client.get(url, params=params)
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nResponse structure:")
            print(f"  Keys: {list(data.keys())}")
            
            result = data.get("result", {})
            print(f"  result keys: {list(result.keys())}")
            
            hits_block = result.get("hits", {})
            print(f"  hits keys: {list(hits_block.keys())}")
            print(f"  @total: {hits_block.get('@total')}")
            print(f"  @sent: {hits_block.get('@sent')}")
            
            hits = hits_block.get("hit", [])
            print(f"  Number of hits: {len(hits)}")
            
            if hits:
                print(f"\nFirst hit structure:")
                print(f"  Keys: {list(hits[0].keys())}")
                info = hits[0].get("info", {})
                print(f"  info keys: {list(info.keys())}")
                print(f"  title: {info.get('title')}")
        else:
            print(f"Error response: {response.text[:500]}")
            
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()


def debug_semantic_scholar():
    print("\n" + "="*60)
    print("DEBUG: Semantic Scholar")
    print("="*60)
    
    client = get_client()
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    
    fields = "paperId,externalIds,title,abstract,year,authors,venue,publicationVenue,publicationTypes,citationCount,openAccessPdf,publicationDate"
    
    params = {
        "query": "neural networks",
        "limit": 3,
        "offset": 0,
        "fields": fields,
    }
    
    print(f"URL: {url}")
    print(f"Params: {params}")
    
    try:
        response = client.get(url, params=params)
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nResponse structure:")
            print(f"  Keys: {list(data.keys())}")
            print(f"  total: {data.get('total')}")
            print(f"  offset: {data.get('offset')}")
            
            items = data.get("data", [])
            print(f"  Number of items: {len(items)}")
            
            if items:
                print(f"\nFirst item structure:")
                print(f"  Keys: {list(items[0].keys())}")
                print(f"  title: {items[0].get('title')}")
                print(f"  paperId: {items[0].get('paperId')}")
        else:
            print(f"Error response: {response.text[:500]}")
            
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    debug_dblp()
    print("\n" + "="*80 + "\n")
    debug_semantic_scholar()
