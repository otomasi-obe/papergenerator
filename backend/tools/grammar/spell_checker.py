#!/usr/bin/env python3
"""
Comprehensive Spell Checker Tool
================================
Multi-strategy spell checking combining:
1. Dictionary-based spell checking (pyspellchecker)
2. Context-aware spell checking using AI
3. Grammar checking using AI
4. Multi-language support (en, id, de, fr, es, pt, ru, ar, zh, ja, ko)
5. Auto-correction with ranked suggestions
6. Batch file processing
7. Statistics (error rate, most common mistakes, error distribution)
8. Domain-specific dictionary support (academic/technical terms)

Uses shared AI client for context-aware and grammar checks.

Usage:
    python spell_checker.py --text "Your textt here"
    python spell_checker.py --file document.txt
    python spell_checker.py --file doc.txt --language id
    python spell_checker.py --file doc.txt --grammar
    python spell_checker.py --file doc.txt --auto-correct
    python spell_checker.py --file doc.txt --domain academic
    python spell_checker.py --batch *.txt --stats
    python spell_checker.py --file doc.txt --output results.json
    python spell_checker.py --text "teh quikc brown fox" --suggest
"""
import argparse
import sys
import os
import re
import json
import string
import unicodedata
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Set, Any

sys.path.append(str(Path(__file__).resolve().parent.parent))
from shared_ai_client import ai_generate


# ---------------------------------------------------------------------------
# Domain-specific dictionaries
# ---------------------------------------------------------------------------
ACADEMIC_TERMS: Set[str] = {
    "abstraction", "acceleration", "accommodation", "accumulation", "acknowledgment",
    "acquisition", "adaptation", "adherence", "adjacency", "aforementioned",
    "aggregation", "algorithm", "allele", "amortization", "amplitude",
    "anthropology", "approximation", "archetype", "asymptote", "asymptotic",
    "autocorrelation", "autoregressive", "bibliography", "biocompatibility",
    "biodegradation", "biomarker", "biomechanics", "biomedicine", "biometrics",
    "biostatistics", "calorimetry", "categorization", "chromatography",
    "classification", "coefficient", "collaboration", "combinatorial",
    "complementarity", "computability", "concatenation", "conceptualization",
    "conditional", "configuration", "confounding", "congruence", "conjecture",
    "consequential", "conservation", "constitutive", "constrained", "constructive",
    "contingency", "contradiction", "convergence", "convolution", "correlation",
    "correspondence", "cosmological", "covariance", "cryptographic", "crystallography",
    "decomposition", "degeneracy", "delimitation", "demarcation", "denominator",
    "derivative", "determinant", "dichotomous", "differentiable", "differentiation",
    "dimensionality", "discretization", "discriminant", "displacement", "dissipation",
    "distribution", "divergence", "documentation", "effectiveness", "eigenvalue",
    "eigenvector", "electrophoresis", "endogeneity", "epidemiology", "equilibrium",
    "equivalence", "ergodicity", "estimation", "ethnography", "eukaryote",
    "extrapolation", "factorization", "falsification", "feasibility", "filtration",
    "fluorescence", "formalization", "fractional", "fractal", "generalization",
    "genotype", "geodesic", "gradient", "granularity", "heterogeneity",
    "heteroscedasticity", "heuristic", "homogeneity", "homomorphism", "hydrodynamics",
    "hyperparameter", "hypothesis", "identifiability", "imputation", "independence",
    "induction", "inequality", "infimum", "infinitesimal", "initialization",
    "integration", "interpolation", "invariance", "isomorphism", "isotope",
    "iterative", "kernel", "kinematics", "lattice", "lemma", "likelihood",
    "linearization", "liposome", "logarithmic", "logistic", "longitudinal",
    "manifold", "marginalization", "markov", "matroid", "maximization",
    "measurement", "metabolomics", "metagenomics", "methodology", "microarray",
    "minimization", "mitochondria", "modularity", "monotonic", "morphology",
    "multicollinearity", "multivariate", "nanoparticle", "nanotechnology",
    "neuroscience", "nonlinear", "nonparametric", "normalization", "normative",
    "null hypothesis", "observational", "optimization", "orthogonal", "orthonormal",
    "oscillation", "parameterization", "participatory", "pathogenesis", "pedagogy",
    "periodicity", "permutation", "pharmacokinetics", "phenomenological", "phenotype",
    "photosynthesis", "polynomial", "posterior", "postulation", "pragmatic",
    "precision", "predictor", "prevalence", "principal", "probabilistic",
    "prognostic", "prokaryote", "proposition", "proximal", "psychometric",
    "quantification", "quantile", "quantum", "quasiconvex", "quasilinear",
    "questionnaire", "quotient", "randomization", "rationalization", "recombination",
    "reconstruction", "recursion", "regularization", "reliability", "representation",
    "reproducibility", "residual", "robustness", "salience", "sample",
    "semantics", "semiparametric", "sensitivity", "significance", "similarity",
    "simulation", "singularity", "sociological", "spectral", "specification",
    "standardization", "stationarity", "statistic", "stochastic", "stratification",
    "subgroup", "subsequence", "subspace", "supremum", "surjectivity",
    "survivorship", "symmetry", "synchronization", "synergistic", "taxonomy",
    "teleological", "tensor", "theorem", "thermodynamic", "topological",
    "transcription", "transformation", "transitivity", "translation", "transversality",
    "triangulation", "truncation", "turbulence", "typological", "unbiased",
    "uncertainty", "univariate", "validation", "variability", "variance",
    "vectorization", "visualization", "volatility", "vulnerability", "wavelet",
}

