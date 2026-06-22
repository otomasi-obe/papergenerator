"""
Text Humanizer
===============
Transform AI-generated text into natural, human-like writing.
Inspired by: StealthHumanizer, Humanizer (VHumanize), humanize-text, mytext, DeSlop.

Features:
  - Multi-pass AI rewriting via AIOTOMASI API
  - Translation chain method (EN->ID->DE->FR->EN)
  - Style-aware rewriting (academic, casual, professional, creative)
  - Slop word removal and replacement (80+ patterns)
  - Sentence structure variation (burstiness engineering)
  - AI detection scoring before/after
  - Batch processing
  - Intensity levels (light, medium, aggressive)
  - Humanity score estimation

Usage:
    from humanizers.humanizer import TextHumanizer

    h = TextHumanizer()
    result = h.humanize("Furthermore, the results indicate...", style="academic", intensity="medium")
    print(result)
"""

import os
import re
import json
import logging
import statistics
from typing import Optional, Dict, List, Tuple
from pathlib import Path

import requests
from dotenv import load_dotenv
from utils.ai_tools.model_config import get_primary_generate_model

# ── Load .env ───────────────────────────────────────────────────────────────
_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

log = logging.getLogger(__name__)

# ── AI slop patterns to remove/replace ──────────────────────────────────────
# Tier 1: Dead giveaways (3pts each) - these appear 5-25x more in AI text
_SLOP_REPLACEMENTS = {
    # === INDONESIAN ACADEMIC PATTERNS (50+ additions) ===
    # Tier 1: Dead giveaways — Turnitin Indonesia
    r'\\bperlu dicatat bahwa\\b': ['', 'Catat bahwa', ''],
    r'\\bdalam era digital ini\\b': ['saat ini', 'sekarang', ''],
    r'\\bdengan pesatnya perkembangan\\b': ['dengan kemajuan', 'seiring dengan', ''],
    r'\\bdi era globalisasi\\b': ['saat ini', 'sekarang', 'dalam konteks global'],
    r'\\bmemainkan peran penting\\b': ['berperan dalam', 'penting untuk', 'menentukan'],
    r'\\bberkontribusi signifikan\\b': ['berkontribusi pada', 'menyumbang pada', 'memberikan'],
    r'\\bmemberikan dampak positif\\b': ['berdampak positif', 'meningkatkan', 'memperbaiki'],
    r'\\bsecara komprehensif\\b': ['menyeluruh', 'lengkap', 'mencakup'],
    r'\\bpendekatan holistik\\b': ['pendekatan terpadu', 'metode lengkap', 'cara menyeluruh'],
    r'\\bsecara menyeluruh\\b': ['keseluruhan', 'lengkap', ''],
    r'\\bdalam penelitian ini\\b': ['kami', 'dalam studi ini', ''],
    r'\\bberdasarkan hasil analisis\\b': ['hasil analisis menunjukkan', 'data menunjukkan', 'analisis memperlihatkan'],
    r'\\bdapat disimpulkan bahwa\\b': ['kesimpulannya,', 'simpulannya,', 'sebagai penutup,'],
    r'\\bsebagaimana telah dijelaskan\\b': ['seperti yang dijelaskan', 'seperti diuraikan', ''],
    r'\\btidak dapat dipungkiri\\b': ['tak bisa dipungkiri', 'jelas bahwa', ''],
    r'\\bperlu digarisbawahi bahwa\\b': ['perlu ditekankan', 'penting untuk dicatat', ''],

    # Tier 2: High Risk — Indonesia
    r'\\bselain itu,?\\b': ['Di samping itu,', 'Juga,', 'Lalu,', ''],
    r'\\boleh karena itu,?\\b': ['Karena itu,', 'Maka,', 'Sehingga,', ''],
    r'\\bnamun demikian,?\\b': ['Tapi,', 'Meski begitu,', 'Walaupun begitu,', ''],
    r'\\bsebagai kesimpulan,?\\b': ['Kesimpulannya,', 'Simpulannya,', ''],
    r'\\bdari hasil penelitian ini dapat diketahui\\b': ['hasilnya:', 'temuan menunjukkan', ''],
    r'\\bmenurut para ahli\\b': ['literatur menunjukkan', 'penelitian sebelumnya menunjukkan', 'sesuai temuan'],
    r'\\bberbagai penelitian menunjukkan\\b': ['studi menunjukkan', 'penelitian menunjukkan', 'riset memperlihatkan'],
    r'\\bpenting untuk dipahami bahwa\\b': ['perlu dipahami:', 'perlu diketahui:', ''],
    r'\\bdalam konteks ini\\b': ['di sini', 'dalam hal ini', ''],
    r'\\bsecara umum dapat dikatakan\\b': ['umumnya', 'secara umum', 'pada dasarnya'],
    r'\\bhal ini menunjukkan bahwa\\b': ['ini menunjukkan bahwa', 'artinya', ''],
    r'\\bsejalan dengan penelitian sebelumnya\\b': ['konsisten dengan studi sebelumnya', 'sejalan dengan riset terdahulu', ''],
    r'\\bhasil ini mengindikasikan adanya\\b': ['hasil ini menunjukkan', 'temuan ini memperlihatkan', ''],
    r'\\blebih lanjut,?\\b': ['Selanjutnya,', 'Kemudian,', 'Lalu,', ''],

    # Tier 3: Formal Indonesia phrases that scream AI
    r'\\bmelakukan penelitian\\b': ['meneliti', 'mengkaji', 'mengeksplorasi'],
    r'\\bmelakukan analisis\\b': ['menganalisis', 'menguji', 'mengkaji'],
    r'\\bmelakukan evaluasi\\b': ['mengevaluasi', 'menilai', 'mengukur'],
    r'\\bmelakukan pengumpulan data\\b': ['mengumpulkan data', 'merekam data', 'mendata'],
    r'\\bmelakukan pengukuran\\b': ['mengukur', 'menghitung', 'mencatat'],
    r'\\bdilakukan dengan menggunakan\\b': ['menggunakan', 'dengan', 'memakai'],
    r'\\bdapat dilihat pada tabel\\b': ['ditampilkan di Tabel', 'tertera di Tabel', 'Tabel X menunjukkan'],
    r'\\bdapat dilihat pada gambar\\b': ['ditampilkan di Fig.', 'terlihat di Fig.', 'Fig. X memperlihatkan'],
    r'\\bberdasarkan gambar tersebut\\b': ['dari Fig. X terlihat', 'Fig. X menunjukkan', ''],
    r'\\bberdasarkan tabel tersebut\\b': ['Tabel X menunjukkan', 'dari Tabel X terlihat', ''],
    r'\\bdapat dikatakan bahwa\\b': ['singkatnya', 'pada dasarnya', ''],
    r'\\bdapat diketahui bahwa\\b': ['terlihat bahwa', 'data menunjukkan bahwa', ''],
    r'\\bdapat dijelaskan bahwa\\b': ['penjelasannya:', 'alasannya:', ''],
    r'\\bdapat disimpulkan\\b': ['simpulannya', 'kesimpulannya', 'sebagai penutup'],
    r'\\bdiperoleh hasil\\b': ['hasilnya', 'didapatkan', 'tercatat'],
    r'\\bsebagai berikut\\b': [':', 'berikut ini', ''],
    r'\\badapun\\b': ['', 'Sementara itu,', ''],

    # === ORIGINAL PATTERNS ===
    r'\bfurthermore,?\b': ['Moreover,', 'Also,', 'And', ''],
    r'\bmoreover,?\b': ['Also,', 'Plus,', 'And', ''],
    r'\badditionally,?\b': ['Also,', 'Plus,', 'On top of that,', ''],
    r'\bconsequently,?\b': ['So,', 'As a result,', 'Thus,', ''],
    r'\bnevertheless,?\b': ['Still,', 'Even so,', 'But', ''],
    r'\bnonetheless,?\b': ['Still,', 'Even so,', 'But', ''],
    r'\bhowever,?\b': ['But', 'Yet', 'Still,', ''],
    r'\btherefore,?\b': ['So,', 'Thus,', 'Hence,', ''],
    r'\bthus,?\b': ['So,', 'Hence,', 'This means', ''],
    r'\bhence,?\b': ['So,', 'This means', 'For this reason,', ''],
    r'\bsubsequently,?\b': ['Then,', 'After that,', 'Later,', ''],
    r'\bspecifically,?\b': ['In particular,', 'Namely,', ''],
    r'\bnotably,?\b': ['Notably,', 'Interestingly,', ''],
    r'\bsignificantly,?\b': ['Notably,', 'Importantly,', ''],
    r'\bimportantly,?\b': ['Notably,', 'Crucially,', ''],
    r'\bit is important to note that\b': ['Note that', 'Note:', ''],
    r'\bit should be noted that\b': ['Note that', 'Note:', ''],
    r'\bit is worth mentioning that\b': ['', 'Worth noting:', ''],
    r'\bit is worth noting that\b': ['', 'Worth noting:', ''],
    r'\bin conclusion\b': ['To sum up,', 'Overall,', 'In short,', ''],
    r'\bto summarize\b': ['In short,', 'To sum up,', 'Overall,', ''],
    r'\bin summary\b': ['In short,', 'Overall,', 'To sum up,', ''],
    r'\bdelve\b': ['explore', 'examine', 'investigate', 'look into'],
    r'\bdelving\b': ['exploring', 'examining', 'investigating'],
    r'\bdelved\b': ['explored', 'examined', 'investigated'],
    r'\bleverage\b': ['use', 'apply', 'take advantage of'],
    r'\bleveraging\b': ['using', 'applying', 'taking advantage of'],
    r'\butilize\b': ['use', 'apply', 'employ'],
    r'\butilizing\b': ['using', 'applying', 'employing'],
    r'\bfacilitate\b': ['help', 'enable', 'support'],
    r'\bfacilitating\b': ['helping', 'enabling', 'supporting'],
    r'\brobust\b': ['strong', 'solid', 'reliable'],
    r'\bcomprehensive\b': ['thorough', 'complete', 'detailed'],
    r'\bholistic\b': ['complete', 'overall', 'broad'],
    r'\bsynergy\b': ['cooperation', 'collaboration', 'combined effect'],
    r'\bparadigm\b': ['model', 'approach', 'framework'],
    r'\blandscape\b': ['field', 'area', 'domain'],
    r'\bmultifaceted\b': ['complex', 'varied', 'diverse'],
    r'\bpivotal\b': ['key', 'crucial', 'important'],
    r'\bcornerstone\b': ['foundation', 'basis', 'core'],
    r'\bcutting-edge\b': ['advanced', 'modern', 'latest'],
    r'\bstate-of-the-art\b': ['advanced', 'modern', 'latest'],
    r'\bever-evolving\b': ['changing', 'developing', 'growing'],
    r'\bseamless\b': ['smooth', 'easy', 'simple'],
    r'\bseamlessly\b': ['smoothly', 'easily', 'simply'],
    r'\bstreamline\b': ['simplify', 'improve', 'optimize'],
    r'\bstreamlined\b': ['simplified', 'improved', 'optimized'],
    r'\boptimize\b': ['improve', 'enhance', 'refine'],
    r'\boptimized\b': ['improved', 'enhanced', 'refined'],
    r'\bempower\b': ['enable', 'help', 'allow'],
    r'\bempowering\b': ['enabling', 'helping', 'allowing'],
    r'\btransformative\b': ['significant', 'major', 'important'],
    r'\bgroundbreaking\b': ['innovative', 'novel', 'new'],
    r'\brevolutionary\b': ['innovative', 'novel', 'new'],
    r'\becosystem\b': ['environment', 'system', 'network'],
    r'\bin the realm of\b': ['in', 'in the field of', 'regarding'],
    r'\bin the context of\b': ['in', 'regarding', 'for'],
    r'\bwith the advent of\b': ['with', 'since', 'after'],
    r'\ba wide range of\b': ['many', 'various', 'numerous'],
    r'\ba plethora of\b': ['many', 'numerous', 'various'],
    r'\ba myriad of\b': ['many', 'numerous', 'various'],
    r'\ba multitude of\b': ['many', 'numerous', 'various'],
    r'\bit is undeniable that\b': ['clearly,', 'obviously,', ''],
    r'\bit is evident that\b': ['clearly,', 'obviously,', ''],
    r'\bit is apparent that\b': ['clearly,', 'obviously,', ''],
    r'\bit is clear that\b': ['clearly,', 'obviously,', ''],
    r'\bit is imperative that\b': ['we must', 'it is essential to', ''],
    r'\bit is essential that\b': ['we must', 'it is important to', ''],
    r'\bit is crucial that\b': ['we must', 'it is important to', ''],
    r'\bcrucial\b': ['important', 'key', 'vital'],
    r'\bleverages\b': ['uses', 'applies', 'takes advantage of'],
    r'\bleveraged\b': ['used', 'applied', 'took advantage of'],
    r'\bplays a crucial role\b': ['is important', 'matters', 'is key'],
    r'\bplays a vital role\b': ['is important', 'matters', 'is key'],
    r'\bplays an important role\b': ['is important', 'matters', 'is key'],
    r'\bresearch has shown that\b': ['research shows', 'studies show', ''],
    r'\bstudies have shown that\b': ['studies show', 'research shows', ''],
    r'\bresearch suggests that\b': ['research indicates', 'studies suggest', ''],
    r'\baccording to research\b': ['research shows', 'studies show', ''],
    r'\baccording to studies\b': ['studies show', 'research shows', ''],
    r'\bat the end of the day\b': ['ultimately', 'in the end', ''],
    r'\bit goes without saying that\b': ['', 'obviously,', ''],
    r'\bneedless to say\b': ['', 'obviously,', ''],
    r'\bin today\'s world\b': ['today', 'now', 'currently'],
    r'\bin this day and age\b': ['today', 'now', 'currently'],
    r'\bwith regard to\b': ['regarding', 'about', 'concerning'],
    r'\bwith respect to\b': ['regarding', 'about', 'concerning'],
    r'\bin terms of\b': ['regarding', 'for', 'in'],
    r'\bon the other hand\b': ['but', 'however', 'yet'],
    r'\bhaving said that\b': ['but', 'however', 'yet'],
    r'\bthat being said\b': ['but', 'however', 'yet'],
    r'\bat the same time\b': ['meanwhile', 'also', ''],
    r'\bdeep dive\b': ['thorough analysis', 'detailed examination'],
    r'\btouch base\b': ['meet', 'discuss', 'connect'],
    r'\bcircle back\b': ['return to', 'revisit', 'follow up'],
    r'\bmove the needle\b': ['make progress', 'improve', 'advance'],

    # === NEW PATTERNS (50+ additions) ===
    # Tier 1: Dead giveaways
    r'\btapestry\b': ['fabric', 'collection', 'array'],
    r'\btestament\b': ['proof', 'evidence', 'example'],
    r'\binterplay\b': ['interaction', 'relationship', 'connection'],
    r'\bintricacies\b': ['details', 'complexities', 'nuances'],
    r'\bvibrant\b': ['active', 'lively', 'dynamic'],
    r'\bshowcasing\b': ['showing', 'featuring', 'highlighting'],
    r'\bunderscoring\b': ['emphasizing', 'stressing', 'highlighting'],
    r'\bfostering\b': ['encouraging', 'promoting', 'supporting'],
    r'\bgarnering\b': ['receiving', 'gaining', 'obtaining'],
    r'\bunderscore\b': ['emphasize', 'stress', 'highlight'],
    r'\blends seamlessly\b': ['integrates well', 'works smoothly'],

    # Tier 2: Corporate/Formal Buzzwords
    r'\balign with\b': ['match', 'fit', 'agree with'],
    r'\bemphasizing\b': ['stressing', 'highlighting', 'focusing on'],
    r'\bvaluable\b': ['useful', 'helpful', 'worthwhile'],
    r'\bnuanced\b': ['subtle', 'detailed', 'sophisticated'],
    r'\bnovel\b': ['new', 'original', 'innovative'],
    r'\bideate\b': ['brainstorm', 'think of', 'imagine'],
    r'\bcircle back on\b': ['return to', 'revisit', 'follow up on'],
    r'\btouch base on\b': ['discuss', 'check on', 'update about'],
    r'\bpassionate\b': ['enthusiastic', 'eager', 'dedicated'],
    r'\bmission-driven\b': ['purposeful', 'dedicated', 'focused'],
    r'\binnovative solution\b': ['new approach', 'creative fix', 'better method'],
    r'\bseamless integration\b': ['smooth connection', 'easy setup', 'working together'],
    r'\bscalable solution\b': ['expandable system', 'growable approach', 'flexible setup'],
    r'\benterprise-grade\b': ['professional', 'business-quality', 'industrial'],
    r'\bturnkey solution\b': ['ready-to-use system', 'complete package', 'all-in-one'],
    r'\bbest-in-class\b': ['top-quality', 'excellent', 'leading'],
    r'\bworld-class\b': ['excellent', 'outstanding', 'top-tier'],
    r'\bbest practices\b': ['good methods', 'effective approaches', 'proven techniques'],
    r'\bthought leadership\b': ['expertise', 'insight', 'knowledge'],
    r'\bdigital transformation\b': ['modernization', 'digitization', 'upgrading'],
    r'\blegacy system\b': ['old system', 'outdated setup', 'older platform'],
    r'\bfuture-proof\b': ['durable', 'lasting', 'long-term'],
    r'\bhyper-local\b': ['local', 'community-level', 'neighborhood'],
    r'\bmicro-moment\b': ['brief instant', 'quick moment', 'split-second'],
    r'\bvalue proposition\b': ['benefit', 'advantage', 'selling point'],
    r'\bjourney\b': ['process', 'experience', 'path'],
    r'\bcontent ecosystem\b': ['content system', 'media setup', 'publishing platform'],
    r'\bomnichannel\b': ['multi-channel', 'across platforms', 'everywhere'],

    # Tier 3: Weak signals but common
    r'\benhance\b': ['improve', 'boost', 'increase'],
    r'\blisten\b': ['hear', 'pay attention', 'notice'],
    r'\bnavigate\b': ['handle', 'deal with', 'manage'],
    r'\bdelve deeper\b': ['explore further', 'look closer', 'examine more'],
    r'\bkey takeaway\b': ['main point', 'key lesson', 'important finding'],
    r'\btakeaways\b': ['points', 'lessons', 'findings'],
    r'\bleverage the power\b': ['use', 'harness', 'tap into'],
    r'\btap into\b': ['use', 'access', 'draw from'],
    r'\bunlock the potential\b': ['realize the value', 'achieve', 'discover'],
    r'\bunlock insights\b': ['reveal findings', 'discover', 'show'],
    r'\bshed light on\b': ['reveal', 'explain', 'clarify'],
    r'\bpave the way\b': ['enable', 'allow', 'prepare'],
    r'\bmake a difference\b': ['matter', 'help', 'change things'],
    r'\bcutting edge\b': ['latest', 'advanced', 'newest'],
    r'\brevolutionary approach\b': ['new method', 'different way', 'fresh approach'],
    r'\bdisruptive innovation\b': ['major change', 'breakthrough', 'transformation'],
    r'\bparadigm shift\b': ['major change', 'big shift', 'transformation'],
    r'\bmove the dial\b': ['make progress', 'improve', 'advance'],
    r'\bquick wins\b': ['easy gains', 'fast improvements', 'simple fixes'],
    r'\bstrategic initiative\b': ['plan', 'effort', 'approach'],
    r'\bholistic approach\b': ['complete method', 'overall strategy', 'broad view'],
    r'\bend-to-end\b': ['complete', 'full', 'comprehensive'],
    r'\brobust solution\b': ['strong system', 'solid approach', 'reliable method'],
    r'\bactionable insights\b': ['useful findings', 'practical data', 'helpful information'],
    r'\bdata-driven\b': ['evidence-based', 'analytical', 'fact-supported'],
    r'\binsights-driven\b': ['analysis-based', 'informed by data', 'data-informed'],
    r'\bhuman-centered\b': ['user-focused', 'people-first', 'person-oriented'],
    r'\bhuman-centric\b': ['user-focused', 'people-first', 'person-centered'],
    r'\buser-centric\b': ['user-focused', 'customer-oriented', 'people-first'],
    r'\bdesign thinking\b': ['creative problem-solving', 'design approach', 'innovation method'],
    r'\bagile methodology\b': ['flexible method', 'iterative approach', 'agile process'],
    r'\bcustomer-centric\b': ['customer-focused', 'client-oriented', 'buyer-first'],
    r'\bgrowth hacking\b': ['rapid growth tactics', 'quick marketing', 'fast scaling'],
    r'\bproduct-market fit\b': ['market fit', 'product alignment', 'customer demand'],
    r'\bmoonshot\b': ['ambitious goal', 'big dream', 'huge project'],
    r'\bzero-to-one\b': ['new creation', 'innovation', 'groundbreaking'],
}

