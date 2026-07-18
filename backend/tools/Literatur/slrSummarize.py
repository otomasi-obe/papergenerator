"""SLR Summarize: dedup → rank → group → structured output.

Main entry points:
  - summarize(papers, query, top_n, llm_call=None) → dict   (LLM-assisted)
  - summarize_fast(papers, query, top_n) → dict              (programmatic only)

Uses normalize_title from dedup.py for title normalization.
Uses rapidfuzz for Jaro-Winkler when available, falls back to difflib.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Optional

# Load environment from root .env
from dotenv import load_dotenv
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_ROOT_ENV, override=False)

log = logging.getLogger(__name__)

# Setup logging directory (absolute path from file location)
_SLR_LOG_DIR_ENV = os.getenv("SLR_LOG_DIR")
if _SLR_LOG_DIR_ENV:
    _LOG_DIR = Path(_SLR_LOG_DIR_ENV)
else:
    # backend/tools/Literatur/slrSummarize.py → backend/log/slr
    _LOG_DIR = Path(__file__).resolve().parent.parent.parent / "log" / "slr"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Configure file handler for slrSummarize
_LOG_FILE = _LOG_DIR / "slrSummarize.log"
_file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
if not any(isinstance(h, logging.FileHandler) for h in log.handlers):
    log.addHandler(_file_handler)
log.info("slrSummarize initialized with logging to %s", _LOG_FILE)

# ── Prompt loader ───────────────────────────────────────────────────────────

_PROMPT_FILE = Path(__file__).parent / "slrSummarizePrompt.txt"


def load_prompt() -> str:
    """Read the system prompt from slrSummarizePrompt.txt."""
    return _PROMPT_FILE.read_text(encoding="utf-8")


# ── Title normalization (import from dedup.py) ────────────────────────────

def _normalize_title(title: str | None) -> str | None:
    """Normalize title for dedup comparison. Reuses dedup.normalize_title."""
    try:
        from tools.Literatur.dedup import normalize_title
        return normalize_title(title)
    except ImportError:
        if not title:
            return None
        t = title.lower().strip()
        t = re.sub(r'[^\w\s-]', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        t = re.sub(r'^the\s+|^a\s+|^an\s+', '', t)
        return t if t else None


def _normalize_doi(doi: str | None) -> str | None:
    """Normalize DOI: lowercase, strip URL prefix."""
    try:
        from tools.Literatur.dedup import normalize_doi
        return normalize_doi(doi)
    except ImportError:
        if not doi or not isinstance(doi, str):
            return None
        doi = doi.strip()
        doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi, flags=re.IGNORECASE)
        doi = doi.strip().lower()
        return doi if doi else None


# ── Fuzzy matching ─────────────────────────────────────────────────────────

def _jaro_winkler_sim(s1: str, s2: str) -> float:
    """Jaro-Winkler similarity: rapidfuzz → difflib fallback."""
    try:
        from rapidfuzz.distance import JaroWinkler
        return JaroWinkler.normalized_similarity(s1, s2)
    except ImportError:
        # difflib fallback — ratio is not Jaro-Winkler but acceptable
        return SequenceMatcher(None, s1, s2).ratio()


# ── Programmatic dedup using dedup.Deduplicator ───────────────────────────

def programmatic_dedup(papers: list[dict]) -> list[dict]:
    """Deduplicate papers using dedup.Deduplicator with ID priority chain.

    Priority: DOI → PMID → PMC → arXiv → S2 → OpenAlex → Crossref → title fuzzy.
    Canonical merge: duplicate sources merged into canonical record.
    """
    try:
        from tools.Literatur.dedup import Deduplicator
        dedup = Deduplicator(auto_dup_threshold=0.95, review_dup_threshold=0.90)

        # Pass full paper dicts — Deduplicator extracts IDs from source/source_id automatically
        paper_data = []
        for idx, paper in enumerate(papers):
            p = dict(paper)  # shallow copy
            p.setdefault("id", p.get("source_id") or f"paper_{idx}")
            paper_data.append(p)

        unique_papers, duplicates = dedup.deduplicate(paper_data)

        # unique_papers already has merged sources from duplicates
        log.info("Dedup: %d → %d unique (removed %d duplicates)",
                 len(papers), len(unique_papers), len(duplicates))
        return unique_papers

    except Exception:
        # Fallback to simple implementation
        return _fallback_dedup(papers)


def _fallback_dedup(papers: list[dict]) -> list[dict]:
    """Simple fallback deduplication using DOI + fuzzy title."""
    seen_dois: dict[str, dict] = {}
    seen_titles: list[tuple[str, dict]] = []  # (normalized, paper)
    unique: list[dict] = []

    for paper in papers:
        doi = _normalize_doi(paper.get("doi"))

        # Stage 1: DOI exact match
        if doi and doi in seen_dois:
            existing = seen_dois[doi]
            if _paper_quality(paper) > _paper_quality(existing):
                unique = [p for p in unique if _normalize_doi(p.get("doi")) != doi]
                seen_dois[doi] = paper
                unique.append(paper)
            log.debug("DOI dup kept: %s", doi)
            continue

        # Stage 2: Fuzzy title match
        title_norm = _normalize_title(paper.get("title"))
        if title_norm:
            threshold = 0.92 if len(title_norm) < 30 else 0.88
            best_match_idx = -1
            best_sim = 0.0
            for idx, (existing_norm, existing_paper) in enumerate(seen_titles):
                if existing_norm == title_norm:
                    best_match_idx = idx
                    best_sim = 1.0
                    break
                sim = _jaro_winkler_sim(title_norm, existing_norm)
                if sim >= threshold and sim > best_sim:
                    best_match_idx = idx
                    best_sim = sim

            if best_match_idx >= 0:
                existing_paper = seen_titles[best_match_idx][1]
                if _paper_quality(paper) > _paper_quality(existing_paper):
                    existing_doi = _normalize_doi(existing_paper.get("doi"))
                    if existing_doi and existing_doi in seen_dois:
                        del seen_dois[existing_doi]
                    unique = [p for p in unique
                              if _normalize_doi(p.get("doi")) != existing_doi
                              and _normalize_title(p.get("title")) != seen_titles[best_match_idx][0]]
                    if doi:
                        seen_dois[doi] = paper
                    seen_titles[best_match_idx] = (title_norm, paper)
                    unique.append(paper)
                log.debug("Title dup (sim=%.3f): %s", best_sim, title_norm[:40])
                continue

        # Not a duplicate — add to tracking
        if doi:
            seen_dois[doi] = paper
        if title_norm:
            seen_titles.append((title_norm, paper))
        unique.append(paper)

    log.info("Dedup: %d → %d unique (%.1f%% removed)",
             len(papers), len(unique),
             (len(papers) - len(unique)) / max(len(papers), 1) * 100)
    return unique


def _paper_quality(paper: dict) -> int:
    """Heuristic quality score for choosing which duplicate to keep."""
    score = 0
    score += paper.get("citations", 0) or 0
    if paper.get("abstract"):
        score += 50
    if paper.get("doi"):
        score += 100
    type_order = {"journal_article": 40, "conference": 30, "book": 20, "preprint": 10}
    score += type_order.get(paper.get("type", ""), 0)
    return score


# ── Programmatic rank ──────────────────────────────────────────────────────

def programmatic_rank(papers: list[dict], query: str) -> list[dict]:
    """Rank papers by relevance to query using BM25 + signals.

    Scoring weights:
      - BM25 title score: 40%
      - BM25 abstract score: 30%
      - Citations (log-normalized 0-1): 20%
      - Recency (2020+ boost): 10%
      - Phrase bonus (exact query phrase in title): +15%
    """
    if not query:
        return papers

    query_words = [w for w in re.findall(r'\w+', query.lower()) if w]
    if not query_words:
        return papers

    query_lower = query.lower()

    # Pre-compute max citations for log-normalization
    max_citations = max((p.get("citations", 0) or 0 for p in papers), default=1)
    if max_citations == 0:
        max_citations = 1
    # Log-scale: log(citations+1) / log(max_citations+1) → prevents single paper dominating
    max_log_cit = math.log(max_citations + 1)

    # ── Build corpus statistics for BM25 (title + abstract) ──────────────
    # Combine title + abstract as document text
    docs = []
    for p in papers:
        title = (p.get("title") or "").lower()
        abstract = (p.get("abstract") or "").lower()
        docs.append(title + " " + abstract)

    # Tokenize all documents
    doc_tokens = [re.findall(r'\w+', d) for d in docs]
    doc_lens = [len(toks) for toks in doc_tokens]
    avg_dl = sum(doc_lens) / len(doc_lens) if doc_lens else 1.0

    # Term frequency per doc + document frequency
    from collections import Counter
    term_doc_freq: Counter[str] = Counter()
    term_freq_per_doc: list[Counter[str]] = []
    for toks in doc_tokens:
        tf = Counter(toks)
        term_freq_per_doc.append(tf)
        term_doc_freq.update(tf.keys())

    N = len(docs)
    # IDF: log((N - df + 0.5) / (df + 0.5) + 1)  (BM25+ variant, never negative)
    idf = {term: math.log((N - df + 0.5) / (df + 0.5) + 1.0) for term, df in term_doc_freq.items()}

    # BM25 params
    k1 = 1.5
    b = 0.75

    def bm25_score(query_terms: list[str], tf: Counter[str], dl: int) -> float:
        score = 0.0
        for term in query_terms:
            if term not in tf:
                continue
            tf_val = tf[term]
            idf_val = idf.get(term, 0.0)
            # BM25 formula: idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
            denom = tf_val + k1 * (1 - b + b * dl / avg_dl)
            score += idf_val * (tf_val * (k1 + 1)) / denom
        return score

    # ── Score each paper ─────────────────────────────────────────────────
    scored: list[tuple[float, dict]] = []
    for i, paper in enumerate(papers):
        title = (paper.get("title") or "").lower()
        abstract = (paper.get("abstract") or "").lower()
        title_words = set(re.findall(r'\w+', title))
        abstract_words = set(re.findall(r'\w+', abstract))

        # BM25 scores (title weight 2x abstract via separate scoring)
        title_tf = Counter(re.findall(r'\w+', title))
        abstract_tf = Counter(re.findall(r'\w+', abstract))
        bm25_title = bm25_score(query_words, title_tf, len(title_tf))
        bm25_abstract = bm25_score(query_words, abstract_tf, len(abstract_tf))

        # Normalize BM25 to 0-1 range (empirical: max BM25 ~3-5)
        norm_bm25_title = min(bm25_title / 5.0, 1.0)
        norm_bm25_abstract = min(bm25_abstract / 5.0, 1.0)

        # Citations (20%): log-normalized to 0-1
        citations = paper.get("citations", 0) or 0
        cit_norm = math.log(citations + 1) / max_log_cit if max_log_cit > 0 else 0

        # Recency (10%): 2020+ gets full score, older gets linear decay
        year = paper.get("year", 0) or 0
        current_year = time.gmtime().tm_year
        if year >= current_year - 5:
            recency = 1.0
        elif year > 0:
            recency = min(1.0, max(0.0, (year - 2000) / (current_year - 5 - 2000)))
        else:
            recency = 0.3  # unknown year → mild default

        # Type prestige bonus (additive small bonus)
        type_bonus = {"journal_article": 0.05, "conference": 0.03, "book": 0.02, "preprint": 0.0}
        prestige = type_bonus.get(paper.get("type", ""), 0.0)

        # Phrase bonus: exact query phrase (>=2 words) in title → +0.15
        phrase_bonus = 0.15 if len(query_words) >= 2 and query_lower in title else 0.0

        score = (norm_bm25_title * 0.40) + (norm_bm25_abstract * 0.30) + (cit_norm * 0.20) + (recency * 0.10) + prestige + phrase_bonus
        paper["relevance_score"] = round(min(score, 1.0), 4)
        scored.append((score, paper))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


# ── Programmatic group ─────────────────────────────────────────────────────

# Keywords for method/theme detection with expanded coverage
_METHOD_KEYWORDS = {
    "Deep Learning": [
        "deep learning", "neural network", "cnn", "convolutional", "transformer",
        "bert", "gpt", "lstm", "rnn", "autoencoder", "gan", "generative",
        "attention mechanism", "resnet", "vgg", "embedding", "fine-tune",
        "deep neural", "deep learning", "transfer learning",
    ],
    "Traditional Machine Learning": [
        "svm", "support vector", "random forest", "decision tree", "knn",
        "k-nearest", "logistic regression", "naive bayes", "ensemble",
        "boosting", "bagging", "xgboost", "gradient boosting",
    ],
    "Statistical Methods": [
        "regression", "correlation", "anova", "chi-square", "t-test",
        "bayesian", "statistical analysis", "hypothesis test", "odds ratio",
        "meta-analysis", "cox", "survival analysis", "factor analysis",
    ],
    "NLP / Text Mining": [
        "nlp", "natural language", "text mining", "sentiment", "topic model",
        "lda", "word2vec", "tokenization", "named entity", "text classification",
        "information extraction", "bow", "bag of words", "tf-idf",
    ],
    "Survey / Review": [
        "survey", "review", "systematic review", "meta-analysis", "overview",
        "bibliometric", "scoping review", "state of the art", "comprehensive review",
    ],
    "Medical / Clinical": [
        "patient", "clinical", "hospital", "diagnosis", "treatment",
        "medical", "health", "disease", "therapy", "surgery",
    ],
    "Engineering": [
        "engineering", "structural", "mechanical", "civil", "electrical",
        "signal processing", "control system", "embedded", "sensor",
    ],
}

_MIN_GROUP_SIZE = 20


def _detect_language_origin(paper: dict) -> str:
    """Detect if paper is Indonesian (id) or English (en) based on text patterns."""
    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract") or "").lower()
    
    id_indicators = {"indonesia", "indonesian", "berbasis", "sistem", "pembangunan", 
                     "penelitian", "analisa", "metode", "penerapan"}
    
    title_id = sum(1 for word in id_indicators if word in title)
    abstract_id = sum(1 for word in id_indicators if word in abstract[:500])
    
    if title_id >= 1 or abstract_id >= 2:
        return "id"
    return "en"


def _extract_method_keywords(paper: dict) -> list[str]:
    """Extract 2-5 method keywords from title + abstract."""
    text = (paper.get("title") or "") + " " + (paper.get("abstract") or "")
    text_lower = text.lower()
    found = []
    for method, kws in _METHOD_KEYWORDS.items():
        for kw in kws:
            if kw in text_lower:
                found.append(kw)
                break  # one keyword per method category
    # Deduplicate and limit
    found = list(dict.fromkeys(found))[:5]
    return found if found else ["general"]


def _assign_method_group(paper: dict) -> str:
    """Assign a paper to a method group based on content."""
    # Books → separate group
    if paper.get("type") == "book":
        return "Reference Books"

    text = (paper.get("title") or "") + " " + (paper.get("abstract") or "")
    text_lower = text.lower()

    best_method = None
    best_count = 0
    for method, kws in _METHOD_KEYWORDS.items():
        count = sum(1 for kw in kws if kw in text_lower)
        if count > best_count:
            best_count = count
            best_method = method

    if best_method and best_count >= 1:
        return best_method

    # Fallback grouping by type
    ptype = paper.get("type", "")
    if ptype == "conference":
        return "Conference Papers"
    if ptype == "preprint":
        return "Preprints"
    return "Other"


def _validate_group_semantic_coherence(papers: list[dict]) -> float:
    """Calculate semantic coherence of a group (0.0-1.0).
    Higher = more tightly related papers."""
    if not papers:
        return 0.0
    
    all_keywords = []
    for p in papers:
        kws = p.get("method_keywords", [])
        all_keywords.extend(kws)
    
    if not all_keywords:
        return 0.5
    
    kw_counts = Counter(all_keywords)
    total_kw = sum(kw_counts.values())
    unique_kw = len(kw_counts)
    
    if total_kw == 0:
        return 0.0
    
    coherence = 1.0 - (unique_kw / total_kw)
    return min(max(coherence, 0.0), 1.0)


def programmatic_group(papers: list[dict], min_group_size: int = _MIN_GROUP_SIZE) -> dict:
    """Group papers by method/theme with minimum 20 papers per group.
    
    Papers with <20 are merged into broader categories or 'Other/Emerging'.
    Returns dict with groups structure and metadata.
    """
    # Add language_origin and method_keywords to each paper
    for paper in papers:
        paper["language_origin"] = _detect_language_origin(paper)
        paper["method_keywords"] = _extract_method_keywords(paper)
    
    # Initial grouping
    groups: dict[str, list[dict]] = {}
    for paper in papers:
        group_label = _assign_method_group(paper)
        if group_label not in groups:
            groups[group_label] = []
        groups[group_label].append(paper)
    
    # Enforce minimum group size: merge small groups
    final_groups: dict[str, list[dict]] = {}
    merged_into_other = []
    
    for label, group_papers in groups.items():
        if len(group_papers) >= min_group_size:
            final_groups[label] = group_papers
        else:
            # Merge into "Other/Emerging" or appropriate broader category
            if label in {"Conference Papers", "Preprints", "Reference Books"}:
                final_groups.setdefault("Other/Emerging", []).extend(group_papers)
            else:
                # Try to merge into most related existing group
                merged = False
                for existing_label, existing_papers in final_groups.items():
                    # Simple similarity: check keyword overlap
                    new_keywords = set()
                    for p in group_papers:
                        new_keywords.update(p.get("method_keywords", []))
                    existing_keywords = set()
                    for p in existing_papers:
                        existing_keywords.update(p.get("method_keywords", []))
                    
                    overlap = len(new_keywords & existing_keywords)
                    if overlap >= 2:
                        existing_papers.extend(group_papers)
                        merged = True
                        break
                
                if not merged:
                    final_groups.setdefault("Other/Emerging", []).extend(group_papers)
    
    # Extract Indonesian papers into separate group if >20
    indonesian_papers = [p for p in papers if p.get("language_origin") == "id"]
    if len(indonesian_papers) >= min_group_size:
        # Remove Indonesian papers from other groups to avoid duplicates
        indonesian_ids = {p.get("source_id") for p in indonesian_papers}
        for label, group_papers in final_groups.items():
            final_groups[label] = [p for p in group_papers if p.get("source_id") not in indonesian_ids]
        final_groups["Indonesian Research"] = indonesian_papers
    
    # Build output structure
    result_groups = []
    total_returned = 0
    groups_with_min = 0
    groups_below_min = 0
    
    for label, group_papers in sorted(final_groups.items(), key=lambda x: -len(x[1])):
        description = _group_description(label)
        coherence = _validate_group_semantic_coherence(group_papers)
        
        # Sort within group by relevance_score descending
        group_papers.sort(key=lambda p: p.get("relevance_score", 0), reverse=True)
        
        result_groups.append({
            "label": label,
            "description": description,
            "semantic_coherence": round(coherence, 3),
            "count": len(group_papers),
            "min_papers_met": len(group_papers) >= min_group_size,
            "papers": group_papers,
        })
        
        total_returned += len(group_papers)
        if len(group_papers) >= min_group_size:
            groups_with_min += 1
        else:
            groups_below_min += 1
    
    grouping_notes = (
        f"Grouping enforced: minimum {min_group_size} papers per group. "
        f"Groups with min met: {groups_with_min}, groups below min: {groups_below_min}. "
        f"Indonesian papers: {len(indonesian_papers)} (>{min_group_size} = separate group)."
    )
    
    return {
        "groups": result_groups,
        "grouping_notes": grouping_notes,
        "groups_with_min_papers": groups_with_min,
        "groups_below_min_papers": groups_below_min,
    }


def _group_description(label: str) -> str:
    """Default description for known group labels."""
    descriptions = {
        "Deep Learning": "Papers using CNN, transformer, LSTM, or other deep neural networks for analysis",
        "Traditional Machine Learning": "Papers using SVM, Random Forest, KNN, and classical ML algorithms",
        "Statistical Methods": "Papers employing statistical tests, regression, or Bayesian approaches",
        "NLP / Text Mining": "Papers focused on natural language processing and text analysis",
        "Survey / Review": "Survey, review, and systematic review papers providing overviews of the field",
        "Medical / Clinical": "Papers focused on medical, clinical, and health-related research",
        "Engineering": "Papers in structural, mechanical, electrical, civil engineering and related fields",
        "Reference Books": "Textbooks and reference works providing foundational knowledge",
        "Conference Papers": "Papers published in conference proceedings",
        "Preprints": "Preprint papers not yet peer-reviewed",
        "Indonesian Research": "Papers from Indonesian researchers and institutions, indexed in Scopus/SINTA",
        "Other/Emerging": "Papers in emerging or niche methodologies not fitting other categories",
        "Other": "Papers not fitting other categories",
    }
    return descriptions.get(label, f"Papers related to {label}")


# ── Statistics builder ──────────────────────────────────────────────────────

def _build_statistics(papers: list[dict]) -> dict:
    """Build statistics summary from paper list."""
    by_source = Counter(p.get("source", "unknown") for p in papers)
    by_year = Counter(str(p.get("year", "unknown")) for p in papers)
    by_type = Counter(p.get("type", "unknown") for p in papers)
    by_language = Counter(p.get("language_origin", "en") for p in papers)
    open_access_count = sum(1 for p in papers if p.get("is_open_access"))

    return {
        "by_source": dict(by_source),
        "by_year": dict(by_year),
        "by_type": dict(by_type),
        "by_language": dict(by_language),
        "open_access_count": open_access_count,
    }


# ── Config ─────────────────────────────────────────────────────────────────

# Cap papers sent to LLM for review to control token cost.
# Programmatic rank filters first, then only top-N get LLM review.
LLM_REVIEW_CAP = int(os.getenv("SLR_LLM_REVIEW_CAP", "75"))

# Abstract truncation length for LLM input (was 800).
LLM_ABSTRACT_MAX_CHARS = int(os.getenv("SLR_LLM_ABSTRACT_MAX_CHARS", "400"))


# ── Main summarize function ────────────────────────────────────────────────

def summarize(
    papers: list[dict],
    query: str,
    top_n: int,
    llm_call: Optional[Callable[[str, str], str]] = None,
) -> dict:
    """Main summarize function: dedup → rank → AI review ALL papers → grouped output.
    
    Pipeline: dedup → rank → assign no → AI review (all papers in batches) → statistics.
    
    Args:
        papers: List of paper dicts from fetchers.
        query: Original search query string.
        top_n: Number of papers the user requested (return top_n in final result).
        llm_call: Optional callable(prompt, user_message) → LLM response string.
                   If provided, reviews ALL papers and assigns new ranking.

    Returns:
        Dict matching the slrSummarizePrompt JSON output schema.
    """
    total_fetched = len(papers)

    # Step 1: Dedup
    unique_papers = programmatic_dedup(papers)
    total_unique = len(unique_papers)

    # Step 2: Rank
    ranked_papers = programmatic_rank(unique_papers, query)

    # Step 3: Assign no (rank order), cap at top_n
    # Only process/return top_n papers as requested by user
    ranked_papers = ranked_papers[:top_n]
    for idx, p in enumerate(ranked_papers, 1):
        p["no"] = idx

    # Step 4: Group (LLM-assisted). If llm_call provided, _llm_group reviews ALL papers
    # and returns them sorted by relevance_score DESC with new_rank assigned.
    # ranked_papers[0]["no"] = original rank (1-based), new_rank assigned by _llm_group.
    if llm_call:
        try:
            grouped = _llm_group(ranked_papers, query, llm_call, top_n=top_n)
            # _llm_group already sorted papers by relevance_score and assigned new_rank.
            # Use its returned papers (sorted by AI relevance) for the final result.
            ranked_papers = ranked_papers  # keep original for stats
        except Exception as e:
            log.warning("LLM grouping failed (%s), falling back to programmatic", e)
            grouped = programmatic_group(ranked_papers, min_group_size=_MIN_GROUP_SIZE)
    else:
        grouped = programmatic_group(ranked_papers, min_group_size=_MIN_GROUP_SIZE)

    # Step 5: Build statistics with language detection
    stats = _build_statistics(ranked_papers)
    stats["groups_with_min_papers"] = grouped.get("groups_with_min_papers", 0)
    stats["groups_below_min_papers"] = grouped.get("groups_below_min_papers", 0)
    
    # If LLM reviewed, use the reviewed papers from grouped (they have new_rank + review).
    # Flatten ALL groups (programmatic fallback produces multiple groups; the LLM
    # path already wraps every reviewed paper in a single group). Taking only
    # groups[0] previously dropped every paper outside the first group.
    reviewed_papers = [
        p for g in (grouped.get("groups") or [])
        for p in g.get("papers", [])
    ][:top_n]  # cap at user-requested count

    method_dist = {g["label"]: g["count"] for g in grouped["groups"]}

    # Build raw_papers: original paper data before AI review (used for display)
    # Preserve order from ranked_papers (relevance-sorted), cap at top_n
    paper_no_map = {p.get("no"): p for p in ranked_papers}
    raw_papers = []
    for p in ranked_papers[:top_n]:
        no = p.get("no")
        raw_papers.append({
            "no": no,
            "title": p.get("title", "Untitled"),
            "year": p.get("year"),
            "citations": p.get("citations", 0) or 0,
            "abstract": p.get("abstract") or "",
            "source": p.get("source", ""),
            "doi": p.get("doi") or "",
            "url": p.get("url") or "",
        })

    return {
        "total_fetched": total_fetched,
        "total_unique": total_unique,
        "total_returned": len(reviewed_papers) if reviewed_papers else len(ranked_papers),
        "raw_papers": raw_papers,         # raw fetcher data: no, title, year, citations, abstract, source
        "reviewed_papers": reviewed_papers,  # AI-reviewed papers with new_rank/no, review, relevance_score
        "groups": grouped["groups"],
        "method_distribution": method_dist,
        "grouping_notes": grouped.get("grouping_notes", ""),
        "statistics": stats,
    }


def _llm_group(
    papers: list[dict],
    query: str,
    llm_call: Callable[[str, str], str],
    top_n: int = 20,
) -> dict:
    """Use LLM to review top papers by programmatic rank, skip rest to save tokens.

    Only the top LLM_REVIEW_CAP papers (sorted by programmatic relevance_score)
    are sent to the LLM. Papers beyond the cap keep their programmatic rank
    but get no AI review text — they still appear in results.

    Abstracts are truncated to LLM_ABSTRACT_MAX_CHARS to further reduce tokens.
    """
    total_all = len(papers)

    # ponytail: hard cap on LLM-reviewed papers. Raise SLR_LLM_REVIEW_CAP env if needed.
    llm_papers = papers[:top_n]  # review only what user requested
    skipped = total_all - len(llm_papers)
    log.info("=== _llm_group START: %d papers total, %d sent to LLM (top_n=%d, skipped=%d) for query '%s' ===",
             total_all, len(llm_papers), top_n, skipped, query[:80])

    prompt = load_prompt()
    log.info("Prompt loaded: %d chars", len(prompt))

    BATCH_SIZE = 50
    all_reviewed = []
    total_batches = (len(llm_papers) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(llm_papers))
        batch = llm_papers[start:end]
        log.info("Batch %d/%d: papers %d-%d", batch_idx + 1, total_batches, start + 1, end)

        # Sort batch by relevance_score DESC for best ordering
        batch_sorted = sorted(
            batch,
            key=lambda x: x.get("relevance_score", 0),
            reverse=True,
        )

        compact = []
        for p in batch_sorted:
            abstract = p.get("abstract") or ""
            if len(abstract) > LLM_ABSTRACT_MAX_CHARS:
                abstract = abstract[:LLM_ABSTRACT_MAX_CHARS] + "..."
            compact.append({
                "no_urut_awal": p.get("no", papers.index(p) + 1),
                "title": p.get("title", "Untitled"),
                "abstract": abstract,
            })

        user_msg = json.dumps({
            "query": query,
            "papers": compact,
        }, ensure_ascii=False)

        # Retry LLM call up to 2 times on failure
        response = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                log.info("LLM call attempt %d/%d for batch %d...", attempt + 1, 3, batch_idx + 1)
                response = llm_call(prompt, user_msg)
                log.info("LLM response received: %d chars", len(response))
                break
            except Exception as e:
                last_error = e
                log.warning("LLM call attempt %d/%d failed: %s", attempt + 1, 3, e)
                if attempt < 2:
                    import time
                    time.sleep(2)
        else:
            log.warning("ALL LLM attempts failed for batch %d: %s", batch_idx + 1, last_error)
            continue  # skip this batch, try next

        # Parse JSON response
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r'^```(?:json)?\s*', '', response)
            response = re.sub(r'\s*```$', '', response)
            response = response.strip()

        if not response:
            log.warning("LLM returned empty response for batch %d", batch_idx + 1)
            continue

        decoder = json.JSONDecoder()
        clean_response = response
        first_brace = clean_response.find('{')
        if first_brace > 5:
            clean_response = clean_response[first_brace:]

        try:
            parsed, end_pos = decoder.raw_decode(clean_response)
        except json.JSONDecodeError as e:
            log.warning("Batch %d JSON parse failed: %s at pos %d", batch_idx + 1, e.msg, e.pos)
            if e.pos > 100:
                truncated = clean_response[:e.pos]
                last_brace = truncated.rfind('}')
                if last_brace > 0:
                    truncated = truncated[:last_brace + 1]
                    try:
                        parsed, _ = json.JSONDecoder().raw_decode(truncated)
                    except (json.JSONDecodeError, ValueError):
                        continue
                else:
                    continue
            else:
                continue

        if "papers" not in parsed:
            log.warning("Batch %d response missing 'papers' key", batch_idx + 1)
            continue

        # Build review map: no_urut_awal → {review, no_urut_baru}
        for rp in parsed.get("papers", []):
            if not isinstance(rp, dict):
                continue
            no = rp.get("no_urut_awal", rp.get("no"))
            if no is None:
                continue
            all_reviewed.append({
                "no": no,
                "review": (rp.get("review") or "")[:2000],
                "no_urut_baru": rp.get("no_urut_baru", rp.get("new_no")),
                "relevance": rp.get("relevance"),
            })

    log.info("Total reviewed: %d papers across %d batches", len(all_reviewed), total_batches)

    # Build review_map: no → review data
    review_map = {r["no"]: r for r in all_reviewed}

    def _ai_rank_value(p: dict) -> int:
        rev = review_map.get(p.get("no"), {})
        try:
            value = int(rev.get("no_urut_baru"))
        except (TypeError, ValueError):
            value = 10**9
        return value if value > 0 else 10**9

    # Apply reviews + AI order back to papers, cap at top_n
    reviewed_papers = []
    for p in papers[:top_n]:  # only return top_n papers
        no = p.get("no")
        rev = review_map.get(no, {})
        reviewed_papers.append({
            **p,
            "review": rev.get("review", ""),
            "no_urut_awal": no,
            "no_urut_baru": rev.get("no_urut_baru"),
            "relevance_score": rev.get("relevance") or p.get("relevance_score", 0),
        })

    # Sort by AI-provided no_urut_baru; fall back to programmatic relevance.
    reviewed_papers.sort(
        key=lambda x: (_ai_rank_value(x), -(x.get("relevance_score", 0) or 0)),
    )

    total_reviewed = len(reviewed_papers)
    for rank, p in enumerate(reviewed_papers, 1):
        p["new_rank"] = rank
        p["new_no"] = rank
        p["no_urut_baru"] = rank
        p["relevance_score"] = total_reviewed - rank + 1

    result_groups = {
        "groups": [{
            "label": "Literature Review",
            "description": f"AI-reviewed papers for query: {query}. Only top {top_n} papers have new_rank.",
            "count": len(reviewed_papers),
            "papers": reviewed_papers,
        }],
        "grouping_notes": f"AI-reviewed {len(reviewed_papers)} papers for '{query}', assigning new_no for top {top_n} papers",
    }
    log.info("=== _llm_group DONE: %d papers with review+relevance, top_n=%d ===", len(reviewed_papers), top_n)
    return result_groups


# ── Fast fallback (no LLM) ─────────────────────────────────────────────────

def summarize_fast(papers: list[dict], query: str, top_n: int) -> dict:
    """Programmatic-only summarize. No LLM needed.

    Same pipeline as summarize() but always uses programmatic grouping.
    """
    return summarize(papers, query, top_n, llm_call=None)


# ── Self-test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Test data
    test_papers = [
        {
            "source": "arxiv", "source_id": "2301.001",
            "title": "Deep Learning for Image Classification",
            "authors": ["Alice Smith", "Bob Jones"],
            "year": 2024, "doi": "10.1000/dl-img",
            "url": "https://doi.org/10.1000/dl-img",
            "pdf_url": None, "abstract": "We propose a CNN-based approach for image classification using transformers.",
            "venue": "Nature Methods", "publisher": "Springer",
            "type": "journal_article", "is_open_access": True,
            "citations": 120, "relevance_score": 0.85,
        },
        {
            "source": "pubmed", "source_id": "PM001",
            "title": "Deep Learning for Image Classification",  # Dup (same title)
            "authors": ["Alice Smith", "Bob Jones"],
            "year": 2024, "doi": "10.1000/dl-img",  # Same DOI → dup
            "url": "https://doi.org/10.1000/dl-img",
            "pdf_url": None, "abstract": "Short abstract.",
            "venue": None, "publisher": None,
            "type": "preprint", "is_open_access": False,
            "citations": 50, "relevance_score": 0.70,
        },
        {
            "source": "crossref", "source_id": "CR002",
            "title": "SVM-Based Text Classification",
            "authors": ["Carol Lee"],
            "year": 2022, "doi": "10.2000/svm-txt",
            "url": "https://doi.org/10.2000/svm-txt",
            "pdf_url": "https://pdfs.example.com/002.pdf",
            "abstract": "We use SVM and random forest for text classification tasks.",
            "venue": "JMLR", "publisher": "MIT Press",
            "type": "journal_article", "is_open_access": True,
            "citations": 80, "relevance_score": 0.75,
        },
        {
            "source": "google_books", "source_id": "GB003",
            "title": "Introduction to Machine Learning",
            "authors": ["David Brown"],
            "year": 2019, "doi": None,
            "url": "https://books.google.com/...",
            "pdf_url": None, "abstract": "A comprehensive textbook covering ML fundamentals.",
            "venue": None, "publisher": "OUP",
            "type": "book", "is_open_access": False,
            "citations": 300, "relevance_score": 0.60,
        },
        {
            "source": "semantic_scholar", "source_id": "SS004",
            "title": "Survey of Deep Learning Methods for NLP",
            "authors": ["Eve Wilson"],
            "year": 2023, "doi": "10.3000/survey-nlp",
            "url": "https://doi.org/10.3000/survey-nlp",
            "pdf_url": None, "abstract": "A systematic survey of deep learning approaches in NLP including BERT and transformers.",
            "venue": "ACL Proceedings", "publisher": "ACL",
            "type": "conference", "is_open_access": True,
            "citations": 200, "relevance_score": 0.90,
        },
    ]

    print("=== Test: programmatic_dedup ===")
    unique = programmatic_dedup(test_papers)
    print(f"  Input: {len(test_papers)}, Unique: {len(unique)}")
    assert len(unique) < len(test_papers), "Should remove some duplicates"
    assert len(unique) >= 3, "Should keep at least 3 unique papers"

    print("=== Test: programmatic_rank ===")
    ranked = programmatic_rank(unique, "deep learning image classification")
    print(f"  Ranked {len(ranked)} papers")
    for p in ranked:
        print(f"    {p.get('relevance_score', 0):.3f} - {p['title'][:40]}")

    print("=== Test: programmatic_group ===")
    grouped = programmatic_group(ranked)
    for g in grouped["groups"]:
        print(f"  {g['label']} ({g['count']} papers)")

    print("=== Test: summarize_fast ===")
    result = summarize_fast(test_papers, "deep learning image classification", top_n=5)
    print(f"  total_fetched: {result['total_fetched']}")
    print(f"  total_unique: {result['total_unique']}")
    print(f"  total_returned: {result['total_returned']}")
    print(f"  method_distribution: {result['method_distribution']}")
    print(f"  statistics: {result['statistics']}")

    # Test load_prompt
    prompt = load_prompt()
    assert len(prompt) > 100, "Prompt should be non-trivial"
    print(f"\n=== load_prompt: {len(prompt)} chars ===")

    print("\n✓ All slrSummarize tests passed")
