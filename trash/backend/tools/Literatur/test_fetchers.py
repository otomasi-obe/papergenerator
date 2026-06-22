#!/usr/bin/env python3
"""Test all fetcher modules to verify abstract handling."""
import os
import sys

# Set up path for module imports
sys.path.insert(0, '/home/sirobo/papergenerator/backend')

import httpx
from tools.Literatur.fetchers.arxiv import search as arxiv_search
from tools.Literatur.fetchers.openalex import search as openalex_search
from tools.Literatur.fetchers.crossref import search as crossref_search
from tools.Literatur.fetchers.ieee import search as ieee_search
from tools.Literatur.fetchers.plos import search as plos_search
from tools.Literatur.fetchers.doaj import search as doaj_search
from tools.Literatur.fetchers.datacite import search as datacite_search
from tools.Literatur.fetchers.zenodo import search as zenodo_search
from tools.Literatur.fetchers.europepmc import search as europepmc_search
from tools.Literatur.fetchers.hal import search as hal_search

client = httpx.Client(timeout=30.0)

def test_fetcher(name, search_fn, query="machine learning", limit=3):
    """Test a fetcher and return success info"""
    try:
        results = list(search_fn(client, query, limit=limit))
        has_abstract = sum(1 for p in results if p.abstract and len(p.abstract) > 80)
        has_title = sum(1 for p in results if p.title)
        return {
            "name": name,
            "total": len(results),
            "has_title": has_title,
            "has_abstract": has_abstract,
            "ok": has_title >= 2 and has_abstract >= 1
        }
    except Exception as e:
        return {"name": name, "error": str(e)[:100], "ok": False}

results = []

# Test each fetcher
tests = [
    ("arxiv", arxiv_search),
    ("openalex", openalex_search),
    ("crossref", crossref_search),
    ("ieee", ieee_search),
    ("plos", plos_search),
    ("doaj", doaj_search),
    ("datacite", datacite_search),
    ("zenodo", zenodo_search),
    ("europepmc", europepmc_search),
    ("hal", hal_search),
]

for name, fn in tests:
    print(f"Testing {name}...")
    r = test_fetcher(name, fn)
    results.append(r)

# Print results
print("\nFETCHER TEST RESULTS")
print("=" * 60)
for r in results:
    if "error" in r:
        print(f"{r['name']}: ERROR - {r['error']}")
    else:
        ok = "✓" if r["ok"] else "✗"
        print(f"{r['name']}: {r['total']} papers, {r['has_title']} with title, {r['has_abstract']} with abstract {ok}")

ok_count = sum(1 for r in results if r.get("ok"))
print("=" * 60)
print(f"PASSED: {ok_count}/{len(results)}")