# ── Intensity level configurations ─────────────────────────────────────────
_INTENSITY_CONFIGS = {
    "light": {
        "slop_replacement_index": 2,  # Use mildest replacement option
        "vary_sentences": False,
        "merge_threshold": 6,
        "llm_passes": 1,
        "grammar_prepass": False,
        "temperature": 0.7,
    },
    "medium": {
        "slop_replacement_index": 1,
        "vary_sentences": True,
        "merge_threshold": 8,
        "llm_passes": 2,
        "grammar_prepass": False,
        "temperature": 0.8,
    },
    "aggressive": {
        "slop_replacement_index": 0,
        "vary_sentences": True,
        "merge_threshold": 10,
        "llm_passes": 3,
        "grammar_prepass": True,
        "temperature": 0.9,
    },
}

# ── AI pattern scoring (for humanity score) ────────────────────────────────
_AI_TIER1_PATTERNS = [
    r'\bdelve\b', r'\btapestry\b', r'\btestament\b', r'\binterplay\b',
    r'\bintricac', r'\bvibrant\b', r'\bshowcas', r'\bundercor',
    r'\bfoster', r'\bgarners?\b', r'\bcornerstone\b',
    r'\bembark (on|upon)\b', r'\bharness', r'\bunlock', r'\bunveil',
    r'\bever-(evolving|changing|growing)\b', r'\bnavigate\b']

