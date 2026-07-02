# PaperGenerator Fetcher Test Results
**Date:** 2026-06-30  
**Test Coverage:** 35 fetchers × 5 domains = 175 tests  
**Timeout:** 20s per test  
**Total Papers Retrieved:** 343

---

## Executive Summary

| Metric | Count |
|--------|-------|
| **Working Fetchers** | 16/35 (46%) |
| **Successful Tests** | 72/175 (41%) |
| **Empty Results** | 92/175 (53%) |
| **Errors/Timeouts** | 11/175 (6%) |
| **Total Papers** | 343 |

---

## Top Performers (by total papers)

| Rank | Fetcher | Papers | Avg Time | Domains Covered |
|------|---------|--------|----------|-----------------|
| 1 | **arxiv** | 25 | 0.1s | 5/5 ✓✓✓✓✓ |
| 2 | **cambridge** | 25 | 2.2s | 5/5 ✓✓✓✓✓ |
| 3 | **crossref** | 25 | 5.8s | 5/5 ✓✓✓✓✓ |
| 4 | **datacite** | 25 | 1.3s | 5/5 ✓✓✓✓✓ |
| 5 | **openalex** | 25 | 2.0s | 5/5 ✓✓✓✓✓ |
| 6 | **orcid** | 25 | 3.0s | 5/5 ✓✓✓✓✓ |
| 7 | **pmc** | 25 | 3.4s | 5/5 ✓✓✓✓✓ |
| 8 | **scopus** | 25 | 0.7s | 5/5 ✓✓✓✓✓ (requires API key) |
| 9 | **zenodo** | 25 | 1.7s | 5/5 ✓✓✓✓✓ |
| 10 | **ieee** | 22 | 10.9s | 5/5 (2–5 papers/domain) |
| 11 | **openaire** | 21 | 2.2s | 5/5 (1–5 papers/domain) |
| 12 | **web** | 21 | 10.7s | 5/5 DuckDuckGo discovery |
| 13 | **pubmed** | 20 | 1.3s | 4/5 (no Economics) |
| 14 | **core** | 20 | 1.7s | 4/5 (Education 403 error) |
| 15 | **open_library** | 8 | 1.8s | 3/5 |
| 16 | **sinta** | 5 | 0.9s | 1/5 (Education only) |

---

## Category Breakdown

### ✓ **TIER 1: Stable & Fast (<3s average)**
- **arxiv** — 0.1s, CS/Physics/Math preprints, 25 papers
- **scopus** — 0.7s, requires ELSEVIER_API_KEY, 25 papers
- **datacite** — 1.3s, datasets & grey literature, 25 papers
- **pubmed** — 1.3s, medical/life sciences, 20 papers
- **zenodo** — 1.7s, open research repository, 25 papers
- **core** — 1.7s, requires CORE_API_KEY, 20 papers (1 failure)
- **openalex** — 2.0s, multidisciplinary, 25 papers
- **cambridge** — 2.2s, HTML scrape, 25 papers
- **openaire** — 2.2s, EU research, 21 papers
- **orcid** — 3.0s, author works, 25 papers

### ✓ **TIER 2: Working but Slower (3–15s)**
- **pmc** — 3.4s, PubMed Central full-text, 25 papers
- **crossref** — 5.8s, DOI registry, 25 papers (OpenAlex enrichment disabled)
- **web** — 10.7s, DuckDuckGo + scraping, 21 papers
- **ieee** — 10.9s, engineering/CS, 22 papers

### ⚠ **TIER 3: Rate-Limited (needs proxy or API key)**
- **semantic_scholar** — 0 papers, 429 errors (7s timeouts)
- **google_books** — 0 papers, 429 errors (9s retries)

### ✗ **TIER 4: Broken / Timeout**
- **doaj** — 5/5 timeouts (20s each)
- **oapen** — 5/5 timeouts (20s each), 1 paper before timeout
- **dblp** — 4/5 empty (500 errors), 1 timeout
- **biorxiv** — 5/5 empty (4.5s avg)
- **europepmc** — 5/5 empty (1.4s avg, API changed?)
- **hal** — 5/5 empty (1.1s avg)
- **plos** — 5/5 empty (1.2s avg)
- **unpaywall** — 5/5 empty (9.3s avg, 422 errors on book DOIs)

### — **TIER 5: No API Key / Disabled**
- **clinicalkey** — requires ELSEVIER_API_KEY (ClinicalKey entitlement)
- **dimensions** — requires DIMENSIONS_API_KEY
- **embase** — requires ELSEVIER_API_KEY + IP whitelist/insttoken
- **lens** — requires LENS_API_KEY
- **opencitations** — deprecated API endpoint
- **sciencedirect** — requires ELSEVIER_API_KEY (ScienceDirect entitlement)
- **wos** — requires WOS_API_KEY

### — **TIER 6: Book Fetchers (academic queries = empty)**
- **doab** — 0 papers (OA books, academic queries not books)
- **gutendex** — 0 papers (Project Gutenberg, literature only)
- **open_library** — 8 papers (3/5 domains, Education strongest)

---

## Domain Coverage

