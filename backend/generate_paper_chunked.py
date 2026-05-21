"""
Chunked Paper Generation — Fix 30s Gateway Timeout
===================================================
Breaks single 90KB API call into 7 smaller chunks, each completing in <30s.

Architecture:
1. _generate_outline()      → title, abstract, keywords, section titles
2. _generate_section()      → individual section content (I-V)
3. _generate_references()   → references based on citations
4. generate_paper_json_chunked() → orchestrator that combines all chunks

Each chunk includes context from previous chunks to maintain consistency.
"""

import os
import re
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from json_repair import repair_json

# Reuse existing API caller with fallback
from generate_ai_json_paper_aiotomasi import _call_aiotomasi_with_fallback

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env", override=True)

AIOTOMASI_API = os.getenv("AIOTOMASI_API")
AIOTOMASI_APIKEY = os.getenv("AIOTOMASI_APIKEY")
AIOTOMASI_MODEL = os.getenv("AIOTOMASI_MODEL", "VIOLAGPT")

# Prompt files
PROMPT_FILE = BASE_DIR / "prompt" / "prompt.txt"
HUMANIZE_FILE = BASE_DIR / "prompt" / "humanize.txt"


# ── Helper: Load prompt sections ──────────────────────────────────────────────
def _load_base_prompt():
    """Load the base prompt.txt content."""
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    raise ValueError("prompt.txt not found")


def _load_humanize_rules():
    """Load humanize.txt rules."""
    if HUMANIZE_FILE.exists():
        return HUMANIZE_FILE.read_text(encoding="utf-8")
    return ""


def _load_style_guide(style: str = None):
    """Load optional style guide."""
    if not style:
        return ""
    style_file = BASE_DIR / "prompt" / "style" / f"{style}.txt"
    if style_file.exists():
        return style_file.read_text(encoding="utf-8")
    return ""


def _load_topic_guide(topic: str = None):
    """Load optional topic guide."""
    if not topic:
        return ""
    topic_file = BASE_DIR / "prompt" / "topic" / f"{topic}.txt"
    if topic_file.exists():
        return topic_file.read_text(encoding="utf-8")
    return ""


# ── Helper: Parse JSON response ───────────────────────────────────────────────
def _parse_json_response(raw_content: str) -> dict:
    """Parse JSON from API response, with repair fallback."""
    # Strip markdown fences
    clean = re.sub(r"^```(?:json)?\s*", "", raw_content.strip(), flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)

    # Try direct parse first
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e1:
        # Fallback to json_repair
        try:
            repaired = repair_json(clean, return_objects=True)
            if isinstance(repaired, dict) and repaired:
                return repaired
            raise ValueError(f"json_repair did not return a dict: {type(repaired)}")
        except Exception as e2:
            raise ValueError(f"JSON parse failed: {e1} | repair: {e2}")


