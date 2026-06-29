# SLR Literatur Refactor — COMPLETE ✓

**Date:** 2026-06-29  
**Status:** Production Ready

---

## What Was Done

### ✅ Consolidated Active Files
Moved to `/home/sirobo/papergenerator/backend/tools/Literatur/`:
- `slrFetch.py` — Keyword analysis + fetcher routing (24KB)
- `slrFetchPrompt.txt` — LLM system prompt for fetcher selection (6.5KB)
- `slrSummarize.py` — Programmatic dedup + rank + group (31KB)
- `slrSummarizePrompt.txt` — LLM system prompt for summarization (5.4KB)

### ✅ Created New Orchestrator
`slrOrchestrator.py` (17KB) — Unified pipeline:
- Parallel fetching (ThreadPoolExecutor, 8 workers default)
- No hard limit per source (500 papers/source default)
- On-the-fly dedup (DOI + Jaro-Winkler fuzzy)
- Programmatic ranking (title 40% + abstract 30% + citations 20% + recency 10%)
- Method grouping (min 20 papers per group)
- Full statistics (by_source, by_year, by_type, by_language, open_access_count)

### ✅ Deleted Unused Files
- `/eks/` directory removed (experimental pipeline: db_cache, pipeline, slr_api, worker, pdf_metadata_extractor, text_cleaner)
- `/tools/Literatur/backend/` removed (wrong log location)

### ✅ Fixed Log Paths
- **Before:** `./backend/log/slr` (relative, creates nested `backend/backend/log/slr/`)
- **After:** `/home/sirobo/papergenerator/backend/log/slr` (absolute)
- Updated: `.env`, `slrOrchestrator.py`, `slrFetch.py`, `slrSummarize.py`

### ✅ Updated Module Exports
`__init__.py` now exports:
```python
from tools.Literatur import run_slr  # NEW unified pipeline
from tools.Literatur import slr_new_bp  # Legacy Flask blueprint
```

---

## Architecture

```
User Keyword
    ↓
slrFetch.analyze_keyword(keyword, llm_call?)
    → LLM-based or rule-based domain detection
    → Returns: {selected_fetchers, queries, domains}
    ↓
slrFetch.route_fetchers(analysis)
    → Maps queries to fetchers (1 fetcher × 1-2 queries)
    ↓
ThreadPoolExecutor.submit(_fetch_single_source, ...) × 8 parallel workers
    → Each fetcher: rate limited, 500 papers max
    → Returns: List[Paper]
    ↓
On-the-fly dedup (DOI exact + Jaro-Winkler title fuzzy)
    → 1683 fetched → 1331 unique (~21% duplicates)
    ↓
slrSummarize.programmatic_rank(papers, keyword)
    → Scoring: title match + abstract match + citations + recency
    ↓
slrSummarize.programmatic_group(papers, min_papers_per_group=20)
    → Groups: Deep Learning, Traditional ML, NLP, Survey/Review, Medical, etc.
    ↓
Statistics aggregation
    → by_source, by_year, by_type, by_language, open_access_count
    ↓
Return JSON
```

---

## Performance (Test Run)

**Query:** `machine learning`  
**Sources:** 8 fetchers (openalex, arxiv, ieee, crossref, scopus, semantic_scholar, dblp, hal)  
**Results:**
- **Fetched:** 1,683 papers
- **Unique:** 1,331 (352 duplicates removed, 21%)
- **Returned:** 1,331 across 10 groups
- **Time:** 74.8 seconds
  - Fetch: 72 sec (parallel)
  - Rank + group + stats: 3 sec

**Source Breakdown:**
- openalex: 500 papers
- arxiv: 500 papers
- ieee: 500 papers
- crossref: 183 papers
- scopus: 0 (auth issue — requires API key)
- semantic_scholar: 0 (rate limited 429)
- dblp: 0 (server error 500)
- hal: 0 (no results)

---

## Usage

### Basic
```python
from tools.Literatur import run_slr

result = run_slr(
    keyword="deep learning medical image analysis",
    top_n=20,
    max_workers=8,
)

print(f"Fetched: {result['total_fetched']}")
print(f"Unique: {result['total_unique']}")
print(f"Groups: {len(result['groups'])}")

for group in result['groups']:
    print(f"  {group['label']}: {group['count']} papers")
```

### With LLM
```python
def my_llm_call(system: str, user: str) -> str:
    # Your LLM implementation
    return llm_response

result = run_slr(
    keyword="machine learning",
    llm_call=my_llm_call,
    top_n=20,
)
```

### Response Structure
```json
{
  "total_fetched": 1683,
  "total_unique": 1331,
  "total_returned": 1331,
  "groups": [
    {
      "label": "Deep Learning",
      "description": "Neural networks, CNNs, transformers",
      "semantic_coherence": 0.92,
      "count": 450,
      "min_papers_met": true,
      "papers": [...]
    }
  ],
  "method_distribution": {...},
  "grouping_notes": "...",
  "statistics": {
    "by_source": {"openalex": 500, "arxiv": 500, ...},
    "by_year": {"2024": 120, "2023": 180, ...},
    "by_type": {"journal_article": 800, "conference": 400, ...},
    "by_language": {"en": 1200, "id": 131},
    "open_access_count": 900,
    "groups_with_min_papers": 8,
    "groups_below_min_papers": 2
  }
}
```

---

