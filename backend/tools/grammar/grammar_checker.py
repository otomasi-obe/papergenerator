"""
Grammar Checker
===============
Comprehensive grammar, spelling, and style checker — fully program-based (no LLM).

Engine stack (all optional, all lazy-loaded):
  1. LanguageTool (https://languagetool.org) via `language_tool_python`
     - Public HTTP API, no API key, supports 20+ languages including en-US, en-GB, id-ID.
  2. pyspellchecker  (used by sibling spell_checker.py) — dictionary-based spelling.
  3. Built-in regex rules (kept from the original implementation):
       - _ACADEMIC_MISSPELLINGS (314+ entries)
       - _COMMON_GRAMMAR_ERRORS (subject-verb agreement, confused words, etc.)
       - _WORDY_PHRASES
       - _INDONESIAN_MISSPELLINGS (new — fills the id-ID gap noted in grammar.md)
       - _INDONESIAN_GRAMMAR_ERRORS (new)
       - _INDONESIAN_WORDY_PHRASES (new)
  4. Readability (10 formulas) — kept verbatim.
  5. Optional: NLTK punkt sentence tokenizer (graceful fallback).

Backwards-compatible:
  - `check(text, domain=...)` still works (domain is preserved in output).
  - `ai_enhance()` is kept as a thin wrapper but no longer used internally.
  - CLI now supports `--mode`, `--language`, `--json` in addition to the
    original `--text/--file/--enhance/--domain/--suggest` flags.

Usage:
    from tools.grammar.grammar_checker import GrammarChecker
    g = GrammarChecker()
    r = g.check("She go to the market.", mode="all", language="en-US")
    r2 = g.check("Saya yg mau ketemu, tp dia blm dateng.", language="id-ID")
"""

import os
import re
import json
import math
import logging
import threading
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from collections import Counter

import requests
from dotenv import load_dotenv
from utils.ai_tools.model_config import get_primary_chat_model

# ── Load .env ───────────────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# CONSTANTS — built-in rule layers
# ════════════════════════════════════════════════════════════════════════════