_AI_TIER2_PATTERNS = [
    r'\bsynergy\b', r'\bleverage\b', r'\bparadigm\b', r'\becosystem\b',
    r'\brobust\b', r'\bscalable\b', r'\bseamless\b', r'\bcutting-edge\b',
    r'\bstate-of-the-art\b', r'\bever-evolving\b', r'\bmultifaceted\b',
    r'\bpivotal\b', r'\btransformative\b', r'\bgroundbreaking\b',
    r'\brevolutionary\b', r'\bholistic\b', r'\bprofound\b',
    r'\bseamless integration\b', r'\bvaluable insights\b',
    r'\bplays a (key|pivotal|crucial|vital) role\b']

_AI_TIER3_PATTERNS = [
    r'\\bfurthermore\\b', r'\\bmoreover\\b', r'\\badditionally\\b',
    r'\\bnevertheless\\b', r'\\bnonetheless\\b', r'\\bsubsequently\\b',
    r'\\bspecifically\\b', r'\\bnotably\\b', r'\\bsignificantly\\b',
    r'\\bit is important to note\\b', r'\\bit is worth noting\\b',
    r'\\bit should be noted\\b', r'\\bin conclusion\\b',
    r'\\bto summarize\\b', r'\\bin summary\\b']

# ── Indonesian AI patterns ────────────────────────────────────────────────
_AI_TIER1_ID_PATTERNS = [
    r'\\bperlu dicatat bahwa\\b', r'\\bdalam era digital ini\\b',
    r'\\bdengan pesatnya perkembangan\\b', r'\\bdi era globalisasi\\b',
    r'\\bmemainkan peran penting\\b', r'\\bberkontribusi signifikan\\b',
    r'\\bmemberikan dampak positif\\b', r'\\bsecara komprehensif\\b',
    r'\\bpendekatan holistik\\b', r'\\bsecara menyeluruh\\b',
    r'\\bdapat disimpulkan bahwa\\b', r'\\btidak dapat dipungkiri\\b']

