"""Test Group 6: oxford, proquest, pubmed - with reduced limits"""
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
        from tools.Literatur.fetchers import oxford
        tester = FetcherTester("oxford", "philosophy ethics")
        result = tester.test_fetcher(oxford, limit=3)
        results.append(result)
    except Exception as e:
        print(f"Error testing oxford: {e}")
        results.append({"fetcher": "oxford", "status": "error", "errors": [str(e)]})
    
    # Test proquest - dissertations
    print("\n" + "="*80)
    print("GROUP 6 - TEST 2/3: ProQuest")
    print("="*80)
    try:
        from tools.Literatur.fetchers import proquest
        tester = FetcherTester("proquest", "doctoral research")
        result = tester.test_fetcher(proquest, limit=3)
        results.append(result)
    except Exception as e:
        print(f"Error testing proquest: {e}")
        results.append({"fetcher": "proquest", "status": "error", "errors": [str(e)]})
    
    # Test pubmed - medical (reduced limit for faster execution)
    print("\n" + "="*80)
    print("GROUP 6 - TEST 3/3: PubMed")
    print("="*80)
    try:
        from tools.Literatur.fetchers import pubmed
        tester = FetcherTester("pubmed", "diabetes")  # Simpler query
        result = tester.test_fetcher(pubmed, limit=3)
        results.append(result)
        
        # Print sample results
        if result.get('papers'):
            print(f"\n✅ PubMed Success! Found {len(result['papers'])} papers")
            print("\nSample PDF links:")
            for i, paper in enumerate(result['papers'][:3], 1):
                print(f"  {i}. {paper.get('title', 'N/A')[:60]}...")
                print(f"     URL: {paper.get('url', 'N/A')}")
                print(f"     DOI: {paper.get('doi', 'N/A')}")
                print(f"     Open Access: {paper.get('is_open_access', False)}")
                print()
    except Exception as e:
        print(f"Error testing pubmed: {e}")
        import traceback
        traceback.print_exc()
        results.append({"fetcher": "pubmed", "status": "error", "errors": [str(e)]})
    
    # Save results
    output_file = Path(__file__).parent.parent / "hasil" / "group_6_results.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✓ Group 6 results saved to {output_file}")
    
    # Print summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    for result in results:
        fetcher = result.get('fetcher', 'unknown')
        status = result.get('status', 'unknown')
        paper_count = len(result.get('papers', []))
        print(f"{fetcher:15} | Status: {status:10} | Papers: {paper_count}")
    
    return results

if __name__ == "__main__":
    test_group_6()
