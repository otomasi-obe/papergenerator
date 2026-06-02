"""Test Group 9: westlaw, wiley"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester
import json

def test_group_9():
    results = []
    
    # Test westlaw - legal
    print("\n" + "="*80)
    print("GROUP 9 - TEST 1/2: Westlaw")
    print("="*80)
    try:
        from slr.fetchers import westlaw
        tester = FetcherTester("westlaw", "constitutional law")
        result = tester.test_fetcher(westlaw, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing westlaw: {e}")
        results.append({"fetcher": "westlaw", "status": "error", "errors": [str(e)]})
    
    # Test wiley
    print("\n" + "="*80)
    print("GROUP 9 - TEST 2/2: Wiley")
    print("="*80)
    try:
        from slr.fetchers import wiley
        tester = FetcherTester("wiley", "organic chemistry")
        result = tester.test_fetcher(wiley, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing wiley: {e}")
        results.append({"fetcher": "wiley", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_9_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Group 9 results saved to {output_file}")
    return results

if __name__ == "__main__":
    test_group_9()