# ── Chunk 1: Generate Outline ─────────────────────────────────────────────────
def _generate_outline(judul: str, custom_prompt: str, topic: str, style: str,
                      api_key: str, base_url: str, model: str, progress_cb=None) -> dict:
    """
    Generate paper outline: title, abstract, keywords, section titles.
    Uses minimal prompt (no full content rules) to reduce size and time.

    Returns:
        {
            "title": "...",
            "abstract": "...",
            "keywords": [...],
            "section_titles": {
                "section1": "INTRODUCTION",
                "section2": "RELATED WORK",
                "section3": "METHODOLOGY",
                "section4": "RESULTS",
                "section5": "CONCLUSION"
            }
        }
    """
    # Build minimal system prompt for outline only
    system_prompt = """You are a senior academic author generating a paper outline.

TASK: Generate ONLY the outline structure in JSON format.

OUTPUT SCHEMA:
{
  "title": "Specific, academic-style title — max 20 words",
  "abstract": "150–250 words: (1) problem, (2) limitation of existing approaches, (3) proposed method, (4) specific results, (5) impact",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6"],
  "section_titles": {
    "section1": "INTRODUCTION",
    "section2": "RELATED WORK (or LITERATURE REVIEW)",
    "section3": "METHODOLOGY (or METHODS or PROPOSED SYSTEM)",
    "section4": "RESULTS (or EXPERIMENTAL RESULTS)",
    "section5": "CONCLUSION (or CONCLUSIONS AND FUTURE WORK)"
  }
}

RULES:
- Title must be specific and academic
- Abstract must include concrete problem, method, and results
- Keywords must be relevant to the topic
- Section titles can be adapted to the field (e.g., IMRAD for medicine, IEEE for engineering)
- Return ONLY the JSON object, no markdown fences
"""

    # Add topic/style guides if provided
    if topic:
        topic_guide = _load_topic_guide(topic)
        if topic_guide:
            system_prompt += f"\n\nTOPIC GUIDE:\n{topic_guide}"

    if style:
        style_guide = _load_style_guide(style)
        if style_guide:
            system_prompt += f"\n\nCITATION STYLE GUIDE:\n{style_guide}"

    user_message = f"""Topic description: {judul}

Additional instructions: {custom_prompt if custom_prompt else "(none)"}

Generate the paper outline following the schema above."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    raw_content, model_used = _call_aiotomasi_with_fallback(
        messages, api_key, base_url, model, timeout=900.0, progress_cb=progress_cb
    )
    print(f"[_generate_outline] succeeded using model={model_used}", flush=True)

    return _parse_json_response(raw_content)


# ── Chunk 2-6: Generate Section ───────────────────────────────────────────────
def _generate_section(section_num: int, outline: dict, previous_sections: list,
                      judul: str, custom_prompt: str, topic: str, style: str,
                      api_key: str, base_url: str, model: str,
                      numbering_state: dict, progress_cb=None) -> dict:
    """
    Generate a single section (I-V) with full content.

    Args:
        section_num: 1-5 (section number)
        outline: Output from _generate_outline()
        previous_sections: List of previously generated section dicts
        numbering_state: {"figure_count": N, "table_count": N, "equation_count": N}

    Returns:
        Section dict matching the schema from prompt.txt
    """
    # Load full prompt for this section
    full_prompt = _load_base_prompt()
    humanize_rules = _load_humanize_rules()

    # Extract section-specific schema from full prompt
    # This is a simplified approach - in production, you'd parse the prompt more carefully
    section_key = f"section{section_num}"
    section_title = outline.get("section_titles", {}).get(section_key, f"SECTION {section_num}")

    # Build context from outline and previous sections
    context_parts = [
        f"PAPER OUTLINE:",
        f"Title: {outline.get('title', '')}",
        f"Abstract: {outline.get('abstract', '')}",
        f"Keywords: {', '.join(outline.get('keywords', []))}",
        "",
        "SECTION TITLES:",
    ]
    for i in range(1, 6):
        sk = f"section{i}"
        st = outline.get("section_titles", {}).get(sk, f"Section {i}")
        context_parts.append(f"  Section {i}: {st}")

    # Add summaries of previous sections
    if previous_sections:
        context_parts.append("\nPREVIOUS SECTIONS SUMMARY:")
        for i, sec in enumerate(previous_sections, 1):
            sec_title = sec.get("title", f"Section {i}")
            # Extract first paragraph as summary
            content = sec.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                first_para = content[0].get("text", "")[:200] if isinstance(content[0], dict) else ""
                context_parts.append(f"  Section {i} ({sec_title}): {first_para}...")

    # Add numbering state
    context_parts.append(f"\nCURRENT NUMBERING STATE:")
    context_parts.append(f"  Next Figure: {numbering_state['figure_count'] + 1}")
    context_parts.append(f"  Next Table: {numbering_state['table_count'] + 1}")
    context_parts.append(f"  Next Equation: {numbering_state['equation_count'] + 1}")

    context = "\n".join(context_parts)

    # Build system prompt with section-specific instructions
    system_prompt = f"""{full_prompt}

{humanize_rules}

CONTEXT FROM PREVIOUS WORK:
{context}