_ACADEMIC_MISSPELLINGS = {
    "analysing": "analyzing",
    "modelling": "modeling",
    "labelled": "labeled",
    "focussed": "focused",
    "behaviour": "behavior",
    "colour": "color",
    "centre": "center",
    "theatre": "theater",
    "aluminium": "aluminum",
    "acknowledgement": "acknowledgment",
    "judgement": "judgment",
    "alot": "a lot",
    "alotof": "a lot of",
    "could of": "could have",
    "would of": "would have",
    "should of": "should have",
    "might of": "might have",
    "must of": "must have",
    "irregardless": "regardless",
    "concious": "conscious",
    "recieve": "receive",
    "acheive": "achieve",
    "beleive": "believe",
    "seperate": "separate",
    "definately": "definitely",
    "occured": "occurred",
    "occuring": "occurring",
    "ocurred": "occurred",
    "priviledge": "privilege",
    "wich": "which",
    "thier": "their",
    "untill": "until",
    "accomodate": "accommodate",
    "accomodation": "accommodation",
    "commitee": "committee",
    "embarass": "embarrass",
    "occassion": "occasion",
    "neccessary": "necessary",
    "reccomend": "recommend",
    "recomend": "recommend",
    "refered": "referred",
    "refering": "referring",
    "conceed": "concede",
    "supercede": "supersede",
    "approximatly": "approximately",
    "independant": "independent",
    "dependancy": "dependency",
    "significent": "significant",
    "significently": "significantly",
    "convulutional": "convolutional",
    "convulution": "convolution",
    "appoximate": "approximate",
    "approxmation": "approximation",
    "algorithim": "algorithm",
    "algorithims": "algorithms",
    "optimzation": "optimization",
    "paramter": "parameter",
    "paramters": "parameters",
    "parrallel": "parallel",
    "impliment": "implement",
    "implimentation": "implementation",
    "integreated": "integrated",
    "neurual": "neural",
    "transfomer": "transformer",
    "transfomers": "transformers",
    "backpropogation": "backpropagation",
    "preceed": "precede",
    "procede": "proceed",
    "miniscule": "minuscule",
    "millenium": "millennium",
    "mispell": "misspell",
    "mispelled": "misspelled",
    "maintainance": "maintenance",
    "calender": "calendar",
    "consciencious": "conscientious",
    "dimenional": "dimensional",
    "dimentional": "dimensional",
    "distribtuion": "distribution",
    "distribtion": "distribution",
    "eighenvalues": "eigenvalues",
    "eigenvactor": "eigenvector",
    "entitity": "entity",
    "enviornment": "environment",
    "envrionment": "environment",
    "equivelant": "equivalent",
    "equivilant": "equivalent",
    "evalulate": "evaluate",
    "existance": "existence",
    "experiement": "experiment",
    "experiemental": "experimental",
    "extracttion": "extraction",
    "feasable": "feasible",
    "foward": "forward",
    "futhermore": "furthermore",
    "gradiant": "gradient",
    "heterogenous": "heterogeneous",
    "hiearchical": "hierarchical",
    "homogenous": "homogeneous",
    "hypothosis": "hypothesis",
    "idnetify": "identify",
    "illistrate": "illustrate",
    "immediatly": "immediately",
    "influance": "influence",
    "inital": "initial",
    "intial": "initial",
    "iterrate": "iterate",
    "knowlege": "knowledge",
    "langauge": "language",
    "logrithm": "logarithm",
    "logrithmic": "logarithmic",
    "managment": "management",
    "metholodogy": "methodology",
    "methodolgy": "methodology",
    "minimium": "minimum",
    "necesary": "necessary",
    "noice": "noise",
    "noneliniar": "nonlinear",
    "nontheless": "nonetheless",
    "normall": "normally",
    "noticable": "noticeable",
    "noticably": "noticeably",
    "occurance": "occurrence",
    "ommission": "omission",
    "oppertunity": "opportunity",
    "optimise": "optimize",
    "orgininal": "original",
    "overfiting": "overfitting",
    "parallell": "parallel",
    "perfomance": "performance",
    "performence": "performance",
    "phenomenom": "phenomenon",
    "posess": "possess",
    "posession": "possession",
    "practicle": "practical",
    "preceeding": "preceding",
    "prefered": "preferred",
    "preferrably": "preferably",
    "presense": "presence",
    "probabilty": "probability",
    "prunning": "pruning",
    "quadradic": "quadratic",
    "quantatitive": "quantitative",
    "quatitative": "quantitative",
    "questionaire": "questionnaire",
    "randomn": "random",
    "realease": "release",
    "realtion": "relation",
    "realtionship": "relationship",
    "reccomendation": "recommendation",
    "reconize": "recognize",
    "recusion": "recursion",
    "redundency": "redundancy",
    "referrence": "reference",
    "regresion": "regression",
    "relevence": "relevance",
    "reliablity": "reliability",
    "reproducability": "reproducibility",
    "reproducable": "reproducible",
    "reson": "reason",
    "responce": "response",
    "responsability": "responsibility",
    "resulant": "resultant",
    "reult": "result",
    "reproduceable": "reproducible",
    "roubust": "robust",
    "ruobust": "robust",
    "scedule": "schedule",
    "scientfic": "scientific",
    "sentance": "sentence",
    "shold": "should",
    "signficant": "significant",
    "simultanous": "simultaneous",
    "soley": "solely",
    "sophistocated": "sophisticated",
    "spacial": "spatial",
    "specfic": "specific",
    "specifc": "specific",
    "statisitical": "statistical",
    "statistcal": "statistical",
    "stocastic": "stochastic",
    "stochastical": "stochastic",
    "stratagy": "strategy",
    "stregnth": "strength",
    "strucutre": "structure",
    "substract": "subtract",
    "succesful": "successful",
    "succesfully": "successfully",
    "sucess": "success",
    "sucessful": "successful",
    "sufficent": "sufficient",
    "suposably": "supposedly",
    "surley": "surely",
    "surounded": "surrounded",
    "sytem": "system",
    "tabel": "table",
    "tahn": "than",
    "teh": "the",
    "temperture": "temperature",
    "tendacy": "tendency",
    "theoratical": "theoretical",
    "theoritical": "theoretical",
    "therefor": "therefore",
    "threshhold": "threshold",
    "toghether": "together",
    "tradionally": "traditionally",
    "traning": "training",
    "transcision": "transition",
    "transfered": "transferred",
    "transfering": "transferring",
    "transformtion": "transformation",
    "trought": "through",
    "turnning": "turning",
    "typicaly": "typically",
    "uneccesary": "unnecessary",
    "unfortunatly": "unfortunately",
    "uniqe": "unique",
    "univeristy": "university",
    "unrealible": "unreliable",
    "unsuperised": "unsupervised",
    "unuseable": "unusable",
    "usally": "usually",
    "useable": "usable",
    "usefull": "useful",
    "vailidty": "validity",
    "vairable": "variable",
    "vairance": "variance",
    "vaildate": "validate",
    "vaildation": "validation",
    "varaiance": "variance",
    "variablity": "variability",
    "varification": "verification",
    "verfication": "verification",
    "verifiy": "verify",
    "verision": "version",
    "versitile": "versatile",
    "vetween": "between",
    "vilian": "villain",
    "visable": "visible",
    "visability": "visibility",
    "visualisation": "visualization",
    "vitually": "virtually",
    "vocabluary": "vocabulary",
    "volumn": "volume",
    "volumne": "volume",
    "vrey": "very",
    "vulnerablity": "vulnerability",
    "warmup": "warm-up",
    "whcih": "which",
    "wheter": "whether",
    "wih": "with",
    "willingess": "willingness",
    "withh": "with",
    "witht": "with",
    "wordl": "world",
    "worsest": "worst",
    "writen": "written",
    "writting": "writing",
    "wronly": "wrongly",
    "yeild": "yield",
    "zeebra": "zebra",
    "zeroeth": "zeroth",
    "intialization": "initialization",
    "reasearch": "research",
    "intresting": "interesting",
    "wether": "whether",
}

_COMMON_GRAMMAR_ERRORS = [
    (r'\b(they|we|these|those|the authors|the results)\s+(is)\b', r'\1 are', 'subject-verb agreement'),
    (r'\b(he|she|it|this|that|the study|the paper|the model)\s+(are)\b', r'\1 is', 'subject-verb agreement'),
    (r'\b(The|the)\s+(\w+)\s+(of|for|in)\s+(\w+)\s+(are)\b', r'\1 \2 \3 \4 is', 'subject-verb agreement'),
    (r'\b(have|has)\s+(beened|haden|wenten)\b', r'\1 been', 'verb tense'),
    (r"\b(ain't|don't|doesn't|didn't|won't|can't|couldn't|wouldn't|shouldn't|needn't)\s+(no|none|nothing|nobody|nowhere|never)\b",
     r'\1 any', 'double negative'),
    (r'\bits\s+(their|they\'re)\b', 'its', 'confused word'),
    (r'\byour\s+(probably|welcome)\b', "you're \1", 'confused word'),
    (r"\byou're\s+(\w+)\s+(is|are|was|were)\b", r'your \1', 'confused word'),
    (r'\b(there)\s+(is|are|was|were|has|have)\s+\w+\s+\2\b', r'their \2', 'confused word'),
    (r'\b(is|was|are|were)\s+(important|crucial|essential|significant|key|major)\s+(part|aspect|factor|role|component)\b',
     r'\1 a \2 \3', 'missing article'),
]

_PASSIVE_VOICE_RE = re.compile(r'\b(am|is|are|was|were|been|being)\s+\w+ed\b', re.IGNORECASE)

