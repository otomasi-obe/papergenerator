#!/usr/bin/env python3
"""
Debug script untuk DBLP fetcher
Test berbagai endpoint dan format query
"""

import requests
import json
from urllib.parse import quote

def test_dblp_api():
    """Test DBLP API dengan berbagai format"""
    
    queries = [
        "machine learning",
        "deep learning",
        "neural networks"
    ]
    
    print("="*80)
    print("DBLP API DEBUG TEST")
    print("="*80)
    
    for query in queries:
        print(f"\n\nTesting query: {query}")
        print("-"*80)
        
        # Test 1: JSON format
        print("\n1. Testing JSON format:")
        url = f"https://dblp.org/search/publ/api?q={quote(query)}&h=5&format=json"
        print(f"   URL: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                
                if 'result' in data:
                    result = data['result']
                    print(f"   Result keys: {list(result.keys())}")
                    
                    if 'hits' in result:
                        hits = result['hits']
                        print(f"   Hits keys: {list(hits.keys())}")
                        
                        if '@total' in hits:
                            print(f"   Total hits: {hits['@total']}")
                        
                        if 'hit' in hits:
                            papers = hits['hit']
                            print(f"   Papers found: {len(papers)}")
                            
                            if papers:
                                print("\n   First paper:")
                                first = papers[0]
                                print(f"   Keys: {list(first.keys())}")
                                
                                if 'info' in first:
                                    info = first['info']
                                    print(f"   Title: {info.get('title', 'N/A')}")
                                    print(f"   Authors: {info.get('authors', 'N/A')}")
                                    print(f"   Year: {info.get('year', 'N/A')}")
                                    print(f"   URL: {info.get('url', 'N/A')}")
                                    print(f"   EE: {info.get('ee', 'N/A')}")
            else:
                print(f"   Error: {response.text[:200]}")
                
        except Exception as e:
            print(f"   Exception: {str(e)}")
        
        # Test 2: XML format
        print("\n2. Testing XML format:")
        url = f"https://dblp.org/search/publ/api?q={quote(query)}&h=5&format=xml"
        print(f"   URL: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"   Response length: {len(response.text)} chars")
                print(f"   First 200 chars: {response.text[:200]}")
            else:
                print(f"   Error: {response.text[:200]}")
                
        except Exception as e:
            print(f"   Exception: {str(e)}")

def test_dblp_direct_url():
    """Test direct DBLP paper URLs"""
    
    print("\n\n" + "="*80)
    print("TESTING DIRECT DBLP URLS")
    print("="*80)
    
    # Test beberapa paper URLs dari DBLP
    test_urls = [
        "https://dblp.org/rec/journals/nature/LeCunBH15.html",
        "https://dblp.org/rec/conf/nips/KrizhevskySH12.html"
    ]
    
    for url in test_urls:
        print(f"\nTesting: {url}")
        try:
            response = requests.get(url, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                # Cek apakah ada link ke PDF
                if 'doi.org' in response.text:
                    print("Found DOI link")
                if 'arxiv.org' in response.text:
                    print("Found ArXiv link")
                if '.pdf' in response.text.lower():
                    print("Found PDF reference")
                    
        except Exception as e:
            print(f"Exception: {str(e)}")

if __name__ == "__main__":
    test_dblp_api()
    test_dblp_direct_url()
    
    print("\n\n" + "="*80)
    print("DEBUG SELESAI")
    print("="*80)
    print("\nCatatan:")
    print("- DBLP adalah database bibliografi, bukan repository paper")
    print("- DBLP menyediakan metadata dan link ke publisher")
    print("- Untuk PDF, perlu follow link ke publisher atau ArXiv")
    print("- Implementasi fetcher perlu extract link dari metadata")
