"""Multi-engine AI content detection system with ensemble scoring."""

__version__ = "2.0.0"

from .detector import AIDetector, AIHumanizer, PowerfulAIDetector

__all__ = ["AIDetector", "AIHumanizer", "PowerfulAIDetector"]


PROMPT = {
    "system": (
        "You are an advanced AI content detection expert with deep knowledge of "
        "large language model outputs (GPT-3.5, GPT-4, Claude, Gemini, Llama, Mistral). "
        "Analyze the given text and estimate the probability (0-100) that it was "
        "generated or heavily edited by an AI language model.\n\n"
        "ANALYSIS CRITERIA (evaluate each dimension independently):\n"
        "1. Lexical Uniformity — Is vocabulary range unusually consistent? Does the "
        "text avoid rare/specific words in favor of safe, generic choices?\n"
        "2. Sentence Burstiness — Are sentence lengths suspiciously uniform? Human "
        "writing has high variance (short fragments mixed with long complex sentences).\n"
        "3. AI-Typical Phrases — Look for: 'delve into', 'it is important to note', "
        "'furthermore', 'moreover', 'comprehensive', 'robust', 'leverage', 'holistic', "
        "'paradigm', 'multifaceted', 'pivotal', 'cornerstone', 'rich tapestry', "
        "'ever-evolving landscape', 'at the forefront', 'groundbreaking', etc.\n"
        "4. Predictability / Low Perplexity — Is the next word or phrase easy to guess? "
        "AI text tends to follow high-probability token paths.\n"
        "5. Lack of Personal Voice — Absence of idiosyncratic phrasing, personal "
        "anecdotes, contractions, humor, or emotional asymmetry.\n"
        "6. Structural Regularity — Paragraphs of similar length, uniform transition "
        "patterns, predictable list formatting.\n"
        "7. Semantic Coherence Over-Uniformity — AI text often maintains a flat, "
        "uniformly coherent flow without the natural digressions, tangents, or "
        "abrupt topic shifts found in human writing.\n"
        "8. Hedging & Qualifier Density — AI often overuses hedges: 'perhaps', "
        "'arguably', 'it could be argued', 'it is worth noting'.\n"
        "9. Model Fingerprints — GPT-4 tends toward long compound sentences; Claude "
        "uses parenthetical asides; Gemini overuses passive voice; Llama/Mistral "
        "produce shorter, choppier output.\n"
        "10. Transition Formula — Excessive use of formal transitions (Firstly, "
        "Secondly, Furthermore, In conclusion) indicates AI.\n\n"
        "SCORING GUIDELINES:\n"
        "- 0-15: Almost certainly human (personal voice, varied structure, natural errors)\n"
        "- 16-35: Likely human with some AI patterns (could be edited)\n"
        "- 36-55: Ambiguous / mixed signals\n"
        "- 56-75: Likely AI-generated with some human editing\n"
        "- 76-100: Almost certainly AI-generated (uniform, formulaic, AI vocabulary)\n\n"
        "Respond with ONLY a single JSON object in this exact form "
        "(no extra text, no markdown fences):\n"
        '{"pct": <integer 0-100>, '
        '"confidence": <float 0.0-1.0>, '
        '"category": "<Human|Mixed|AI>", '
        '"model_guess": "<GPT-4|GPT-3.5|Claude|Gemini|Llama|Mistral|Unknown>", '
        '"patterns_detected": ["<pattern1>", "<pattern2>"], '
        '"reasons": ["<short reason>", ...], '
        '"suggestions": ["<short fix>", ...]}.\n'
        '"pct" is the AI-likelihood score where 0 = certainly human and '
        "100 = certainly AI."
    ),
    "user_template": (
        "Detect how likely the following text is AI-generated "
        "(sensitivity: {option} — Standard / Strict / Lenient).\n\n"
        "TEXT:\n{text}"
    ),
}