_WORDY_PHRASES = {
    r'\bin order to\b': 'to',
    r'\bdue to the fact that\b': 'because',
    r'\bin spite of the fact that\b': 'although',
    r'\bin the event that\b': 'if',
    r'\bwith the exception of\b': 'except',
    r'\bas a matter of fact\b': 'in fact',
    r'\bin the process of\b': 'during',
    r'\bthe majority of\b': 'most',
    r'\ba number of\b': 'several',
    r'\bthe presence of\b': '',
    r'\bwhether or not\b': 'whether',
    r'\bin the vicinity of\b': 'near',
    r'\bat this point in time\b': 'now',
    r'\bprior to\b': 'before',
    r'\bsubsequent to\b': 'after',
    r'\bhas the ability to\b': 'can',
    r'\bis able to\b': 'can',
    r'\bis capable of\b': 'can',
}


# ════════════════════════════════════════════════════════════════════════════
# Indonesian (id-ID) rule layer  — fills the gap noted in PaperRiset/toolsRef/grammar.md
# ════════════════════════════════════════════════════════════════════════════

# Informal chat / SMS abbreviations frequently used in formal writing.
_INDONESIAN_MISSPELLINGS = {
    "yg": "yang",
    "tdk": "tidak",
    "gak": "tidak",
    "ga": "tidak",
    "gk": "tidak",
    "ngga": "tidak",
    "enggak": "tidak",
    "sdh": "sudah",
    "udah": "sudah",
    "udh": "sudah",
    "blm": "belum",
    "blom": "belum",
    "skrg": "sekarang",
    "skg": "sekarang",
    "skr": "sekarang",
    "skrng": "sekarang",
    "kmrn": "kemarin",
    "kmren": "kemarin",
    "bsk": "besok",
    "besok": "besok",
    "jga": "juga",
    "tp": "tapi",
    "tapi": "tapi",
    "klo": "kalau",
    "kalo": "kalau",
    "klu": "kalau",
    "krn": "karena",
    "karna": "karena",
    "krna": "karena",
    "soalnya": "karena",
    "spy": "supaya",
    "sprt": "seperti",
    "kayak": "seperti",
    "kyk": "seperti",
    "ky": "seperti",
    "msh": "masih",
    "msi": "masih",
    "sm": "sama",
    "sma": "sama",
    "utk": "untuk",
    "bngt": "banget",
    "bgd": "banget",
    "trs": "terus",
    "trus": "terus",
    "dgn": "dengan",
    "dg": "dengan",
    "ama": "dengan",
    "emang": "memang",
    "emg": "memang",
    "org": "orang",
    "orng": "orang",
    "shg": "sehingga",
    "bhw": "bahwa",
    "krng": "kurang",
    "byk": "banyak",
    "bnyk": "banyak",
    "trhdp": "terhadap",
    "thd": "terhadap",
    "dr": "dari",
    "dri": "dari",
    "dlm": "dalam",
    "dlam": "dalam",
    "pd": "pada",
    "pda": "pada",
    "kpd": "kepada",
    "bbrp": "beberapa",
    "beberpa": "beberapa",
    "tsb": "tersebut",
    "tsbt": "tersebut",
    "ybs": "yang bersangkutan",
    "sbg": "sebagai",
    "sbgi": "sebagai",
    "mnjadi": "menjadi",
    "menjdi": "menjadi",
    "trjd": "terjadi",
    "terjdi": "terjadi",
    "mhn": "mohon",
    "mhon": "mohon",
    "slm": "selama",
    "selma": "selama",
    "smua": "semua",
    "smu": "semua",
    "skl": "sekali",
    "skali": "sekali",
    "jg": "juga",
    "hrs": "harus",
    "harus": "harus",
    "bisa": "dapat",
    "bs": "dapat",
    "bsa": "dapat",
    "kdg": "kadang",
    "kdang": "kadang",
    "kpn": "kapan",
    "knp": "kenapa",
    "knpa": "kenapa",
    "gimana": "bagaimana",
    "gmn": "bagaimana",
    "gmana": "bagaimana",
    "brp": "berapa",
    "brpa": "berapa",
    "bln": "bulan",
    "thn": "tahun",
    "th": "tahun",
    "hr": "hari",
    "hri": "hari",
    "mhs": "mahasiswa",
    "mahsiswa": "mahasiswa",
    "dosen": "dosen",
    "dsn": "dosen",
    "kampus": "kampus",
    "kmpus": "kampus",
    "skripsi": "skripsi",
    "skrip": "skripsi",
    "bgt": "sangat",
}

# Indonesian grammar / usage patterns.
_INDONESIAN_GRAMMAR_ERRORS = [
    # "di" as preposition should be spelled terpisah; "di" as prefix of verb is joined.
    # Common slip: "disana" → "di sana", "dikampus" → "di kampus".
    (r'\b(di)(sana|situ|sini|kantor|rumah|kampus|kelas|ruang|jakarta|bandung|surabaya)\b',
     r'di \2', 'preposition spacing'),
    (r'\b(ke)(sana|situ|sini|kantor|rumah|kampus|kelas|jakarta|bandung)\b',
     r'ke \2', 'preposition spacing'),
    # "yang" sometimes duplicated.
    (r'\b(yang)\s+\w+(?:\s+\w+){0,4}\s+(yang)\b', r'\1 \2', 'redundant yang'),
    # "para" should not precede "se-", "semua", "seluruh" (redundant).
    (r'\bpara\s+(semua|seluruh|se-)\b', r'\1', 'redundant para'),
    # "sedangkan" sometimes misspelled "sedangakan".
    (r'\bsedangakan\b', 'sedangkan', 'typo'),
    (r'\bkarena\s+nya\b', 'karenanya', 'typo'),
    (r'\b(\w+)nya\s+(jadi|merupakan|adalah)\b', r'\1 \2', 'affix -nya spacing'),
    # "dimana" / "kepada" / "kepadah" misuse.
    (r'\bdimana\b', 'di mana', 'word spelling'),
    (r'\bdarimana\b', 'dari mana', 'word spelling'),
    (r'\bketika\b', 'ketika', 'word spelling'),
    # "diantara" should be "di antara" by PUEBI.
    (r'\bdiantara\b', 'di antara', 'preposition spacing'),
    (r'\bkeatas\b', 'ke atas', 'preposition spacing'),
    (r'\bke bawah\b', 'ke bawah', 'preposition spacing'),
    (r'\bdidepan\b', 'di depan', 'preposition spacing'),
    (r'\bdibelakang\b', 'di belakang', 'preposition spacing'),
    (r'\bdidalam\b', 'di dalam', 'preposition spacing'),
    (r'\bdiluar\b', 'di luar', 'preposition spacing'),
    # "ataupun" misuse after "baik".
    (r'\bbaik\s+(dan|atau)\s+(juga|ataupun)\b', r'baik \1 \2', 'parallelism'),
]

