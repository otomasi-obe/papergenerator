#!/usr/bin/env python3
"""
Debug script untuk Semantic Scholar fetcher
Test berbagai endpoint dan parameter
"""

import requests
import json
from urllib.parse import quote

def test_semantic_scholar_api():
    """Test Semantic Scholar API dengan berbagai format"""
    
    queries = [
        "machine learning",
        "deep learning",
        "neural networks"
    ]
    
    print("="*80)
    print("SEMANTIC SCHOLAR API DEBUG TEST")
    print("="*80)
    
    # Headers yang direkomendasikan
    headers = {
        'User-Agent': 'PaperGenerator/1.0 (mailto:test@example.com)'
    }
    
    for query in queries:
        print(f"\n\nTesting query: {query}")
        print("-"*80)
        
        # Test 1: Paper search endpoint
        print("\n1. Testing paper search endpoint:")
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={quote(query)}&limit=5"
        print(f"   URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Response keys: {list(data.keys())}")
                
                if 'data' in data:
                    papers = data['data']
                    print(f"   Papers found: {len(papers)}")
                    
                    if papers:
                        print("\n   First paper:")
                        first = papers[0]
                        print(f"   Keys: {list(first.keys())}")
                        print(f"   Paper ID: {first.get('paperId', 'N/A')}")
                        print(f"   Title: {first.get('title', 'N/A')}")
                        
                if 'total' in data:
                    print(f"   Total results: {data['total']}")
                    
            elif response.status_code == 429:
                print("   Rate limit exceeded!")
                print(f"   Headers: {dict(response.headers)}")
            else:
                print(f"   Error: {response.text[:200]}")
                
        except Exception as e:
            print(f"   Exception: {str(e)}")
        
        # Test 2: Paper search with fields
        print("\n2. Testing with specific fields:")
        fields = "title,authors,year,abstract,url,openAccessPdf,externalIds"
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={quote(query)}&limit=5&fields={fields}"
        print(f"   URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if 'data' in data and data['data']:
                    papers = data['data']
                    print(f"   Papers found: {len(papers)}")
                    
                    print("\n   First paper details:")
                    first = papers[0]
                    print(f"   Title: {first.get('title', 'N/A')}")
                    print(f"   Year: {first.get('year', 'N/A')}")
                    print(f"   URL: {first.get('url', 'N/A')}")
                    
                    # Check for PDF
                    if 'openAccessPdf' in first and first['openAccessPdf']:
                        pdf_info = first['openAccessPdf']
                        print(f"   PDF URL: {pdf_info.get('url', 'N/A')}")
                        print(f"   PDF Status: {pdf_info.get('status', 'N/A')}")
                    else:
                        print("   No open access PDF")
                    
                    # Check external IDs
                    if 'externalIds' in first and first['externalIds']:
                        ext_ids = first['externalIds']
                        print(f"   External IDs: {ext_ids}")
                        
                        # If has ArXiv ID, can get PDF
                        if 'ArXiv' in ext_ids:
                            arxiv_id = ext_ids['ArXiv']
                            print(f"   ArXiv PDF: https://arxiv.org/pdf/{arxiv_id}.pdf")
                        
                        # If has DOI, can try to get PDF
                        if 'DOI' in ext_ids:
                            doi = ext_ids['DOI']
                            print(f"   DOI: https://doi.org/{doi}")
                    
            elif response.status_code == 429:
                print("   Rate limit exceeded!")
            else:
                print(f"   Error: {response.text[:200]}")
                
        except Exception as e:
            print(f"   Exception: {str(e)}")

def test_semantic_scholar_paper_details():
    """Test getting paper details by ID"""
    
    print("\n\n" + "="*80)
    print("TESTING PAPER DETAILS ENDPOINT")
    print("="*80)
    
    # Test dengan paper ID yang dikenal
    paper_ids = [
        "649def34f8be52c8b66281af98ae884c09aef38b",  # BERT paper
        "204e3073870fae3d05bcbc2f6a8e263d9b72e776"   # Attention is All You Need
    ]
    
    headers = {
        'User-Agent': 'PaperGenerator/1.0 (mailto:test@example.com)'
    }
    
    fields = "title,authors,year,abstract,url,openAccessPdf,externalIds"
    
    for paper_id in paper_ids:
        print(f"\nTesting paper ID: {paper_id}")
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}?fields={fields}"
        print(f"URL: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Title: {data.get('title', 'N/A')}")
                print(f"Year: {data.get('year', 'N/A')}")
                
                if 'openAccessPdf' in data and data['openAccessPdf']:
                    print(f"PDF: {data['openAccessPdf'].get('url', 'N/A')}")
                else:
                    print("No open access PDF")
                    
            elif response.status_code == 429:
                print("Rate limit exceeded!")
            else:
                print(f"Error: {response.text[:200]}")
                
        except Exception as e:
            print(f"Exception: {str(e)}")

def test_rate_limits():
    """Test rate limiting"""
    
    print("\n\n" + "="*80)
    print("TESTING RATE LIMITS")
    print("="*80)
    
    headers = {
        'User-Agent': 'PaperGenerator/1.0 (mailto:test@example.com)'
    }
    
    print("\nMaking 5 rapid requests to check rate limiting...")
    
    for i in range(5):
        url = "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1"
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Request {i+1}: Status {response.status_code}")
            
            # Check rate limit headers
            if 'x-ratelimit-limit' in response.headers:
                print(f"  Rate limit: {response.headers['x-ratelimit-limit']}")
            if 'x-ratelimit-remaining' in response.headers:
                print(f"  Remaining: {response.headers['x-ratelimit-remaining']}")
            if 'x-ratelimit-reset' in response.headers:
                print(f"  Reset: {response.headers['x-ratelimit-reset']}")
                
        except Exception as e:
            print(f"Request {i+1}: Exception - {str(e)}")

if __name__ == "__main__":
    test_semantic_scholar_api()
    test_semantic_scholar_paper_details()
    test_rate_limits()
    
    print("\n\n" + "="*80)
    print("DEBUG SELESAI")
    print("="*80)
    print("\nCatatan:")
    print("- Semantic Scholar API gratis tanpa API key")
    print("- Rate limit: 100 requests per 5 minutes")
    print("- Perlu User-Agent header yang proper")
    print("- openAccessPdf field berisi link PDF jika tersedia")
    print("- Bisa fallback ke ArXiv PDF jika ada ArXiv ID")
