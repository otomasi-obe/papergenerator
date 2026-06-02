"""Test PubMed fetcher only with timeout"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester
import json
import signal

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Test timed out")

def test_pubmed():
    print("\n" + "="*80)
    print("Testing PubMed Fetcher")
    print("="*80)
    
    # Set timeout of 30 seconds
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(30)
    
    try:
        from slr.fetchers import pubmed
        tester = FetcherTester("pubmed", "cancer immunotherapy")
        result = tester.test_fetcher(pubmed, limit=3)  # Reduced limit
        
        signal.alarm(0)  # Cancel timeout
        
        print(f"\n✅ Test completed!")
        print(f"Papers found: {len(result.get('papers', []))}")
        
        # Show sample data
        if result.get('papers'):
            print("\nSample paper:")
            paper = result['papers'][0]
            print(f"  Title: {paper.get('title', 'N/A')[:80]}...")
            print(f"  Authors: {', '.join(paper.get('authors', [])[:3])}")
            print(f"  DOI: {paper.get('doi', 'N/A')}")
            print(f"  PDF URL: {paper.get('url', 'N/A')}")
            
        return result
        
    except TimeoutException:
        signal.alarm(0)
        print("\n⏱️ Test timed out after 30 seconds")
        print("PubMed API may be slow or unreachable")
        return {"fetcher": "pubmed", "status": "timeout", "errors": ["Request timed out"]}
    except Exception as e:
        signal.alarm(0)
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {"fetcher": "pubmed", "status": "error", "errors": [str(e)]}

if __name__ == "__main__":
    result = test_pubmed()