_INDONESIAN_WORDY_PHRASES = {
    r'\b pada saat yang bersamaan\b': 'pada saat itu',
    r'\b pada waktu yang bersamaan\b': 'pada saat itu',
    r'\b tidak hanya \.\.\. tetapi juga\b': 'tidak hanya \.\.\. tetapi juga',
    r'\b di dalam \b': 'di ',
    r'\b di dalam\b': 'di',
    r'\b bagi \b': 'untuk ',
    r'\b akan tetapi\b': 'tetapi',
    r'\b namun demikian\b': 'namun',
    r'\b oleh karena itu\b': 'karena itu',
    r'\b oleh sebab itu\b': 'karena itu',
    r'\b yang mana\b': 'yang',
    r'\b hal tersebut\b': 'itu',
    r'\b hal ini\b': 'ini',
    r'\b melakukan \w+an\b': r'meng\1',  # rough: "melakukan pengujian" -> "menguji"
    r'\b pada dasarnya\b': 'pada dasarnya',
    r'\b sama sekali tidak\b': 'tidak',
    r'\b yang dimana\b': 'yang',
    r'\b yang apabila\b': 'apabila',
    r'\b dalam rangka\b': 'untuk',
    r'\b guna untuk\b': 'untuk',
}

# Word-set that's always correct in ID (to avoid flagging common words in spell layer).
_INDONESIAN_COMMON_WORDS = {
    "yang", "dan", "atau", "tetapi", "tapi", "namun", "sedangkan", "karena",
    "karna", "kalau", "jika", "apabila", "bila", "dengan", "tanpa", "untuk",
    "kepada", "terhadap", "dari", "ke", "di", "pada", "dalam", "luar", "atas",
    "bawah", "depan", "belakang", "samping", "antara", "sama", "lain",
    "ini", "itu", "sini", "situ", "sana", "saya", "aku", "kamu", "anda",
    "dia", "mereka", "kita", "kami", "kalian", "beliau", "nya", "mu", "ku",
    "tidak", "bukan", "belum", "sudah", "telah", "akan", "sedang", "masih",
    "bisa", "dapat", "mampu", "boleh", "harus", "perlu", "hendak", "ingin",
    "mau", "tahu", "tidak", "tahukah", "apakah", "bagaimana", "kapan",
    "dimana", "kemanakah", "kenapa", "mengapa", "siapa", "apa", "mana",
    "berapa", "beberapa", "banyak", "sedikit", "semua", "seluruh", "sebagian",
    "setiap", "tiap", "semua", "sangat", "amat", "terlalu", "cukup",
    "agak", "sekali", "banget", "lagi", "juga", "pun", "saja", "hanya",
    "cuma", "mungkin", "barangkali", "pasti", "tentu", "rasanya", "seperti",
    "umpama", "bagaikan", "ibarat", "yaitu", "yakni", "adalah", "merupakan",
    "yaitu", "ia", "beliau", "tersebut", "demikian", "begitu", "begitupun",
    "meskipun", "walaupun", "sekalipun", "biarpun", "andaikata", "andai",
    "agar", "supaya", "untuk", "demi", "biar", "biarlah", "mari", "ayo",
    "silakan", "silahkan", "maaf", "mohon", "tolong", "terima", "kasih",
    "selamat", "salam", "halo", "hai", "ya", "tidak", "benar", "salah",
    "benar", "betul", "betul", "begitu", "demikian", "ya", "baik", "oke",
}


# ════════════════════════════════════════════════════════════════════════════
# Optional engine probes (lazy)
# ════════════════════════════════════════════════════════════════════════════

_LT_CACHE: Dict[str, Any] = {}
_LT_LOCK = threading.Lock()
_LT_AVAILABLE: Optional[bool] = None
_LT_AVAILABLE_LANGS: Dict[str, bool] = {}
_LT_LANG_MAP = {
    "en-US": "en-US",
    "en-GB": "en-GB",
    "en": "en-US",
    "id-ID": "id-ID",
    "id": "id-ID",
    "de-DE": "de-DE",
    "fr-FR": "fr-FR",
    "es-ES": "es-ES",
    "pt-BR": "pt-BR",
    "it-IT": "it-IT",
    "nl-NL": "nl-NL",
}

_SPELL_CACHE: Dict[str, Any] = {}
_SPELL_LOCK = threading.Lock()
_SPELL_AVAILABLE: Optional[bool] = None
_SPELL_LANG_MAP = {
    "en-US": "en",
    "en-GB": "en",
    "en": "en",
    "id-ID": "id",
    "id": "id",
    "de-DE": "de",
    "fr-FR": "fr",
    "es-ES": "es",
    "pt-BR": "pt",
    "it-IT": "it",
    "nl-NL": "nl",
}


