"""Test Group 2: clinicalkey, crossref, dblp"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester
import json

def test_group_2():
    results = []
    
    # Test clinicalkey - medical
    print("\n" + "="*80)
    print("GROUP 2 - TEST 1/3: ClinicalKey")
    print("="*80)
    try:
        from tools.Literatur.fetchers import clinicalkey
        tester = FetcherTester("clinicalkey", "diabetes treatment")
        result = tester.test_fetcher(clinicalkey, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing clinicalkey: {e}")
        results.append({"fetcher": "clinicalkey", "status": "error", "errors": [str(e)]})
    
    # Test crossref - metadata
    print("\n" + "="*80)
    print("GROUP 2 - TEST 2/3: Crossref")
    print("="*80)
    try:
        from tools.Literatur.fetchers import crossref
        tester = FetcherTester("crossref", "machine learning")
        result = tester.test_fetcher(crossref, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing crossref: {e}")
        results.append({"fetcher": "crossref", "status": "error", "errors": [str(e)]})
    
    # Test dblp - computer science
    print("\n" + "="*80)
    print("GROUP 2 - TEST 3/3: DBLP")
    print("="*80)
    try:
        from tools.Literatur.fetchers import dblp
        tester = FetcherTester("dblp", "database systems")
        result = tester.test_fetcher(dblp, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing dblp: {e}")
        results.append({"fetcher": "dblp", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_2_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Group 2 results saved to {output_file}")
    return results

if __name__ == "__main__":
    test_group_2()
