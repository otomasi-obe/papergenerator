"""SLR fetcher router — LLM-assisted source selection with keyword fallback.

Usage::

    from tools.Literatur.slrFetch import analyze_keyword, route_fetchers, guess_fetchers

    # With LLM
    analysis = analyze_keyword("deep learning for medical image analysis", llm_call=my_llm)
    fetch_map = route_fetchers(analysis)
    # → {"openalex": ["deep learning medical image analysis"], "pubmed": ["..."], ...}

    # Without LLM (keyword matching fallback)
    fetch_map = guess_fetchers("deep learning for medical image analysis")
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Callable, Optional

# Load environment from root .env
from dotenv import load_dotenv
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_ROOT_ENV, override=False)

from tools.Literatur.fetchers import ALL, SOURCE_TOPICS

log = logging.getLogger(__name__)

# Setup logging directory (absolute path from file location)
_SLR_LOG_DIR_ENV = os.getenv("SLR_LOG_DIR")
if _SLR_LOG_DIR_ENV:
    _LOG_DIR = Path(_SLR_LOG_DIR_ENV)
else:
    # backend/tools/Literatur/slrFetch.py → backend/log/slr
    _LOG_DIR = Path(__file__).resolve().parent.parent.parent / "log" / "slr"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Configure file handler for slrFetch
_LOG_FILE = _LOG_DIR / "slrFetch.log"
_file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
if not any(isinstance(h, logging.FileHandler) for h in log.handlers):
    log.addHandler(_file_handler)
log.info("slrFetch initialized with logging to %s", _LOG_FILE)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROMPT_FILE = Path(__file__).with_name("slrFetchPrompt.txt")
_MAX_FETCHERS = 12

# Base fetchers for international research (Scopus prioritized)
BASE_FETCHERS_INTERNATIONAL = ["scopus", "openalex", "crossref", "semantic_scholar"]

# Base fetchers for Indonesian research (Sinta prioritized)
BASE_FETCHERS_INDONESIAN = ["sinta", "scopus", "openalex", "crossref"]

# Book fetchers added for multi-word queries
BOOK_FETCHERS = ["google_books", "open_library"]
BOOK_EXT_FETCHERS = ["doab", "oapen", "cambridge", "crossref_publishers"]

# Fetcher quality tiers for prioritization
TIER_1_PREMIUM = {"scopus", "sciencedirect", "ieee", "pubmed", "europepmc"}
TIER_2_BROAD = {"openalex", "crossref", "semantic_scholar", "dimensions", "lens"}
TIER_3_SPECIALIZED = {"arxiv", "dblp", "pmc", "biorxiv", "plos"}
TIER_4_INDONESIAN = {"sinta"}
TIER_5_BOOKS = {"google_books", "open_library", "doab", "oapen", "gutendex", "cambridge", "crossref_publishers"}

# Domain keyword → fetcher mapping for fallback
_DOMAIN_FETCHERS: dict[str, list[str]] = {
    "medical": ["europepmc", "pubmed", "pmc", "biorxiv", "plos", "embase", "clinicalkey"],
    "health": ["europepmc", "pubmed", "pmc", "biorxiv", "plos", "clinicalkey"],
    "biology": ["europepmc", "pubmed", "pmc", "biorxiv", "plos"],
    "neuroscience": ["biorxiv", "pubmed", "europepmc"],
    "pharmacology": ["embase", "clinicalkey", "pubmed"],
    "cs": ["arxiv", "dblp", "ieee", "hal"],
    "ai": ["arxiv", "dblp", "ieee"],
    "engineering": ["ieee", "sciencedirect", "lens"],
    "electrical": ["ieee"],
    "robotics": ["ieee"],
    "physics": ["arxiv", "hal"],
    "math": ["arxiv"],
    "stats": ["arxiv"],
    "economics": ["openaire", "doab"],
    "social": ["openaire", "doab", "oapen"],
    "education": ["openaire"],
    "agriculture": ["lens"],
    "indonesia": ["sinta"],
    "environmental": ["openaire", "zenodo"],
    "humanities": ["google_books", "open_library", "doab", "oapen"],
    "literature": ["google_books", "open_library", "gutendex"],
    "law": ["oapen", "crossref_publishers"],
    "business": ["crossref_publishers"],
    "philosophy": ["gutendex", "oapen"],
}

# Keywords that indicate medical/health domain
_MEDICAL_KEYWORDS = frozenset({
    "medical", "health", "disease", "patient", "clinical", "hospital",
    "diagnosis", "treatment", "surgery", "pharmac", "drug", "therapy",
    "cancer", "tumor", "virus", "bacterial", "infection", "genomic",
    "protein", "cell", "tissue", "organ", "neural", "brain", "cardiac",
    "heart", "lung", "kidney", "liver", "blood", "immune", "vaccine",
    "epidemiolog", "patholog", "anatomy", "physiolog", "radiolog",
    "oncolog", "cardiolog", "dermatolog", "gastroenterolog", "urolog",
    "ophthalmolog", "neurolog", "psychiatr", "pediatric", "geriatric",
    "medicine", "nursing", "public health", "biomedical",
})

# Keywords that indicate CS/AI domain
_CS_AI_KEYWORDS = frozenset({
    "computer", "software", "algorithm", "programming", "code", "database",
    "network", "internet", "web", "cloud", "cyber", "blockchain",
    "machine learning", "deep learning", "neural network", "artificial intelligence",
    "nlp", "natural language", "computer vision", "image recognition",
    "data mining", "big data", "reinforcement learning", "generative",
    "transformer", "convolutional", "recurrent", "lstm", "gan",
    "robot", "autonomous", "iot", "embedded", "compiler", "operating system",
    "distributed", "parallel", "security", "encryption", "malware",
})

# Keywords that indicate engineering domain
_ENGINEERING_KEYWORDS = frozenset({
    "engineering", "structural", "mechanical", "civil", "electrical",
    "chemical", "aerospace", "automotive", "manufacturing", "material",
    "sensor", "actuator", "control system", "signal processing",
    "power", "energy", "renewable", "solar", "wind", "battery",
    "circuit", "semiconductor", "microcontroller", "vlsi",
})

# Keywords that indicate Indonesian research
_INDONESIAN_KEYWORDS = frozenset({
    "indonesia", "indonesian", "nusantara", "jawa", "sumatera", "kalimantan",
    "sulawesi", "papua", "bahasa indonesia", "pancasila", "batik",
    "pendidikan", "kesehatan", "pertanian", "pembangunan", "masyarakat",
    "pemerintah", "kebijakan", "ekonomi indonesia", "umkm",
    "sistem", "berbasis", "penelitian", "analisis", "metode",
    "teknik", "algoritma", "penerapan", "kajian", "studi",
    "rencana", "pemodelan", "implementasi", "pembuatan", "analisa",
})

# Indonesian-to-English academic term translation for API queries
_INDONESIAN_TO_ENGLISH = {
    # Core academic terms
    "pemanfaatan": "utilization",
    "teknik": "technique",
    "kultur": "culture",
    "jaringan": "network",
    "kultur jaringan": "tissue culture",  # biology domain: tissue culture
    "teknik kultur jaringan": "tissue culture technique",
    "konservasi": "conservation",
    "tumbuhan": "plant",
    "langka": "rare",
    "penerapan": "application",
    # Indonesian stopwords → remove (empty string = skip)
    "untuk": "",
    "dan": "",
    "yang": "",
    "dengan": "",
    "pada": "",
    "dalam": "",
    "atau": "",
    "dari": "",
    "ke": "",
    "di": "",
    "ini": "",
    "itu": "",
    "adalah": "",
    "akan": "",
    "sudah": "",
    "belum": "",
    "tidak": "",
    "bisa": "",
    "dapat": "",
    "harus": "",
    "perlu": "",
    "masih": "",
    "sangat": "",
    "lebih": "",
    "juga": "",
    "hanya": "",
    "saja": "",
    "lain": "",
    "semua": "",
    "setiap": "",
    "beberapa": "",
    "seperti": "",
    "sebagai": "",
    "menjadi": "",
    "merupakan": "",
    "mengenai": "",
    "terkait": "",
    "hubungan": "",
    "kaitan": "",
    "berkaitan": "",
    "berhubungan": "",
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
    "klasifikasi": "classification",
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
    "sel": "cell",
    "protein": "protein",
    "enzim": "enzyme",
    "dna": "dna",
    "rna": "rna",
    "gen": "gene",
    "genomik": "genomics",
    "proteomik": "proteomics",
    "bioinformatika": "bioinformatics",
    "farmakologi": "pharmacology",
    "farmasi": "pharmacy",
    "obat": "drug",
    "terapi": "therapy",
    "penyakit": "disease",
    "penyakit": "disease",
    "diagnosis": "diagnosis",
    "klinis": "clinical",
    "pasien": "patient",
    "rumah sakit": "hospital",
    "kesehatan": "health",
    "kedokteran": "medicine",
    "keperawatan": "nursing",
    "gizi": "nutrition",
    "makanan": "food",
    "pertanian": "agriculture",
    "tanaman": "plant",
    "benih": "seed",
    "pupuk": "fertilizer",
    "hama": "pest",
    "penyakit tanaman": "plant disease",
    "irigasi": "irrigation",
    "lahan": "land",
    "tanah": "soil",
    "air": "water",
    "iklim": "climate",
    "cuaca": "weather",
    "lingkungan": "environment",
    "ekologi": "ecology",
    "biodiversitas": "biodiversity",
    "ekosistem": "ecosystem",
    "polusi": "pollution",
    "limbah": "waste",
    "daur ulang": "recycling",
    "energi terbarukan": "renewable energy",
    "solar": "solar",
    "angin": "wind",
    "biomassa": "biomass",
    "hidro": "hydro",
    "geotermal": "geothermal",
    "baterai": "battery",
    "sel surya": "solar cell",
    "pengisian": "charging",
    "pengosongan": "discharging",
    "kapasitas": "capacity",
    "daya": "power",
    "energi": "energy",
    "listrik": "electricity",
    "arus": "current",
    "tegangan": "voltage",
    "frekuensi": "frequency",
    "sinyal": "signal",
    "gelombang": "wave",
    "modulasi": "modulation",
    "demodulasi": "demodulation",
    "antena": "antenna",
    "propagasi": "propagation",
    "transmisi": "transmission",
    "penerima": "receiver",
    "pengirim": "transmitter",
    "komunikasi": "communication",
    "jaringan": "network",
    "protokol": "protocol",
    "routing": "routing",
    "switching": "switching",
    "bandwidth": "bandwidth",
    "latency": "latency",
    "throughput": "throughput",
    "keamanan": "security",
    "enkripsi": "encryption",
    "dekripsi": "decryption",
    "autentikasi": "authentication",
    "otorisasi": "authorization",
    "firewall": "firewall",
    "vpn": "vpn",
    "database": "database",
    "basis data": "database",
    "sql": "sql",
    "nosql": "nosql",
    "query": "query",
    "indeks": "index",
    "transaksi": "transaction",
    "konsistensi": "consistency",
    "replikasi": "replication",
    "sharding": "sharding",
    "backup": "backup",
    "recovery": "recovery",
    "pemrograman": "programming",
    "bahasa pemrograman": "programming language",
    "kompilator": "compiler",
    "interpreter": "interpreter",
    "debugging": "debugging",
    "testing": "testing",
    "deployment": "deployment",
    "devops": "devops",
    "ci/cd": "ci/cd",
    "container": "container",
    "docker": "docker",
    "kubernetes": "kubernetes",
    "microservices": "microservices",
    "api": "api",
    "rest": "rest",
    "graphql": "graphql",
    "websocket": "websocket",
    "frontend": "frontend",
    "backend": "backend",
    "fullstack": "fullstack",
    "ui": "ui",
    "ux": "ux",
    "desain": "design",
    "antarmuka pengguna": "user interface",
    "pengalaman pengguna": "user experience",
    "aksesibilitas": "accessibility",
    "responsif": "responsive",
    "mobile": "mobile",
    "android": "android",
    "ios": "ios",
    "web": "web",
    "html": "html",
    "css": "css",
    "javascript": "javascript",
    "typescript": "typescript",
    "react": "react",
    "vue": "vue",
    "angular": "angular",
    "nodejs": "nodejs",
    "python": "python",
    "java": "java",
    "c++": "c++",
    "c#": "c#",
    "go": "go",
    "rust": "rust",
    "php": "php",
    "ruby": "ruby",
    "swift": "swift",
    "kotlin": "kotlin",
    "flutter": "flutter",
    "react native": "react native",
    "database": "database",
    "machine learning": "machine learning",
    "deep learning": "deep learning",
    "neural network": "neural network",
    "computer vision": "computer vision",
    "natural language processing": "natural language processing",
    "nlp": "nlp",
    "reinforcement learning": "reinforcement learning",
    "supervised learning": "supervised learning",
    "unsupervised learning": "unsupervised learning",
    "transfer learning": "transfer learning",
    "fine-tuning": "fine-tuning",
    "llm": "llm",
    "large language model": "large language model",
    "transformer": "transformer",
    "attention": "attention",
    "bert": "bert",
    "gpt": "gpt",
    "chatgpt": "chatgpt",
    "generative ai": "generative ai",
    "ai generatif": "generative ai",
}

def _translate_id_to_en(keyword: str) -> str:
    """Translate Indonesian academic keyword to English for international APIs.
    
    Uses word-by-word lookup for common academic terms. Preserves words
    not in dictionary (proper nouns, numbers, etc.). Stopwords map to ""
    and are skipped.
    """
    words = keyword.lower().split()
    translated = []
    i = 0
    while i < len(words):
        # Try 3-word phrases first
        if i + 2 < len(words):
            phrase3 = " ".join(words[i:i+3])
            if phrase3 in _INDONESIAN_TO_ENGLISH:
                val = _INDONESIAN_TO_ENGLISH[phrase3]
                if val:
                    translated.append(val)
                i += 3
                continue
        # Try 2-word phrases
        if i + 1 < len(words):
            phrase2 = " ".join(words[i:i+2])
            if phrase2 in _INDONESIAN_TO_ENGLISH:
                val = _INDONESIAN_TO_ENGLISH[phrase2]
                if val:
                    translated.append(val)
                i += 2
                continue
        # Single word
        word = words[i]
        if word in _INDONESIAN_TO_ENGLISH:
            val = _INDONESIAN_TO_ENGLISH[word]
            if val:
                translated.append(val)
        else:
            translated.append(word)
        i += 1
    return " ".join(translated)


def _detect_language(keyword: str) -> str:
    """Detect query language: 'id' (Indonesian), 'en' (English), or 'mixed'."""
    kw_lower = keyword.lower()
    words = set(re.findall(r"[a-z]+", kw_lower))
    
    id_score = len(words & _INDONESIAN_KEYWORDS)
    
    if id_score >= 2:
        return "id"
    if id_score == 1:
        return "mixed"
    return "en"


def _is_indonesian_research(domains: list[str]) -> bool:
    """Check if query targets Indonesian research."""
    return "indonesia" in domains


def _get_fetcher_priority(fetcher: str, is_indonesian: bool) -> int:
    """Get priority score for fetcher ordering. Lower = higher priority."""
    if is_indonesian:
        if fetcher == "sinta":
            return 1  # Highest priority for Indonesian research
        if fetcher == "scopus":
            return 2  # Second - Indonesian journals in Scopus
    else:
        if fetcher == "scopus":
            return 1  # Highest priority for international research
    
    if fetcher in TIER_1_PREMIUM:
        return 3
    if fetcher in TIER_2_BROAD:
        return 4
    if fetcher in TIER_3_SPECIALIZED:
        return 5
    if fetcher in TIER_4_INDONESIAN:
        return 6
    if fetcher in TIER_5_BOOKS:
        return 8
    return 7

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompt() -> str:
    """Read slrFetchPrompt.txt from the same directory."""
    return _PROMPT_FILE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# LLM-based analysis
# ---------------------------------------------------------------------------

def _parse_llm_json(text: str) -> dict:
    """Extract JSON from LLM response, tolerating markdown fences."""
    text = text.strip()
    # Strip ```json ... ``` wrappers
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def analyze_keyword(
    keyword: str,
    llm_call: Optional[Callable[[str, str], str]] = None,
) -> dict:
    """Analyze a keyword and return a structured fetcher plan.

    Parameters
    ----------
    keyword : str
        The user's search keyword.
    llm_call : callable, optional
        ``llm_call(system_prompt, user_message) -> str`` that returns JSON.
        If None, falls back to ``guess_fetchers``.

    Returns
    -------
    dict with keys: main_keyword, domains, selected_fetchers,
         expanded_queries, fetcher_query_map, include_books,
         book_fetchers, book_query.
    """
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("keyword must not be empty")

    if llm_call is None:
        # Fallback to rule-based
        return guess_fetchers(keyword)

    system_prompt = load_prompt()
    user_msg = f"Keyword: {keyword}"

    try:
        raw = llm_call(system_prompt, user_msg)
        result = _parse_llm_json(raw)
    except Exception as exc:
        log.warning("LLM call failed (%s), falling back to guess_fetchers", exc)
        return guess_fetchers(keyword)

    # Validate & sanitize
    result = _validate_analysis(result, keyword)
    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_analysis(raw: dict, keyword: str) -> dict:
    """Ensure the analysis dict is well-formed and fetchers exist in ALL."""
    result: dict = {}
    result["main_keyword"] = keyword
    
    # Language and scope detection
    detected_language = raw.get("detected_language") or _detect_language(keyword)
    result["detected_language"] = detected_language
    
    research_scope = raw.get("research_scope") or (
        "indonesian" if detected_language == "id" else 
        "mixed" if detected_language == "mixed" else "international"
    )
    result["research_scope"] = research_scope

    # Domains
    domains = raw.get("domains", [])
    if not isinstance(domains, list):
        domains = []
    result["domains"] = [d.lower().strip() for d in domains if isinstance(d, str)]

    # Add "indonesia" domain if Indonesian language detected
    if detected_language in ["id", "mixed"] and "indonesia" not in result["domains"]:
        result["domains"].append("indonesia")

    # Selected fetchers — filter to those that exist in ALL
    raw_fetchers = raw.get("selected_fetchers", [])
    if not isinstance(raw_fetchers, list):
        # Use appropriate base fetchers based on language/scope
        is_indonesian = research_scope in ["indonesian", "mixed"]
        raw_fetchers = list(BASE_FETCHERS_INDONESIAN if is_indonesian else BASE_FETCHERS_INTERNATIONAL)
    
    valid_fetchers = [f for f in raw_fetchers if f in ALL]
    
    # Enforce base fetchers are present with proper prioritization
    is_indonesian_research = research_scope in ["indonesian", "mixed"]
    base_fetchers = BASE_FETCHERS_INDONESIAN if is_indonesian_research else BASE_FETCHERS_INTERNATIONAL
    
    for bf in base_fetchers:
        if bf not in valid_fetchers and bf in ALL:
            valid_fetchers.insert(0, bf)
    
    # Sort by priority (Scopus first for international, Sinta first for Indonesian)
    valid_fetchers.sort(key=lambda f: _get_fetcher_priority(f, is_indonesian_research))
    
    # Cap at MAX_FETCHERS
    valid_fetchers = valid_fetchers[:_MAX_FETCHERS]
    result["selected_fetchers"] = valid_fetchers
    
    # Build fetcher priority mapping
    fetcher_priority = {}
    for i, fetcher in enumerate(valid_fetchers, 1):
        fetcher_priority[fetcher] = i
    result["fetcher_priority"] = fetcher_priority

    # Expanded queries
    expanded = raw.get("expanded_queries", [])
    if not isinstance(expanded, list):
        expanded = [keyword]
    # Always include main keyword
    if keyword not in expanded:
        expanded.insert(0, keyword)
    result["expanded_queries"] = [q.strip() for q in expanded if isinstance(q, str) and q.strip()]

    # Fetcher-query map with language-aware assignments
    raw_map = raw.get("fetcher_query_map", {})
    if not isinstance(raw_map, dict):
        raw_map = {}
    
    fmap: dict[str, str] = {}
    for fetcher in valid_fetchers:
        q = raw_map.get(fetcher)
        if not q or not isinstance(q, str) or not q.strip():
            # Smart query assignment based on fetcher type and language
            q = _get_smart_query_for_fetcher(fetcher, keyword, result["expanded_queries"], detected_language)
        fmap[fetcher] = q.strip()
    result["fetcher_query_map"] = fmap

    # Books
    include_books = bool(raw.get("include_books", False))
    book_fetchers = raw.get("book_fetchers", [])
    if not isinstance(book_fetchers, list):
        book_fetchers = []
    book_fetchers = [f for f in book_fetchers if f in ALL]
    result["include_books"] = include_books and bool(book_fetchers)
    result["book_fetchers"] = book_fetchers
    result["book_query"] = raw.get("book_query", "") if include_books else ""

    return result


def _get_smart_query_for_fetcher(fetcher: str, main_keyword: str, expanded_queries: list[str], language: str) -> str:
    """Get appropriate query for specific fetcher based on language and fetcher type."""
    # For Indonesian databases, use Indonesian query
    if fetcher == "sinta" and language in ["id", "mixed"]:
        return main_keyword  # Keep original Indonesian
    
    # For international databases, prefer English
    if fetcher in {"scopus", "sciencedirect", "ieee", "pubmed", "europepmc", "pmc"}:
        # Try to find English variant in expanded queries
        for q in expanded_queries:
            if not any(word in q.lower() for word in _INDONESIAN_KEYWORDS):
                return q
        return main_keyword  # Fallback
    
    # For broad databases, use main keyword or first expanded
    if fetcher in {"openalex", "crossref", "semantic_scholar"}:
        return expanded_queries[0] if expanded_queries else main_keyword
    
    return main_keyword


# ---------------------------------------------------------------------------
# Route fetchers → {fetcher_name: [query1, query2, ...]}
# ---------------------------------------------------------------------------

def route_fetchers(analysis: dict) -> dict[str, list[str]]:
    """Convert analysis dict to {fetcher_name: [queries...]} mapping.

    Each fetcher gets its assigned query from fetcher_query_map.
    Book fetchers additionally receive the book_query if present.
    Returns ordered dict by fetcher priority (Scopus/Sinta first).
    """
    route: dict[str, list[str]] = {}
    
    # Get priority-ordered fetcher list
    fetcher_priority = analysis.get("fetcher_priority", {})
    priority_order = sorted(
        analysis.get("selected_fetchers", []),
        key=lambda f: fetcher_priority.get(f, 999)
    )

    # Main fetchers (priority order)
    fmap = analysis.get("fetcher_query_map", {})
    for fetcher in priority_order:
        query = fmap.get(fetcher, analysis.get("main_keyword", ""))
        queries = [query] if query else [analysis["main_keyword"]]
        route[fetcher] = queries

    # Book fetchers
    if analysis.get("include_books") and analysis.get("book_query"):
        book_q = analysis["book_query"]
        for bf in analysis.get("book_fetchers", []):
            if bf in route:
                if book_q not in route[bf]:
                    route[bf].append(book_q)
            else:
                route[bf] = [book_q]

    # Also add expanded queries to broad fetchers for wider recall
    expanded = analysis.get("expanded_queries", [])
    broad = {"openalex", "crossref", "semantic_scholar", "scopus"}
    for fetcher, queries in route.items():
        if fetcher in broad:
            fetcher_query = fmap.get(fetcher, "")
            # Don't duplicate the main query
            for eq in expanded:
                if eq != fetcher_query and eq not in queries:
                    queries.append(eq)
    
    # Ensure scopus gets English query even for Indonesian queries
    language = analysis.get("detected_language", "en")
    if language in ["id", "mixed"] and "scopus" in route:
        # Make sure scopus has English/translated query alongside Indonesian
        main_q = route["scopus"][0]
        # If query contains Indonesian words, try to add English variant
        if any(w.lower() in _INDONESIAN_KEYWORDS for w in main_q.split()):
            # Try to find or create English variant
            has_english = any(
                not any(ik in q.lower() for ik in _INDONESIAN_KEYWORDS)
                for q in route["scopus"]
            )
            if not has_english and expanded:
                # Use first expanded that doesn't look Indonesian
                for eq in expanded:
                    if not any(ik in eq.lower() for ik in _INDONESIAN_KEYWORDS):
                        route["scopus"].append(eq)
                        break

    return route


# ---------------------------------------------------------------------------
# Fallback: keyword matching (no LLM needed)
# ---------------------------------------------------------------------------

def _detect_domains(keyword: str) -> list[str]:
    """Detect domains from keyword using pattern matching."""
    kw_lower = keyword.lower()
    words = set(re.findall(r"[a-z]+", kw_lower))
    domains: list[str] = []

    # Check medical keywords
    if words & _MEDICAL_KEYWORDS:
        domains.append("medical")

    # Check CS/AI keywords
    found_multi = False
    for cs_kw in _CS_AI_KEYWORDS:
        if " " in cs_kw:
            if cs_kw in kw_lower:
                domains.append("cs")
                if any(ai in cs_kw for ai in ("learning", "intelligence", "neural", "deep", "ai", "natural", "vision", "nlp", "generative", "transformer")):
                    domains.append("ai")
                found_multi = True
                break  # first multi-word match wins
        elif cs_kw in words:
            domains.append("cs")
            if cs_kw in ("ai",):
                domains.append("ai")
            # Don't break on single-word — keep looking for multi-word (more specific)
    # Also check for individual AI indicators in the keyword
    if "ai" in words:
        if "ai" not in domains:
            domains.append("ai")
    ai_indicators = {"deep learning", "machine learning", "artificial intelligence",
                     "neural network", "computer vision", "nlp", "natural language",
                     "transformer", "reinforcement learning", "generative"}
    if any(ind in kw_lower for ind in ai_indicators):
        if "ai" not in domains:
            domains.append("ai")

    # Check engineering keywords
    if words & _ENGINEERING_KEYWORDS:
        domains.append("engineering")

    # Check Indonesian keywords
    if words & _INDONESIAN_KEYWORDS:
        domains.append("indonesia")

    # Additional heuristics
    edu_kw = {"education", "teaching", "curriculum", "school", "university", "pedagogy"}
    if words & edu_kw:
        domains.append("education")

    social_kw = {"social", "society", "culture", "politics", "governance", "policy"}
    if words & social_kw:
        domains.append("social")

    econ_kw = {"economics", "economy", "finance", "market", "trade", "gdp", "inflation"}
    if words & econ_kw:
        domains.append("economics")

    physics_kw = {"physics", "quantum", "relativity", "particle", "thermodynamic", "optics"}
    if words & physics_kw:
        domains.append("physics")

    chem_kw = {"chemistry", "chemical", "molecule", "catalyst", "reaction", "compound"}
    if words & chem_kw:
        domains.append("chemistry")

    agr_kw = {"agriculture", "crop", "soil", "farming", "irrigation", "livestock", "plant breeding"}
    if words & agr_kw:
        domains.append("agriculture")

    env_kw = {"environment", "climate", "pollution", "ecology", "biodiversity", "sustainability"}
    if words & env_kw:
        domains.append("environmental")

    book_kw = {"textbook", "handbook", "monograph", "reference work", "encyclopedia", "manual"}
    if any(bk in kw_lower for bk in book_kw):
        domains.append("humanities")

    return list(dict.fromkeys(domains))  # deduplicate preserving order


def _make_book_query(keyword: str) -> str:
    """Create a book-oriented query from the keyword."""
    kw_lower = keyword.lower()
    # Remove common filler words
    filler = {"for", "in", "of", "the", "and", "with", "on", "by", "an", "a"}
    words = kw_lower.split()
    core = [w for w in words if w not in filler]
    return " ".join(core[:5]) + " textbook" if len(core) > 3 else keyword + " textbook"


def guess_fetchers(keyword: str) -> dict:
    """Rule-based fallback with language detection and Scopus prioritization.

    Uses keyword matching to detect domains and language, then maps domains 
    to fetchers using prioritization: Scopus first for international, 
    Sinta first for Indonesian.

    Returns
    -------
    dict
        Same structure as ``analyze_keyword`` output with language and scope.
    """
    keyword = keyword.strip()
    language = _detect_language(keyword)
    domains = _detect_domains(keyword)
    word_count = len(keyword.split())
    
    is_indonesian = language in ["id", "mixed"]
    research_scope = "indonesian" if language == "id" else "mixed" if language == "mixed" else "international"

    # Start with priority-ordered base fetchers
    selected: list[str] = list(BASE_FETCHERS_INDONESIAN if is_indonesian else BASE_FETCHERS_INTERNATIONAL)
    seen = set(selected)

    # Add domain-specific fetchers with tier-based priority
    for domain in domains:
        domain_fetchers = _DOMAIN_FETCHERS.get(domain, [])
        for f in domain_fetchers:
            if f not in seen and f in ALL:
                selected.append(f)
                seen.add(f)

    # If keyword >= 4 words → add book fetchers
    include_books = word_count >= 4
    book_fetchers: list[str] = []
    if include_books:
        for bf in BOOK_FETCHERS:
            if bf not in seen and bf in ALL:
                selected.append(bf)
                seen.add(bf)
                book_fetchers.append(bf)
        # Extended book fetchers for book-oriented keywords
        if "humanities" in domains:
            for bf in BOOK_EXT_FETCHERS:
                if bf not in seen and bf in ALL:
                    selected.append(bf)
                    seen.add(bf)
                    book_fetchers.append(bf)

    # Cap at MAX_FETCHERS — re-sort by priority
    if len(selected) > _MAX_FETCHERS:
        selected.sort(key=lambda f: _get_fetcher_priority(f, is_indonesian))
        selected = selected[:_MAX_FETCHERS]
    else:
        # Sort all by priority (Scopus/Sinta first)
        selected.sort(key=lambda f: _get_fetcher_priority(f, is_indonesian))

    # Build fetcher_query_map with language-aware queries
    fmap: dict[str, str] = {}
    # For international APIs, use English query
    international_fetchers = {
        "scopus", "sciencedirect", "ieee", "pubmed", "europepmc", "pmc",
        "openalex", "crossref", "semantic_scholar", "dimensions", "lens",
        "arxiv", "dblp", "biorxiv", "plos", "google_books", "open_library"
    }
    for f in selected:
        if f in international_fetchers and language in ("id", "mixed"):
            fmap[f] = _translate_id_to_en(keyword)
        elif f == "sinta" and language in ("en", "mixed"):
            # For English queries going to Sinta, could translate but less critical
            fmap[f] = keyword
        else:
            fmap[f] = keyword

    # Expanded queries for long keywords (5+ words)
    expanded = [keyword]
    if word_count >= 5:
        # Broader: remove least important words
        words = keyword.split()
        if len(words) > 5:
            broader = " ".join(words[:4])
            expanded.append(broader)
        # Add variants
        kw_lower = keyword.lower()
        if "review" not in kw_lower and "survey" not in kw_lower:
            expanded.append(keyword + " review")
        if "systematic" not in kw_lower:
            expanded.append("systematic " + keyword)

    book_query = _make_book_query(keyword) if include_books else ""

    result = {
        "main_keyword": keyword,
        "detected_language": language,
        "research_scope": research_scope,
        "domains": domains,
        "selected_fetchers": selected,
        "expanded_queries": expanded,
        "fetcher_query_map": fmap,
        "include_books": include_books and bool(book_fetchers),
        "book_fetchers": book_fetchers,
        "book_query": book_query,
    }
    
    # Build fetcher priority mapping
    fetcher_priority = {}
    for i, fetcher in enumerate(selected, 1):
        fetcher_priority[fetcher] = i
    result["fetcher_priority"] = fetcher_priority
    
    return result