def _try_get_language_tool(language: str) -> Tuple[Optional[Any], bool]:
    """Return (lt_instance_or_None, available_bool). Cached per language."""
    global _LT_AVAILABLE
    if _LT_AVAILABLE is False:
        return None, False
    lang = _LT_LANG_MAP.get(language, language)
    with _LT_LOCK:
        if _LT_AVAILABLE is None:
            try:
                import language_tool_python  # noqa: F401
                _LT_AVAILABLE = True
            except Exception as e:
                log.info("language_tool_python unavailable: %s", e)
                _LT_AVAILABLE = False
                return None, False
        if not _LT_AVAILABLE:
            return None, False
        if lang in _LT_CACHE:
            return _LT_CACHE[lang], True
        # Probe this specific language lazily.
        try:
            import language_tool_python
            lt = language_tool_python.LanguageToolPublicAPI(lang)
            _LT_CACHE[lang] = lt
            _LT_AVAILABLE_LANGS[lang] = True
            return lt, True
        except Exception as e:
            log.info("LanguageTool(%s) unavailable: %s", lang, e)
            _LT_AVAILABLE_LANGS[lang] = False
            return None, False


def _try_get_spellchecker(language: str) -> Tuple[Optional[Any], str]:
    """Return (spell_instance_or_None, dict_name_or_'none'). Cached per language."""
    global _SPELL_AVAILABLE
    if _SPELL_AVAILABLE is False:
        return None, "none"
    lang = _SPELL_LANG_MAP.get(language, language)
    with _SPELL_LOCK:
        if _SPELL_AVAILABLE is None:
            try:
                import spellchecker  # noqa: F401
                _SPELL_AVAILABLE = True
            except Exception as e:
                log.info("pyspellchecker unavailable: %s", e)
                _SPELL_AVAILABLE = False
                return None, "none"
        if not _SPELL_AVAILABLE:
            return None, "none"
        if lang in _SPELL_CACHE:
            return _SPELL_CACHE[lang], "pyspellchecker"
        try:
            from spellchecker import SpellChecker
            sp = SpellChecker(distance=1, language=lang) if lang != "en" else SpellChecker(distance=1)
            _SPELL_CACHE[lang] = sp
            return sp, "pyspellchecker"
        except Exception as e:
            log.info("SpellChecker(%s) init failed: %s", lang, e)
            return None, "none"


# ════════════════════════════════════════════════════════════════════════════
# GrammarChecker
# ════════════════════════════════════════════════════════════════════════════

