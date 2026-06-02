"""Test Group 1: ASCE and Cambridge (skipping arXiv due to network issues)"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from test_framework import FetcherTester


def test_group_1_partial():
    results = []
    
    # Skip arXiv due to network connectivity issues
    print("\n" + "="*80)
    print("GROUP 1 - TEST 1/3: arXiv")
    print("="*80)
    print("⚠️  Skipping arXiv - HTTPS connection to export.arxiv.org is timing out")
    print("    This is a network connectivity issue, not a fetcher problem.")
    results.append({
        "fetcher": "arxiv",
        "status": "skipped",
        "errors": ["Network connectivity issue: HTTPS to export.arxiv.org times out"]
    })
    
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
        print(f"❌ Error testing asce: {e}")
        import traceback
        traceback.print_exc()
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
        print(f"❌ Error testing cambridge: {e}")
        import traceback
        traceback.print_exc()
        results.append({"fetcher": "cambridge", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_1_results.json"
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print("\n" + "="*80)
    print("GROUP 1 TEST SUMMARY")
    print("="*80)
    for result in results:
        fetcher = result.get("fetcher", "unknown")
        status = result.get("status", "unknown")
        papers = result.get("papers_found", 0)
        print(f"\n{fetcher}:")
        print(f"  Status: {status}")
        if status == "success":
            print(f"  Papers found: {papers}")
            print(f"  Papers with URLs: {result.get('papers_with_urls', 0)}")
            print(f"  Valid download links: {result.get('valid_download_links', 0)}")
        elif status == "no_results":
            print(f"  Papers found: 0 (query returned no results)")
        elif status == "skipped":
            print(f"  Reason: {result.get('errors', ['Unknown'])[0]}")
        elif "errors" in result:
            print(f"  Errors: {', '.join(result['errors'])}")
    
    print(f"\n✓ Group 1 results saved to {output_file}")
    print("\n" + "="*80)
    print("NOTE: arXiv was skipped due to network connectivity issues.")
    print("The HTTPS connection to export.arxiv.org is timing out.")
    print("This is not a fetcher code issue - it's a network/firewall issue.")
    print("="*80)
    
    return results


if __name__ == "__main__":
    test_group_1_partial()