TECHNICAL_TERMS: Set[str] = {
    "abstraction", "accessor", "accumulator", "acknowledgment", "adapter",
    "aggregator", "algorithm", "allocator", "ambiguity", "annotation",
    "append", "applet", "architecture", "artifact", "assembler",
    "asynchronous", "attribute", "authentication", "authorization", "autoboxing",
    "backpropagation", "backtracking", "bandwidth", "benchmark", "biginteger",
    "bijection", "binary", "bind", "bitmask", "bitwise",
    "blockchain", "boolean", "bootstrapping", "breakpoint", "broadcast",
    "buffer", "bytecode", "caching", "callback", "camunda",
    "cardinality", "changelog", "checksum", "classpath", "closure",
    "clustering", "codec", "combinator", "compilation", "compiler",
    "component", "composable", "concurrency", "concurrent", "configuration",
    "connection", "consistency", "constant", "constructor", "containerization",
    "continuation", "contravariant", "controller", "coroutine", "covariant",
    "daemon", "deadlock", "debounce", "debugger", "declarative",
    "decorator", "dependency", "deployment", "deque", "dereference",
    "deserialization", "descriptor", "deterministic", "dictionary", "diffing",
    "dispatcher", "documentation", "domain", "driver", "dynamic",
    "ecosystem", "elasticsearch", "encapsulation", "endianness", "enumeration",
    "environment", "ephemeral", "eventual", "exception", "executor",
    "factory", "failover", "fallback", "fanout", "fibonacci",
    "filesystem", "filter", "finalizer", "firewall", "fixture",
    "framework", "function", "functor", "garbage", "generator",
    "generic", "glob", "goroutine", "gradient", "graph",
    "graphql", "greedy", "hashmap", "hashset", "heap",
    "heuristic", "higherorder", "hook", "hostname", "hyperlink",
    "idempotent", "immutable", "imperative", "implementation", "import",
    "indexer", "inference", "inheritance", "initializer", "inline",
    "instance", "interceptor", "interface", "interpolation", "interpreter",
    "introspection", "invariant", "invocation", "io", "ipaddress",
    "iterable", "iterator", "jacobian", "javascript", "json",
    "kubernetes", "lambda", "latency", "lazy", "lexer",
    "lifecycle", "linker", "livelock", "loadbalancer", "localization",
    "lock", "logarithm", "marshalling", "memoization", "memory",
    "messaging", "metadata", "metaclass", "metaprogramming", "microservice",
    "middleware", "migration", "mixin", "modular", "module",
    "monad", "monoid", "monomorphism", "monotonic", "mutex",
    "namespace", "neural", "normalization", "nosql", "nullable",
    "object", "observable", "observer", "opcode", "optimization",
    "overloading", "overriding", "package", "pagination", "paradigm",
    "parallelism", "parameter", "parser", "partition", "patch",
    "path", "payload", "persistence", "pipelining", "polymorphism",
    "pool", "postcondition", "precondition", "predicate", "preemption",
    "primitive", "procedure", "process", "profiler", "projection",
    "protocol", "prototype", "proxy", "pubsub", "queue",
    "quicksort", "race", "recursion", "refactoring", "reference",
    "reflection", "regex", "registry", "reification", "reliability",
    "repository", "resolution", "resolver", "resource", "restful",
    "retry", "rollback", "routing", "runtime", "scheduler",
    "schema", "scope", "serialization", "serverless", "shader",
    "sharding", "singleton", "socket", "software", "sorting",
    "specification", "stack", "stateful", "stateless", "static",
    "stream", "string", "struct", "subclass", "subroutine",
    "subtype", "supertype", "surjection", "swap", "symmetric",
    "synchronization", "syntactic", "syntax", "system", "template",
    "tensor", "test", "thread", "throughput", "timestamp",
    "tokenization", "topology", "transaction", "transformer", "transpiler",
    "traversal", "tree", "tuple", "type", "unary",
    "unmarshalling", "unboxing", "unicode", "unification", "unit",
    "uri", "utilization", "validator", "variable", "vector",
    "viewmodel", "virtual", "visitor", "volatile", "watchdog",
    "websocket", "widget", "workflow", "yaml", "zip",
}

MEDICAL_TERMS: Set[str] = {
    "adenocarcinoma", "anesthesia", "angiography", "antibiotic", "antibody",
    "antigen", "antihypertensive", "antiinflammatory", "antimicrobial", "antiviral",
    "appendectomy", "arrhythmia", "arteriosclerosis", "arthroplasty", "atherosclerosis",
    "bacteremia", "benign", "biopsy", "bradycardia", "bronchoscopy",
    "cardiomyopathy", "chemotherapy", "cholecystectomy", "cirrhosis", "coagulopathy",
    "colonoscopy", "contraindication", "coronary", "cryotherapy", "cyanosis",
    "diagnosis", "dialysis", "diuretic", "dysfunction", "dyspnea",
    "electrocardiogram", "embolism", "endocarditis", "endoscopy", "epidural",
    "erythrocyte", "esophageal", "etiology", "fibrillation", "gastroenterology",
    "hemorrhage", "hepatomegaly", "histopathology", "hyperglycemia", "hyperplasia",
    "hypertension", "hypotension", "immunocompromised", "immunosuppression", "incision",
    "intravenous", "intubation", "ischemia", "laparoscopy", "leukocyte",
    "lymphadenopathy", "malignant", "metastasis", "microbiology", "myocardial",
    "neoplasm", "nephrology", "neuropathy", "obstetrics", "oncology",
    "ophthalmology", "orthopedic", "osteoporosis", "pathogenesis", "pathology",
    "percutaneous", "pharmacology", "phlebotomy", "pneumonia", "prophylaxis",
    "prosthesis", "pulmonary", "radiography", "radiotherapy", "rhinoplasty",
    "sarcoma", "sclerosis", "significance", "splenomegaly", "stethoscope",
    "stomatitis", "symptomatology", "syncope", "tachycardia", "thrombosis",
    "tonsillectomy", "toxicology", "tracheostomy", "ultrasound", "vaccination",
    "vasodilation", "ventilator", "vertebroplasty", "virology", "xerostomia",
}