class GrammarChecker:
    """Comprehensive grammar, spelling, and style checker — pure program-based.

    See module docstring for the full engine stack.
    """

    def __init__(self):
        self.nltk = None
        try:
            import nltk
            try:
                nltk.data.find('tokenizers/punkt')
            except LookupError:
                try:
                    nltk.download('punkt', quiet=True)
                except Exception:
                    pass
            self.nltk = nltk
        except ImportError:
            self.nltk = None

        # Cache engine probes so first check() is fast.
        self._engine_probe = {
            "language_tool": "unavailable",
            "rules_builtin": (
                len(_ACADEMIC_MISSPELLINGS)
                + len(_COMMON_GRAMMAR_ERRORS)
                + len(_WORDY_PHRASES)
                + len(_INDONESIAN_MISSPELLINGS)
                + len(_INDONESIAN_GRAMMAR_ERRORS)
                + len(_INDONESIAN_WORDY_PHRASES)
            ),
            "spell_dictionary": "none",
        }

    # ── Main entry point ────────────────────────────────────────────────────

    def check(
        self,
        text: str,
        *,
        mode: str = "grammar",
        language: str = "en-US",
        domain: str = "academic",
    ) -> Dict[str, Any]:
        """Pure program-based check. No LLM call.

        Args:
            text: Text to check.
            mode: 'grammar' | 'spelling' | 'style' | 'all'.
            language: BCP-47 code, e.g. 'en-US', 'en-GB', 'id-ID'.
            domain: 'academic' | 'general' | 'technical' (preserved; affects tone layer).

        Returns: see module docstring for the full schema.
        """
        result: Dict[str, Any] = {
            "text": text,
            "corrected": text,
            "language": language,
            "mode": mode,
            "domain": domain,
            "word_count": 0,
            "sentence_count": 0,
            "errors": [],
            "warnings": [],
            "suggestions": [],
            "readability": {},
            "engine": {
                "language_tool": "unavailable",
                "rules_builtin": self._engine_probe["rules_builtin"],
                "spell_dictionary": "none",
            },
            "stats": {"total_issues": 0, "errors_count": 0, "warnings_count": 0},
        }

        if not text or not text.strip():
            return result

        words = re.findall(r'\b\w+\b', text)
        sentences = self._split_sentences(text)
        result["word_count"] = len(words)
        result["sentence_count"] = len(sentences)

        # Layer A — built-in regex rules
        errors: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        suggestions: List[Dict[str, Any]] = []

        errors.extend(self._check_academic_spelling(text))
        if self._is_english(language):
            errors.extend(self._check_grammar_en(text))
        if self._is_indonesian(language):
            errors.extend(self._check_grammar_id(text))

        warnings.extend(self._check_style(text, language))
        warnings.extend(self._check_passive_voice(text, language))
        if domain == "academic" and self._is_english(language):
            warnings.extend(self._check_academic_tone(text))

        # Layer B — LanguageTool
        lt_errs, lt_ok = self._check_languagetool(text, language)
        if lt_ok:
            result["engine"]["language_tool"] = "available"
        errors.extend(lt_errs)

        # Layer C — pyspellchecker (for en/en-GB/id)
        sp_errs, sp_engine = self._check_pyspell(text, language)
        result["engine"]["spell_dictionary"] = sp_engine
        errors.extend(sp_errs)

        # Mode filtering
        m = (mode or "all").lower()
        if m == "grammar":
            errors = [e for e in errors if e.get("type") in ("grammar", "punctuation")]
            warnings, suggestions = [], []
        elif m == "spelling":
            errors = [e for e in errors if e.get("type") == "spelling"]
            warnings, suggestions = [], []
        elif m == "style":
            errors = []
            # keep warnings + suggestions for style mode
        # "all" → keep everything

        # Auto-correct
        corrected = self._apply_replacements(
            text, list(errors) + list(warnings)
        )
        result["corrected"] = corrected

        # Sort by offset (descending is irrelevant for output; use ascending for readability)
        errors.sort(key=lambda x: (x.get("offset", 0), x.get("rule_id", "")))
        warnings.sort(key=lambda x: (x.get("offset", 0), x.get("type", "")))
        suggestions.sort(key=lambda x: (x.get("offset", 0), x.get("type", "")))

        result["errors"] = errors
        result["warnings"] = warnings
        result["suggestions"] = suggestions
        result["readability"] = self._readability_scores(text)
        result["stats"] = {
            "total_issues": len(errors) + len(warnings),
            "errors_count": len(errors),
            "warnings_count": len(warnings),
        }
        return result

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _split_sentences(self, text: str) -> List[str]:
        if self.nltk:
            try:
                return self.nltk.sent_tokenize(text)
            except Exception:
                pass
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _is_english(self, language: str) -> bool:
        return language.lower().startswith("en")

    def _is_indonesian(self, language: str) -> bool:
        return language.lower().startswith("id")

    def _resolve_lang(self, language: str) -> str:
        return _LT_LANG_MAP.get(language, language)

    # ── Layer 1: built-in regex rules ───────────────────────────────────────

    def _check_academic_spelling(self, text: str) -> List[Dict[str, Any]]:
        """Token-based check against the academic misspellings dict."""
        errors: List[Dict[str, Any]] = []
        for match in re.finditer(r'\b[A-Za-z][A-Za-z\'-]*\b', text):
            word = match.group(0).lower()
            if len(word) < 2 or word.isdigit():
                continue
            if word in _ACADEMIC_MISSPELLINGS:
                correction = _ACADEMIC_MISSPELLINGS[word]
                if correction and correction != word:
                    errors.append({
                        "type": "spelling",
                        "rule_id": "ACADEMIC_MISSPELL",
                        "match": match.group(0),
                        "offset": match.start(),
                        "length": match.end() - match.start(),
                        "suggestion": correction,
                        "severity": "error",
                        "message": f"'{match.group(0)}' may be misspelled. Did you mean '{correction}'?",
                    })
        return errors

    def _check_grammar_en(self, text: str) -> List[Dict[str, Any]]:
        errors: List[Dict[str, Any]] = []
        for pattern, replacement, error_type in _COMMON_GRAMMAR_ERRORS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                suggestion = re.sub(pattern, replacement, match.group(0), flags=re.IGNORECASE)
                errors.append({
                    "type": "grammar",
                    "rule_id": f"EN_GRAMMAR_{error_type.upper().replace(' ', '_')}",
                    "match": match.group(0),
                    "offset": match.start(),
                    "length": match.end() - match.start(),
                    "suggestion": suggestion,
                    "severity": "error",
                    "message": f"Possible {error_type}: '{match.group(0)}' → '{suggestion}'",
                })
        return errors

    def _check_grammar_id(self, text: str) -> List[Dict[str, Any]]:
        """Indonesian informal-formal spelling + grammar."""
        errors: List[Dict[str, Any]] = []
        # Informal abbreviations.
        for match in re.finditer(r'\b[A-Za-z]+\b', text):
            w = match.group(0).lower()
            if w in _INDONESIAN_MISSPELLINGS:
                corr = _INDONESIAN_MISSPELLINGS[w]
                if corr and corr != w:
                    errors.append({
                        "type": "spelling",
                        "rule_id": "ID_INFORMAL",
                        "match": match.group(0),
                        "offset": match.start(),
                        "length": match.end() - match.start(),
                        "suggestion": corr,
                        "severity": "error",
                        "message": f"Bentuk tidak baku: '{match.group(0)}' → '{corr}'",
                    })
        # Grammar patterns.
        for pattern, replacement, error_type in _INDONESIAN_GRAMMAR_ERRORS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                suggestion = re.sub(pattern, replacement, match.group(0), flags=re.IGNORECASE)
                errors.append({
                    "type": "grammar",
                    "rule_id": f"ID_GRAMMAR_{error_type.upper().replace(' ', '_')}",
                    "match": match.group(0),
                    "offset": match.start(),
                    "length": match.end() - match.start(),
                    "suggestion": suggestion,
                    "severity": "error",
                    "message": f"Kesalahan {error_type}: '{match.group(0)}' → '{suggestion}'",
                })
        return errors

    def _check_style(self, text: str, language: str) -> List[Dict[str, Any]]:
        """Wordy phrases and style warnings."""
        suggestions: List[Dict[str, Any]] = []
        wordy = dict(_WORDY_PHRASES)
        if self._is_indonesian(language):
            wordy.update(_INDONESIAN_WORDY_PHRASES)
        for pattern, replacement in wordy.items():
            for match in re.finditer(pattern, text, re.IGNORECASE):
                if replacement:
                    suggestions.append({
                        "type": "wordy",
                        "match": match.group(0),
                        "offset": match.start(),
                        "length": match.end() - match.start(),
                        "suggestion": replacement,
                        "severity": "info",
                        "message": f"Wordy phrase: '{match.group(0)}' → '{replacement}'",
                    })
                else:
                    suggestions.append({
                        "type": "wordy",
                        "match": match.group(0),
                        "offset": match.start(),
                        "length": match.end() - match.start(),
                        "suggestion": "",
                        "severity": "info",
                        "message": f"Wordy phrase: '{match.group(0)}' can be removed",
                    })
        return suggestions

    def _check_passive_voice(self, text: str, language: str) -> List[Dict[str, Any]]:
        """Detect English passive constructions and warn when ratio is high."""
        if not self._is_english(language):
            return []
        sentences = self._split_sentences(text)
        passive_count = len(_PASSIVE_VOICE_RE.findall(text))
        out: List[Dict[str, Any]] = []
        if sentences and passive_count / max(len(sentences), 1) > 0.3:
            out.append({
                "type": "passive",
                "match": "",
                "offset": 0,
                "length": 0,
                "suggestion": "Consider using active voice.",
                "severity": "info",
                "message": f"High passive voice usage ({passive_count}/{len(sentences)} sentences)",
            })
        return out

    def _check_academic_tone(self, text: str) -> List[Dict[str, Any]]:
        """Light academic-tone warnings (e.g. contractions)."""
        out: List[Dict[str, Any]] = []
        for match in re.finditer(r"\b(can't|won't|don't|doesn't|didn't|isn't|aren't|wasn't|weren't|haven't|hasn't|hadn't|wouldn't|shouldn't|couldn't)\b",
                                 text):
            out.append({
                "type": "academic",
                "match": match.group(0),
                "offset": match.start(),
                "length": match.end() - match.start(),
                "suggestion": re.sub(r"n't", " not", match.group(0)),
                "severity": "info",
                "message": f"Contraction '{match.group(0)}' is informal; consider the full form in academic writing.",
            })
        return out

    # ── Layer 2: LanguageTool ───────────────────────────────────────────────

    def _check_languagetool(self, text: str, language: str) -> Tuple[List[Dict[str, Any]], bool]:
        lt, ok = _try_get_language_tool(language)
        if not ok or not lt:
            return [], False
        try:
            matches = lt.check(text)
        except Exception as e:
            log.info("LanguageTool.check() failed: %s", e)
            return [], True
        errors: List[Dict[str, Any]] = []
        for m in matches:
            repl = m.replacements[0] if m.replacements else ""
            errors.append({
                "type": "grammar" if m.ruleIssueType != "misspelling" else "spelling",
                "rule_id": f"LT_{m.ruleId}"[:80],
                "match": text[m.offset:m.offset + m.errorLength] if m.errorLength else m.matchedText,
                "offset": m.offset,
                "length": m.errorLength,
                "suggestion": repl,
                "severity": "error",
                "message": (m.message or "").strip()[:240],
                "engine": "language_tool",
            })
        return errors, True

    # ── Layer 3: pyspellchecker ─────────────────────────────────────────────

    def _check_pyspell(self, text: str, language: str) -> Tuple[List[Dict[str, Any]], str]:
        sp, engine_name = _try_get_spellchecker(language)
        if sp is None:
            return [], engine_name
        is_id = self._is_indonesian(language)
        allow = _INDONESIAN_COMMON_WORDS if is_id else set()
        errors: List[Dict[str, Any]] = []
        for match in re.finditer(r"\b[A-Za-z][A-Za-z'-]*\b", text):
            word = match.group(0)
            w = word.lower()
            if len(w) < 2:
                continue
            if is_id and w in allow:
                continue
            if w in _ACADEMIC_MISSPELLINGS:
                continue  # already covered
            if is_id and w in _INDONESIAN_MISSPELLINGS:
                continue  # already covered
            try:
                if w in sp.unknown([w]):
                    cands = sp.candidates(w) or []
                    best = cands[0] if cands else ""
                    if best and best != w:
                        errors.append({
                            "type": "spelling",
                            "rule_id": "PYSPELL",
                            "match": word,
                            "offset": match.start(),
                            "length": match.end() - match.start(),
                            "suggestion": best,
                            "severity": "error",
                            "message": f"'{word}' may be misspelled. Did you mean '{best}'?",
                            "engine": "pyspellchecker",
                        })
            except Exception:
                continue
        return errors, engine_name

    # ── Auto-correct ────────────────────────────────────────────────────────

    @staticmethod
    def _apply_replacements(text: str, items: List[Dict[str, Any]]) -> str:
        """Apply non-overlapping replacements from the end so offsets stay valid."""
        valid: List[Dict[str, Any]] = []
        for it in items:
            if it.get("offset") is None or it.get("length") is None:
                continue
            sug = it.get("suggestion", "")
            if not sug:
                continue
            off = int(it["offset"])
            ln = int(it["length"])
            if off < 0 or ln <= 0 or off + ln > len(text):
                continue
            valid.append((off, off + ln, sug))
        valid.sort(key=lambda x: x[0], reverse=True)
        out = text
        occupied: List[Tuple[int, int]] = []
        for start, end, sug in valid:
            if any(not (end <= s or start >= e) for s, e in occupied):
                continue
            occupied.append((start, end))
            out = out[:start] + sug + out[end:]
        return out

    def auto_correct(self, text: str, language: str = "en-US", domain: str = "academic") -> str:
        """Produce a best-effort auto-corrected string. No LLM."""
        result = self.check(text, mode="all", language=language, domain=domain)
        # Prefer errors first (more confident), then warnings.
        ordered = list(result.get("errors", [])) + list(result.get("warnings", []))
        return self._apply_replacements(text, ordered)

    # ── Readability ─────────────────────────────────────────────────────────

    def _readability_scores(self, text: str) -> Dict[str, float]:
        words = re.findall(r'\b\w+\b', text)
        sentences = self._split_sentences(text)
        if not words or not sentences:
            return {}

        word_count = len(words)
        sent_count = len(sentences)
        char_count = sum(len(w) for w in words)
        syllable_counts = [self._count_syllables(w) for w in words]
        total_syllables = sum(syllable_counts)
        complex_words = sum(1 for s in syllable_counts if s >= 3)

        avg_syllables = total_syllables / word_count if word_count else 0
        avg_words_per_sent = word_count / sent_count if sent_count else 0

        flesch = 206.835 - 1.015 * avg_words_per_sent - 84.6 * avg_syllables
        fk_grade = 0.39 * avg_words_per_sent + 11.8 * avg_syllables - 15.59
        fog = 0.4 * (avg_words_per_sent + 100 * (complex_words / word_count if word_count else 0))
        l = (char_count / word_count) * 100 if word_count else 0  # L = average letters per 100 words
        s = (sent_count / word_count) * 100 if word_count else 0  # S = average sentences per 100 words
        coleman = 0.0588 * l - 0.296 * s - 15.8
        smog = 1.0430 * math.sqrt(complex_words * 30 / sent_count) + 3.1291 if sent_count else 0
        ari = 4.71 * (char_count / word_count) + 0.5 * (word_count / sent_count) - 21.43 if word_count and sent_count else 0
        easy_words = sum(1 for s in syllable_counts if s <= 2)
        easy_pct = easy_words / word_count if word_count else 0
        dale_chall = 0.1579 * (100 - easy_pct * 100) + 0.0496 * avg_words_per_sent

        return {
            "flesch_reading_ease": round(max(0, min(100, flesch)), 1),
            "flesch_kincaid_grade": round(max(1, min(20, fk_grade)), 1),
            "gunning_fog": round(max(1, min(20, fog)), 1),
            "coleman_liau": round(max(1, min(20, coleman)), 1),
            "smog_index": round(max(1, min(20, smog)), 1),
            "automated_readability_index": round(max(1, min(20, ari)), 1),
            "dale_chall_score": round(max(1, min(20, dale_chall)), 1),
            "avg_sentence_length": round(avg_words_per_sent, 1),
            "avg_syllables_per_word": round(avg_syllables, 2),
            "complex_word_pct": round(complex_words / word_count * 100, 1),
        }

    @staticmethod
    def _count_syllables(word: str) -> int:
        word = word.lower().strip(".,!?;:\"'()[]{}-")
        if not word:
            return 0
        vowels = "aeiouy"
        count = 0
        prev_vowel = False
        for char in word:
            is_vowel = char in vowels
            if is_vowel and not prev_vowel:
                count += 1
            prev_vowel = is_vowel
        if word.endswith("e") and count > 1:
            count -= 1
        return max(1, count)

    # ── AI enhance (legacy, kept for backwards compat) ──────────────────────

    def ai_enhance(self, text: str, instruction: str = "improve clarity") -> str:
        try:
            from utils.ai_tools.ai_client import chat as _chain_chat
            from utils.ai_tools.model_config import get_endpoint_chain as _gec
            if not _gec(heavy=False):
                return text
            system = f"You are an expert academic editor. {instruction}. Fix all grammar and spelling errors while preserving meaning and academic tone. Output ONLY the corrected text."
            content, _used = _chain_chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                heavy=False,
                max_tokens=4096,
                temperature=0.3,
                timeout=120,
            )
            return content
        except Exception as e:
            log.error("AI enhancement failed: %s", e)
            return text

    @staticmethod
    def _build_api_url() -> str:
        base = os.getenv("AIOTOMASI_API", "").rstrip("/")
        return f"{base}/chat/completions" if base else ""


