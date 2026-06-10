PROMPT = {
    "system": (
        "You are an expert academic writing and paraphrasing specialist with deep knowledge "
        "of multiple writing styles across disciplines.\n\n"
        "## Core Principles\n"
        "- Preserve the original meaning with absolute fidelity\n"
        "- Maintain author's voice and intent\n"
        "- Improve clarity, flow, and readability\n"
        "- Use natural, human-like language patterns\n\n"
        "## Citation & Reference Preservation\n"
        "- EXACT preservation required for: [1], [2,3], (Author, 2023), (Author et al., 2020)\n"
        "- DOI references: doi:10.xxxx/xxxxx\n"
        "- URLs and web references\n"
        "- Figure/table references: Figure 1, Table 2\n"
        "- Section references: Section 3.2\n"
        "- NEVER modify, reformat, or relocate citations\n\n"
        "## Formatting Preservation\n"
        "- Maintain **bold**, *italic*, ~~strikethrough~~ formatting\n"
        "- Preserve ## Heading levels and structure\n"
        "- Keep lists (numbered and bulleted) intact\n"
        "- Preserve `code blocks` and inline `code`\n"
        "- Maintain HTML attributes and tags (class, id, href)\n"
        "- Preserve LaTeX math: $inline$ and $$block$$\n\n"
        "## Technical Term Handling\n"
        "- DO NOT paraphrase established technical terms\n"
        "- DO NOT change proper nouns (names, brands, products)\n"
        "- DO NOT modify acronyms on first occurrence (keep full form + acronym)\n"
        "- Preserve domain-specific terminology exactly"
    ),
    "user_template": (
        "Paraphrase the following text in the **{option}** style.\n\n"
        "## Available Styles\n"
        "- **Standard**: Clear, balanced paraphrasing suitable for general use\n"
        "- **Academic**: Formal scholarly language with passive voice and hedging\n"
        "- **Formal**: Professional, polished tone for business contexts\n"
        "- **Casual**: Conversational, friendly, approachable tone\n"
        "- **Simple**: Easy-to-read, accessible language (Grade 8 level)\n"
        "- **Creative**: Engaging, vivid language with varied sentence structures\n"
        "- **SEO**: Search-optimized with natural keyword integration\n"
        "- **Fluency**: Natural, native-level flow and expression\n"
        "- **Concise**: Condensed while preserving key information\n\n"
        "## Text to Paraphrase\n"
        "{text}\n\n"
        "## Output Requirements\n"
        "- Return ONLY the paraphrased text, no explanations\n"
        "- Maintain paragraph structure\n"
        "- Preserve all formatting (bold, italic, code, links)\n"
        "- Keep all citations in their original positions"
    ),
}

STYLE_CONFIGS = {
    "standard": {
        "description": "Clear, balanced paraphrasing for general use",
        "temperature": 0.7,
        "formality": "neutral",
        "voice": "mixed",
        "sentence_variety": "moderate",
    },
    "academic": {
        "description": "Formal scholarly language with passive voice and hedging",
        "temperature": 0.5,
        "formality": "high",
        "voice": "passive_preferred",
        "sentence_variety": "moderate",
        "hedging": True,
    },
    "formal": {
        "description": "Professional, polished tone for business contexts",
        "temperature": 0.5,
        "formality": "high",
        "voice": "active_preferred",
        "sentence_variety": "moderate",
    },
    "casual": {
        "description": "Conversational, friendly, approachable tone",
        "temperature": 0.8,
        "formality": "low",
        "voice": "active",
        "sentence_variety": "high",
        "contractions": True,
    },
    "simple": {
        "description": "Easy-to-read, accessible language",
        "temperature": 0.6,
        "formality": "neutral",
        "voice": "active",
        "sentence_variety": "moderate",
        "max_sentence_length": 20,
        "avoid_jargon": True,
    },
    "creative": {
        "description": "Engaging, vivid language with varied structures",
        "temperature": 0.9,
        "formality": "neutral",
        "voice": "active",
        "sentence_variety": "very_high",
    },
    "seo": {
        "description": "Search-optimized with natural keyword integration",
        "temperature": 0.6,
        "formality": "neutral",
        "voice": "active",
        "sentence_variety": "high",
        "keyword_preservation": True,
    },
    "fluency": {
        "description": "Natural, native-level flow and expression",
        "temperature": 0.6,
        "formality": "neutral",
        "voice": "natural",
        "sentence_variety": "high",
    },
    "concise": {
        "description": "Condensed while preserving key information",
        "temperature": 0.5,
        "formality": "neutral",
        "voice": "active",
        "sentence_variety": "moderate",
        "compression_target": 0.75,
    },
}

CITATION_PATTERNS = [
    r'\[\d+\]',
    r'\[\d+(?:,\s*\d+)*\]',
    r'\([A-Za-z]+(?:\s+(?:et\s+al\.|&\s+[A-Za-z]+))?,?\s*\d{4}[a-z]?\)',
    r'\([A-Za-z]+\s+(?:et\s+al\.|&\s+[A-Za-z]+),?\s*\d{4}[a-z]?\)',
    r'(?:doi|DOI):\s*\d+\.\S+',
    r'(?:https?://|www\.)\S+',
]

PRESERVE_TERMS = [
    "AI", "ML", "NLP", "LLM", "GPT", "BERT", "CNN", "RNN", "LSTM",
    "API", "REST", "JSON", "XML", "HTML", "CSS", "SQL", "NoSQL",
    "CPU", "GPU", "RAM", "SSD", "OS", "UI", "UX", "SaaS", "PaaS", "IaaS",
]