DOMAIN_DICTIONARIES: Dict[str, Set[str]] = {
    "academic": ACADEMIC_TERMS,
    "technical": TECHNICAL_TERMS,
    "medical": MEDICAL_TERMS,
    "all": ACADEMIC_TERMS | TECHNICAL_TERMS | MEDICAL_TERMS,
}

# Common misspellings map for fast correction
COMMON_MISSPELLINGS: Dict[str, str] = {
    "teh": "the", "recieve": "receive", "occured": "occurred",
    "seperate": "separate", "definately": "definitely", "occassion": "occasion",
    "accomodate": "accommodate", "untill": "until", "begining": "beginning",
    "calender": "calendar", "collegue": "colleague", "commited": "committed",
    "concious": "conscious", "curiousity": "curiosity", "enviroment": "environment",
    "existance": "existence", "foriegn": "foreign", "goverment": "government",
    "happend": "happened", "immediatly": "immediately", "knowlege": "knowledge",
    "langauge": "language", "liason": "liaison", "maintenence": "maintenance",
    "neccessary": "necessary", "noticable": "noticeable", "occurence": "occurrence",
    "persistant": "persistent", "posession": "possession", "prefered": "preferred",
    "privlege": "privilege", "recomend": "recommend", "refered": "referred",
    "relavent": "relevant", "relevent": "relevant", "repitition": "repetition",
    "responsability": "responsibility", "seige": "siege", "succesful": "successful",
    "suprise": "surprise", "tommorow": "tomorrow", "tommorrow": "tomorrow",
    "wierd": "weird", "writting": "writing", "acheive": "achieve",
    "arguement": "argument", "beleive": "believe", "buisness": "business",
    "comming": "coming", "committment": "commitment", "comparision": "comparison",
    "dependant": "dependent", "dissapoint": "disappoint", "exersize": "exercise",
    "facinate": "fascinate", "fourty": "forty", "freind": "friend",
    "gaurd": "guard", "harrass": "harass", "ignorence": "ignorance",
    "independant": "independent", "inteligence": "intelligence", "its": "it's",
    "kernal": "kernel", "libary": "library", "managment": "management",
    "medival": "medieval", "minature": "miniature", "naturaly": "naturally",
    "neccesary": "necessary", "nieghbor": "neighbor", "occasionaly": "occasionally",
    "publically": "publicly", "realy": "really", "reccomend": "recommend",
    "refrence": "reference", "religous": "religious", "rember": "remember",
    "resistence": "resistance", "sargent": "sergeant",
    "sentance": "sentence", "speach": "speech", "strenght": "strength",
    "succede": "succeed", "supress": "suppress", "temperture": "temperature",
    "tendancy": "tendency", "therefor": "therefore", "threshhold": "threshold",
    "tounge": "tongue", "truely": "truly", "unfortunatly": "unfortunately",
    "vaccum": "vacuum", "vegatable": "vegetable", "wether": "whether",
    "wich": "which",
}

# Language codes supported by pyspellchecker
SUPPORTED_LANGUAGES = {
    "en": "English", "de": "German", "es": "Spanish", "fr": "French",
    "pt": "Portuguese", "ru": "Russian", "ar": "Arabic", "la": "Latin",
    "pl": "Polish", "uk": "Ukrainian", "it": "Italian", "nl": "Dutch",
    "tl": "Tagalog", "vi": "Vietnamese", "cs": "Czech", "he": "Hebrew",
    "hu": "Hungarian", "el": "Greek", "sv": "Swedish", "tr": "Turkish",
    "da": "Danish", "fi": "Finnish", "nb": "Norwegian", "ko": "Korean",
    "ca": "Catalan", "bg": "Bulgarian", "hr": "Croatian", "lt": "Lithuanian",
    "sl": "Slovenian", "et": "Estonian", "lv": "Latvian", "ro": "Romanian",
    "sk": "Slovak", "af": "Afrikaans",
}

# AI-only languages (not supported by pyspellchecker but handled via AI)
AI_ONLY_LANGUAGES = {
    "id": "Indonesian", "zh": "Chinese", "ja": "Japanese", "ms": "Malay",
    "th": "Thai", "hi": "Hindi", "bn": "Bengali", "ta": "Tamil",
    "te": "Telugu", "mr": "Marathi", "fa": "Persian", "sw": "Swahili",
}

ALL_LANGUAGES = {**SUPPORTED_LANGUAGES, **AI_ONLY_LANGUAGES}


# ---------------------------------------------------------------------------
# Spell Check Result Data Classes
# ---------------------------------------------------------------------------
class SpellError:
    """Represents a single spell check error."""
    __slots__ = ("word", "line", "col", "suggestions", "context", "error_type")

    def __init__(self, word: str, line: int, col: int,
                 suggestions: List[str] = None, context: str = "",
                 error_type: str = "spelling"):
        self.word = word
        self.line = line
        self.col = col
        self.suggestions = suggestions or []
        self.context = context
        self.error_type = error_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "line": self.line,
            "col": self.col,
            "suggestions": self.suggestions,
            "context": self.context,
            "error_type": self.error_type,
        }

    def __repr__(self) -> str:
        return (f"SpellError(word='{self.word}', line={self.line}, "
                f"col={self.col}, suggestions={self.suggestions[:3]}, "
                f"type='{self.error_type}')")


class GrammarError:
    """Represents a grammar/style error."""
    __slots__ = ("message", "line", "col", "suggestion", "context", "severity")

    def __init__(self, message: str, line: int, col: int,
                 suggestion: str = "", context: str = "",
                 severity: str = "warning"):
        self.message = message
        self.line = line
        self.col = col
        self.suggestion = suggestion
        self.context = context
        self.severity = severity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "line": self.line,
            "col": self.col,
            "suggestion": self.suggestion,
            "context": self.context,
            "severity": self.severity,
        }


