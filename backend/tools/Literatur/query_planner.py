"""Query Planner Tool — extract structured query plan from raw research topic.

Input: raw topic string (Indonesian/English)
Output: structured plan with preserved phrases, translated queries, must-have phrases, low-weight terms.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Load environment from root .env
from dotenv import load_dotenv
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_ROOT_ENV, override=False)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Indonesian stopwords / low-weight terms (method/academic words)
# ---------------------------------------------------------------------------
_INDONESIAN_LOW_WEIGHT = frozenset({
    # Academic/method words
    "pemanfaatan", "teknik", "kultur", "penerapan", "kajian", "studi",
    "analisis", "implementasi", "pembangunan", "pengembangan", "penelitian",
    "metode", "metodologi", "pendekatan", "sistem", "model", "perancangan",
    "evaluasi", "validasi", "optimasi", "perbandingan", "tinjauan",
    "survei", "eksplorasi", "investigasi", "eksperimen", "simulasi",
    "pemodelan", "berbasis", "pembuatan", "analisa", "pemantauan",
    "kontrol", "otomatisasi", "pengendalian", "rekomendasi",
    "klasifikasi", "deteksi", "prediksi", "segmentasi", "ekstraksi",
    "identifikasi", "peningkatan", "perbaikan", "efektivitas", "efisiensi",
    "performa", "akurasi", "presisi", "sensitivitas", "spesifisitas",
    "korelasi", "regresi", "klustering", "pengelompokan", "visualisasi",
    "perhitungan", "perancangan", "prototipe", "antarmuka", "arsitektur",
    "framework", "algoritma", "jaringan saraf", "pembelajaran mesin",
    "pembelajaran dalam", "visikom", "pengolahan citra", "pengolahan sinyal",
    "kecerdasan buatan", "data besar", "komputasi awan", "internet hal",
    "realitas maya", "realitas tambahan", "blockchain", "kriptografi",
    "keamanan siber", "jaringan komputer", "sistem tertanam", "robotika",
    "otomatisasi", "manufaktur", "material", "bahan", "sifat",
    "karakterisasi", "sintesis", "karakteristik", "morfologi", "struktur",
    "komposisi", "fase", "kristal", "nanomaterial", "nanoteknologi",
    "bioteknologi", "genetika", "molekuler",
    # Stopwords/prepositions
    "untuk", "dan", "yang", "dengan", "pada", "dalam", "atau", "dari",
    "ke", "di", "ini", "itu", "adalah", "akan", "sudah", "belum",
    "tidak", "bisa", "dapat", "harus", "perlu", "masih", "sangat",
    "lebih", "juga", "hanya", "saja", "lain", "lainnya", "semua",
    "setiap", "beberapa", "banyak", "sedikit", "cukup", "seperti",
    "sebagai", "menjadi", "merupakan", "berhubungan", "berkaitan",
    "mengenai", "terkait", "hubungan", "kaitan",
})

# Must-preserve phrase patterns (multi-word terms that should stay together)
_INDONESIAN_PHRASE_PATTERNS = [
    r"kultur jaringan tumbuhan",   # plant tissue culture (overlap fix)
    r"konservasi tumbuhan langka", # rare plant conservation (overlap fix)
    r"konservasi tanaman langka",  # rare plant conservation (alt)
    r"kultur jaringan",          # tissue culture
    r"jaringan tumbuhan",        # plant tissue
    r"tumbuhan langka",          # rare plants
    r"tanaman langka",           # rare plants (alt)
    r"konservasi tumbuhan",      # plant conservation
    r"konservasi tanaman",       # plant conservation (alt)
    r"in vitro",                 # in vitro
    r"invitro",                  # invitro (typo)
    r"propagasi vegetatif",      # vegetative propagation
    r"mikropropagasi",           # micropropagation
    r"kultur organ",             # organ culture
    r"kultur anther",            # anther culture
    r"kultur embrio",            # embryo culture
    r"somatic embryogenesis",    # somatic embryogenesis
    r"embriogenesis somatik",    # somatic embryogenesis (id)
    r"regenerasi tumbuhan",      # plant regeneration
    r"medium kultur",            # culture medium
    r"medium pertumbuhan",       # growth medium
    r"hormon tumbuhan",          # plant hormone
    r"auksin", "sitokinin", "gibberelin",  # plant hormones
]

# Indonesian research keywords (copied from slrFetch.py)
_INDONESIAN_KEYWORDS = frozenset({
    "indonesia", "indonesian", "nusantara", "jawa", "sumatera", "kalimantan",
    "sulawesi", "papua", "bahasa indonesia", "pancasila", "batik",
    "pendidikan", "kesehatan", "pertanian", "pembangunan", "masyarakat",
    "pemerintah", "kebijakan", "ekonomi indonesia", "umkm",
    "sistem", "berbasis", "penelitian", "analisis", "metode",
    "teknik", "algoritma", "penerapan", "kajian", "studi",
    "rencana", "pemodelan", "implementasi", "pembuatan", "analisa",
})

# Indonesian → English phrase-level translations (must match phrase patterns above)
_ID_TO_EN_PHRASES = {
    "kultur jaringan tumbuhan": "plant tissue culture",
    "konservasi tumbuhan langka": "rare plant conservation",
    "konservasi tanaman langka": "rare plant conservation",
    "kultur jaringan": "plant tissue culture",
    "jaringan tumbuhan": "plant tissue",
    "tumbuhan langka": "rare plants",
    "tanaman langka": "rare plants",
    "konservasi tumbuhan": "plant conservation",
    "konservasi tanaman": "plant conservation",
    "in vitro": "in vitro",
    "invitro": "in vitro",
    "propagasi vegetatif": "vegetative propagation",
    "mikropropagasi": "micropropagation",
    "kultur organ": "organ culture",
    "kultur anther": "anther culture",
    "kultur embrio": "embryo culture",
    "embriogenesis somatik": "somatic embryogenesis",
    "somatic embryogenesis": "somatic embryogenesis",
    "regenerasi tumbuhan": "plant regeneration",
    "medium kultur": "culture medium",
    "medium pertumbuhan": "growth medium",
    "hormon tumbuhan": "plant hormone",
    "auksin": "auxin",
    "sitokinin": "cytokinin",
    "gibberelin": "gibberellin",
    # General academic
    "pemanfaatan teknik": "technique utilization",
    "teknik kultur": "culture technique",
    "kultur jaringan": "tissue culture",
}

# Single-word Indonesian → English (after phrases removed)
_ID_TO_EN_WORDS = {
    "pemanfaatan": "utilization",
    "teknik": "technique",
    "kultur": "culture",
    "jaringan": "network",  # but "kultur jaringan" already handled
    "konservasi": "conservation",
    "tumbuhan": "plant",
    "langka": "rare",
    "penerapan": "application",
    "perubahan": "change",
    "iklim": "climate",
    "pertanian": "agriculture",
    "pengaruh": "impact",
    "tentang": "",
    "terhadap": "",
    "kajian": "study",
    "studi": "study",
    "analisis": "analysis",
    "implementasi": "implementation",
    "pembangunan": "development",
    "pengembangan": "development",
    "penelitian": "research",
    "metode": "method",
    "metodologi": "methodology",
    "pendekatan": "approach",
    "sistem": "system",
    "model": "model",
    "perancangan": "design",
    "evaluasi": "evaluation",
    "validasi": "validation",
    "optimasi": "optimization",
    "perbandingan": "comparison",
    "tinjauan": "review",
    "survei": "survey",
    "eksplorasi": "exploration",
    "investigasi": "investigation",
    "eksperimen": "experiment",
    "simulasi": "simulation",
    "pemodelan": "modeling",
    "berbasis": "based",
    "pembuatan": "fabrication",
    "analisa": "analysis",
    "pemantauan": "monitoring",
    "kontrol": "control",
    "otomatisasi": "automation",
    "pengendalian": "control",
    "rekomendasi": "recommendation",
    "klasifikasi": "classification",
    "deteksi": "detection",
    "prediksi": "prediction",
    "segmentasi": "segmentation",
    "ekstraksi": "extraction",
    "identifikasi": "identification",
    "peningkatan": "improvement",
    "perbaikan": "improvement",
    "efektivitas": "effectiveness",
    "efisiensi": "efficiency",
    "performa": "performance",
    "akurasi": "accuracy",
    "presisi": "precision",
    "sensitivitas": "sensitivity",
    "spesifisitas": "specificity",
    "korelasi": "correlation",
    "regresi": "regression",
    "klustering": "clustering",
    "pengelompokan": "grouping",
    "visualisasi": "visualization",
    "perhitungan": "computation",
    "perancangan": "design",
    "prototipe": "prototype",
    "antarmuka": "interface",
    "arsitektur": "architecture",
    "framework": "framework",
    "algoritma": "algorithm",
    "jaringan saraf": "neural network",
    "pembelajaran mesin": "machine learning",
    "pembelajaran dalam": "deep learning",
    "visikom": "computer vision",
    "pengolahan citra": "image processing",
    "pengolahan sinyal": "signal processing",
    "kecerdasan buatan": "artificial intelligence",
    "data besar": "big data",
    "komputasi awan": "cloud computing",
    "internet hal": "internet of things",
    "realitas maya": "virtual reality",
    "realitas tambahan": "augmented reality",
    "blockchain": "blockchain",
    "kriptografi": "cryptography",
    "keamanan siber": "cybersecurity",
    "jaringan komputer": "computer network",
    "sistem tertanam": "embedded system",
    "robotika": "robotics",
    "otomatisasi": "automation",
    "manufaktur": "manufacturing",
    "material": "material",
    "bahan": "material",
    "sifat": "property",
    "karakterisasi": "characterization",
    "sintesis": "synthesis",
    "karakteristik": "characteristic",
    "morfologi": "morphology",
    "struktur": "structure",
    "komposisi": "composition",
    "fase": "phase",
    "kristal": "crystal",
    "nanomaterial": "nanomaterial",
    "nanoteknologi": "nanotechnology",
    "bioteknologi": "biotechnology",
    "genetika": "genetics",
    "molekuler": "molecular",
}


def _detect_language(text: str) -> str:
    """Simple language detection: 'id', 'en', or 'mixed'."""
    text_lower = text.lower()
    id_count = sum(1 for w in _INDONESIAN_LOW_WEIGHT if w in text_lower)
    en_words = {"the", "and", "for", "with", "from", "this", "that", "are", "was", "have", "has", "been"}
    en_count = sum(1 for w in en_words if w in text_lower)
    # Strong signal if many ID words and NO English words
    if id_count >= 3 and en_count == 0:
        return "id"
    # Strong signal if many EN words and NO Indonesian words
    if en_count >= 3 and id_count == 0:
        return "en"
    # If both present or neither clearly dominant
    return "mixed"


def _extract_phrases(text: str) -> list[str]:
    """Extract known multi-word phrases from text (longest match first, no subsets)."""
    found = []
    text_lower = text.lower()
    # Sort patterns by length descending
    patterns = sorted(_INDONESIAN_PHRASE_PATTERNS, key=len, reverse=True)
    for pat in patterns:
        if re.search(rf"\b{re.escape(pat)}\b", text_lower):
            # Check if this phrase is already covered by a longer found phrase
            covered = False
            for existing in found:
                if pat in existing:
                    covered = True
                    break
            if not covered:
                found.append(pat)
    return found


def _translate_to_english(text: str, phrases_found: list[str]) -> str:
    """Translate Indonesian text to English using phrase-level then word-level dict."""
    result = text.lower()

    # Replace phrases first (longest first)
    for phrase in sorted(phrases_found, key=len, reverse=True):
        en = _ID_TO_EN_PHRASES.get(phrase, phrase)
        if en:
            result = re.sub(rf"\b{re.escape(phrase)}\b", en, result)

    # Then replace individual words (skip words that are part of already-found phrases)
    phrase_words = set()
    for p in phrases_found:
        phrase_words.update(p.split())

    for id_word, en_word in _ID_TO_EN_WORDS.items():
        if not en_word:
            # Stopwords → remove
            result = re.sub(rf"\b{re.escape(id_word)}\b", "", result)
            continue
        # Skip single words that are part of a matched phrase (already handled)
        if id_word in phrase_words:
            continue
        result = re.sub(rf"\b{re.escape(id_word)}\b", en_word, result)

    # Clean up: remove any remaining Indonesian low-weight words
    for w in _INDONESIAN_LOW_WEIGHT:
        result = re.sub(rf"\b{re.escape(w)}\b", "", result)

    # Clean up extra spaces
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _extract_domain_keywords(text: str, phrases_found: list[str]) -> list[str]:
    """Extract domain-specific keywords (not low-weight, not stopwords)."""
    words = re.findall(r"[a-zA-Z]+(?:'[a-zA-Z]+)?", text.lower())
    keywords = []
    for w in words:
        if len(w) < 3:
            continue
        if w in _INDONESIAN_LOW_WEIGHT:
            continue
        # Skip if part of a found phrase
        if any(w in p for p in phrases_found):
            continue
        if w not in keywords:
            keywords.append(w)
    return keywords[:10]  # cap


def _determine_domain(text: str, phrases_found: list[str]) -> list[str]:
    """Determine research domain from text and phrases."""
    domains = []
    text_lower = text.lower()

    # Plant/conservation/biology keywords
    if any(p in text_lower for p in ["kultur jaringan", "tumbuhan", "tanaman", "konservasi", "langka", "in vitro", "propagasi", "mikropropagasi"]):
        domains.extend(["plant science", "conservation biology", "plant tissue culture"])

    # Medical/health
    medical_kw = {"medical", "health", "disease", "patient", "clinical", "hospital", "cancer", "treatment", "therapy"}
    if any(kw in text_lower for kw in medical_kw):
        domains.append("medical")

    # CS/AI
    cs_kw = {"computer", "software", "algorithm", "machine learning", "deep learning", "neural", "ai", "artificial intelligence"}
    if any(kw in text_lower for kw in cs_kw):
        domains.append("computer science")

    # Engineering
    eng_kw = {"engineering", "structural", "mechanical", "electrical", "civil", "chemical"}
    if any(kw in text_lower for kw in eng_kw):
        domains.append("engineering")

    # Indonesian research
    if any(kw in text_lower for kw in _INDONESIAN_KEYWORDS):
        domains.append("indonesia")

    return list(dict.fromkeys(domains)) or ["general"]


def _generate_indonesian_queries(topic: str, phrases_found: list[str], keywords: list[str]) -> list[str]:
    """Generate Indonesian query variants for Sinta."""
    queries = []
    # Primary: main topic as-is
    queries.append(topic.strip())

    # Phrase-focused
    if phrases_found:
        queries.append(" ".join(phrases_found))

    # Phrases + top keywords
    if phrases_found and keywords:
        queries.append(" ".join(phrases_found + keywords[:3]))

    # Keywords only
    if keywords:
        queries.append(" ".join(keywords[:5]))

    return list(dict.fromkeys(queries))  # dedup, preserve order


def _generate_english_queries(topic: str, phrases_found: list[str], keywords: list[str]) -> list[str]:
    """Generate English query variants for international databases."""
    queries = []

    # Translate phrases
    en_phrases = [_ID_TO_EN_PHRASES.get(p, p) for p in phrases_found]
    en_phrases = [p for p in en_phrases if p]

    # Translate keywords
    en_keywords = [_ID_TO_EN_WORDS.get(k, k) for k in keywords]
    en_keywords = [k for k in en_keywords if k]

    # Main query translated
    en_topic = _translate_to_english(topic, phrases_found)
    if en_topic:
        queries.append(f'"{en_topic}"')

    # Phrase-based queries (most important)
    if en_phrases:
        # Exact phrase match
        queries.append(" ".join(f'"{p}"' for p in en_phrases))
        # Phrase + keywords
        if en_keywords:
            queries.append(" ".join(f'"{p}"' for p in en_phrases) + " " + " ".join(en_keywords[:3]))

    # Keyword combinations
    if en_keywords:
        queries.append(" ".join(en_keywords[:5]))
        queries.append(" AND ".join(f'"{k}"' for k in en_keywords[:3]))

    # Specific known good patterns for plant tissue culture
    if "plant tissue culture" in en_phrases:
        if "rare plants" in en_keywords or "rare" in en_keywords or "endangered" in en_keywords:
            queries.append('"plant tissue culture" "rare plants" conservation')
            queries.append('"plant tissue culture" "endangered plants"')
            queries.append('"in vitro propagation" "rare plants"')
            queries.append('"micropropagation" "rare plants" conservation')

    return list(dict.fromkeys(queries))[:8]  # cap at 8


def _generate_must_have_phrases(phrases_found: list[str], keywords: list[str]) -> list[str]:
    """Phrases that a relevant paper MUST mention."""
    must_have = list(phrases_found)
    # Add important single keywords that are domain-specific
    important_kw = [k for k in keywords if k not in _INDONESIAN_LOW_WEIGHT and len(k) > 3]
    must_have.extend(important_kw[:5])
    return must_have


def _generate_low_weight_terms() -> list[str]:
    """Terms that should have low weight in relevance scoring."""
    return sorted(_INDONESIAN_LOW_WEIGHT)


def _run_query_planner(topic: str) -> dict[str, Any]:
    """Main entry point: generate full query plan from raw topic."""
    if not topic or not topic.strip():
        raise ValueError("Topic cannot be empty")

    topic = topic.strip()
    language = _detect_language(topic)
    phrases_found = _extract_phrases(topic)
    keywords = _extract_domain_keywords(topic, phrases_found)
    domain = _determine_domain(topic, phrases_found)

    indonesian_queries = _generate_indonesian_queries(topic, phrases_found, keywords)
    english_queries = _generate_english_queries(topic, phrases_found, keywords)
    must_have = _generate_must_have_phrases(phrases_found, keywords)
    low_weight = _generate_low_weight_terms()

    return {
        "main_topic": topic,
        "detected_language": language,
        "domain": domain,
        "phrases_found": phrases_found,
        "domain_keywords": keywords,
        "indonesian_queries": indonesian_queries,
        "english_queries": english_queries,
        "must_have_phrases": must_have,
        "low_weight_terms": low_weight,
    }


# ── Tool runner for tools_api.py ──────────────────────────────────────────

def run_query_planner_tool(data: Dict[str, Any]) -> Dict[str, Any]:
    """Entry point for tools_api TOOL_RUNNERS.
    Expects data: { text: <topic>, password?: <str> }
    Password check is done in the endpoint; this just runs the planner.
    """
    topic = (data.get("text") or "").strip()
    if not topic:
        raise ValueError("No topic provided")

    plan = _run_query_planner(topic)
    return plan