| Domain | Total Papers | Working Fetchers |
|--------|--------------|------------------|
| **Education** | 75 | 15 |
| **Environment** | 71 | 16 |
| **AI/ML** | 70 | 14 |
| **Medical** | 67 | 14 |
| **Economics** | 60 | 14 |

**Best Environment coverage:** open_library, web discovered marine papers  
**Worst Economics coverage:** pubmed (0), medical fetchers empty

---

## Speed Rankings (working fetchers only)

| Fetcher | Avg Time | Note |
|---------|----------|------|
| arxiv | 0.1s | ⚡ Fastest |
| scopus | 0.7s | API key required |
| sinta | 0.9s | Indonesian only, 1 domain |
| datacite | 1.3s | — |
| pubmed | 1.3s | — |
| core | 1.7s | API key required |
| zenodo | 1.7s | — |
| open_library | 1.8s | Books, 3/5 domains |
| openalex | 2.0s | — |
| cambridge | 2.2s | HTML scrape |
| openaire | 2.2s | — |
| orcid | 3.0s | Author works |
| pmc | 3.4s | Full-text medical |
| crossref | 5.8s | DOI registry |
| web | 10.7s | DuckDuckGo discovery |
| ieee | 10.9s | 🐌 Slowest working |

---

## Key Findings

### ✅ Strengths
1. **16 working fetchers** without proxy (up from 12 in previous test)
2. **9 fetchers** return 25/25 papers (100% success rate)
3. **Fast retrieval**: 10 fetchers average <3s
4. **Broad coverage**: Every domain has 14–16 working sources
5. **New `web` fetcher** adds DuckDuckGo discovery (21 papers across all domains)

### ⚠ Issues Fixed Since Last Test
- **openaire** now working (21 papers, was "deprecated v1 API")
- **open_library** now working (8 papers, Education strong)
- **web** fetcher added (DuckDuckGo + landing page scrape)

### ❌ Persistent Issues
1. **Rate limits** without proxy:
   - semantic_scholar: 429 (needs S2_API_KEY or proxy)
   - google_books: 429 (needs proxy)
   - openalex: working now (no longer rate-limited!)

2. **Timeouts** (>20s):
   - doaj: 100% timeout (API slow/broken)
   - oapen: 100% timeout (OAI-PMH slow)
   - dblp: 1 timeout, 4× 500 errors

3. **API changes** (empty but fast):
   - europepmc: 200 OK but no results
   - biorxiv: empty results (preprint API changed?)
   - hal: empty results
   - plos: empty results
   - unpaywall: 422 errors on book DOIs

4. **Entitlement-locked** (Elsevier):
   - sciencedirect: 401 (needs SD entitlement)
   - embase: 403 (needs IP whitelist)
   - clinicalkey: 404 (endpoint doesn't exist for general keys)

### 🔧 Recommended Actions
1. **Enable proxy rotation** for semantic_scholar + google_books → +2 fetchers
2. **Investigate europepmc** API (returns 200 but empty)
3. **Disable doaj, oapen** from default selection (timeouts)
4. **Add S2_API_KEY** if available → semantic_scholar unlimited
5. **Skip book fetchers** for paper queries (doab, gutendex)

---

## Query Effectiveness

### AI/ML Query
**"transformer attention mechanism deep learning"**  
✓ Best: arxiv, scopus, ieee, openalex, crossref  
✗ Worst: sinta, biorxiv, plos, book fetchers

### Medical Query
**"mRNA vaccine cancer immunotherapy"**  
✓ Best: pubmed, pmc, arxiv, scopus, openalex  
✗ Worst: ieee (2 papers only), sinta, book fetchers

### Environment Query
**"microplastic pollution marine ecosystem"**  
✓ Best: All 16 working fetchers returned results  
⭐ open_library found 2 environment books

### Education Query
**"project based learning STEM education"**  
✓ Best: sinta (Indonesian), open_library (5 books), all major fetchers  
✗ Worst: core (403 error on this query only)

### Economics Query
**"monetary policy inflation central bank digital currency"**  
✓ Best: crossref, scopus, openalex, cambridge  
✗ Worst: pubmed (0 — medical focus), sinta

---

## Comparison to Skill Documentation

| Skill Status | Actual Test | Delta |
|--------------|-------------|-------|
| Stable (8) | **16 working** | +8 🎉 |
| Rate-limited (4) | **2 rate-limited** | -2 (openalex fixed) |
| Broken (3) | **11 broken/timeout** | +8 ⚠ |

**New discoveries:**
- openaire WORKS (was listed as broken)
- open_library WORKS (books)
- web fetcher WORKS (new, not in skill)
- doaj/oapen now TIMEOUT (slow APIs)
- dblp mostly broken (500 errors)
- europepmc/hal/plos/biorxiv empty (API changes)

---

## Test Queries Used

```python
QUERIES = {
    "AI/ML": "transformer attention mechanism deep learning",
    "Medical": "mRNA vaccine cancer immunotherapy",
    "Environment": "microplastic pollution marine ecosystem",
    "Education": "project based learning STEM education",
    "Economics": "monetary policy inflation central bank digital currency",
}
```

---

## Files Generated
- `test_results.json` — Full 343-paper dataset with metadata
- `test_summary.csv` — 175 rows, all fetcher×domain combinations
- `RESULTS_SUMMARY.md` — This file