class SpellCheckResult:
    """Aggregated result of a spell check run."""

    def __init__(self, source: str = "", language: str = "en"):
        self.source = source
        self.language = language
        self.timestamp = datetime.now().isoformat()
        self.spell_errors: List[SpellError] = []
        self.grammar_errors: List[GrammarError] = []
        self.total_words: int = 0
        self.corrected_text: str = ""
        self.domain: str = ""

    @property
    def error_count(self) -> int:
        return len(self.spell_errors)

    @property
    def grammar_error_count(self) -> int:
        return len(self.grammar_errors)

    @property
    def error_rate(self) -> float:
        if self.total_words == 0:
            return 0.0
        return self.error_count / self.total_words

    @property
    def most_common_errors(self) -> List[Tuple[str, int]]:
        counter = Counter(e.word for e in self.spell_errors)
        return counter.most_common(20)

    @property
    def error_distribution(self) -> Dict[str, int]:
        dist: Dict[str, int] = defaultdict(int)
        for e in self.spell_errors:
            dist[e.error_type] += 1
        return dict(dist)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "language": self.language,
            "timestamp": self.timestamp,
            "domain": self.domain,
            "total_words": self.total_words,
            "spell_error_count": self.error_count,
            "grammar_error_count": self.grammar_error_count,
            "error_rate": round(self.error_rate, 6),
            "most_common_errors": self.most_common_errors,
            "error_distribution": self.error_distribution,
            "spell_errors": [e.to_dict() for e in self.spell_errors],
            "grammar_errors": [e.to_dict() for e in self.grammar_errors],
            "corrected_text": self.corrected_text,
        }

    def summary(self) -> str:
        lines = [
            f"═══════════════════════════════════════════════════",
            f"  Spell Check Report",
            f"═══════════════════════════════════════════════════",
            f"  Source    : {self.source}",
            f"  Language  : {ALL_LANGUAGES.get(self.language, self.language)}",
            f"  Domain    : {self.domain or 'general'}",
            f"  Timestamp : {self.timestamp}",
            f"───────────────────────────────────────────────────",
            f"  Total words        : {self.total_words}",
            f"  Spelling errors    : {self.error_count}",
            f"  Grammar errors     : {self.grammar_error_count}",
            f"  Error rate         : {self.error_rate:.4%}",
            f"───────────────────────────────────────────────────",
        ]
        if self.most_common_errors:
            lines.append("  Most common misspellings:")
            for word, count in self.most_common_errors[:10]:
                lines.append(f"    • {word:<25s} ×{count}")
            lines.append("───────────────────────────────────────────────────")
        if self.error_distribution:
            lines.append("  Error distribution:")
            for etype, count in sorted(self.error_distribution.items(), key=lambda x: -x[1]):
                lines.append(f"    • {etype:<20s} : {count}")
            lines.append("───────────────────────────────────────────────────")
        if self.spell_errors:
            lines.append("  Spelling errors (first 30):")
            for err in self.spell_errors[:30]:
                sugg = ", ".join(err.suggestions[:3]) if err.suggestions else "—"
                lines.append(f"    L{err.line:>3d}:{err.col:>3d}  {err.word:<20s} → {sugg}")
            if len(self.spell_errors) > 30:
                lines.append(f"    ... and {len(self.spell_errors) - 30} more")
            lines.append("───────────────────────────────────────────────────")
        if self.grammar_errors:
            lines.append("  Grammar errors (first 20):")
            for gerr in self.grammar_errors[:20]:
                lines.append(f"    L{gerr.line:>3d}  [{gerr.severity}] {gerr.message}")
                if gerr.suggestion:
                    lines.append(f"         → {gerr.suggestion}")
            if len(self.grammar_errors) > 20:
                lines.append(f"    ... and {len(self.grammar_errors) - 20} more")
            lines.append("───────────────────────────────────────────────────")
        lines.append("═══════════════════════════════════════════════════")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dictionary-based Spell Checker
