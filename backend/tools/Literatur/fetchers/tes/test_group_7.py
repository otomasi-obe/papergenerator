"""Test Group 7: sciencedirect, scopus, semantic_scholar"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester
import json

def test_group_7():
    results = []
    
    # Test sciencedirect - elsevier
    print("\n" + "="*80)
    print("GROUP 7 - TEST 1/3: ScienceDirect")
    print("="*80)
    try:
        from tools.Literatur.fetchers import sciencedirect
        tester = FetcherTester("sciencedirect", "materials science")
        result = tester.test_fetcher(sciencedirect, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing sciencedirect: {e}")
        results.append({"fetcher": "sciencedirect", "status": "error", "errors": [str(e)]})
    
    # Test scopus
    print("\n" + "="*80)
    print("GROUP 7 - TEST 2/3: Scopus")
    print("="*80)
    try:
        from tools.Literatur.fetchers import scopus
        tester = FetcherTester("scopus", "renewable energy")
        result = tester.test_fetcher(scopus, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing scopus: {e}")
        results.append({"fetcher": "scopus", "status": "error", "errors": [str(e)]})
    
    # Test semantic_scholar
    print("\n" + "="*80)
    print("GROUP 7 - TEST 3/3: Semantic Scholar")
    print("="*80)
    try:
        from tools.Literatur.fetchers import semantic_scholar
        tester = FetcherTester("semantic_scholar", "deep learning")
        result = tester.test_fetcher(semantic_scholar, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing semantic_scholar: {e}")
        results.append({"fetcher": "semantic_scholar", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_7_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Group 7 results saved to {output_file}")
    return results

if __name__ == "__main__":
    test_group_7()