CURRENT TASK: Generate ONLY Section {section_num} ({section_title}) following the schema in PART A.
Return the section{section_num} object as JSON. Include all required subsections, figures, tables, and equations as specified in the schema.
"""

    if topic:
        topic_guide = _load_topic_guide(topic)
        if topic_guide:
            system_prompt += f"\n\nTOPIC GUIDE:\n{topic_guide}"

    if style:
        style_guide = _load_style_guide(style)
        if style_guide:
            system_prompt += f"\n\nCITATION STYLE GUIDE:\n{style_guide}"

    user_message = f"""Topic: {judul}

Additional instructions: {custom_prompt if custom_prompt else "(none)"}

Generate Section {section_num} ({section_title}) following the schema and context above.
Ensure figure/table/equation numbering continues from the current state.
Return ONLY the JSON object for section{section_num}."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    raw_content, model_used = _call_aiotomasi_with_fallback(
        messages, api_key, base_url, model, timeout=900.0, progress_cb=progress_cb
    )
    print(f"[_generate_section] Section {section_num} succeeded using model={model_used}", flush=True)

    section_data = _parse_json_response(raw_content)

    # Update numbering state by counting figures/tables/equations in this section
    def count_items(section, item_type):
        count = 0
        if isinstance(section, dict):
            for key, value in section.items():
                if isinstance(value, dict):
                    if value.get("id") == item_type:
                        count += 1
                    count += count_items(value, item_type)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            if item.get("id") == item_type:
                                count += 1
                            count += count_items(item, item_type)
        return count

    numbering_state["figure_count"] += count_items(section_data, "gambar")
    numbering_state["table_count"] += count_items(section_data, "tabel")
    numbering_state["equation_count"] += count_items(section_data, "rumus")

    return section_data