# ---------------------------------------------------------------------------
class DictionaryChecker:
    """Dictionary-based spell checking using pyspellchecker."""

    def __init__(self, language: str = "en",
                 domain_dicts: List[str] = None,
                 custom_dict_path: str = None):
        self.language = language
        self.domain_dicts = domain_dicts or []
        self.custom_words: Set[str] = set()
        self.spell = None

        # Load domain-specific words
        for d in self.domain_dicts:
            if d in DOMAIN_DICTIONARIES:
                self.custom_words.update(DOMAIN_DICTIONARIES[d])

        # Load custom dictionary file
        if custom_dict_path and Path(custom_dict_path).exists():
            with open(custom_dict_path, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip().lower()
                    if w:
                        self.custom_words.add(w)

        # Initialize pyspellchecker
        if language in SUPPORTED_LANGUAGES:
            try:
                from spellchecker import SpellChecker
                self.spell = SpellChecker(language=language, distance=2)
                # Add domain/custom words to the known dictionary
                for w in self.custom_words:
                    self.spell.word_frequency.load_words([w])
            except ImportError:
                print("WARNING: pyspellchecker not installed. "
                      "Install with: pip install pyspellchecker")
                print("  Falling back to common-misspellings-only mode.")
                self.spell = None
        elif language in AI_ONLY_LANGUAGES:
            # No pyspellchecker support; rely on AI + common misspellings
            self.spell = None

    def check_word(self, word: str) -> Tuple[bool, List[str]]:
        """Check a single word. Returns (is_correct, suggestions)."""
        clean = self._normalize_word(word)
        if not clean or self._is_special(clean):
            return True, []

        # Check custom/domain dictionary first
        if clean.lower() in self.custom_words:
            return True, []

        # Check common misspellings fast-path
        if clean.lower() in COMMON_MISSPELLINGS:
            return False, [COMMON_MISSPELLINGS[clean.lower()]]

        # Use pyspellchecker
        if self.spell is not None:
            if self.spell.unknown([clean]):
                candidates = self.spell.candidates(clean)
                suggestions = list(candidates) if candidates else []
                # Remove the misspelled word itself from suggestions
                suggestions = [s for s in suggestions if s.lower() != clean.lower()]
                return False, suggestions[:10]
            return True, []

        # No dictionary available — cannot determine
        return True, []

    def check_text(self, text: str) -> List[SpellError]:
        """Check all words in text, returning errors."""
        errors = []
        lines = text.split("\n")
        for line_idx, line in enumerate(lines, start=1):
            for match in re.finditer(r'\b[\w\'-]+\b', line):
                word = match.group()
                col = match.start() + 1
                is_correct, suggestions = self.check_word(word)
                if not is_correct:
                    # Extract context window
                    start = max(0, match.start() - 30)
                    end = min(len(line), match.end() + 30)
                    context = line[start:end].strip()
                    errors.append(SpellError(
                        word=word, line=line_idx, col=col,
                        suggestions=suggestions, context=context,
                        error_type="dictionary",
                    ))
        return errors

    def auto_correct(self, text: str) -> str:
        """Auto-correct text using best available suggestion for each error."""
        def replace_word(m):
            word = m.group()
            is_correct, suggestions = self.check_word(word)
            if not is_correct and suggestions:
                # Preserve original capitalization pattern
                return self._match_case(word, suggestions[0])
            return word

        return re.sub(r'\b[\w\'-]+\b', replace_word, text)

    @staticmethod
    def _normalize_word(word: str) -> str:
        """Strip punctuation and normalize unicode."""
        word = word.strip(string.punctuation)
        word = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode("ascii")
        return word

    @staticmethod
    def _is_special(word: str) -> bool:
        """Check if word is a number, abbreviation, or special token."""
        if not word:
            return True
        if word.isdigit():
            return True
        if re.match(r'^[A-Z]{2,}$', word):  # Abbreviation like AI, NASA
            return True
        if re.match(r'^[\d.,:/%-]+$', word):  # Number-like
            return True
        if word.startswith(("http", "www", "@", "#")):  # URL / handle / hashtag
            return True
        if re.match(r'^[a-z]$', word):  # Single letter
            return True
        return False

    @staticmethod
    def _match_case(original: str, replacement: str) -> str:
        """Try to match the capitalization of original in replacement."""
        if original.isupper():
            return replacement.upper()
        if original.istitle():
            return replacement.title()
        if original.islower():
            return replacement.lower()
        return replacement


# ---------------------------------------------------------------------------
# AI-powered Context-Aware Spell Checker
# ---------------------------------------------------------------------------
class AISpellChecker:
    """Context-aware spell checking using AI."""

    def __init__(self, language: str = "en", domain: str = ""):
        self.language = language
        self.domain = domain
        self.lang_name = ALL_LANGUAGES.get(language, language)

    def check_text(self, text: str, max_tokens: int = 4096) -> List[SpellError]:
        """Use AI to find spelling errors in context."""
        if len(text.strip()) < 5:
            return []

        lang_label = self.lang_name
        domain_hint = f" in the {self.domain} domain" if self.domain else ""

        system_prompt = (
            f"You are an expert {lang_label} spelling and proofreading assistant{domain_hint}. "
            f"Your task is to identify misspelled words in the provided text. "
            f"Return ONLY a JSON array of objects, each with keys: "
            f'"word", "line", "col" (1-based), "suggestions" (list of corrections), '
            f'"context" (short surrounding text). '
            f"If no errors are found, return an empty array []. "
            f"Do NOT flag proper nouns, technical terms, abbreviations, or domain-specific jargon as errors. "
            f"Respond with valid JSON only, no markdown fences."
        )

        # Chunk text if very long
        chunks = self._chunk_text(text, max_chars=3000)
        all_errors: List[SpellError] = []

        for chunk_text, line_offset in chunks:
            prompt = f"Find spelling errors in this {lang_label} text:\n\n{chunk_text}"
            try:
                raw = ai_generate(prompt, system_prompt=system_prompt,
                                  max_tokens=max_tokens, temperature=0.1)
                errors = self._parse_ai_errors(raw, line_offset)
                all_errors.extend(errors)
            except Exception as e:
                print(f"  AI spell check error: {e}")

        return all_errors

    def check_grammar(self, text: str, max_tokens: int = 4096) -> List[GrammarError]:
        """Use AI to find grammar and style errors."""
        if len(text.strip()) < 10:
            return []

        lang_label = self.lang_name
        domain_hint = f" in the {self.domain} domain" if self.domain else ""

        system_prompt = (
            f"You are an expert {lang_label} grammar and style checker{domain_hint}. "
            f"Identify grammar errors, awkward phrasing, subject-verb disagreement, "
            f"tense issues, article misuse, and style problems. "
            f"Return ONLY a JSON array of objects with keys: "
            f'"message", "line" (1-based), "col" (1-based), "suggestion" (corrected version), '
            f'"context" (short surrounding text), "severity" (error|warning|info). '
            f"If no errors, return []. "
            f"Respond with valid JSON only, no markdown fences."
        )

        chunks = self._chunk_text(text, max_chars=3000)
        all_errors: List[GrammarError] = []

        for chunk_text, line_offset in chunks:
            prompt = f"Check grammar and style in this {lang_label} text:\n\n{chunk_text}"
            try:
                raw = ai_generate(prompt, system_prompt=system_prompt,
                                  max_tokens=max_tokens, temperature=0.1)
                errors = self._parse_grammar_errors(raw, line_offset)
                all_errors.extend(errors)
            except Exception as e:
                print(f"  AI grammar check error: {e}")

        return all_errors

    def auto_correct(self, text: str, max_tokens: int = 4096) -> str:
        """Use AI to auto-correct spelling and grammar."""
        lang_label = self.lang_name
        domain_hint = f" in the {self.domain} domain" if self.domain else ""

        system_prompt = (
            f"You are an expert {lang_label} proofreader{domain_hint}. "
            f"Correct all spelling and grammar errors in the text. "
            f"Preserve the original meaning, tone, and formatting. "
            f"Return ONLY the corrected text, nothing else."
        )

        # For very long text, process in chunks
        if len(text) <= 4000:
            try:
                return ai_generate(
                    f"Correct this text:\n\n{text}",
                    system_prompt=system_prompt,
                    max_tokens=max_tokens, temperature=0.1,
                )
            except Exception as e:
                print(f"  AI auto-correct error: {e}")
                return text

        # Chunked correction
        chunks = self._chunk_text(text, max_chars=3000)
        corrected_parts = []
        for chunk_text, _ in chunks:
            try:
                part = ai_generate(
                    f"Correct this text:\n\n{chunk_text}",
                    system_prompt=system_prompt,
                    max_tokens=max_tokens, temperature=0.1,
                )
                corrected_parts.append(part)
            except Exception as e:
                print(f"  AI auto-correct chunk error: {e}")
                corrected_parts.append(chunk_text)
        return "\n\n".join(corrected_parts)

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 3000) -> List[Tuple[str, int]]:
        """Split text into chunks at paragraph boundaries, returning (chunk, line_offset)."""
        paragraphs = text.split("\n\n")
        chunks: List[Tuple[str, int]] = []
        current = ""
        line_offset = 1

        for para in paragraphs:
            candidate = current + "\n\n" + para if current else para
            if len(candidate) > max_chars and current:
                chunks.append((current.strip(), line_offset))
                line_offset += current.count("\n") + 2
                current = para
            else:
                current = candidate

        if current.strip():
            chunks.append((current.strip(), line_offset))
        return chunks

    @staticmethod
    def _parse_ai_errors(raw: str, line_offset: int = 0) -> List[SpellError]:
        """Parse AI response into SpellError objects."""
        errors: List[SpellError] = []
        try:
            # Strip markdown fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'\s*```$', '', cleaned)
            data = json.loads(cleaned)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "word" in item:
                        errors.append(SpellError(
                            word=str(item["word"]),
                            line=int(item.get("line", 1)) + line_offset - 1,
                            col=int(item.get("col", 1)),
                            suggestions=item.get("suggestions", []),
                            context=item.get("context", ""),
                            error_type="ai_context",
                        ))
        except (json.JSONDecodeError, ValueError, TypeError):
            # Try to extract partial results
            for m in re.finditer(r'"word"\s*:\s*"([^"]+)"', raw):
                errors.append(SpellError(
                    word=m.group(1), line=1, col=1,
                    error_type="ai_context",
                ))
        return errors

    @staticmethod
    def _parse_grammar_errors(raw: str, line_offset: int = 0) -> List[GrammarError]:
        """Parse AI grammar response into GrammarError objects."""
        errors: List[GrammarError] = []
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'\s*```$', '', cleaned)
            data = json.loads(cleaned)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "message" in item:
                        errors.append(GrammarError(
                            message=str(item["message"]),
                            line=int(item.get("line", 1)) + line_offset - 1,
                            col=int(item.get("col", 1)),
                            suggestion=item.get("suggestion", ""),
                            context=item.get("context", ""),
                            severity=item.get("severity", "warning"),
                        ))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
        return errors


