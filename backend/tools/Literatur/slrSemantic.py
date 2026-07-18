"""SBERT Semantic Ranking for SLR — optional enhancement over BM25.

This module provides semantic similarity scoring using sentence-transformers (SBERT).
It's designed to be optional: if sentence-transformers is not installed, it gracefully
falls back to BM25-only ranking.

Usage:
    from tools.Literatur.slrSemantic import semantic_rank
    
    ranked_papers = semantic_rank(papers, query, weight=0.4)
    
    # Or use directly with a model:
    from tools.Literatur.slrSemantic import SBertRanker
    ranker = SBertRanker()
    ranked = ranker.rank(papers, query)
"""

from __future__ import annotations

import logging
import math
from typing import Optional

log = logging.getLogger(__name__)

# Global model cache
_MODEL: Optional[object] = None
_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # Supports Indonesian + English


def _load_model():
    """Lazy-load the SBERT model."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    
    try:
        from sentence_transformers import SentenceTransformer
        log.info("Loading SBERT model: %s", _MODEL_NAME)
        _MODEL = SentenceTransformer(_MODEL_NAME)
        log.info("SBERT model loaded successfully")
    except ImportError:
        log.warning("sentence-transformers not installed. Run: pip install sentence-transformers")
        return None
    except Exception as exc:
        log.error("Failed to load SBERT model: %s", exc)
        return None
    
    return _MODEL


def _encode_texts(texts: list[str]) -> Optional[list[list[float]]]:
    """Encode list of texts to embeddings."""
    model = _load_model()
    if model is None:
        return None
    
    try:
        embeddings = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,  # Unit vectors for cosine similarity
        )
        return embeddings.tolist()
    except Exception as exc:
        log.error("SBERT encoding failed: %s", exc)
        return None


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two unit vectors."""
    return sum(a * b for a, b in zip(vec1, vec2))


def _get_paper_text(paper: dict) -> str:
    """Extract searchable text from paper (title + abstract)."""
    title = paper.get("title", "") or ""
    abstract = paper.get("abstract", "") or ""
    # Limit abstract length to avoid token limits
    if len(abstract) > 500:
        abstract = abstract[:500]
    return f"{title}. {abstract}"


def semantic_rank(
    papers: list[dict],
    query: str,
    weight: float = 0.4,
    batch_size: int = 64,
) -> list[dict]:
    """Combine BM25 score with SBERT semantic similarity.
    
    Args:
        papers: List of paper dicts (must have 'relevance_score' from BM25)
        query: Search query string
        weight: Weight for semantic score (0.0-1.0). 
                Final score = (1-weight)*BM25 + weight*Semantic
                Default 0.4 = 60% BM25, 40% Semantic
        batch_size: Batch size for encoding
    
    Returns:
        Papers sorted by combined score (descending)
    """
    if not papers or not query:
        return papers
    
    # Validate weight
    weight = max(0.0, min(1.0, weight))
    if weight == 0.0:
        return papers
    
    model = _load_model()
    if model is None:
        log.debug("SBERT model not available, returning BM25-only ranking")
        return papers
    
    try:
        # Prepare texts
        paper_texts = [_get_paper_text(p) for p in papers]
        
        # Encode query + papers
        log.debug("Encoding %d papers + query with SBERT", len(papers))
        query_emb = model.encode([query], normalize_embeddings=True)[0]
        paper_embs = model.encode(
            paper_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        
        # Compute semantic similarities
        for i, paper in enumerate(papers):
            sem_score = float(paper_embs[i] @ query_emb)  # Cosine similarity (unit vectors)
            # Ensure BM25 score exists
            bm25_score = paper.get("relevance_score", 0.0)
            # Combine: weighted average
            combined = (1.0 - weight) * bm25_score + weight * sem_score
            paper["relevance_score"] = round(combined, 4)
            paper["semantic_score"] = round(sem_score, 4)
            paper["bm25_score"] = round(bm25_score, 4)
        
        # Re-sort by combined score
        papers.sort(key=lambda p: p.get("relevance_score", 0.0), reverse=True)
        
        log.info("SBERT semantic ranking complete: %d papers re-ranked", len(papers))
        return papers
        
    except Exception as exc:
        log.error("Semantic ranking failed: %s", exc)
        return papers


class SBertRanker:
    """Reusable SBERT ranker for multiple queries."""
    
    def __init__(self, model_name: str = _MODEL_NAME):
        global _MODEL_NAME
        _MODEL_NAME = model_name
        _load_model()
    
    def rank(self, papers: list[dict], query: str, weight: float = 0.4) -> list[dict]:
        """Rank papers using combined BM25 + semantic score."""
        return semantic_rank(papers, query, weight)
    
    def encode(self, texts: list[str]) -> Optional[list[list[float]]]:
        """Encode texts to embeddings."""
        return _encode_texts(texts)
    
    def similarity(self, query: str, texts: list[str]) -> list[float]:
        """Compute similarity between query and texts."""
        model = _load_model()
        if model is None:
            return [0.0] * len(texts)
        
        query_emb = model.encode([query], normalize_embeddings=True)[0]
        text_embs = model.encode(texts, normalize_embeddings=True)
        
        return [float(text_embs[i] @ query_emb) for i in range(len(texts))]


def is_available() -> bool:
    """Check if SBERT is available."""
    return _load_model() is not None


# Convenience function for testing
def test_semantic_rank():
    """Test semantic ranking with sample papers."""
    sample_papers = [
        {
            "title": "Deep Learning for Medical Image Analysis",
            "abstract": "We propose a CNN-based approach for classifying lung nodules in CT scans...",
            "relevance_score": 0.85,
        },
        {
            "title": "Neural Networks in Healthcare Applications",
            "abstract": "A survey of deep learning methods applied to medical diagnosis...",
            "relevance_score": 0.72,
        },
        {
            "title": "Traditional Machine Learning for Image Classification",
            "abstract": "Comparing SVM and Random Forest for medical image classification...",
            "relevance_score": 0.65,
        },
    ]
    
    query = "deep learning medical imaging"
    ranked = semantic_rank(sample_papers, query, weight=0.4)
    
    print(f"Query: {query}")
    for i, p in enumerate(ranked, 1):
        print(f"  {i}. {p['title'][:60]}...")
        print(f"      BM25: {p.get('bm25_score', 'N/A'):.3f}, "
              f"Semantic: {p.get('semantic_score', 'N/A'):.3f}, "
              f"Combined: {p['relevance_score']:.3f}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_semantic_rank()