# ── Chunk 7: Generate References ──────────────────────────────────────────────
def _generate_references(outline: dict, all_sections: list, style: str,
                        api_key: str, base_url: str, model: str, progress_cb=None) -> list:
    """
    Generate references based on citations found in all sections.

    Returns:
        List of reference strings in the required citation format.
    """
    # Extract all citations from sections
    citations = set()

    def extract_citations(obj):
        """Recursively extract [N] citations from text."""
        if isinstance(obj, dict):
            for value in obj.values():
                extract_citations(value)
        elif isinstance(obj, list):
            for item in obj:
                extract_citations(item)
        elif isinstance(obj, str):
            # Find [1], [2], [3], etc.
            matches = re.findall(r'\[(\d+)\]', obj)
            citations.update(int(m) for m in matches)

    for section in all_sections:
        extract_citations(section)

    # Determine how many references to generate
    max_citation = max(citations) if citations else 20
    num_refs = max(max_citation, 20)  # Minimum 20 references

    # Build system prompt for references
    style_guide = _load_style_guide(style) if style else ""

    system_prompt = f"""You are generating references for an academic paper.

TASK: Generate {num_refs} references in the required citation format.

PAPER CONTEXT:
Title: {outline.get('title', '')}
Abstract: {outline.get('abstract', '')}
Keywords: {', '.join(outline.get('keywords', []))}

CITATION STYLE:
{style_guide if style_guide else "Use numbered IEEE format: [1], [2], etc."}

RULES:
- Generate exactly {num_refs} references
- All references must be realistic and plausible for this topic
- Use realistic author names, plausible titles, correct venue names
- Years should be 2010-2025
- Every reference must be relevant to the paper topic
- Format: Return a JSON array of strings, each string is one reference

OUTPUT SCHEMA:
{{
  "references": [
    "[1] A. Author, B. Coauthor, 'Title of Paper,' Journal Name, vol. X, no. Y, pp. ZZ-ZZ, Year.",
    "[2] C. Author, 'Title of Book,' Publisher, City, Year.",
    ...
  ]
}}

Return ONLY the JSON object."""

    user_message = f"""Generate {num_refs} references for this paper following the citation style above.
The paper is about: {outline.get('title', '')}

Return the references as a JSON object with a "references" array."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    raw_content, model_used = _call_aiotomasi_with_fallback(
        messages, api_key, base_url, model, timeout=900.0, progress_cb=progress_cb
    )
    print(f"[_generate_references] succeeded using model={model_used}", flush=True)

    refs_data = _parse_json_response(raw_content)
    return refs_data.get("references", [])


# ── Main Orchestrator ─────────────────────────────────────────────────────────
def generate_paper_json_chunked(
    judul: str,
    custom_prompt: str = "",
    api_key: str = None,
    base_url: str = None,
    model: str = None,
    topic: str = None,
    style: str = None,
    progress_cb=None,
) -> dict:
    """
    Generate a complete IEEE conference paper JSON via chunked API calls.

    This is a drop-in replacement for generate_paper_json() that breaks the
    generation into 7 smaller chunks to avoid 30s gateway timeouts.

    Args:
        judul: Paper title / topic.
        custom_prompt: Additional instructions for the AI.
        api_key: API key (falls back to AIOTOMASI_APIKEY env var).
        base_url: API base URL (falls back to AIOTOMASI_API env var).
        model: Model name (falls back to AIOTOMASI_MODEL env var).
        topic: Topic guide file name (without .txt).
        style: Style guide file name (without .txt).
        progress_cb: Optional callable(chars_done: int) for progress feedback.

    Returns:
        Complete paper dict matching the schema from prompt.txt.

    Raises:
        ValueError: If API key/URL is missing or JSON cannot be parsed.
    """
    _api_key = api_key or AIOTOMASI_APIKEY
    _base_url = base_url or AIOTOMASI_API
    _model = model or AIOTOMASI_MODEL

    if not _api_key:
        raise ValueError("AIOTOMASI_APIKEY not found in environment")
    if not _base_url:
        raise ValueError("AIOTOMASI_API not found in environment")

    print("[generate_paper_json_chunked] Starting chunked generation...", flush=True)
    t_start = time.time()

    # Chunk 1: Generate outline
    print("[1/7] Generating outline...", flush=True)
    outline = _generate_outline(judul, custom_prompt, topic, style,
                                _api_key, _base_url, _model, progress_cb)

    # Initialize numbering state
    numbering_state = {"figure_count": 0, "table_count": 0, "equation_count": 0}

    # Chunks 2-6: Generate sections I-V
    sections = []
    for i in range(1, 6):
        print(f"[{i+1}/7] Generating Section {i}...", flush=True)
        section = _generate_section(i, outline, sections, judul, custom_prompt,
                                    topic, style, _api_key, _base_url, _model,
                                    numbering_state, progress_cb)
        sections.append(section)

    # Chunk 7: Generate references
    print("[7/7] Generating references...", flush=True)
    references = _generate_references(outline, sections, style,
                                     _api_key, _base_url, _model, progress_cb)

    # Combine all chunks into final paper structure
    paper_json = {
        "title": outline.get("title", ""),
        "abstract": outline.get("abstract", ""),
        "keywords": outline.get("keywords", []),
        "authors": [
            {
                "name": "Author Name",
                "affiliation": "Department, University",
                "location": "City, Country",
                "email": "author@example.com"
            }
        ],
        "section1": sections[0] if len(sections) > 0 else {},
        "section2": sections[1] if len(sections) > 1 else {},
        "section3": sections[2] if len(sections) > 2 else {},
        "section4": sections[3] if len(sections) > 3 else {},
        "section5": sections[4] if len(sections) > 4 else {},
        "acknowledgment": "",
        "references": references,
        "figures": [],  # Extracted from sections
        "tables": [],   # Extracted from sections
        "equations": []  # Extracted from sections
    }

    # Extract figures, tables, equations from all sections
    def extract_items(obj, item_type, collection):
        """Recursively extract items of a specific type."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, dict):
                    if value.get("id") == item_type:
                        collection.append(value)
                    extract_items(value, item_type, collection)
                elif isinstance(value, list):
                    for item in value:
                        extract_items(item, item_type, collection)

    for section in sections:
        extract_items(section, "gambar", paper_json["figures"])
        extract_items(section, "tabel", paper_json["tables"])
        extract_items(section, "rumus", paper_json["equations"])

    elapsed = time.time() - t_start
    print(f"[generate_paper_json_chunked] Completed in {elapsed:.1f}s", flush=True)

    return paper_json
