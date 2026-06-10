"""Framework untuk testing fetcher - verifikasi search dan download link"""

import sys
import os
import json
import time
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tools.Literatur.http_client import get_client
import httpx


class FetcherTester:
    def __init__(self, fetcher_name: str, test_query: str = "machine learning"):
        self.fetcher_name = fetcher_name
        self.test_query = test_query
        self.results = {
            "fetcher": fetcher_name,
            "test_time": datetime.now().isoformat(),
            "test_query": test_query,
            "status": "unknown",
            "papers_found": 0,
            "papers_with_urls": 0,
            "valid_download_links": 0,
            "invalid_download_links": 0,
            "errors": [],
            "papers": [],
            "download_link_checks": []
        }

    def test_fetcher(self, fetcher_module, limit: int = 3):
        """Test a fetcher module"""
        print(f"\n{'='*60}")
        print(f"Testing: {self.fetcher_name}")
        print(f"Query: {self.test_query}")
        print(f"{'='*60}\n")

        client = get_client()

        try:
            # Try to search
            print(f"🔍 Searching for papers...")
            papers = list(fetcher_module.search(client, self.test_query, limit=limit))

            self.results["papers_found"] = len(papers)
            print(f"✓ Found {len(papers)} papers")

            if len(papers) == 0:
                self.results["status"] = "no_results"
                self.results["errors"].append("No papers found for query")
                print("⚠️  No papers found")
                return self.results

            # Check each paper
            for i, paper in enumerate(papers, 1):
                print(f"\n--- Paper {i}/{len(papers)} ---")
                print(f"Title: {paper.title[:80]}...")
                print(f"Authors: {', '.join(paper.authors[:3])}...")
                print(f"Year: {paper.year}")
                print(f"DOI: {paper.doi}")
                print(f"URL: {paper.url}")

                paper_info = {
                    "title": paper.title,
                    "authors": paper.authors[:5],
                    "year": paper.year,
                    "doi": paper.doi,
                    "url": paper.url,
                    "is_open_access": paper.is_open_access,
                    "venue": paper.venue
                }
                self.results["papers"].append(paper_info)

                if paper.url:
                    self.results["papers_with_urls"] += 1
                    # Check if URL is valid
                    link_status = self.check_download_link(paper.url, client)
                    self.results["download_link_checks"].append({
                        "paper_title": paper.title[:100],
                        "url": paper.url,
                        "status": link_status["status"],
                        "status_code": link_status.get("status_code"),
                        "content_type": link_status.get("content_type"),
                        "accessible": link_status["accessible"]
                    })

                    if link_status["accessible"]:
                        self.results["valid_download_links"] += 1
                        print(f"✓ Download link is accessible")
                    else:
                        self.results["invalid_download_links"] += 1
                        print(f"✗ Download link is NOT accessible: {link_status['status']}")
                else:
                    print("⚠️  No URL provided")

            # Determine overall status
            if self.results["valid_download_links"] > 0:
                self.results["status"] = "success"
            elif self.results["papers_with_urls"] > 0:
                self.results["status"] = "partial_success"
            else:
                self.results["status"] = "no_urls"

            print(f"\n{'='*60}")
            print(f"Summary for {self.fetcher_name}:")
            print(f"  Papers found: {self.results['papers_found']}")
            print(f"  Papers with URLs: {self.results['papers_with_urls']}")
            print(f"  Valid download links: {self.results['valid_download_links']}")
            print(f"  Invalid download links: {self.results['invalid_download_links']}")
            print(f"  Status: {self.results['status']}")
            print(f"{'='*60}\n")

        except Exception as e:
            self.results["status"] = "error"
            self.results["errors"].append(str(e))
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()

        return self.results

    def check_download_link(self, url: str, client: httpx.Client, timeout: int = 10) -> dict:
        """Check if a download link is accessible"""
        print(f"  Checking URL: {url[:80]}...")

        try:
            # Use HEAD request first to avoid downloading large files
            response = client.head(url, timeout=timeout, follow_redirects=True)

            if response.status_code == 405:  # Method not allowed, try GET
                response = client.get(url, timeout=timeout, follow_redirects=True)

            accessible = response.status_code in [200, 201, 202, 203, 204, 206]

            return {
                "status": "accessible" if accessible else f"http_{response.status_code}",
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", "unknown"),
                "accessible": accessible
            }
        except httpx.TimeoutException:
            return {"status": "timeout", "accessible": False}
        except httpx.HTTPError as e:
            return {"status": f"http_error: {str(e)}", "accessible": False}
        except Exception as e:
            return {"status": f"error: {str(e)}", "accessible": False}

    def save_report(self, report_dir: str = "/home/sirobo/papergenerator/backend/slr/fetchers/laporan"):
        """Save test report to JSON file"""
        os.makedirs(report_dir, exist_ok=True)

        report_file = os.path.join(report_dir, f"{self.fetcher_name}_report.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)

        print(f"📄 Report saved to: {report_file}")

        # Also create a human-readable summary
        summary_file = os.path.join(report_dir, f"{self.fetcher_name}_summary.txt")
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(f"Test Report: {self.fetcher_name}\n")
            f.write(f"{'='*60}\n\n")
            f.write(f"Test Time: {self.results['test_time']}\n")
            f.write(f"Test Query: {self.results['test_query']}\n")
            f.write(f"Status: {self.results['status']}\n\n")
            f.write(f"Results:\n")
            f.write(f"  Papers found: {self.results['papers_found']}\n")
            f.write(f"  Papers with URLs: {self.results['papers_with_urls']}\n")
            f.write(f"  Valid download links: {self.results['valid_download_links']}\n")
            f.write(f"  Invalid download links: {self.results['invalid_download_links']}\n\n")

            if self.results['errors']:
                f.write(f"Errors:\n")
                for error in self.results['errors']:
                    f.write(f"  - {error}\n")
                f.write("\n")

            if self.results['papers']:
                f.write(f"Papers:\n")
                for i, paper in enumerate(self.results['papers'], 1):
                    f.write(f"\n  {i}. {paper['title'][:100]}\n")
                    f.write(f"     Year: {paper['year']}, DOI: {paper['doi']}\n")
                    f.write(f"     URL: {paper['url']}\n")

            if self.results['download_link_checks']:
                f.write(f"\nDownload Link Checks:\n")
                for check in self.results['download_link_checks']:
                    f.write(f"\n  - {check['paper_title'][:80]}\n")
                    f.write(f"    URL: {check['url']}\n")
                    f.write(f"    Status: {check['status']} (Code: {check.get('status_code', 'N/A')})\n")
                    f.write(f"    Accessible: {'✓' if check['accessible'] else '✗'}\n")

        print(f"📄 Summary saved to: {summary_file}")

        return report_file, summary_file


def test_fetcher_by_name(fetcher_name: str, test_query: str = "machine learning", limit: int = 3):
    """Test a fetcher by its module name"""
    try:
        # Import the fetcher module
        fetcher_module = __import__(f"slr.fetchers.{fetcher_name}", fromlist=[fetcher_name])

        # Create tester and run test
        tester = FetcherTester(fetcher_name, test_query)
        results = tester.test_fetcher(fetcher_module, limit=limit)
        tester.save_report()

        return results
    except ImportError as e:
        print(f"✗ Failed to import fetcher '{fetcher_name}': {e}")
        return None
    except Exception as e:
        print(f"✗ Unexpected error testing '{fetcher_name}': {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fetcher_name = sys.argv[1]
        test_query = sys.argv[2] if len(sys.argv) > 2 else "machine learning"
        test_fetcher_by_name(fetcher_name, test_query)
    else:
        print("Usage: python test_framework.py <fetcher_name> [test_query]")
        print("Example: python test_framework.py arxiv 'deep learning'")