_AI_TIER2_ID_PATTERNS = [
    r'\\bselain itu\\b', r'\\boleh karena itu\\b', r'\\bnamun demikian\\b',
    r'\\bsebagai kesimpulan\\b', r'\\bmenurut para ahli\\b',
    r'\\bberbagai penelitian menunjukkan\\b', r'\\bdalam konteks ini\\b',
    r'\\bhal ini menunjukkan bahwa\\b', r'\\blebih lanjut\\b']


class TextHumanizer:
    """Transform AI-generated text into natural human writing."""

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_url = api_url or self._build_api_url()
        self.api_key = api_key or os.getenv("AIOTOMASI_APIKEY", "")
        self.model = model or get_primary_generate_model()

    @staticmethod
    def _build_api_url() -> str:
        base = os.getenv("AIOTOMASI_API", "").rstrip("/")
        return f"{base}/chat/completions" if base else ""

    def _call_llm(self, system: str, user: str, temperature: float = 0.8) -> str:
        """Call the LLM via the per-index endpoint chain (MODELGENERATE1..3,
        each with its own endpoint+key)."""
        from utils.ai_tools.ai_client import chat as _chain_chat
        content, _used = _chain_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            heavy=True,
            max_tokens=4096,
            temperature=temperature,
            timeout=120,
        )
        return content

    def remove_slop(self, text: str, intensity: str = "medium") -> str:
        """Remove/replace AI slop words and phrases.

        Args:
            text: Input text
            intensity: 'light', 'medium', or 'aggressive' - controls replacement intensity
        """
        result = text
        config = _INTENSITY_CONFIGS.get(intensity, _INTENSITY_CONFIGS["medium"])

        for pattern, replacements in _SLOP_REPLACEMENTS.items():
            if replacements:
                idx = min(config["slop_replacement_index"], len(replacements) - 1)
                replacement = replacements[idx] if replacements[idx] else ''
                result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        # Clean up double spaces
        result = re.sub(r'  +', ' ', result)
        # Clean up double commas from replacement artifacts
        result = re.sub(r',,\s*', ', ', result)
        result = re.sub(r',\s*,\s*', ', ', result)
        # Clean up empty lines from removed phrases
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

    def vary_sentences(self, text: str, intensity: str = "medium") -> str:
        """Vary sentence structure to break AI patterns (burstiness engineering).

        Args:
            text: Input text
            intensity: Controls how aggressive the variation is
        """
        config = _INTENSITY_CONFIGS.get(intensity, _INTENSITY_CONFIGS["medium"])
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) < 3:
            return text

        merge_threshold = config["merge_threshold"]
        result = []
        i = 0

        while i < len(sentences):
            sent = sentences[i]

            # Combine short consecutive sentences
            if (i < len(sentences) - 1 and
                    len(sent.split()) < merge_threshold and
                    len(sentences[i + 1].split()) < merge_threshold):
                # Use varied connectors based on intensity
                if intensity == "aggressive":
                    connectors = [', and ', '. But ', '. Still, ', '; ']
                elif intensity == "medium":
                    connectors = [', and ', ', but ', '. And ']
                else:  # light
                    connectors = [', and ', ' and ']
                connector = connectors[i % len(connectors)]
                next_sent = sentences[i + 1]
                if connector.rstrip().endswith(','):
                    first_char = next_sent[0].lower()
                else:
                    first_char = next_sent[0]
                combined = sent.rstrip('.!?') + connector + first_char + next_sent[1:]
                result.append(combined)
                i += 2
                continue

            # Split long sentences at natural breakpoints
            if config["vary_sentences"] and len(sent.split()) > 25:
                # Try splitting at commas, semicolons, or 'and'/'but'
                for sep in ['; ', ', and ', ', but ', ', ']:
                    if sep in sent:
                        parts = sent.split(sep, 1)
                        if len(parts[0].split()) > 5:
                            result.append(parts[0].strip() + '.')
                            result.append(parts[1].strip())
                            break
                else:
                    result.append(sent)
            else:
                result.append(sent)
            i += 1

        return ' '.join(result)

    def estimate_humanity_score(self, text: str) -> Dict:
        """Estimate how human-like the text is (0-10 scale).

        Analyzes:
        - AI slop patterns (tier-weighted scoring)
        - Sentence length variance
        - Vocabulary richness
        - Voice indicators

        Returns dict with score breakdown.
        """
        if not text.strip():
            return {"overall": 0, "patterns": 0, "variance": 0, "voice": 0}

        # Count AI patterns by tier (English)
        text_lower = text.lower()
        tier1_count = sum(1 for p in _AI_TIER1_PATTERNS if re.search(p, text_lower))
        tier2_count = sum(1 for p in _AI_TIER2_PATTERNS if re.search(p, text_lower))
        tier3_count = sum(1 for p in _AI_TIER3_PATTERNS if re.search(p, text_lower))

        # Count AI patterns by tier (Indonesian)
        tier1_id_count = sum(1 for p in _AI_TIER1_ID_PATTERNS if re.search(p, text_lower))
        tier2_id_count = sum(1 for p in _AI_TIER2_ID_PATTERNS if re.search(p, text_lower))

        words = text.split()
        word_count = len(words) if words else 1

        # Normalize per 1000 words (combined English + Indonesian)
        raw_score = ((tier1_count + tier1_id_count) * 3 +
                     (tier2_count + tier2_id_count) * 2 +
                     tier3_count * 1) * (1000 / word_count)

        # Pattern score (lower is better, normalize to 0-10)
        pattern_score = max(0, 10 - raw_score)

        # Sentence length variance (higher CV = more human)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        sent_lengths = [len(s.split()) for s in sentences if s.strip()]
        if len(sent_lengths) > 1:
            mean_len = statistics.mean(sent_lengths)
            std_len = statistics.stdev(sent_lengths)
            cv = std_len / mean_len if mean_len > 0 else 0
            # CV > 0.3 is good, < 0.2 is suspicious
            variance_score = min(10, cv * 30)
        else:
            variance_score = 5

        # Voice indicators
        voice_score = 0
        if re.search(r'\b(I|we|my|our|me|us)\b', text, re.IGNORECASE):
            voice_score += 2
        if re.search(r'\bit\'s|don\'t|can\'t|won\'t|that\'s|there\'s\b', text):
            voice_score += 1.5
        if re.search(r'[.!?]', text):
            voice_score += 0.5
        if len(sentences) > 2 and any(len(s.split()) < 5 for s in sentences if s.strip()):
            voice_score += 1
        if re.search(r'\b(obviously|clearly|frankly|honestly|personally)\b', text, re.IGNORECASE):
            voice_score += 1
        voice_score = min(7, voice_score)

        # Composite score (weighted average)
        overall = (pattern_score * 0.4 + variance_score * 0.3 + voice_score * 0.3)

        return {
            "overall": round(overall, 1),
            "patterns": round(pattern_score, 1),
            "variance": round(variance_score, 1),
            "voice": round(voice_score, 1),
            "ai_signals": {
                "tier1_count": tier1_count,
                "tier2_count": tier2_count,
                "tier3_count": tier3_count,
                "tier1_id_count": tier1_id_count,
                "tier2_id_count": tier2_id_count,
            },
            "word_count": word_count,
            "sentence_count": len(sentences),
            "avg_sentence_length": round(statistics.mean(sent_lengths) if sent_lengths else 0, 1),
        }

    def humanize(
        self,
        text: str,
        style: str = "academic",
        intensity: str = "medium",
        passes: int = 3,
        use_llm: bool = True,
    ) -> str:
        """Humanize AI-generated text.

        Args:
            text: AI-generated text to humanize.
            style: Target style ('academic', 'casual', 'professional', 'creative', 'standard').
            intensity: Humanization intensity ('light', 'medium', 'aggressive').
            passes: Number of rewriting passes (1-3).
            use_llm: Whether to use LLM for rewriting (vs. rule-based only).

        Returns:
            Humanized text.
        """
        if not text.strip():
            return text

        config = _INTENSITY_CONFIGS.get(intensity, _INTENSITY_CONFIGS["medium"])
        passes = min(passes, config["llm_passes"])

        result = text

        # Pass 1: Rule-based slop removal
        result = self.remove_slop(result, intensity)

        # Pass 2: Sentence structure variation (if enabled)
        if config["vary_sentences"]:
            result = self.vary_sentences(result, intensity)

        # Pass 3: Grammar pre-pass for aggressive mode
        if config["grammar_prepass"] and intensity == "aggressive":
            result = self._grammar_prepass_low_risk(result)

        # Pass 4: LLM rewriting (if enabled)
        if use_llm:
            result = self._llm_humanize(result, style, intensity, passes)

        return result

    def _llm_humanize(self, text: str, style: str, intensity: str, passes: int) -> str:
        """Multi-pass LLM humanization."""
        result = text
        for i in range(passes):
            result = self._llm_rewrite_pass(result, style, intensity, i + 1, passes)
        return result

    def _llm_rewrite_pass(self, text: str, style: str, intensity: str, current_pass: int, total: int) -> str:
        """Single LLM rewriting pass with style and intensity awareness."""
        config = _INTENSITY_CONFIGS.get(intensity, _INTENSITY_CONFIGS["medium"])
        temperature = config["temperature"] + current_pass * 0.05

        style_guides = {
            "academic": "Write with scholarly rigor but natural voice. Vary sentence complexity. Include occasional first-person where the field allows.",
            "casual": "Write like a knowledgeable friend explaining something. Use contractions freely. Include rhetorical questions and asides.",
            "professional": "Write with authority and clarity. Use active voice. Be direct and concise. Avoid corporate buzzwords.",
            "creative": "Write with personality and flair. Use vivid, specific language. Break conventional structures.",
            "standard": "Balance formality and readability. Use natural transitions. Avoid AI-typical patterns.",
        }

        intensity_descriptions = {
            "light": "Make minimal surgical changes. Replace AI-slop words and add a few contractions.",
            "medium": "Make noticeable humanization changes. Restructure sentences, add personality.",
            "aggressive": "Complete rewrite from human perspective. Use colloquialisms, fragments, dramatic variation.",
        }

        pass_focus = {
            1: "Focus on: varying sentence length and structure, breaking predictable patterns, removing AI phrases.",
            2: "Focus on: replacing stiff vocabulary with natural alternatives, adding subtle personality, varying paragraph structure.",
            3: "Focus on: ensuring natural flow and rhythm, authentic transitions, natural imperfections.",
        }

        system = (
            f"Expert humanization editor. Apply style: {style} ("
            f"{style_guides.get(style, style_guides['standard'])}). "
            f"Intensity: {intensity} ({intensity_descriptions.get(intensity, '')}).\n"
            f"{pass_focus.get(current_pass, pass_focus[3])}\n"
            "Preserve all technical terms, citations, and factual content. "
            "NEVER use: 'Furthermore', 'Moreover', 'Additionally', 'In conclusion', 'delve', 'tapestry', 'testament'."
        )

        user = f"Humanize this text ({current_pass}/{total} pass):\n\n{text}"
        return self._call_llm(system, user, temperature=temperature)

    def translation_chain(self, text: str, chain: Optional[List[Tuple[str, str]]] = None) -> str:
        """Humanize via translation chain (EN->ID->DE->FR->EN).

        This method translates through multiple languages and back to English,
        which naturally breaks AI patterns while preserving meaning.

        Args:
            text: Input text
            chain: Custom translation chain as (language, instruction) tuples.
                   Defaults to EN->ID->DE->FR->EN
        """
        if chain is None:
            chain = [
                ("Indonesian", "Translate the following English text to natural Indonesian:"),
                ("German", "Translate the following Indonesian text to natural German:"),
                ("French", "Translate the following German text to natural French:"),
                ("English", "Translate the following French text to natural, fluent English. "
                            "Ensure it reads as if written by a human expert:"),
            ]

        result = text
        for lang, instruction in chain:
            system = f"You are a professional translator. {instruction} Output ONLY the translation."
            result = self._call_llm(system, result, temperature=0.7)

        return result

    def back_translate(self, text: str, intermediate_langs: Optional[List[str]] = None) -> str:
        """Humanize using back-translation via translation chain.

        This is an alias translation_chain with a simpler interface, supporting
        custom intermediate languages.

        Args:
            text: Input text
            intermediate_langs: Languages to translate through (default: ['id', 'de', 'fr'])
        """
        if intermediate_langs is None:
            intermediate_langs = ['id', 'de', 'fr']

        lang_instructions = {
            'id': ("Indonesian", "Translate the following English text to natural Indonesian:"),
            'de': ("German", "Translate the previous text to natural German:"),
            'fr': ("French", "Translate the previous text to natural French:"),
            'es': ("Spanish", "Translate the previous text to natural Spanish:"),
            'ja': ("Japanese", "Translate the previous text to natural Japanese:"),
            'zh': ("Chinese", "Translate the previous text to natural Chinese:"),
            'ar': ("Arabic", "Translate the previous text to natural Arabic:"),
            'ru': ("Russian", "Translate the previous text to natural Russian:"),
            'pt': ("Portuguese", "Translate the previous text to natural Portuguese:"),
            'ko': ("Korean", "Translate the previous text to natural Korean:"),
        }

        chain = []
        for lang in intermediate_langs:
            if lang in lang_instructions:
                chain.append(lang_instructions[lang])

        # Always end with English
        chain.append(("English", "Translate the previous text to natural, fluent English. "
                            "Ensure it reads as if written by a human expert:"))

        return self.translation_chain(text, chain)

    def detect_and_humanize(
        self,
        text: str,
        style: str = "academic",
        intensity: str = "medium",
        threshold: float = 50.0,
    ) -> Dict:
        """Detect AI score, humanize if above threshold, return comparison."""
        # Import detector from sibling package
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai-detectors"))
        from detector import AIDetector

        detector = AIDetector()
        orig_score, orig_details = detector.analyze(text)

        if orig_score < threshold:
            return {
                "original_score": orig_score,
                "humanized_text": text,
                "new_score": orig_score,
                "was_humanized": False,
            }

        humanized = self.humanize(text, style=style, intensity=intensity)
        new_score, new_details = detector.analyze(humanized)

        return {
            "original_score": orig_score,
            "humanized_text": humanized,
            "new_score": new_score,
            "was_humanized": True,
            "score_reduction": orig_score - new_score,
        }

    def batch_humanize(
        self,
        texts: List[str],
        style: str = "academic",
        intensity: str = "medium",
    ) -> List[str]:
        """Humanize multiple texts."""
        return [self.humanize(t, style=style, intensity=intensity) for t in texts]

    def humanize_program(self, text: str, option: str = "Standard", intensity: str = "medium") -> str:
        """Pure rule-based humanization (no LLM). Fast, deterministic, offline.

        Pipeline varies by option:
          - Light/Standard: remove_slop only
          - Medium: remove_slop + vary_sentences
          - Aggressive: remove_slop + vary_sentences + low-risk grammar pre-pass

        Args:
            text: Input text to humanize.
            option: 'Light', 'Standard', 'Medium', 'Aggressive' (case-insensitive).
            intensity: Direct intensity override (used if option is 'Standard').

        Returns:
            Humanized text string.
        """
        if not text or not text.strip():
            return text or ""

        opt = (option or "Standard").strip().capitalize()
        if opt not in ("Light", "Standard", "Medium", "Aggressive"):
            opt = "Standard"

        # Map option to intensity
        option_to_intensity = {
            "Light": "light",
            "Standard": "medium",
            "Medium": "medium",
            "Aggressive": "aggressive",
        }
        effective_intensity = option_to_intensity.get(opt, intensity)

        result = self.remove_slop(text, intensity=effective_intensity)

        config = _INTENSITY_CONFIGS.get(effective_intensity, _INTENSITY_CONFIGS["medium"])
        if config["vary_sentences"]:
            result = self.vary_sentences(result, intensity=effective_intensity)

        # Always apply transition reduction (major Turnitin signal)
        result = self._reduce_transitions(result)

        # Always apply uniformity breaking
        result = self._break_uniformity(result)

        if config["grammar_prepass"]:
            result = self._grammar_prepass_low_risk(result)

        # Final cleanup
        result = re.sub(r'  +', ' ', result)
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

    def _reduce_transitions(self, text: str) -> str:
        """Reduce excessive explicit transition words — fold them into sentence structure.
        
        Turnitin AIR-1 specifically measures transition word density.
        Target: max 2 per paragraph, 30%+ of paragraphs open without a transition."""
        if not text or not text.strip():
            return text
        
        paragraphs = text.split('\n')
        result_paragraphs = []
        
        # Transition words that are most AI-signaling at sentence/paragraph start
        _SENTENCE_START_TRANSITIONS = [
            (r'^(Furthermore,\s*)', ''),
            (r'^(Moreover,\s*)', ''),
            (r'^(Additionally,\s*)', ''),
            (r'^(Consequently,\s*)', ''),
            (r'^(Nevertheless,\s*)', ''),
            (r'^(Nonetheless,\s*)', ''),
            (r'^(Subsequently,\s*)', ''),
            (r'^(Importantly,\s*)', ''),
        ]
        
        transition_count = 0
        for para in paragraphs:
            if not para.strip():
                result_paragraphs.append(para)
                continue
            
            sentences = re.split(r'(?<=[.!?])\s+', para)
            new_sentences = []
            para_transition_count = 0
            
            for j, sent in enumerate(sentences):
                modified = sent
                # Only strip transitions from sentence starts (not mid-sentence)
                if para_transition_count < 2:  # Keep max 2 per paragraph
                    for pattern, repl in _SENTENCE_START_TRANSITIONS:
                        if re.match(pattern, modified, re.IGNORECASE):
                            # 50% chance to keep, 50% to remove (for variety)
                            if j % 2 == 0:
                                modified = re.sub(pattern, repl, modified, flags=re.IGNORECASE)
                                if modified and modified[0].islower():
                                    modified = modified[0].upper() + modified[1:]
                            para_transition_count += 1
                            break
                else:
                    # Already hit max, strip all remaining
                    for pattern, repl in _SENTENCE_START_TRANSITIONS:
                        modified = re.sub(pattern, repl, modified, flags=re.IGNORECASE)
                        if modified and modified[0].islower():
                            modified = modified[0].upper() + modified[1:]
                
                new_sentences.append(modified)
            
            result_paragraphs.append(' '.join(new_sentences))
        
        return '\n'.join(result_paragraphs)

    def _break_uniformity(self, text: str) -> str:
        """Break paragraph and sentence uniformity patterns.
        
        Targets:
        - 3+ consecutive paragraphs of similar sentence count
        - 3+ consecutive sentences of similar word count
        - Identical paragraph arc patterns
        """
        if not text or not text.strip():
            return text
        
        paragraphs = text.split('\n')
        result_paragraphs = []
        
        for i, para in enumerate(paragraphs):
            if not para.strip():
                result_paragraphs.append(para)
                continue
            
            sentences = re.split(r'(?<=[.!?])\s+', para)
            
            # If we have 3+ consecutive short sentences, merge the last two
            if len(sentences) >= 3:
                new_sentences = []
                j = 0
                while j < len(sentences):
                    sent = sentences[j]
                    word_count = len(sent.split())
                    
                    # Check if next sentence is also short
                    if (j + 1 < len(sentences) and 
                        word_count < 8 and 
                        len(sentences[j + 1].split()) < 8):
                        # Merge with comma or conjunction
                        next_sent = sentences[j + 1]
                        next_lower = next_sent[0].lower() + next_sent[1:]
                        merged = sent.rstrip('.!?') + ', and ' + next_lower
                        new_sentences.append(merged)
                        j += 2
                    else:
                        new_sentences.append(sent)
                        j += 1
                
                result_paragraphs.append(' '.join(new_sentences))
            else:
                result_paragraphs.append(para)
        
        return '\n'.join(result_paragraphs)

    def _grammar_prepass_low_risk(self, text: str) -> str:
        """Apply ONLY wordy + academic tone suggestions from GrammarChecker.

        Avoids applying grammar/spelling/punctuation corrections to keep the
        transformation safe (we don't want to introduce false positives).
        Gracefully no-ops if GrammarChecker can't be imported or fails.
        """
        try:
            from tools.grammar.grammar_checker import GrammarChecker
        except Exception as e:
            log.info("GrammarChecker import skipped: %s", e)
            return text
        try:
            gc = GrammarChecker()
            check_result = gc.check(text, mode="style", language="en-US", domain="academic")
        except Exception as e:
            log.info("GrammarChecker pre-pass failed: %s", e)
            return text

        safe_types = {"wordy", "academic"}
        items: List[Dict] = []
        for it in list(check_result.get("suggestions", [])) + list(check_result.get("warnings", [])):
            if (it.get("type") in safe_types
                    and it.get("offset") is not None
                    and it.get("length")
                    and it.get("suggestion") is not None):
                items.append(it)

        valid: List[tuple] = []
        for it in items:
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
        occupied: List[tuple] = []
        for start, end, sug in valid:
            if any(not (end <= s or start >= e) for s, e in occupied):
                continue
            occupied.append((start, end))
            out = out[:start] + sug + out[end:]
        return out


