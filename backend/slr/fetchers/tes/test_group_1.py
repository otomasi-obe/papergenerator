"""Test Group 1: arxiv, asce, cambridge"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester
import json

def test_group_1():
    results = []
    
    # Test arxiv - preprint server
    print("\n" + "="*80)
    print("GROUP 1 - TEST 1/3: arXiv")
    print("="*80)
    try:
        from slr.fetchers import arxiv
        tester = FetcherTester("arxiv", "quantum computing")
        result = tester.test_fetcher(arxiv, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing arxiv: {e}")
        results.append({"fetcher": "arxiv", "status": "error", "errors": [str(e)]})
    
    # Test asce - civil engineering
    print("\n" + "="*80)
    print("GROUP 1 - TEST 2/3: ASCE")
    print("="*80)
    try:
        from slr.fetchers import asce
        tester = FetcherTester("asce", "structural engineering")
        result = tester.test_fetcher(asce, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing asce: {e}")
        results.append({"fetcher": "asce", "status": "error", "errors": [str(e)]})
    
    # Test cambridge
    print("\n" + "="*80)
    print("GROUP 1 - TEST 3/3: Cambridge")
    print("="*80)
    try:
        from slr.fetchers import cambridge
        tester = FetcherTester("cambridge", "mathematics education")
        result = tester.test_fetcher(cambridge, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing cambridge: {e}")
        results.append({"fetcher": "cambridge", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_1_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Group 1 results saved to {output_file}")
    return results

if __name__ == "__main__":
    test_group_1()
