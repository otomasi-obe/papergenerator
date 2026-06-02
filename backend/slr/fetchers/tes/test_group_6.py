"""Test Group 6: oxford, proquest, pubmed"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester
import json

def test_group_6():
    results = []
    
    # Test oxford
    print("\n" + "="*80)
    print("GROUP 6 - TEST 1/3: Oxford")
    print("="*80)
    try:
        from slr.fetchers import oxford
        tester = FetcherTester("oxford", "philosophy ethics")
        result = tester.test_fetcher(oxford, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing oxford: {e}")
        results.append({"fetcher": "oxford", "status": "error", "errors": [str(e)]})
    
    # Test proquest - dissertations
    print("\n" + "="*80)
    print("GROUP 6 - TEST 2/3: ProQuest")
    print("="*80)
    try:
        from slr.fetchers import proquest
        tester = FetcherTester("proquest", "doctoral research")
        result = tester.test_fetcher(proquest, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing proquest: {e}")
        results.append({"fetcher": "proquest", "status": "error", "errors": [str(e)]})
    
    # Test pubmed - medical
    print("\n" + "="*80)
    print("GROUP 6 - TEST 3/3: PubMed")
    print("="*80)
    try:
        from slr.fetchers import pubmed
        tester = FetcherTester("pubmed", "cancer immunotherapy")
        result = tester.test_fetcher(pubmed, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing pubmed: {e}")
        results.append({"fetcher": "pubmed", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_6_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Group 6 results saved to {output_file}")
    return results

if __name__ == "__main__":
    test_group_6()