# ── Module-level entry point for tools_api ──────────────────────────────────

def run_humanizer(data: dict) -> dict:
    """tools_api-compatible entry point for the humanizer tool.

    Args:
        data: Request body dict with keys:
            - text (str, required)
            - option (str, optional, default 'Standard'): Style option
                ('Standard', 'Academic', 'Casual', 'Professional', 'Creative')
            - mode (str, optional, default 'ai'): 'program' | 'ai' | 'back_translate'
            - intensity (str, optional, default 'medium'): 'light' | 'medium' | 'aggressive'
            - include_scores (bool, optional, default False): Include humanity scores

    Returns:
        Dict with keys:
            - text (str): the humanized text
            - result (dict): metadata {
                - mode: str
                - engine: str
                - option: str
                - intensity: str
                - scores: dict (if include_scores=True) {
                    - before: dict
                    - after: dict
                    - improvement: float
                }
            }

    Raises:
        ValueError: when 'text' is missing or empty.
    """
    text = (data.get("text") or "").strip()
    if not text:
        raise ValueError("No text provided")

    option = (data.get("option") or "Standard").strip() or "Standard"
    mode = (data.get("mode") or "ai").strip().lower()
    intensity = (data.get("intensity") or "medium").strip().lower()
    include_scores = data.get("include_scores", False)

    # Validate intensity
    if intensity not in ("light", "medium", "aggressive"):
        intensity = "medium"

    humanizer = TextHumanizer()

    # Get scores before if requested
    scores_before = None
    if include_scores:
        scores_before = humanizer.estimate_humanity_score(text)

    if mode == "program":
        out = humanizer.humanize_program(text, option=option, intensity=intensity)
        result = {
            "text": out,
            "result": {
                "mode": "program",
                "engine": "rule-based",
                "option": option,
                "intensity": intensity,
            },
        }
    elif mode == "back_translate":
        # Check if API is available
        from utils.ai_tools.model_config import get_endpoint_chain as _gec
        if not _gec(heavy=True):
            log.warning("AIOTOMASI env empty; falling back to program mode")
            out = humanizer.humanize_program(text, option=option, intensity=intensity)
            result = {
                "text": out,
                "result": {
                    "mode": "program",
                    "engine": "rule-based-fallback",
                    "option": option,
                    "intensity": intensity,
                },
            }
        else:
            try:
                out = humanizer.back_translate(text)
                result = {
                    "text": out,
                    "result": {
                        "mode": "back_translate",
                        "engine": "aiotomasi",
                        "option": option,
                        "intensity": intensity,
                    },
                }
            except Exception as e:
                log.warning("Back-translation failed (%s); falling back to program mode", e)
                out = humanizer.humanize_program(text, option=option, intensity=intensity)
                result = {
                    "text": out,
                    "result": {
                        "mode": "program",
                        "engine": "rule-based-fallback",
                        "option": option,
                        "intensity": intensity,
                    },
                }
    else:
        # mode == "ai" (default, backward compatible)
        from utils.ai_tools.model_config import get_endpoint_chain as _gec
        if not _gec(heavy=True):
            log.warning("AIOTOMASI env empty; falling back to program mode")
            out = humanizer.humanize_program(text, option=option, intensity=intensity)
            result = {
                "text": out,
                "result": {
                    "mode": "program",
                    "engine": "rule-based-fallback",
                    "option": option,
                    "intensity": intensity,
                },
            }
        else:
            try:
                out = humanizer.humanize(
                    text,
                    style=(option or "Standard").lower(),
                    intensity=intensity,
                    passes=2 if intensity == "light" else 3,
                    use_llm=True,
                )
                result = {
                    "text": out,
                    "result": {
                        "mode": "ai",
                        "engine": "aiotomasi",
                        "option": option,
                        "intensity": intensity,
                    },
                }
            except Exception as e:
                log.warning("AI humanization failed (%s); falling back to program mode", e)
                out = humanizer.humanize_program(text, option=option, intensity=intensity)
                result = {
                    "text": out,
                    "result": {
                        "mode": "program",
                        "engine": "rule-based-fallback",
                        "option": option,
                        "intensity": intensity,
                    },
                }

    # Add scores if requested
    if include_scores and scores_before:
        scores_after = humanizer.estimate_humanity_score(result["text"])
        result["result"]["scores"] = {
            "before": scores_before,
            "after": scores_after,
            "improvement": round(scores_after["overall"] - scores_before["overall"], 1),
        }

    return result


