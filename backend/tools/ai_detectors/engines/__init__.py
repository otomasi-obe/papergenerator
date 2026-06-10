"""Registry of all AI detection engines."""

__version__ = "1.0.0"

from .linguistic import LinguisticMarkerEngine
from .vocabulary import VocabularyRichnessEngine
from .structural import StructuralEngine
from .formulaic import FormulaicEngine
from .readability import ReadabilityUniformityEngine
from .burstiness import BurstinessEngine
from .sentiment import SentimentHedgingEngine
from .slop import SlopWordEngine
from .fingerprint import PhraseFingerprintEngine
from .common_words import CommonWordEngine
from .repetition import RepetitionEngine
from .syntactic import SyntacticUniformityEngine
from .perplexity_proxy import PerplexityProxyEngine
from .punctuation import PunctuationEngine
from .model_attribution import ModelAttributionEngine
from .human_signal import HumanSignalEngine
from .semantic_coherence import SemanticCoherenceEngine

ALL_ENGINES = [
    LinguisticMarkerEngine,
    VocabularyRichnessEngine,
    StructuralEngine,
    FormulaicEngine,
    ReadabilityUniformityEngine,
    BurstinessEngine,
    SentimentHedgingEngine,
    SlopWordEngine,
    PhraseFingerprintEngine,
    CommonWordEngine,
    RepetitionEngine,
    SyntacticUniformityEngine,
    PerplexityProxyEngine,
    PunctuationEngine,
    ModelAttributionEngine,
    HumanSignalEngine,
    SemanticCoherenceEngine,
]

__all__ = ["ALL_ENGINES"]