# ---------------------------------------------------------------------------
# Composite Spell Checker
# ---------------------------------------------------------------------------
class CompositeSpellChecker:
    """Combines dictionary-based and AI-based spell checking."""

    def __init__(self, language: str = "en",
                 domain: str = "",
                 custom_dict_path: str = None,
                 use_ai: bool = True,
                 check_grammar: bool = False):
        self.language = language
        self.domain = domain
        self.use_ai = use_ai
        self.check_grammar_flag = check_grammar

        domain_list = [domain] if domain and domain in DOMAIN_DICTIONARIES else []
        self.dict_checker = DictionaryChecker(
            language=language,
            domain_dicts=domain_list,
            custom_dict_path=custom_dict_path,
        )
        self.ai_checker = AISpellChecker(
            language=language,
            domain=domain,
        ) if use_ai else None

    def check(self, text: str, ai_max_tokens: int = 4096) -> SpellCheckResult:
        """Run full spell check on text."""
        result = SpellCheckResult(language=self.language)
        result.domain = self.domain

        # Count words
        words = re.findall(r'\b[\w\'-]+\b', text)
        result.total_words = len(words)

        # Step 1: Dictionary-based check
        dict_errors = self.dict_checker.check_text(text)
        result.spell_errors.extend(dict_errors)

        # Step 2: AI context-aware check (finds errors dictionary misses)
        if self.ai_checker:
            ai_errors = self.ai_checker.check_text(text, max_tokens=ai_max_tokens)
            # Deduplicate: skip AI errors already found by dictionary
            dict_error_words = {(e.word.lower(), e.line) for e in dict_errors}
            for ae in ai_errors:
                if (ae.word.lower(), ae.line) not in dict_error_words:
                    result.spell_errors.append(ae)

            # Step 3: Grammar check
            if self.check_grammar_flag:
                grammar_errors = self.ai_checker.check_grammar(text, max_tokens=ai_max_tokens)
                result.grammar_errors.extend(grammar_errors)

        # Sort errors by line, then column
        result.spell_errors.sort(key=lambda e: (e.line, e.col))
        result.grammar_errors.sort(key=lambda e: (e.line, e.col))

        return result

    def auto_correct(self, text: str, use_ai: bool = True) -> str:
        """Auto-correct text using best available method."""
        if use_ai and self.ai_checker:
            return self.ai_checker.auto_correct(text)
        return self.dict_checker.auto_correct(text)

    def suggest(self, word: str, n: int = 10) -> List[str]:
        """Get suggestions for a single word."""
        is_correct, suggestions = self.dict_checker.check_word(word)
        if is_correct:
            return []
        return suggestions[:n]