# ── CLI ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Text Humanizer")
    sub = parser.add_subparsers(dest="command")

    # Humanize
    hum = sub.add_parser("humanize", help="Humanize text")
    hum.add_argument("text", nargs="?", help="Text to humanize")
    hum.add_argument("--file", "-f", help="File to humanize")
    hum.add_argument("--style", "-s", default="academic",
                     choices=["academic", "casual", "professional", "creative", "standard"])
    hum.add_argument("--intensity", "-i", default="medium",
                     choices=["light", "medium", "aggressive"])
    hum.add_argument("--passes", "-p", type=int, default=3, choices=[1, 2, 3])
    hum.add_argument("--no-llm", action="store_true", help="Rule-based only")
    hum.add_argument("--scores", action="store_true", help="Include humanity scores")

    # Back-translate
    bt = sub.add_parser("back-translate", help="Humanize via back-translation")
    bt.add_argument("text", nargs="?", help="Text to process")
    bt.add_argument("--file", "-f", help="File to process")
    bt.add_argument("--languages", "-l", default="id,de,fr",
                    help="Intermediate languages (comma-separated)")

    # Slop removal only
    slop = sub.add_parser("deslop", help="Remove AI slop words only")
    slop.add_argument("text", nargs="?", help="Text to process")
    slop.add_argument("--file", "-f", help="File to process")
    slop.add_argument("--intensity", "-i", default="medium",
                      choices=["light", "medium", "aggressive"])

    # Translation chain
    tc = sub.add_parser("translate-chain", help="Humanize via translation chain")
    tc.add_argument("text", nargs="?", help="Text to process")
    tc.add_argument("--file", "-f", help="File to process")

    # Score
    score = sub.add_parser("score", help="Estimate humanity score of text")
    score.add_argument("text", nargs="?", help="Text to analyze")
    score.add_argument("--file", "-f", help="File to analyze")
    score.add_argument("--json", action="store_true", help="Output as JSON")

    # Auto (detect + humanize)
    auto = sub.add_parser("auto", help="Detect AI score and humanize if needed")
    auto.add_argument("text", nargs="?", help="Text to process")
    auto.add_argument("--file", "-f", help="File to process")
    auto.add_argument("--threshold", "-t", type=float, default=50.0)
    auto.add_argument("--style", "-s", default="academic")
    auto.add_argument("--intensity", "-i", default="medium")
    auto.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    text = getattr(args, "text", None)
    if hasattr(args, "file") and args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    if not text:
        import sys
        text = sys.stdin.read()
    if not text:
        print("No input text provided.")
        return

    humanizer = TextHumanizer()

    if args.command == "humanize":
        result = humanizer.humanize(
            text, style=args.style, intensity=args.intensity,
            passes=args.passes, use_llm=not args.no_llm,
        )
        if args.scores:
            before = humanizer.estimate_humanity_score(text)
            after = humanizer.estimate_humanity_score(result)
            print(f"Score before: {before['overall']}/10")
            print(f"Score after: {after['overall']}/10")
            print(f"Improvement: {after['overall'] - before['overall']:+.1f}")
            print()
        print(result)

    elif args.command == "back-translate":
        languages = args.languages.split(",")
        result = humanizer.back_translate(text, intermediate_langs=languages)
        print(result)

    elif args.command == "deslop":
        result = humanizer.remove_slop(text, intensity=args.intensity)
        print(result)

    elif args.command == "translate-chain":
        print(humanizer.translation_chain(text))

    elif args.command == "score":
        scores = humanizer.estimate_humanity_score(text)
        if args.json:
            print(json.dumps(scores, indent=2))
        else:
            print(f"Overall Humanity Score: {scores['overall']}/10")
            print(f"  Pattern Score: {scores['patterns']}/10")
            print(f"  Variance Score: {scores['variance']}/10")
            print(f"  Voice Score: {scores['voice']}/7")
            print(f"\nText Stats:")
            print(f"  Word Count: {scores['word_count']}")
            print(f"  Sentence Count: {scores['sentence_count']}")
            print(f"  Avg Sentence Length: {scores['avg_sentence_length']}")
            print(f"\nAI Signals:")
            print(f"  Tier 1 (dead giveaways): {scores['ai_signals']['tier1_count']}")
            print(f"  Tier 2 (buzzwords): {scores['ai_signals']['tier2_count']}")
            print(f"  Tier 3 (weak signals): {scores['ai_signals']['tier3_count']}")

    elif args.command == "auto":
        intensity = args.intensity
        result = humanizer.detect_and_humanize(text, style=args.style, intensity=intensity, threshold=args.threshold)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Original AI Score: {result['original_score']}/100")
            print(f"Humanized: {result['was_humanized']}")
            if result['was_humanized']:
                print(f"New AI Score: {result['new_score']}/100")
                print(f"Reduction: {result['score_reduction']:.1f}")
            print(f"\n{result['humanized_text']}")


if __name__ == "__main__":
    main()
