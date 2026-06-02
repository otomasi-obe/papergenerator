"""Test Group 3: ebscohost, embase, emerald"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester
import json

def test_group_3():
    results = []
    
    # Test ebscohost
    print("\n" + "="*80)
    print("GROUP 3 - TEST 1/3: EBSCOhost")
    print("="*80)
    try:
        from slr.fetchers import ebscohost
        tester = FetcherTester("ebscohost", "educational psychology")
        result = tester.test_fetcher(ebscohost, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing ebscohost: {e}")
        results.append({"fetcher": "ebscohost", "status": "error", "errors": [str(e)]})
    
    # Test embase - pharmacology
    print("\n" + "="*80)
    print("GROUP 3 - TEST 2/3: Embase")
    print("="*80)
    try:
        from slr.fetchers import embase
        tester = FetcherTester("embase", "drug interactions")
        result = tester.test_fetcher(embase, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing embase: {e}")
        results.append({"fetcher": "embase", "status": "error", "errors": [str(e)]})
    
    # Test emerald - business
    print("\n" + "="*80)
    print("GROUP 3 - TEST 3/3: Emerald")
    print("="*80)
    try:
        from slr.fetchers import emerald
        tester = FetcherTester("emerald", "supply chain management")
        result = tester.test_fetcher(emerald, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing emerald: {e}")
        results.append({"fetcher": "emerald", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_3_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Group 3 results saved to {output_file}")
    return results

if __name__ == "__main__":
    test_group_3()