# ---------------------------------------------------------------------------
# Batch Processing
# ---------------------------------------------------------------------------
class BatchProcessor:
    """Process multiple files in batch."""

    def __init__(self, checker: CompositeSpellChecker):
        self.checker = checker

    def process_files(self, file_paths: List[str],
                      auto_correct: bool = False,
                      output_dir: str = None) -> List[SpellCheckResult]:
        """Process a list of files."""
        results = []
        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                print(f"  SKIP: {fp} not found")
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"  SKIP: {fp} read error: {e}")
                continue

            print(f"  Checking: {fp} ({len(text)} chars) ...")
            result = self.checker.check(text)
            result.source = str(path)
            results.append(result)

            # Auto-correct and save
            if auto_correct:
                corrected = self.checker.auto_correct(text)
                result.corrected_text = corrected
                if output_dir:
                    out_path = Path(output_dir) / f"{path.stem}_corrected{path.suffix}"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(corrected, encoding="utf-8")
                    print(f"    Saved corrected: {out_path}")

        return results

    def process_directory(self, directory: str, pattern: str = "*.txt",
                          auto_correct: bool = False,
                          output_dir: str = None) -> List[SpellCheckResult]:
        """Process all matching files in a directory."""
        dir_path = Path(directory)
        if not dir_path.is_dir():
            print(f"  ERROR: {directory} is not a directory")
            return []

        files = sorted(dir_path.glob(pattern))
        if not files:
            print(f"  No files matching '{pattern}' in {directory}")
            return []

        print(f"  Found {len(files)} files matching '{pattern}'")
        return self.process_files(
            [str(f) for f in files],
            auto_correct=auto_correct,
            output_dir=output_dir,
        )


# ---------------------------------------------------------------------------
# Statistics Aggregator
# ---------------------------------------------------------------------------
class StatisticsAggregator:
    """Aggregate statistics across multiple results."""

    @staticmethod
    def aggregate(results: List[SpellCheckResult]) -> Dict[str, Any]:
        """Compute aggregate statistics."""
        if not results:
            return {}

        total_words = sum(r.total_words for r in results)
        total_spell_errors = sum(r.error_count for r in results)
        total_grammar_errors = sum(r.grammar_error_count for r in results)

        # Global error rate
        error_rate = total_spell_errors / total_words if total_words else 0.0

        # Most common misspellings across all files
        global_counter: Counter = Counter()
        for r in results:
            for e in r.spell_errors:
                global_counter[e.word] += 1

        # Error type distribution
        type_dist: Dict[str, int] = defaultdict(int)
        for r in results:
            for e in r.spell_errors:
                type_dist[e.error_type] += 1

        # Per-file summary
        per_file = []
        for r in results:
            per_file.append({
                "source": r.source,
                "total_words": r.total_words,
                "spell_errors": r.error_count,
                "grammar_errors": r.grammar_error_count,
                "error_rate": round(r.error_rate, 6),
            })

        # Files sorted by error rate (worst first)
        worst_files = sorted(per_file, key=lambda x: -x["error_rate"])[:10]

        return {
            "files_checked": len(results),
            "total_words": total_words,
            "total_spell_errors": total_spell_errors,
            "total_grammar_errors": total_grammar_errors,
            "overall_error_rate": round(error_rate, 6),
            "most_common_errors": global_counter.most_common(30),
            "error_type_distribution": dict(type_dist),
            "worst_files": worst_files,
            "per_file": per_file,
        }

    @staticmethod
    def format_aggregate(stats: Dict[str, Any]) -> str:
        """Format aggregate stats as readable report."""
        if not stats:
            return "No statistics available."

        lines = [
            "╔═══════════════════════════════════════════════════╗",
            "║         Batch Spell Check — Aggregate Report       ║",
            "╚═══════════════════════════════════════════════════╝",
            "",
            f"  Files checked       : {stats['files_checked']}",
            f"  Total words         : {stats['total_words']:,}",
            f"  Total spell errors  : {stats['total_spell_errors']:,}",
            f"  Total grammar errors: {stats['total_grammar_errors']:,}",
            f"  Overall error rate  : {stats['overall_error_rate']:.4%}",
            "",
        ]

        if stats.get("most_common_errors"):
            lines.append("  Top misspellings across all files:")
            for word, count in stats["most_common_errors"][:15]:
                lines.append(f"    • {word:<25s} ×{count}")
            lines.append("")

        if stats.get("error_type_distribution"):
            lines.append("  Error type distribution:")
            for etype, count in sorted(stats["error_type_distribution"].items(),
                                       key=lambda x: -x[1]):
                lines.append(f"    • {etype:<20s} : {count}")
            lines.append("")

        if stats.get("worst_files"):
            lines.append("  Worst files (by error rate):")
            for f in stats["worst_files"][:5]:
                lines.append(f"    • {f['source']:<40s}  rate={f['error_rate']:.4%}")
            lines.append("")

        lines.append("═══════════════════════════════════════════════════")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Custom Dictionary Builder