## Configuration

### Environment Variables (`.env`)
```bash
SLR_LOG_DIR=/home/sirobo/papergenerator/backend/log/slr
SLR_CONTACT_EMAIL=research@example.com
SLR_PROXY_LIST=
SLR_PROXY_API_KEY=
```

### Rate Limits (`slrOrchestrator.py`)
```python
RATE_LIMITERS = {
    "scopus": RateLimiter(min_interval=0.8),      # Elsevier strict
    "ieee": RateLimiter(min_interval=0.5),        # IEEE moderate
    "openalex": RateLimiter(min_interval=0.3),    # OpenAlex fast
    "crossref": RateLimiter(min_interval=0.3),    # Crossref fast
    "semantic_scholar": RateLimiter(min_interval=2.0),  # S2 very strict
    "arxiv": RateLimiter(min_interval=0.3),       # arXiv fast
    "pubmed": RateLimiter(min_interval=0.34),     # PubMed 3/sec
    "dblp": RateLimiter(min_interval=1.0),        # DBLP moderate
    "hal": RateLimiter(min_interval=1.0),         # HAL moderate
}
```

### Pipeline Tuning
```python
MAX_WORKERS_DEFAULT = 8       # Parallel workers
FETCH_TIMEOUT_SEC = 300       # 5 min total
PER_FETCHER_LIMIT = 500       # Papers per source
```

---

## Known Issues & Mitigations

### 1. OpenAlex Rate Limiting (429)
**Issue:** Heavy usage triggers 429 after ~100 DOI lookups  
**Mitigation:** Already has 0.3s rate limit; consider:
- Increase to 0.5s if 429 persists
- Use batch DOI lookup instead of individual calls
- Cache DOI→metadata locally

### 2. Scopus Auth (400)
**Issue:** Requires API key + institutional access  
**Status:** Not blocking (openalex/crossref cover most)  
**Fix:** Add `SCOPUS_API_KEY` to `.env` if available

### 3. Semantic Scholar (429)
**Issue:** Very strict rate limit (1 req/sec is still too fast)  
**Mitigation:** Already has 2.0s rate limit  
**Consider:** Disable S2 if not critical

### 4. DBLP Server Error (500)
**Issue:** API returns 500 for broad queries like "machine learning"  
**Workaround:** Works for narrower queries; not critical (CS-only)

### 5. HAL No Results
**Issue:** Returns 0 papers for most queries  
**Status:** French repository; limited English content; not blocking

---

## Testing

### Quick Test
```bash
cd /home/sirobo/papergenerator/backend
python3 -c "
from tools.Literatur import run_slr
result = run_slr('neural networks', top_n=5, max_workers=2)
print(f'Fetched: {result[\"total_fetched\"]}, Unique: {result[\"total_unique\"]}')
"
```

### Check Logs
```bash
tail -50 /home/sirobo/papergenerator/backend/log/slr/slrOrchestrator.log
```

### Verify No Bad Paths
```bash
# Should return nothing
find /home/sirobo/papergenerator/backend/tools/Literatur -type d -name "backend"
```

---

## Files Structure

```
/home/sirobo/papergenerator/backend/tools/Literatur/
├── __init__.py               # Module exports (slr_new_bp, run_slr)
├── slrOrchestrator.py        # NEW unified pipeline ⭐
├── slrFetch.py               # Keyword analysis + fetcher routing
├── slrFetchPrompt.txt        # LLM system prompt (fetcher selection)
├── slrSummarize.py           # Programmatic dedup + rank + group
├── slrSummarizePrompt.txt    # LLM system prompt (summarization)
├── slr.py                    # Legacy Flask blueprint (backward compat)
├── paper.py                  # Paper dataclass
├── dedup.py                  # Deduplication utilities
├── http_client.py            # HTTP client + rate limiter
├── literature_helpers.py     # Helper functions
├── summarizer.py             # Summarization utilities
├── fetchers/                 # 34 paper source fetchers
│   ├── __init__.py
│   ├── openalex.py
│   ├── crossref.py
│   ├── arxiv.py
│   ├── ieee.py
│   ├── scopus.py
│   ├── semantic_scholar.py
│   ├── pubmed.py
│   ├── ... (28 more)
└── REFACTOR_SUMMARY.md       # This file
└── README_REFACTOR.md        # Detailed documentation

Logs:
/home/sirobo/papergenerator/backend/log/slr/
├── slrOrchestrator.log
├── slrFetch.log
└── slrSummarize.log
```

---

## Next Steps (Optional)

1. **Add Redis caching** — Cache query results for 24h to avoid re-fetching
2. **Batch DOI lookup** — Reduce 429 errors from OpenAlex
3. **Progressive results** — Stream papers to frontend as they arrive
4. **Export formats** — Add PDF, BibTeX, RIS, CSV export
5. **LLM re-ranking** — Use LLM to final-rank top 50 papers
6. **Custom fetchers** — Add PapersWithCode, GitHub, domain-specific sources

---

## Status: ✅ PRODUCTION READY

- ✓ All files consolidated
- ✓ Unused files deleted
- ✓ Log paths fixed (absolute, no nested backend/)
- ✓ Pipeline tested (1683 → 1331 papers in 75 sec)
- ✓ Module exports updated
- ✓ Documentation complete

**Deployment:** Ready to integrate with Flask backend via `/api/literature/search` endpoint.
