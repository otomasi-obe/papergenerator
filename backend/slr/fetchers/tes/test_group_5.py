"""Test Group 5: jstor, mcgrawhill, openalex"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester
import json

def test_group_5():
    results = []
    
    # Test jstor - humanities
    print("\n" + "="*80)
    print("GROUP 5 - TEST 1/3: JSTOR")
    print("="*80)
    try:
        from slr.fetchers import jstor
        tester = FetcherTester("jstor", "american history")
        result = tester.test_fetcher(jstor, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing jstor: {e}")
        results.append({"fetcher": "jstor", "status": "error", "errors": [str(e)]})
    
    # Test mcgrawhill - education
    print("\n" + "="*80)
    print("GROUP 5 - TEST 2/3: McGraw Hill")
    print("="*80)
    try:
        from slr.fetchers import mcgrawhill
        tester = FetcherTester("mcgrawhill", "educational technology")
        result = tester.test_fetcher(mcgrawhill, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing mcgrawhill: {e}")
        results.append({"fetcher": "mcgrawhill", "status": "error", "errors": [str(e)]})
    
    # Test openalex - open access
    print("\n" + "="*80)
    print("GROUP 5 - TEST 3/3: OpenAlex")
    print("="*80)
    try:
        from slr.fetchers import openalex
        tester = FetcherTester("openalex", "artificial intelligence")
        result = tester.test_fetcher(openalex, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing openalex: {e}")
        results.append({"fetcher": "openalex", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_5_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Group 5 results saved to {output_file}")
    return results

if __name__ == "__main__":
    test_group_5()