# ---------------------------------------------------------------------------
def build_custom_dict_from_file(filepath: str, output_path: str = None) -> int:
    """Extract unique words from a file to build a custom dictionary."""
    text = Path(filepath).read_text(encoding="utf-8")
    words = set(re.findall(r'\b[a-zA-Z]{3,}\b', text.lower()))
    sorted_words = sorted(words)

    out = output_path or str(Path(filepath).with_suffix(".dict"))
    Path(out).write_text("\n".join(sorted_words) + "\n", encoding="utf-8")
    print(f"  Extracted {len(sorted_words)} unique words → {out}")
    return len(sorted_words)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive Spell Checker — dictionary + AI + grammar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --text "teh quikc brown fox"
  %(prog)s --file document.txt
  %(prog)s --file doc.txt --language id
  %(prog)s --file doc.txt --grammar
  %(prog)s --file doc.txt --auto-correct
  %(prog)s --file doc.txt --domain academic
  %(prog)s --batch dir/*.txt --stats
  %(prog)s --file doc.txt --output results.json
  %(prog)s --text "recieve the occurence" --suggest
  %(prog)s --build-dict corpus.txt
        """,
    )

    # Input sources
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--text", help="Text to check directly")
    input_group.add_argument("--file", help="File to check")
    input_group.add_argument("--batch", nargs="+", help="Files/patterns for batch processing")
    input_group.add_argument("--build-dict", metavar="FILE",
                             help="Build custom dictionary from file")

    # Options
    parser.add_argument("--language", "-l", default="en",
                        help=f"Language code (default: en). "
                             f"Supported: {', '.join(sorted(ALL_LANGUAGES.keys()))}")
    parser.add_argument("--domain", "-d", default="",
                        choices=["", "academic", "technical", "medical", "all"],
                        help="Domain-specific dictionary")
    parser.add_argument("--grammar", "-g", action="store_true",
                        help="Also check grammar using AI")
    parser.add_argument("--auto-correct", "-a", action="store_true",
                        help="Auto-correct and output corrected text")
    parser.add_argument("--suggest", "-s", action="store_true",
                        help="Show suggestions for each error")
    parser.add_argument("--no-ai", action="store_true",
                        help="Disable AI-based checking (dictionary only)")
    parser.add_argument("--custom-dict", help="Path to custom dictionary file")
    parser.add_argument("--output", "-o", help="Output results as JSON to file")
    parser.add_argument("--stats", action="store_true",
                        help="Show aggregate statistics (batch mode)")
    parser.add_argument("--output-dir", help="Directory for corrected files (batch)")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Minimal output (errors only)")
    parser.add_argument("--max-tokens", type=int, default=4096,
                        help="Max tokens for AI calls (default: 4096)")

    args = parser.parse_args()

    # --- Build dictionary mode ---
    if args.build_dict:
        count = build_custom_dict_from_file(args.build_dict)
        print(f"  Done. {count} words extracted.")
        return

    # --- Validate language ---
    if args.language not in ALL_LANGUAGES:
        print(f"ERROR: Unsupported language '{args.language}'.")
        print(f"  Supported: {', '.join(sorted(ALL_LANGUAGES.keys()))}")
        sys.exit(1)

    # --- Initialize checker ---
    checker = CompositeSpellChecker(
        language=args.language,
        domain=args.domain,
        custom_dict_path=args.custom_dict,
        use_ai=not args.no_ai,
        check_grammar=args.grammar,
    )

    # --- Single text mode ---
    if args.text:
        result = checker.check(args.text, ai_max_tokens=args.max_tokens)
        result.source = "<stdin>"

        if args.auto_correct:
            corrected = checker.auto_correct(args.text, use_ai=not args.no_ai)
            result.corrected_text = corrected
            if not args.quiet:
                print("\n── Corrected Text ──")
                print(corrected)
                print()

        if not args.quiet:
            print(result.summary())

        if args.suggest:
            print("\n── Suggestions ──")
            for err in result.spell_errors:
                sugg = ", ".join(err.suggestions[:5]) if err.suggestions else "—"
                print(f"  {err.word:<25s} → {sugg}")

        if args.output:
            _save_json(result.to_dict(), args.output)
        return

    # --- Single file mode ---
    if args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"ERROR: File not found: {args.file}")
            sys.exit(1)

        text = filepath.read_text(encoding="utf-8")
        result = checker.check(text, ai_max_tokens=args.max_tokens)
        result.source = str(filepath)

        if args.auto_correct:
            corrected = checker.auto_correct(text, use_ai=not args.no_ai)
            result.corrected_text = corrected
            if not args.quiet:
                print("\n── Corrected Text ──")
                print(corrected)
                print()

        if not args.quiet:
            print(result.summary())

        if args.suggest:
            print("\n── Suggestions ──")
            for err in result.spell_errors:
                sugg = ", ".join(err.suggestions[:5]) if err.suggestions else "—"
                print(f"  {err.word:<25s} → {sugg}")

        if args.output:
            _save_json(result.to_dict(), args.output)
        return

    # --- Batch mode ---
    if args.batch:
        # Expand glob patterns
        file_list = _expand_patterns(args.batch)
        if not file_list:
            print("ERROR: No files matched the given patterns.")
            sys.exit(1)

        processor = BatchProcessor(checker)
        results = processor.process_files(
            file_list,
            auto_correct=args.auto_correct,
            output_dir=args.output_dir,
        )

        if not args.quiet:
            for r in results:
                print(r.summary())
                print()

        if args.stats:
            stats = StatisticsAggregator.aggregate(results)
            print(StatisticsAggregator.format_aggregate(stats))
            if args.output:
                _save_json(stats, args.output)
        elif args.output:
            batch_data = {
                "results": [r.to_dict() for r in results],
                "aggregate": StatisticsAggregator.aggregate(results),
            }
            _save_json(batch_data, args.output)
        return

    # No input provided
    parser.print_help()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _save_json(data: Any, path: str) -> None:
    """Save data as JSON file."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Results saved to: {path}")


def _expand_patterns(patterns: List[str]) -> List[str]:
    """Expand glob patterns into file list."""
    from glob import glob
    files = []
    for p in patterns:
        matches = glob(p, recursive=True)
        if matches:
            files.extend(matches)
        elif Path(p).exists():
            files.append(p)
    return sorted(set(files))


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
