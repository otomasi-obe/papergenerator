"""Test Group 8: sinta, springer, taylor_francis"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester
import json

def test_group_8():
    results = []
    
    # Test sinta - indonesian research
    print("\n" + "="*80)
    print("GROUP 8 - TEST 1/3: SINTA")
    print("="*80)
    try:
        from slr.fetchers import sinta
        tester = FetcherTester("sinta", "pendidikan")
        result = tester.test_fetcher(sinta, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing sinta: {e}")
        results.append({"fetcher": "sinta", "status": "error", "errors": [str(e)]})
    
    # Test springer
    print("\n" + "="*80)
    print("GROUP 8 - TEST 2/3: Springer")
    print("="*80)
    try:
        from slr.fetchers import springer
        tester = FetcherTester("springer", "computational biology")
        result = tester.test_fetcher(springer, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing springer: {e}")
        results.append({"fetcher": "springer", "status": "error", "errors": [str(e)]})
    
    # Test taylor_francis
    print("\n" + "="*80)
    print("GROUP 8 - TEST 3/3: Taylor & Francis")
    print("="*80)
    try:
        from slr.fetchers import taylor_francis
        tester = FetcherTester("taylor_francis", "social psychology")
        result = tester.test_fetcher(taylor_francis, limit=5)
        results.append(result)
    except Exception as e:
        print(f"Error testing taylor_francis: {e}")
        results.append({"fetcher": "taylor_francis", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_8_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Group 8 results saved to {output_file}")
    return results

if __name__ == "__main__":
    test_group_8()
