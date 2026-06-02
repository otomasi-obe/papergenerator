"""Test Group 4: europepmc, ieee, igi_global"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester
import json

def test_group_4():
    results = []
    
    # Test europepmc - biomedical
    print("\n" + "="*80)
    print("GROUP 4 - TEST 1/3: Europe PMC")
    print("="*80)
    try:
        from slr.fetchers import europepmc
        tester = FetcherTester("europepmc", "COVID-19 vaccine")
        result = tester.test_fetcher(europepmc, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing europepmc: {e}")
        results.append({"fetcher": "europepmc", "status": "error", "errors": [str(e)]})
    
    # Test ieee - engineering
    print("\n" + "="*80)
    print("GROUP 4 - TEST 2/3: IEEE")
    print("="*80)
    try:
        from slr.fetchers import ieee
        tester = FetcherTester("ieee", "signal processing")
        result = tester.test_fetcher(ieee, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing ieee: {e}")
        results.append({"fetcher": "ieee", "status": "error", "errors": [str(e)]})
    
    # Test igi_global - information science
    print("\n" + "="*80)
    print("GROUP 4 - TEST 3/3: IGI Global")
    print("="*80)
    try:
        from slr.fetchers import igi_global
        tester = FetcherTester("igi_global", "information systems")
        result = tester.test_fetcher(igi_global, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing igi_global: {e}")
        results.append({"fetcher": "igi_global", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_4_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Group 4 results saved to {output_file}")
    return results

if __name__ == "__main__":
    test_group_4()
