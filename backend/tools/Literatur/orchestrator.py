"""Orchestrator multi-source SLR.

Strategi baru sesuai brief:

1. Tahap 1 — `fetch_titles()` panggil semua source (max 10 worker pool) hanya
   untuk dapat metadata ringan: title, authors, year, doi, source, venue,
   citations, abstract (kalau gratis di-include source langsung). Maks 60 hasil
   per source, lalu dedup global by DOI/title-normalized.
2. Topic-aware source selection: kalau topic terdeteksi medical → europepmc
   diprioritaskan, kalau IT/CS → ieee/dblp/arxiv. Source yang tidak match topic
   tetap dipanggil tapi dengan limit lebih kecil (signal pelengkap).
3. Hasil siap dirank di pipeline.py dengan kombinasi citation+recency+SBERT
   tanpa perlu fetch detail tambahan dulu.

Modul ini cuma menangani fetching + dedup. Ranking + summarization tetap di
pipeline.py / scoring.py / summarizer.py.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .fetchers import ALL, SOURCE_TOPICS
from .http_client import get_client
from .paper import Paper

log = logging.getLogger(__name__)

PREDATORY_PUBLISHERS = {
    "omics",
    "scirp",
    "scientific research publishing",
    "academic journals",
    "david publishing",
    "academic and scientific publishing",
    "bentham science",
}

MAX_WORKERS = 10
DEFAULT_LIMIT_PER_SOURCE = 60


_TOPIC_KEYWORDS = {
    "medical": (
        "medic",
        "medis",
        "clinic",
        "klinis",
        "patient",
        "covid",
        "cancer",
        "drug",
        "obat",
        "pharma",
        "therapy",
        "disease",
        "penyakit",
        "diagnosis",
        "kesehatan",
        "kedokteran",
        "hospital",
        "rumah sakit",
        "surgery",
        "bedah",
        "vaccine",
        "vaksin",
        "epidemiol",
        "public health",
        "mental health",
        "nutrition",
        "gizi",
        "patolog",
        "anatomy",
        "anatomi",
        "immunol",
        "cardio",
        "jantung",
    ),
    "biology": (
        "biolog",
        "gene",
        "protein",
        "cell",
        "neuron",
        "genome",
        "genom",
        "ecosystem",
        "ekosistem",
        "species",
        "spesies",
        "evolution",
        "evolusi",
        "microbio",
        "mikroba",
        "molecular",
        "molekuler",
        "bioinform",
        "biodiversity",
        "biodiversitas",
    ),
    "cs": (
        "software",
        "algorit",
        "programming",
        "compiler",
        "database",
        "system",
        "network",
        "cloud",
        "distributed",
        "kernel",
        "komputer",
        "informatika",
        "computing",
        "cyber",
        "security",
        "keamanan",
        "blockchain",
        "cryptography",
        "kriptografi",
        "web",
        "mobile",
        "operating system",
        "sistem operasi",
        "data mining",
        "tambang data",
        "big data",
        "information system",
        "sistem informasi",
    ),
    "ai": (
        "machine learning",
        "deep learning",
        "neural",
        "ml",
        "ai",
        "lstm",
        "transformer",
        "nlp",
        "computer vision",
        "agent",
        "reinforcement",
        "kecerdasan buatan",
        "pembelajaran mesin",
        "pembelajaran mendalam",
        "artificial intelligence",
        "generative",
        "llm",
        "large language model",
        "gpt",
        "bert",
        "chatbot",
        "natural language",
        "bahasa alami",
        "image recognition",
        "pengenalan citra",
        "speech recognition",
        "pengenalan suara",
        "autonomous",
        "otonom",
        "knowledge graph",
        "expert system",
        "sistem pakar",
    ),
    "engineering": (
        "engineering",
        "control",
        "robot",
        "iot",
        "embedded",
        "signal",
        "circuit",
        "rangkaian",
        "teknik elektro",
        "teknik",
        "rekayasa",
        "elektronika",
        "mesin",
        "renewable",
        "terbarukan",
        "solar",
        "energi",
        "energy",
        "material",
        "structural",
        "infrastruktur",
        "infrastructure",
        "manufacturing",
        "manufaktur",
        "aerospace",
        "dirgantara",
        "automotive",
        "otomotif",
    ),
    "physics": (
        "physics",
        "quantum",
        "particle",
        "astro",
        "fisika",
        "optics",
        "optik",
        "thermo",
        "relativity",
        "relativitas",
        "nuclear",
        "nuklir",
        "plasma",
        "condensed matter",
    ),
    "indonesia": (
        "indonesia",
        "sinta",
        "garuda",
        "kemdikbud",
        "lokal",
        "akreditasi sinta",
        "lokal indonesia",
        "nusantara",
        "jawa",
        "sumatera",
        "kalimantan",
        "sulawesi",
    ),
    "economics": (
        "econom",
        "ekonomi",
        "finance",
        "keuangan",
        "market",
        "pasar",
        "inflation",
        "inflasi",
        "gdp",
        "pib",
        "monetary",
        "moneter",
        "fiscal",
        "fiskal",
        "banking",
        "perbankan",
        "trade",
        "perdagangan",
        "investment",
        "investasi",
        "stock",
        "saham",
        "cryptocurrency",
        "crypto",
    ),
    "social": (
        "social",
        "sosial",
        "society",
        "masyarakat",
        "culture",
        "budaya",
        "politic",
        "politik",
        "governance",
        "tata kelola",
        "democracy",
        "demokrasi",
        "gender",
        "poverty",
        "kemiskinan",
        "inequality",
        "ketimpangan",
        "migration",
        "migrasi",
        "community",
        "komunitas",
        "psycholog",
        "psikolog",
    ),
    "education": (
        "education",
        "pendidikan",
        "learning",
        "pembelajaran",
        "teaching",
        "pengajaran",
        "curriculum",
        "kurikulum",
        "school",
        "sekolah",
        "university",
        "universitas",
        "student",
        "siswa",
        "mahasiswa",
        "pedagog",
        "e-learning",
        "pembelajaran daring",
        "assessment",
        "asesmen",
        "literacy",
        "literasi",
    ),
    "law": (
        "law",
        "hukum",
        "legal",
        "regulation",
        "regulasi",
        "policy",
        "kebijakan",
        "constitutional",
        "konstitusi",
        "criminal",
        "pidana",
        "civil",
        "perdata",
        "human rights",
        "hak asasi",
        "intellectual property",
        "hak kekayaan intelektual",
        "compliance",
        "kepatuhan",
        "justice",
        "keadilan",
    ),
    "agriculture": (
        "agriculture",
        "pertanian",
        "crop",
        "tanaman",
        "farming",
        "tani",
        "food security",
        "ketahanan pangan",
        "irrigation",
        "irigasi",
        "soil",
        "tanah",
        "pest",
        "hama",
        "fertilizer",
        "pupuk",
        "agronomy",
        "agronomi",
        "livestock",
        "peternakan",
        "fishery",
        "perikanan",
        "forestry",
        "kehutanan",
    ),
    "food_science": (
        "functional food",
        "nutraceutical",
        "nutrasetikal",
        "glycemic",
        "glikemik",
        "glycaemic",
        "bioactive",
        "bioaktif",
        "antioxidant",
        "antioksidan",
        "fermentation",
        "fermentasi",
        "probiotic",
        "probiotik",
        "germination",
        "perkecambahan",
        "legume",
        "kacang-kacangan",
        "tuber",
        "umbi",
        "snack",
        "snack bar",
        "baked",
        "roti",
        "bread",
        "extrusion",
        "ekstrusi",
        "organoleptic",
        "organoleptik",
        "sensory",
        "sensoris",
        "food processing",
        "food product",
        "dietary fiber",
        "serat pangan",
        "resistant starch",
        "pati resisten",
        "protein isolate",
        "isolat protein",
        "polyphenol",
        "polifenol",
        "flavonoid",
        "mineral bioavail",
        "phytic acid",
        "asam fitat",
        "tannin",
        "pasting properties",
        "gelatinization",
        "gelatinisasi",
        "nutritional",
        "nutrition",
        "nutrisi",
        "gizi",
        "food science",
        "food technology",
        "cereal",
        "serealia",
        "composite flour",
        "tepung komposit",
        "gluten free",
        "bebas gluten",
    ),
    "chemistry": (
        "chemist",
        "kimia",
        "chemical",
        "organic",
        "inorganic",
        "polymer",
        "polimer",
        "catalyst",
        "katalis",
        "compound",
        "senyawa",
        "reaction",
        "reaksi",
        "synthesis",
        "sintesis",
        "derivative",
        "turunan",
        "ligand",
        "ligan",
        "nanoparticle",
        "nanopartikel",
        "electrochem",
        "elektrokimia",
        "spectroscop",
        "spektroskopi",
        "chromatograph",
        "kromatografi",
        "reagent",
        "reagen",
        "solvent",
        "pelarut",
        "ionic",
        "covalent",
        "kovalen",
    ),
    "materials": (
        "nanomaterial",
        "coating",
        "pelapis",
        "composite",
        "komposit",
        "alloy",
        "paduan",
        "ceramic",
        "keramik",
        "semiconductor",
        "semikonduktor",
        "thin film",
        "superconduct",
        "biomaterial",
        "corrosion",
        "korosi",
        "mechanical properties",
        "sifat mekanik",
        "tensile",
        "fatigue",
        "fracture",
        "wear",
    ),
    "environmental": (
        "environment",
        "lingkungan",
        "pollution",
        "polusi",
        "pencemaran",
        "waste",
        "limbah",
        "emission",
        "emisi",
        "carbon",
        "karbon",
        "greenhouse",
        "climate",
        "iklim",
        "ecology",
        "ekologi",
        "conservation",
        "konservasi",
        "biodiversity",
        "biodiversitas",
        "deforestation",
        "deforestasi",
        "water quality",
        "kualitas air",
        "air pollution",
        "sustainability",
        "sustainable",
        "berkelanjutan",
        "recycling",
        "daur ulang",
        "circular economy",
        "ekonomi sirkular",
    ),
    "psychology": (
        "psycholog",
        "psikolog",
        "cognitive",
        "kognitif",
        "behavior",
        "perilaku",
        "mental",
        "depression",
        "depresi",
        "anxiety",
        "kecemasan",
        "emotion",
        "emosi",
        "personality",
        "kepribadian",
        "trauma",
        "therapy",
        "terapi",
        "counseling",
        "konseling",
        "mindfulness",
        "wellbeing",
        "well being",
        "kesejahteraan",
        "stress",
        "stres",
        "adolescent",
        "remaja",
        "attachment",
        "development",
        "perkembangan",
    ),
    "business_management": (
        "management",
        "manajemen",
        "marketing",
        "pemasaran",
        "strategy",
        "strategi",
        "business",
        "bisnis",
        "entrepreneur",
        "wirausaha",
        "supply chain",
        "rantai pasok",
        "human resource",
        "sdm",
        "organizational",
        "organisasi",
        "leadership",
        "kepemimpinan",
        "consumer",
        "konsumen",
        "brand",
        "merek",
        "innovation",
        "inovasi",
        "startup",
        "corporate",
        "perusahaan",
        "logistics",
        "logistik",
        "accounting",
        "akuntansi",
        "audit",
    ),
    "sports": (
        "sport",
        "olahraga",
        "athlete",
        "atlet",
        "exercise",
        "latihan",
        "fitness",
        "kebugaran",
        "training",
        "pelatihan",
        "coach",
        "pelatih",
        "physical activity",
        "aktivitas fisik",
        "performance",
        "performa",
        "injury",
        "cedera",
        "rehabilitation",
        "rehabilitasi",
        "biomechanic",
        "biomekanika",
        "physiology",
        "fisiologi",
    ),
    "linguistics": (
        "linguistic",
        "linguistik",
        "language",
        "bahasa",
        "syntax",
        "sintaksis",
        "semantic",
        "semantik",
        "phonolog",
        "fonologi",
        "morpholog",
        "morfologi",
        "discourse",
        "wacana",
        "pragmatic",
        "pragmatik",
        "translation",
        "penerjemahan",
        "bilingual",
        "multilingual",
        "sociolinguistic",
        "sosiolinguistik",
        "corpus",
        "korpus",
    ),
    "geology": (
        "geolog",
        "geology",
        "mineral",
        "rock",
        "batuan",
        "sediment",
        "sedimen",
        "volcanic",
        "vulkanik",
        "earthquake",
        "gempa",
        "seismic",
        "seismik",
        "tectonic",
        "tektonik",
        "geothermal",
        "panas bumi",
        "mining",
        "pertambangan",
        "petroleum",
        "reservoir",
        "hydrology",
        "hidrologi",
        "groundwater",
        "air tanah",
    ),
    "pharmacology": (
        "pharmacol",
        "farmakologi",
        "drug",
        "obat",
        "dose",
        "dosis",
        "toxicity",
        "toksisitas",
        "toxicology",
        "toksikologi",
        "pharmacokinetic",
        "farmakokinetik",
        "bioavailability",
        "bioavailabilitas",
        "medicine",
        "prescription",
        "reseptor",
        "receptor",
        "herbal",
        "ekstrak",
        "extract",
        "clinical trial",
        "uji klinis",
        "adverse effect",
        "efek samping",
    ),
    "arts_design": (
        "design",
        "desain",
        "art",
        "seni",
        "visual",
        "graphic",
        "grafis",
        "illustration",
        "ilustrasi",
        "aesthetic",
        "estetika",
        "creative",
        "kreatif",
        "architecture",
        "arsitektur",
        "fashion",
        "textile",
        "tekstil",
        "craft",
        "kerajinan",
        "painting",
        "lukisan",
        "sculpture",
        "patung",
    ),
    "tourism": (
        "tourism",
        "pariwisata",
        "tourist",
        "wisatawan",
        "hospitality",
        "hotel",
        "destination",
        "destinasi",
        "travel",
        "perjalanan",
        "cultural heritage",
        "warisan budaya",
        "ecotourism",
        "ekowisata",
        "visitor",
        "pengunjung",
        "accommodation",
        "akomodasi",
    ),
    "communication": (
        "communication",
        "komunikasi",
        "media",
        "journalism",
        "jurnalisme",
        "broadcasting",
        "penyiaran",
        "social media",
        "media sosial",
        "public relation",
        "hubungan masyarakat",
        "advertising",
        "periklanan",
        "persuasion",
        "persuasi",
        "interpersonal",
        "digital media",
        "media digital",
    ),
    "mathematics": (
        "mathematics",
        "matematika",
        "mathematical",
        "algorithm",
        "algoritma",
        "optimization",
        "optimasi",
        "statistics",
        "statistik",
        "statistika",
        "probability",
        "probabilitas",
        "numerical",
        "numerik",
        "topology",
        "topologi",
        "geometry",
        "geometri",
        "algebra",
        "aljabar",
        "calculus",
        "kalkulus",
        "differential equation",
        "persamaan diferensial",
    ),
}


# Indonesian → English term mapping for query expansion
_ID_TO_EN = {
    # AI/CS
    "kecerdasan buatan": "artificial intelligence",
    "pembelajaran mesin": "machine learning",
    "pembelajaran mendalam": "deep learning",
    "jaringan saraf": "neural network",
    "pengolahan bahasa alami": "natural language processing",
    "penglihatan komputer": "computer vision",
    "sistem pakar": "expert system",
    "penambangan data": "data mining",
    "keamanan siber": "cyber security",
    "komputasi awan": "cloud computing",
    "internet segala": "internet of things",
    "pembelajaran daring": "e-learning",
    "sistem informasi": "information system",
    "rekayasa perangkat lunak": "software engineering",
    # Health/Medical
    "kesehatan masyarakat": "public health",
    "ilmu kedokteran": "medical science",
    # Environment
    "ketahanan pangan": "food security",
    "energi terbarukan": "renewable energy",
    "perubahan iklim": "climate change",
    "pembangunan berkelanjutan": "sustainable development",
    "pencemaran lingkungan": "environmental pollution",
    "pengelolaan limbah": "waste management",
    "daur ulang": "recycling",
    "ekonomi sirkular": "circular economy",
    # Law/Social
    "hak asasi manusia": "human rights",
    "kebijakan publik": "public policy",
    "hukum pidana": "criminal law",
    "hukum perdata": "civil law",
    # Education
    "pembelajaran hybrid": "hybrid learning",
    "pembelajaran berbasis proyek": "project-based learning",
    "project based learning": "project-based learning",
    "sosial emosional": "social-emotional",
    "perkembangan sosial emosional": "social-emotional development",
    "anak usia dini": "early childhood",
    "pendidikan anak usia dini": "early childhood education",
    "paud": "preschool",
    "pasca pandemi": "post-pandemic",
    "pembelajaran jarak jauh": "distance learning",
    "model pembelajaran": "learning model",
    "efektivitas pembelajaran": "learning effectiveness",
    "hasil belajar": "learning outcomes",
    "kurikulum merdeka": "independent curriculum",
    # Food Science
    "pangan fungsional": "functional food",
    "indeks glikemik": "glycemic index",
    "senyawa bioaktif": "bioactive compound",
    "aktivitas antioksidan": "antioxidant activity",
    "tepung komposit": "composite flour",
    "serat pangan": "dietary fiber",
    "pati resisten": "resistant starch",
    "bebas gluten": "gluten free",
    "sifat organoleptik": "organoleptic properties",
    "daya terima": "consumer acceptance",
    "perkecambahan": "germination",
    "kacang kacangan": "legumes",
    "umbi umbian": "tubers",
    # Chemistry
    "senyawa kimia": "chemical compound",
    "bahan kimia": "chemical substance",
    "reaksi kimia": "chemical reaction",
    # Materials
    "sifat mekanik": "mechanical properties",
    "material komposit": "composite material",
    "lapisan tipis": "thin film",
    # Psychology
    "kesehatan mental": "mental health",
    "perkembangan kognitif": "cognitive development",
    "perilaku konsumen": "consumer behavior",
    "kecerdasan emosional": "emotional intelligence",
    "stres kerja": "work stress",
    # Business
    "manajemen sumber daya": "human resource management",
    "pemasaran digital": "digital marketing",
    "kewirausahaan": "entrepreneurship",
    "rantai pasok": "supply chain",
    "kepemimpinan": "leadership",
    # Sports
    "olahraga prestasi": "sports performance",
    "cedera olahraga": "sports injury",
    "aktivitas fisik": "physical activity",
    "kebugaran jasmani": "physical fitness",
    # Linguistics
    "penerjemahan": "translation",
    "analisis wacana": "discourse analysis",
    "kemampuan berbahasa": "language proficiency",
    # Geology
    "panas bumi": "geothermal",
    "bencana alam": "natural disaster",
    "air tanah": "groundwater",
    "pertambangan": "mining",
    # Pharmacology
    "obat tradisional": "herbal medicine",
    "uji klinis": "clinical trial",
    "efek samping": "adverse effect",
    "toksisitas": "toxicity",
    # Communication
    "media sosial": "social media",
    "hubungan masyarakat": "public relations",
    "komunikasi massa": "mass communication",
    "penyiaran": "broadcasting",
    # Tourism
    "pariwisata berkelanjutan": "sustainable tourism",
    "destinasi wisata": "tourist destination",
    "warisan budaya": "cultural heritage",
    "ekowisata": "ecotourism",
    # Mathematics/Stats
    "persamaan diferensial": "differential equation",
    "analisis statistik": "statistical analysis",
    "optimasi": "optimization",
}

# Common academic synonym expansion (English → additional terms)
_SYNONYMS = {
    # AI/CS
    "machine learning": "ml",
    "deep learning": "dl",
    "natural language processing": "nlp",
    "artificial intelligence": "ai",
    "internet of things": "iot",
    "cloud computing": "cloud",
    "data mining": "knowledge discovery",
    "neural network": "neural net",
    "computer vision": "image recognition",
    "reinforcement learning": "rl",
    "software engineering": "software development",
    "information retrieval": "search",
    "sentiment analysis": "opinion mining",
    "image classification": "image recognition",
    "object detection": "object recognition",
    # Environment/Climate
    "climate change": "global warming",
    "renewable energy": "green energy",
    "sustainable development": "sustainability",
    "circular economy": "circularity closed loop",
    # Health
    "public health": "epidemiology",
    "mental health": "psychological well-being",
    # Food Science
    "functional food": "nutraceutical functional ingredient",
    "glycemic index": "GI blood glucose response",
    "bioactive compound": "phytochemical phenolic flavonoid",
    "dietary fiber": "crude fiber soluble fiber",
    "antioxidant activity": "DPPH radical scavenging",
    "sensory evaluation": "organoleptic consumer acceptance",
    "gluten free": "celiac wheat alternative",
    # Chemistry
    "chemical reaction": "chemical synthesis",
    "catalyst": "catalysis catalytic",
    # Materials
    "composite material": "reinforced matrix",
    "mechanical properties": "tensile strength hardness",
    # Psychology
    "cognitive": "mental intellectual",
    "wellbeing": "wellness quality life",
    # Business
    "entrepreneurship": "startup venture",
    "supply chain": "logistics distribution",
    "human resource": "HR personnel management",
    # Sports
    "sports performance": "athletic performance",
    "physical activity": "exercise physical exercise",
    # Geoscience
    "geothermal": "geothermal energy hot spring",
    "groundwater": "aquifer subsurface water",
    # Pharmacology
    "herbal medicine": "traditional medicine phytomedicine",
    "toxicity": "toxic effect poisoning",
}


def expand_query(query: str) -> str:
    """Expand a search query with Indonesian→English translations and synonyms.

    - Detects Indonesian terms and adds English equivalents.
    - Adds common synonyms for academic terms.
    - Preserves existing boolean operators (AND, OR) if user already used them.
    - Returns expanded query string suitable for academic search APIs.
    """
    if not query or not query.strip():
        return query

    q_lower = query.lower().strip()

    # If user already uses boolean operators, respect their structure
    has_booleans = bool(re.search(r'\b(AND|OR|NOT)\b', query))

    terms_added: list[str] = []

    # Indonesian → English translation
    for id_term, en_term in _ID_TO_EN.items():
        if id_term in q_lower and en_term not in q_lower:
            terms_added.append(en_term)

    # Synonym expansion
    for base_term, syn in _SYNONYMS.items():
        if base_term in q_lower and syn not in q_lower:
            terms_added.append(syn)

    # Reverse synonym lookup (if user typed the short form, add the full form)
    # Use word-boundary matching to avoid false positives (e.g. "rl" matching in "learning")
    for base_term, syn in _SYNONYMS.items():
        # syn is the short form (e.g. "rl", "nlp")
        # Only match if syn appears as a whole word in the query
        pattern = rf'\b{re.escape(syn)}\b'
        if re.search(pattern, q_lower) and base_term not in q_lower:
            terms_added.append(base_term)

    if not terms_added:
        return query

    if has_booleans:
        # Append with OR to broaden results without breaking user's boolean logic
        expansion = " OR ".join(terms_added)
        return f"({query}) OR ({expansion})"
    else:
        # Simple space-separated append — most academic APIs treat spaces as AND
        return f"{query} {' '.join(terms_added)}"


def build_sub_queries(query: str) -> list[str]:
    """Decompose a flat query into focused sub-queries for better API search.
    
    Problem: Flat queries like "project based learning hybrid social emotional 
    early childhood development" sent to academic APIs as AND of all terms → 
    few/no results; as OR → massive noise. 
    
    Solution: Identify core concepts (multi-word terms) and build 2-3 focused
    sub-queries that combine complementary concepts. Each sub-query is short
    enough for AND matching but specific enough to filter noise.
    
    Returns list of sub-queries (3-5 items), prioritized by specificity.
    """
    q_lower = query.lower().strip().replace('-', ' ')
    words = q_lower.split()
    
    # ── Step 1: Identify known compound concepts ──
    # These are multi-word terms that should NOT be split into n-grams
    _KNOWN_CONCEPTS = [
        # Food science concepts (NEW — critical for functional food/legume/snack queries)
        "functional food", "functional foods", "functional snack", "snack bar",
        "energy bar", "protein bar", "nutrition bar", "granola bar",
        "low glycemic", "low glycaemic", "low glycemic index", "glycemic index",
        "glycemic response", "glikemik", "indeks glikemik",
        "legume flour", "legume protein", "cowpea", "mung bean", "kacang hijau",
        "kidney bean", "chickpea", "lentil", "soybean", "kedelai",
        "sweet potato", "ubi jalar", "cassava", "singkong", "taro", "talas",
        "yam", "gembili", "local tuber", "local legume", "umbi lokal",
        "composite flour", "tepung komposit", "germinated", "perkecambahan",
        "fermented", "fermentasi", "bioactive compound", "senyawa bioaktif",
        "antioxidant activity", "aktivitas antioksidan", "antioxidant capacity",
        "polyphenol content", "total phenolic", "total flavonoid",
        "dietary fiber", "serat pangan", "crude fiber", "resistant starch",
        "pati resisten", "in vitro starch digestibility", "glucose response",
        "protein digestibility", "mineral bioavailability",
        "nutritional composition", "proximate analysis", "proksimat",
        "amino acid profile", "fatty acid profile", "mineral content",
        "sensory evaluation", "organoleptic test", "hedonic test",
        "texture profile", "hardness", "chewiness", "water absorption",
        "oil absorption", "water holding capacity", "swelling power",
        "pasting properties", "gelatinization temperature", "thermal properties",
        "food extrusion", "snack extrusion", "baking process",
        "gluten free", "bebas gluten", "shelf life", "water activity",
        "microbial stability", "food safety",
        # Education concepts
        "project based learning", "problem based learning", "inquiry based learning",
        "hybrid learning", "blended learning", "online learning", "distance learning",
        "social emotional", "socio emotional", "social emotional learning",
        "early childhood", "early childhood education", "early childhood development",
        "preschool education", "kindergarten education", "early childhood care",
        "child development", "emotional development", "social development",
        "play based learning", "game based learning", "game based",
        "project based", "problem based", "inquiry based",
        "e learning", "mobile learning", "collaborative learning",
        "post pandemic", "post covid", "after pandemic",
        # AI/CS concepts
        "machine learning", "deep learning", "artificial intelligence",
        "natural language processing", "computer vision", "data mining",
        "neural network", "reinforcement learning", "object detection",
        "internet of things", "cloud computing", "cyber security",
        # Health concepts
        "heart disease", "public health", "mental health",
        # Environment concepts  
        "climate change", "renewable energy", "food security",
        "sustainable development", "air pollution", "water quality",
        "waste management", "carbon emission", "circular economy",
        # Chemistry concepts
        "chemical reaction", "chemical synthesis", "thin layer chromatography",
        "spectroscopy analysis", "molecular docking", "response surface",
        "ascorbic acid", "essential oil", "extraction method",
        # Materials concepts
        "mechanical properties", "tensile strength", "composite material",
        "thin film", "coating process", "corrosion resistance",
        # Psychology concepts
        "cognitive behavioral", "mental health", "social support",
        "self esteem", "quality of life", "coping strategy",
        "emotional regulation", "well being", "life satisfaction",
        # Business/Management concepts
        "human resource", "supply chain", "organizational commitment",
        "job satisfaction", "customer satisfaction", "brand loyalty",
        "digital marketing", "financial performance", "competitive advantage",
        "corporate social", "decision making",
        # Sports concepts
        "physical activity", "sports performance", "exercise training",
        "body composition", "muscle strength", "aerobic capacity",
        "high intensity interval", "high intensity interval training", "HIIT training",
        "resistance training", "flexibility training",
        # Linguistics concepts
        "speech recognition", "language acquisition", "second language",
        "foreign language", "discourse analysis", "translation quality",
        # Pharmacology/Medical concepts
        "clinical trial", "drug delivery", "adverse effect",
        "antimicrobial activity", "antibacterial activity", "cytotoxic activity",
        "wound healing", "oxidative stress", "lipid profile",
        "blood pressure", "body mass", "risk factor",
        # Geology/Geography concepts
        "land use", "remote sensing", "spatial analysis",
        "geographic information", "land cover", "climate variability",
        # Generic cross-domain academic terms
        "artificial neural", "statistical analysis", "case study",
        "literature review", "experimental study", "comparative analysis",
        "correlation analysis", "regression analysis", "factor analysis",
        "sensitivity analysis", "performance evaluation", "risk assessment",
    ]
    
    # Sort by length (longest first) to match compound terms before shorter ones
    _KNOWN_CONCEPTS.sort(key=lambda c: -len(c.split()))
    
    # Find concepts present in query — longest first, no overlaps, no duplicates
    found_concepts: list[str] = []
    consumed_positions: set[int] = set()  # word positions already claimed
    seen_concepts: set[str] = set()  # concept names already added
    for concept in _KNOWN_CONCEPTS:
        if concept in seen_concepts:
            continue
        # Skip if this shorter concept is already contained in a longer one we found
        if any(concept in c for c in seen_concepts if c != concept):
            continue
        concept_words = concept.split()
        n = len(concept_words)
        for i in range(len(words) - n + 1):
            window = " ".join(words[i:i+n])
            if window == concept:
                positions = set(range(i, i+n))
                if positions & consumed_positions:
                    continue
                found_concepts.append(concept)
                consumed_positions.update(positions)
                seen_concepts.add(concept)
                break
    
    # Remaining single words that aren't in any concept
    unconsumed_words = [words[i] for i in range(len(words)) if i not in consumed_positions]
    leftover = sorted([w for w in unconsumed_words if len(w) >= 4 and w not in {
        "the", "and", "for", "with", "from", "of", "to", "in", "on", "by",
        "a", "an", "is", "be", "are", "was", "were", "has", "have", "been",
        "that", "this", "which", "who", "what", "how", "why", "not", "but",
        "using", "study", "analysis", "approach", "method", "model", "system",
        "based", "effect", "impact", "review", "role", "case",
    }])
    
    if not found_concepts:
        # ── Fallback: auto-extract meaningful phrases from query ──
        # When no known concepts match, extract 2-3 word n-grams as
        # ad-hoc concepts. This prevents the flat query from being sent
        # to APIs with OR semantics (which produces massive noise).
        # Every domain benefits: chemistry, sports, tourism, linguistics,
        # pharmacology, etc.
        stop_words = {
            "the", "and", "for", "with", "from", "of", "to", "in", "on", "by",
            "a", "an", "is", "be", "are", "was", "were", "has", "have", "been",
            "that", "this", "which", "who", "what", "how", "why", "not", "but",
            "using", "study", "analysis", "approach", "method", "model", "system",
            "based", "effect", "impact", "review", "role", "case", "also", "can",
            "may", "its", "their", "our", "into", "or", "as", "at", "than",
            "more", "less", "new", "used", "two", "one", "well",
        }
        n = len(words)
        adhoc_concepts = []
        # Extract 3-grams first (most specific), then 2-grams
        for window_size in [3, 2]:
            for i in range(n - window_size + 1):
                phrase_words = words[i:i+window_size]
                # Skip if any word is a stop word
                if any(w in stop_words for w in phrase_words):
                    continue
                phrase = " ".join(phrase_words)
                if phrase not in adhoc_concepts:
                    adhoc_concepts.append(phrase)
                if len(adhoc_concepts) >= 4:
                    break
            if len(adhoc_concepts) >= 2:
                break
        if adhoc_concepts:
            # Build sub-queries from adhoc concepts
            sub_queries = []
            if len(adhoc_concepts) >= 3:
                sub_queries.append(" ".join(adhoc_concepts[:3]))
                sub_queries.append(" ".join(adhoc_concepts[1:4]) if len(adhoc_concepts)>=4 else " ".join(adhoc_concepts[1:]))
            elif len(adhoc_concepts) == 2:
                sub_queries.append(" ".join(adhoc_concepts))
                sub_queries.append(adhoc_concepts[0])
            else:
                sub_queries.append(adhoc_concepts[0])
            # Deduplicate + add original query
            seen_sq = set()
            unique_sq = []
            for sq in sub_queries:
                if sq and sq not in seen_sq:
                    seen_sq.add(sq)
                    unique_sq.append(sq)
            if query not in seen_sq:
                unique_sq.append(query)
            return unique_sq[:5]
        return [query]
    
    # ── Step 2: Build focused sub-queries ──
    # Strategy: each sub-query = 2-3 core concepts
    sub_queries = []
    n_concepts = len(found_concepts)
    
    if n_concepts >= 3:
        # Group 1: primary concepts (first 2-3)
        sub_queries.append(" ".join(found_concepts[:3]))
        # Group 2: secondary concepts (shift by 1)
        sub_queries.append(" ".join(found_concepts[1:4]))
        # Group 3: first + last (broad but anchored)
        if n_concepts >= 4:
            sub_queries.append(f"{found_concepts[0]} {found_concepts[-1]}")
    elif n_concepts == 2:
        # Two concepts: combine them + add leftover for specificity
        if leftover:
            sub_queries.append(f"{found_concepts[0]} {found_concepts[1]} {leftover[0]}")
        sub_queries.append(f"{found_concepts[0]} {found_concepts[1]}")
    else:
        # Only 1 concept: combine with leftover
        if leftover:
            sub_queries.append(f"{found_concepts[0]} {leftover[0]} {leftover[1] if len(leftover)>1 else ''}".strip())
        sub_queries.append(found_concepts[0])
    
    # Add a synonym-expanded variant for breadth
    # Use domain-specific synonyms based on detected concepts
    _FOOD_SCIENCE_SYNS = {
        "functional food": "nutraceutical functional ingredients bioactive",
        "snack bar": "energy bar protein bar granola bar nutrition bar",
        "low glycemic": "low glycaemic glycemic index GI blood glucose",
        "legume flour": "legume protein bean flour pulse flour",
        "local tuber": "sweet potato cassava yam taro indigenous tuber",
        "local legume": "cowpea mung bean kidney bean indigenous legume",
        "composite flour": "blended flour mixed flour composite dough",
        "germinated": "sprouted germination malted",
        "fermented": "fermentation microbial lactic acid LAB",
        "bioactive compound": "phenolic flavonoid antioxidant phytochemical",
        "dietary fiber": "crude fiber carbohydrate soluble fiber insoluble fiber",
        "resistant starch": "slowly digestible starch RS glycemic response",
        "sensory evaluation": "organoleptic test hedonic test consumer acceptance",
        "protein digestibility": "in vitro digestion protein quality amino acid",
        "food extrusion": "extrusion cooking expanded snack twin screw",
    }
    _EDUCATION_SYNS = {
        "project based learning": "PBL project approach",
        "social emotional": "socioemotional SEL emotional regulation",
        "early childhood": "preschool prekindergarten ECE",
        "hybrid learning": "blended learning mixed-mode",
        "post pandemic": "post-COVID after pandemic recovery",
    }
    # Merge: food science takes priority for synonym expansion
    _ALL_DOMAIN_SYNS = {**_FOOD_SCIENCE_SYNS, **_EDUCATION_SYNS}
    syn_variant_parts = []
    for concept in found_concepts[:2]:
        if concept in _ALL_DOMAIN_SYNS:
            syn_variant_parts.append(_ALL_DOMAIN_SYNS[concept])
        else:
            syn_variant_parts.append(concept)
    if syn_variant_parts:
        sub_queries.append(" ".join(syn_variant_parts))
    
    # Deduplicate and limit to 5
    seen = set()
    unique = []
    for sq in sub_queries:
        sq_clean = sq.strip()
        if sq_clean and sq_clean not in seen:
            seen.add(sq_clean)
            unique.append(sq_clean)
    
    # Always include original query as last fallback
    if query not in seen:
        unique.append(query)
    
    return unique[:5]


def _detect_topics(query: str) -> set[str]:
    q = f" {(query or '').lower().strip()} "
    found: set[str] = set()
    for topic, kws in _TOPIC_KEYWORDS.items():
        if any(f" {k.strip()} " in q for k in kws):
            found.add(topic)
    # Also check partial matches for longer keywords
    q_stripped = (query or "").lower().strip()
    for topic, kws in _TOPIC_KEYWORDS.items():
        if topic in found:
            continue
        for k in kws:
            k_stripped = k.strip()
            if len(k_stripped) >= 5 and k_stripped in q_stripped:
                found.add(topic)
                break
    if not found:
        found.add("any")
    return found


def pick_sources_for_topic(query: str, explicit: list[str] | None = None) -> list[str]:
    """Pilih sumber yang relevan utk query. Kalau caller spesifik
    (`explicit=[…]`), dipakai apa adanya (subset dari ALL)."""
    if explicit:
        return [s for s in explicit if s in ALL]
    topics = _detect_topics(query)
    chosen = []
    for src, src_topics in SOURCE_TOPICS.items():
        if src_topics & topics or "any" in src_topics:
            chosen.append(src)
    if not chosen:
        chosen = list(ALL.keys())
    return chosen


def is_predatory(paper: Paper) -> bool:
    if not paper.publisher:
        return False
    p = paper.publisher.lower()
    return any(bad in p for bad in PREDATORY_PUBLISHERS)


_PUNCT_RE = re.compile(r"[^\w\s]")


def _norm_title(t: str | None) -> str:
    """Normalize title for dedup — same algorithm as db_cache.normalize_title."""
    s = (t or "").lower().strip()
    # Match db_cache.normalize_title: strip all non-alphanumeric
    return re.sub(r'[^a-z0-9]+', '', s)


def fetch_from_source(name: str, query: str, limit: int, filters: dict | None) -> list[Paper]:
    module = ALL[name]
    with get_client() as client:
        try:
            return list(module.search(client, query, limit=limit, filters=filters))
        except Exception as e:
            log.warning("SLR fetch [%s] error: %s", name, e)
            return []


def fetch_titles(
    query: str,
    sources: list[str] | None = None,
    limit_per_source: int = DEFAULT_LIMIT_PER_SOURCE,
    filters: dict | None = None,
    max_total: int | None = None,
    skip_predatory: bool = True,
    progress_cb=None,
    source_save_cb=None,
    use_cache: bool = True,
) -> list[Paper]:
    """Tahap 1 — DB FIRST, lalu API kalau kurang.

    Redesign (2026-06-17):
    1. Check DB cache for target papers. If enough → skip API entirely (<1s).
    2. If DB insufficient → fetch APIs in parallel with:
       - Global timeout: 15 min hard stop
       - Per-fetcher timeout: 30 s without results = skip
       - Early stop: target reached → stop fetching
    3. Dedup (round-robin across sources).

    source_save_cb: Callable[[list[Paper]], None] — called per-source after
    fetch for streaming save to DB (API path only).

    use_cache: If True, check DB first before fetching from API.
    """
    from . import db_cache

    sources = sources or pick_sources_for_topic(query)
    sources = [s for s in sources if s in ALL]
    if not sources:
        return []

    # Expand query with Indonesian→English translations and synonyms
    expanded = expand_query(query)
    if expanded != query:
        log.debug("Query expanded: %r → %r", query, expanded)

    # Build focused sub-queries for better API recall
    sub_queries = build_sub_queries(expanded)
    if len(sub_queries) > 1:
        log.info("Using %d sub-queries for fetch: %s", len(sub_queries), sub_queries[:3])
    else:
        sub_queries = [expanded]

    # Target: how many papers we want for scoring (passed as max_total)
    target = max_total or limit_per_source * len(sources)
    new_papers_count = 0  # tracks API-fetched papers (0 in DB-only path)

    # ── Step 1: DB FIRST ─────────────────────────────────────────────────
    cached_papers: list[Paper] = []
    if use_cache:
        try:
            cached_papers = db_cache.search_papers(
                query=expanded,
                limit=target * 2,  # fetch extra for dedup headroom
                sources=sources,
            )
            log.info("Cache hit: %d papers from DB (target=%d)", len(cached_papers), target)
        except Exception as e:
            log.warning("DB cache lookup failed: %s", e)
            cached_papers = []

    # Enough from DB → SKIP API entirely
    if len(cached_papers) >= target:
        log.info(
            "DB has enough papers (%d >= %d), skipping API fetch",
            len(cached_papers), target,
        )
        if progress_cb:
            progress_cb("fetching", {
                "sources": sources, "started": 0, "total": len(sources),
                "from_cache": True,
            })

        all_papers = list(cached_papers)
        # DB path: no source_save_cb needed (papers already in DB cache)
        # Dedup + save_cb in pipeline still run normally
    else:
        # ── Step 2: API FETCH (DB insufficient) ──────────────────────────
        GLOBAL_TIMEOUT = 180  # 3 min hard stop
        PER_FETCHER_TIMEOUT = 30  # 30 s per source

        api_start = time.time()
        deadline = api_start + GLOBAL_TIMEOUT

        workers = min(MAX_WORKERS, max(1, len(sources)))
        all_papers = list(cached_papers)  # start with cached
        completed = 0
        new_papers_count = 0
        timed_out_sources: list[str] = []
        error_sources: list[str] = []

        if progress_cb:
            progress_cb("fetching", {
                "sources": sources, "started": 0, "total": len(sources),
            })

        with ThreadPoolExecutor(max_workers=workers) as ex:
            # Submit multiple sub-queries per source for better recall
            futures = {}
            per_sub_limit = max(limit_per_source // len(sub_queries), 10)
            for name in sources:
                for sq in sub_queries:
                    fut = ex.submit(
                        fetch_from_source, name, sq, per_sub_limit, filters
                    )
                    futures[fut] = (name, sq)

            try:
                while True:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        log.warning("SLR global timeout reached, stopping fetch")
                        break

                    pending = [f for f in futures if not f.done()]
                    if not pending:
                        break  # all done

                    try:
                        batch = list(as_completed(
                            pending,
                            timeout=min(remaining, PER_FETCHER_TIMEOUT),
                        ))
                    except (TimeoutError, Exception) as e:
                        # Python 3.10: concurrent.futures.TimeoutError ≠ TimeoutError
                        # Catch both to handle per-fetcher timeout
                        if "TimeoutError" not in type(e).__name__ and not isinstance(e, TimeoutError):
                            raise
                        # Per-fetcher timeout: cancel slow sources
                        still_pending = [f for f in futures if not f.done()]
                        for f in still_pending:
                            name, sq = futures[f]
                            f.cancel()
                            timed_out_sources.append(name)
                            log.warning(
                                "SLR fetch [%s] timed out after %ds, skipping",
                                name, PER_FETCHER_TIMEOUT,
                            )
                        # BUG-6.1: continue collecting from completed futures
                        # instead of breaking out of the entire loop
                        continue

                    for fut in batch:
                        name, sq = futures[fut]
                        try:
                            papers = fut.result(timeout=0) or []
                        except TimeoutError:
                            timed_out_sources.append(name)
                            log.warning("SLR fetch [%s] timed out, skipping", name)
                            continue
                        except Exception as e:
                            error_sources.append(name)
                            log.warning("SLR future [%s] error: %s", name, e)
                            papers = []

                        completed += 1
                        new_papers_count += len(papers)

                        if progress_cb:
                            progress_cb("source_done", {
                                "source": name,
                                "count": len(papers),
                                "completed": completed,
                                "total": len(sources),
                            })

                        if source_save_cb and papers:
                            try:
                                source_save_cb(papers)
                            except Exception as e:
                                log.warning(
                                    "slr.source_save_cb failed for %s: %s",
                                    name, e,
                                )

                        all_papers.extend(papers)

                        # Early stop: enough papers collected
                        if target and len(all_papers) >= target:
                            log.info(
                                "Early stop: %d papers >= target %d",
                                len(all_papers), target,
                            )
                            for f in futures:
                                if not f.done():
                                    f.cancel()
                            break
                    else:
                        continue  # inner for completed normally → next while iter
                    break  # inner for broke (early stop) → exit while

            except BaseException:
                for f in futures:
                    f.cancel()
                raise

        elapsed = time.time() - api_start
        log.info(
            "SLR API fetch done: %d new papers, %d completed, "
            "%d timed out, %d errors in %.1fs",
            new_papers_count, completed,
            len(timed_out_sources), len(error_sources), elapsed,
        )

    # ── Step 3: Dedup + round-robin ──────────────────────────────────────
    by_source: dict[str, list[Paper]] = {}
    for p in all_papers:
        by_source.setdefault(p.source, []).append(p)

    seen_keys: set[str] = set()
    seen_titles: set[str] = set()
    results: list[Paper] = []
    queues = [list(reversed(by_source[name])) for name in sorted(by_source.keys())]

    while queues:
        next_queues = []
        for q in queues:
            if not q:
                continue
            p = q.pop()
            key = p.dedup_key()
            title_key = _norm_title(p.title)
            if key in seen_keys:
                if q:
                    next_queues.append(q)
                continue
            if title_key and title_key in seen_titles:
                if q:
                    next_queues.append(q)
                continue
            if skip_predatory and is_predatory(p):
                if q:
                    next_queues.append(q)
                continue
            seen_keys.add(key)
            if title_key:
                seen_titles.add(title_key)
            results.append(p)
            if max_total and len(results) >= max_total:
                break
            if q:
                next_queues.append(q)
        queues = next_queues

    if progress_cb:
        progress_cb("dedup_done", {"count": len(results)})

    # ── Step 4: Save new papers to DB cache (API path only) ──────────────
    if use_cache and new_papers_count > 0:
        try:
            saved = db_cache.save_papers(results, source=None)
            log.info("Saved %d papers to DB cache", saved)
        except Exception as e:
            log.warning("Failed to save papers to DB: %s", e)

    # ── Step 5: Complete SLR job ─────────────────────────────────────────
    # job tracking removed from fetch_titles — handled by pipeline/worker

    # Post-sort by year desc (newest first) after relevance fetch
    results.sort(key=lambda p: p.year or 0, reverse=True)

    return results



# Backward-compat alias used by old call sites.
fetch_all = fetch_titles