# ════════════════════════════════════════════════════════════════════════════
# Legacy public entry point (preserved for the existing dispatcher)
# ════════════════════════════════════════════════════════════════════════════

def check_legacy(text: str, domain: str = "academic") -> Dict[str, Any]:
    return GrammarChecker().check(text, mode="all", language="en-US", domain=domain)


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Grammar & Spell Checker (program-only, no LLM).")
    parser.add_argument("--text", "-t", help="Text to check")
    parser.add_argument("--file", "-f", help="File to check")
    parser.add_argument("--domain", "-d", default="academic",
                        choices=["academic", "business", "technical", "general"])
    parser.add_argument("--mode", "-m", default="all",
                        choices=["grammar", "spelling", "style", "all"],
                        help="What kinds of issues to return")
    parser.add_argument("--language", "-l", default="en-US",
                        help="BCP-47 code: en-US, en-GB, id-ID, etc.")
    parser.add_argument("--enhance", "-e", action="store_true",
                        help="Use AI (LLM) to fix errors — off by default for the program path")
    parser.add_argument("--json", "-j", action="store_true",
                        help="JSON output")
    parser.add_argument("--suggest", action="store_true",
                        help="Show correction suggestions inline")
    parser.add_argument("--auto-correct", action="store_true",
                        help="Print the auto-corrected text instead of the analysis")
    args = parser.parse_args()

    text = args.text
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    if not text:
        text = sys.stdin.read()
    if not text:
        parser.print_help()
        return

    checker = GrammarChecker()

    if args.enhance:
        result = checker.ai_enhance(text)
        print(result if not args.json else json.dumps({"enhanced": result}, indent=2, ensure_ascii=False))
        return

    if args.auto_correct:
        corrected = checker.auto_correct(text, language=args.language, domain=args.domain)
        print(corrected if not args.json else json.dumps({"corrected": corrected}, indent=2, ensure_ascii=False))
        return

    result = checker.check(text, mode=args.mode, language=args.language, domain=args.domain)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"\nText: {len(result['text'])} chars, {result['word_count']} words, {result['sentence_count']} sentences")
    print(f"Language: {result['language']}   Mode: {result['mode']}   Domain: {result['domain']}")
    print(f"Engine: {result['engine']}")

    rd = result.get("readability", {})
    if rd:
        print(f"\nReadability Scores:")
        for k, v in rd.items():
            print(f"  {k.replace('_', ' ').title():.<40} {v}")

    if result.get("errors"):
        print(f"\nErrors ({len(result['errors'])}):")
        for err in result["errors"]:
            sug = err.get("suggestion") or ""
            print(f"  [{err.get('severity','error')}] {err.get('rule_id','?')}: {err.get('message','')}   '{err.get('match','')}' -> '{sug}'")

    if result.get("warnings"):
        print(f"\nWarnings ({len(result['warnings'])}):")
        for w in result["warnings"]:
            print(f"  [{w.get('severity','info')}] {w.get('type','?')}: {w.get('message','')}")

    if result.get("suggestions"):
        print(f"\nSuggestions ({len(result['suggestions'])}):")
        for s in result["suggestions"]:
            print(f"  [{s.get('severity','info')}] {s.get('type','?')}: {s.get('message','')}")

    if args.suggest:
        print(f"\nInline Suggestions:")
        for s in result.get("suggestions", []):
            print(f"  '{s.get('match','')}' -> '{s.get('suggestion','')}'")
        for e in result.get("errors", []):
            print(f"  '{e.get('match','')}' -> '{e.get('suggestion','')}'")


if __name__ == "__main__":
    main()
