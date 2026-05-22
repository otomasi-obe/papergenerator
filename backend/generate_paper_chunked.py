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
import logging
from pathlib import Path
from env_loader import load_app_env
from json_repair import repair_json

# Reuse existing API caller with fallback
from generate_ai_json_paper_aiotomasi import _call_aiotomasi_with_fallback

log = logging.getLogger(__name__)


class GenerationCancelled(Exception):
    """Raised by the orchestrator when a cancel_check() returns True.

    The ``stage`` attribute names the chunk that was about to run (or had just
    finished checkpointing) when the cancellation was observed. Callers use
    this to persist a partial paper + accurate cancellation point.
    """

    def __init__(self, stage: str):
        super().__init__(f"cancelled at {stage}")
        self.stage = stage


# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
load_app_env()

AIOTOMASI_API = os.getenv("AIOTOMASI_API")
AIOTOMASI_APIKEY = os.getenv("AIOTOMASI_APIKEY")
AIOTOMASI_MODEL = os.getenv("AIOTOMASI_MODEL", "V-OPUS")

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


# ── Helper: Literature catalog extraction ────────────────────────────────────
_LIT_HEADING_RE = re.compile(
    r"^##\s*Literature catalog\b.*$", re.IGNORECASE | re.MULTILINE
)
_LIT_LINE_RE = re.compile(
    r"^\[L(\d+)\]\s*(.+?)\s*$", re.MULTILINE
)


def _extract_literature_block(custom_prompt: str) -> str:
    """Return the literature catalog markdown block embedded in custom_prompt.

    The block begins with a line like ``## Literature catalog ...`` (produced
    by ``chat_tools._format_literature_block``) and runs until the next ``## ``
    heading or end-of-string. Returns "" when no catalog is present.
    """
    if not custom_prompt:
        return ""
    match = _LIT_HEADING_RE.search(custom_prompt)
    if not match:
        return ""
    start = match.start()
    tail = custom_prompt[match.end():]
    next_heading = re.search(r"^##\s+\S", tail, re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(custom_prompt)
    return custom_prompt[start:end].strip()


def _parse_literature_entries(block: str) -> list:
    """Parse a literature catalog block into a list of (idx, body) tuples.

    ``idx`` is the 1-based number from ``[Lidx]``; ``body`` is the trailing
    text (title, authors, venue, DOI, optional summary collapsed to one line).
    Returns [] on empty/invalid input.
    """
    if not block:
        return []
    entries = []
    lines = block.splitlines()
    current = None
    for raw in lines:
        m = _LIT_LINE_RE.match(raw)
        if m:
            if current is not None:
                entries.append(current)
            current = (int(m.group(1)), m.group(2).strip())
        elif current is not None and raw.strip().lower().startswith("summary:"):
            idx, body = current
            extra = raw.strip()
            current = (idx, f"{body} | {extra}")
    if current is not None:
        entries.append(current)
    entries.sort(key=lambda e: e[0])
    return entries


def _format_lit_for_refs(entries: list) -> str:
    """Render parsed literature entries as a compact numbered list for the
    reference-generation prompt."""
    if not entries:
        return ""
    return "\n".join(f"[{i}] {body}" for i, (_, body) in enumerate(entries, 1))


# ── Helper: Load full context (history + literature + files) ──────────────────
def _load_full_context(paper_id, conv_id=None, max_files=5, max_lit=20,
                       history_msgs=10, custom_prompt=None):
    """Build a context block with chat history + literature + files for injection.

    Per user requirement (perintah.txt 2026-05-22): inject full context into
    chunked generation to restore quality lost by slim prompts.

    Args:
        paper_id: Required. The paper being generated.
        conv_id: Optional. Conversation ID for chat history.
        max_files: Max attached files to include (default 5).
        max_lit: Max literature items to include (default 20).
        history_msgs: Max recent chat messages to include (default 10).
        custom_prompt: Optional caller-supplied prompt. When it already
            contains a ``[REFERENCE DOCUMENTS]`` marker the file injection
            block is skipped to avoid duplicating attached PDFs that were
            inlined upstream by ``app._run_generate_full_job``.

    Returns:
        String under 30KB with chat history + literature + files context.
    """
    from models import db, ChatMessage, LiteratureItem, PaperFile

    skip_files = bool(custom_prompt and "[REFERENCE DOCUMENTS]" in custom_prompt)

    lines = []
    total_chars = 0
    max_context_size = 30_000  # 30KB budget
    
    # ── Chat history ──────────────────────────────────────────────────────────
    if conv_id:
        try:
            messages = (db.session.query(ChatMessage)
                       .filter_by(conversation_id=conv_id)
                       .order_by(ChatMessage.created_at.desc())
                       .limit(history_msgs)
                       .all())
            if messages:
                lines.append("## Recent chat history (context from conversation)")
                # Reverse to chronological order
                for msg in reversed(messages):
                    role = msg.role
                    content = (msg.content or "")[:500]  # Cap per message
                    if content:
                        lines.append(f"**{role}**: {content}")
                        total_chars += len(content) + 20
                        if total_chars > max_context_size:
                            break
                lines.append("")  # Blank line separator
        except Exception as e:
            log.warning("[_load_full_context] chat history failed: %s", e)
    
    # ── Literature catalog ────────────────────────────────────────────────────
    if paper_id and total_chars < max_context_size:
        try:
            items = (db.session.query(LiteratureItem)
                    .filter_by(paper_id=paper_id)
                    .order_by(LiteratureItem.pinned.desc(),
                             LiteratureItem.must_read.desc(),
                             LiteratureItem.score_total.desc())
                    .limit(max_lit)
                    .all())
            if items:
                lines.append("## Literature catalog (authoritative reference list)")
                for i, it in enumerate(items, 1):
                    authors_list = it.authors or []
                    authors = ", ".join(authors_list[:3])
                    if len(authors_list) > 3:
                        authors += " et al."
                    marker = "[MUST READ] " if (it.pinned or it.must_read) else ""
                    bits = [f"[L{i}] {marker}{it.title}"]
                    if authors:
                        bits.append(f"— {authors}")
                    if it.year:
                        bits.append(f"({it.year})")
                    if it.venue:
                        bits.append(f"in {it.venue}")
                    if it.doi:
                        bits.append(f"DOI: {it.doi}")
                    line = " ".join(bits)
                    if it.summary and total_chars < max_context_size - 300:
                        line += f"\n   Summary: {it.summary[:200]}"
                    lines.append(line)
                    total_chars += len(line) + 10
                    if total_chars > max_context_size:
                        break
                lines.append("")
        except Exception as e:
            log.warning("[_load_full_context] literature failed: %s", e)
    
    # ── Attached files ────────────────────────────────────────────────────────
    if paper_id and not skip_files and total_chars < max_context_size:
        try:
            files = (db.session.query(PaperFile)
                    .filter_by(paper_id=paper_id)
                    .order_by(PaperFile.created_at.desc())
                    .limit(max_files)
                    .all())
            if files:
                lines.append("## Attached files (reference materials)")
                for f in files:
                    text = (f.extracted_text or "")[:800]  # Cap per file
                    if text:
                        lines.append(f"**{f.original_name}** ({f.ext}):")
                        lines.append(text[:600] + ("..." if len(text) > 600 else ""))
                        lines.append("")
                        total_chars += len(text) + 50
                        if total_chars > max_context_size:
                            break
        except Exception as e:
            log.warning("[_load_full_context] files failed: %s", e)
    
    result = "\n".join(lines)
    # Final safety cap
    if len(result) > max_context_size:
        result = result[:max_context_size] + "\n... [context truncated to 30KB]"
    
    return result


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
                      api_key: str, base_url: str, model: str, progress_cb=None,
                      paper_id=None, conv_id=None) -> dict:
    """
    Generate paper outline: title, abstract, keywords, section titles.
    
    Per user requirement (perintah.txt 2026-05-22): use full prompt.txt + 
    humanize.txt for quality, NOT slim prompts. Trade token savings for quality.

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
    # Per user requirement (perintah.txt 2026-05-22): use full prompt+humanize for quality
    full_prompt = _load_base_prompt()
    humanize_rules = _load_humanize_rules()
    
    # Load full context: chat history + literature + files
    context_block = _load_full_context(paper_id, conv_id, max_files=5, max_lit=20,
                                       history_msgs=10, custom_prompt=custom_prompt)
    
    # Build system prompt with full rules + context
    system_prompt = f"""{full_prompt}

{humanize_rules}

CURRENT TASK: Generate ONLY the outline structure (title, abstract, keywords, section_titles).
Return a JSON object with these fields:
{{
  "title": "Specific, academic-style title — max 20 words",
  "abstract": "150–250 words: (1) problem, (2) limitation of existing approaches, (3) proposed method, (4) specific results, (5) impact",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6"],
  "section_titles": {{
    "section1": "INTRODUCTION",
    "section2": "RELATED WORK (or LITERATURE REVIEW)",
    "section3": "METHODOLOGY (or METHODS or PROPOSED SYSTEM)",
    "section4": "RESULTS (or EXPERIMENTAL RESULTS)",
    "section5": "CONCLUSION (or CONCLUSIONS AND FUTURE WORK)"
  }}
}}

Section titles can be adapted to the field (e.g., IMRAD for medicine, IEEE for engineering).
Return ONLY the JSON object, no markdown fences.
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
    
    # Inject full context
    if context_block:
        system_prompt += f"\n\nCONTEXT FROM PROJECT:\n{context_block}"

    user_message = f"""Topic description: {judul}

Additional instructions: {custom_prompt if custom_prompt else "(none)"}

Generate the paper outline following the schema above."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    # Log prompt size for observability
    prompt_size_kb = len(system_prompt.encode('utf-8')) / 1024
    log.info("outline prompt size: %.1f KB", prompt_size_kb)

    raw_content, model_used = _call_aiotomasi_with_fallback(
        messages, api_key, base_url, model, timeout=900.0, progress_cb=progress_cb
    )
    print(f"[_generate_outline] succeeded using model={model_used}", flush=True)

    return _parse_json_response(raw_content)


# ── Chunk 2-6: Generate Section ───────────────────────────────────────────────
def _generate_section(section_num: int, outline: dict, previous_sections: list,
                      judul: str, custom_prompt: str, topic: str, style: str,
                      api_key: str, base_url: str, model: str,
                      numbering_state: dict, progress_cb=None,
                      paper_id=None, conv_id=None) -> dict:
    """
    Generate a single section (I-V) with full content.
    
    Per user requirement (perintah.txt 2026-05-22): use FULL prompt.txt + 
    humanize.txt + context (history + literature + files) for quality.

    Args:
        section_num: 1-5 (section number)
        outline: Output from _generate_outline()
        previous_sections: List of previously generated section dicts
        numbering_state: {"figure_count": N, "table_count": N, "equation_count": N}
        paper_id: Optional paper ID for context loading
        conv_id: Optional conversation ID for chat history

    Returns:
        Section dict matching the schema from prompt.txt
    """
    # Per user requirement (perintah.txt 2026-05-22): use full prompt+humanize for quality
    full_prompt = _load_base_prompt()
    humanize_rules = _load_humanize_rules()
    
    # Load full context: chat history + literature + files
    context_block = _load_full_context(paper_id, conv_id, max_files=5, max_lit=20,
                                       history_msgs=10, custom_prompt=custom_prompt)

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

CURRENT TASK: Generate ONLY Section {section_num} ({section_title}) as the
JSON object for "section{section_num}" following the SECTION JSON SCHEMA at
the top of this prompt. Include subsections, figures, tables, and equations
appropriate for this section type. Continue figure/table/equation numbering
from the current numbering state.
"""

    if topic:
        topic_guide = _load_topic_guide(topic)
        if topic_guide:
            system_prompt += f"\n\nTOPIC GUIDE:\n{topic_guide}"

    if style:
        style_guide = _load_style_guide(style)
        if style_guide:
            system_prompt += f"\n\nCITATION STYLE GUIDE:\n{style_guide}"
    
    # Inject full context (history + literature + files)
    if context_block:
        system_prompt += f"\n\nCONTEXT FROM PROJECT:\n{context_block}"

    user_message = f"""Topic: {judul}

Additional instructions: {custom_prompt if custom_prompt else "(none)"}

Generate Section {section_num} ({section_title}) following the schema and context above.
Ensure figure/table/equation numbering continues from the current state.
Return ONLY the JSON object for section{section_num}."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    # Log prompt size for observability (per user requirement)
    prompt_size_kb = len(system_prompt.encode('utf-8')) / 1024
    log.info("section %d prompt size: %.1f KB", section_num, prompt_size_kb)

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
                        api_key: str, base_url: str, model: str,
                        custom_prompt: str = "", progress_cb=None,
                        paper_id=None, conv_id=None) -> list:
    """
    Generate references for the paper.

    Per user requirement (perintah.txt 2026-05-22): inject literature catalog
    from DB directly when available, plus full prompt.txt rules for refs.
    
    When ``custom_prompt`` carries a "## Literature catalog" block (produced
    by ``chat_tools._format_literature_block`` from the user's curated SLR
    rows), the prompt is rewritten to forbid fabrication and the AI is
    instructed to convert ONLY those entries into the requested citation
    style. When the catalog is absent (no SLR run yet) the original
    "plausible-but-fabricated" fallback is preserved for backward compat.

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

    style_guide = _load_style_guide(style) if style else ""

    # Literature-aware path: try custom_prompt first, then fall back to DB query.
    lit_block = _extract_literature_block(custom_prompt)
    lit_entries = _parse_literature_entries(lit_block)
    
    # If no literature in custom_prompt, try loading from DB via paper_id
    if not lit_entries and paper_id:
        try:
            from models import db, LiteratureItem
            items = (db.session.query(LiteratureItem)
                    .filter_by(paper_id=paper_id)
                    .order_by(LiteratureItem.pinned.desc(),
                             LiteratureItem.must_read.desc(),
                             LiteratureItem.score_total.desc())
                    .limit(50).all())
            if items:
                # Build entries in (idx, body) format
                lit_entries = []
                for i, it in enumerate(items, 1):
                    authors_list = it.authors or []
                    authors = ", ".join(authors_list[:3])
                    if len(authors_list) > 3:
                        authors += " et al."
                    bits = [it.title or "Untitled"]
                    if authors:
                        bits.append(f"— {authors}")
                    if it.year:
                        bits.append(f"({it.year})")
                    if it.venue:
                        bits.append(f"in {it.venue}")
                    if it.doi:
                        bits.append(f"DOI: {it.doi}")
                    elif it.url:
                        bits.append(f"URL: {it.url}")
                    body = " ".join(bits)
                    lit_entries.append((i, body))
        except Exception as e:
            log.warning("[_generate_references] DB literature load failed: %s", e)

    if lit_entries:
        num_refs = len(lit_entries)
        lit_inline = _format_lit_for_refs(lit_entries)

        system_prompt = f"""You are converting a curated literature list into the IEEE/APA reference list of an academic paper.

Use ONLY the entries below as references. DO NOT invent, fabricate, or add references not in the list. Match the requested citation style. If the paper text uses [N] markers higher than the catalog size, ignore them.

PAPER CONTEXT:
Title: {outline.get('title', '')}
Abstract: {outline.get('abstract', '')}
Keywords: {', '.join(outline.get('keywords', []))}

CITATION STYLE:
{style_guide if style_guide else "Use numbered IEEE format: [1], [2], etc."}

CURATED LITERATURE LIST (authoritative — use exactly these {num_refs} entries, in this order, numbered [1]..[{num_refs}]):
{lit_inline}

RULES:
- Output exactly {num_refs} references, numbered [1]..[{num_refs}], matching the order above.
- Reformat each entry into the requested citation style (authors, title, venue, year, DOI/URL).
- Do NOT add, remove, merge, or invent references.
- Do NOT drop DOIs or URLs that are present in the source entry.
- Preserve author names, year, and venue exactly as given.

OUTPUT SCHEMA:
{{
  "references": [
    "[1] <reformatted reference 1>",
    "[2] <reformatted reference 2>",
    ...
    "[{num_refs}] <reformatted reference {num_refs}>"
  ]
}}

Return ONLY the JSON object, no markdown fences."""

        user_message = f"""Reformat the {num_refs} curated literature entries above into the citation style for this paper.
Topic: {outline.get('title', '')}

Return the references as a JSON object with a "references" array of {num_refs} items."""

    else:
        # Fallback: no curated literature — generate plausible references.
        max_citation = max(citations) if citations else 20
        num_refs = max(max_citation, 20)

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

    # Log prompt size for observability
    prompt_size_kb = len(system_prompt.encode('utf-8')) / 1024
    log.info("references prompt size: %.1f KB", prompt_size_kb)

    raw_content, model_used = _call_aiotomasi_with_fallback(
        messages, api_key, base_url, model, timeout=900.0, progress_cb=progress_cb
    )
    mode = "literature-aware" if lit_entries else "fallback-plausible"
    print(f"[_generate_references] succeeded using model={model_used} mode={mode} count={num_refs}", flush=True)

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
    *,
    checkpoint_cb=None,
    cancel_check=None,
    resume_state=None,
    paper_id=None,
    conv_id=None,
) -> dict:
    """
    Generate a complete academic paper JSON via chunked API calls.

    This is a drop-in replacement for generate_paper_json() that breaks the
    generation into 7 smaller chunks to avoid 30s gateway timeouts. The new
    keyword-only params let callers persist progress, cancel mid-flight, and
    resume from the last successful chunk.

    Args:
        judul: Paper title / topic.
        custom_prompt: Additional instructions for the AI.
        api_key: API key (falls back to AIOTOMASI_APIKEY env var).
        base_url: API base URL (falls back to AIOTOMASI_API env var).
        model: Model name (falls back to AIOTOMASI_MODEL env var).
        topic: Topic guide file name (without .txt).
        style: Style guide file name (without .txt).
        progress_cb: Optional callable(chars_done: int) for low-level streaming
            feedback (forwarded to the AI client).
        checkpoint_cb: Optional callable(stage, progress, partial). Invoked AFTER
            each chunk lands. ``stage`` is one of ``outline``, ``section_1`` ..
            ``section_5``, ``references``, ``combine``. ``progress`` is 0..100.
            ``partial`` is the current accumulated paper dict, safe to persist.
            Exceptions raised by the callback are logged and swallowed so a
            broken sink can never abort generation.
        cancel_check: Optional callable() -> bool. Polled BEFORE each chunk and
            after each checkpoint. When it returns True, ``GenerationCancelled``
            is raised so the caller can persist the partial paper.
        resume_state: Optional dict with keys ``chunks_done`` (list of stage
            names already completed) and ``partial_paper`` (the partial dict
            from a previous run). Chunks present in ``chunks_done`` are skipped.
        paper_id: Optional paper ID. When provided, full context (literature
            catalog, attached files) is loaded from the DB and injected into
            every chunk's prompt. Per user requirement (perintah.txt 2026-05-22).
        conv_id: Optional conversation ID. When provided, recent chat history
            is loaded and injected as context for every chunk.

    Returns:
        Complete paper dict matching the schema from prompt.txt.

    Raises:
        ValueError: If API key/URL is missing or JSON cannot be parsed.
        GenerationCancelled: If ``cancel_check`` returned True at a checkpoint.
    """
    _api_key = api_key or AIOTOMASI_APIKEY
    _base_url = base_url or AIOTOMASI_API
    _model = model or AIOTOMASI_MODEL

    if not _api_key:
        raise ValueError("AIOTOMASI_APIKEY not found in environment")
    if not _base_url:
        raise ValueError("AIOTOMASI_API not found in environment")

    # ── State machine ────────────────────────────────────────────────────────
    state = resume_state or {}
    if not isinstance(state, dict):
        state = {}
    chunks_done = list(state.get("chunks_done") or [])
    done = set(chunks_done)
    partial = dict(state.get("partial_paper") or {})

    def _check_cancel(stage: str) -> None:
        if cancel_check and cancel_check():
            raise GenerationCancelled(stage)

    def _checkpoint(stage: str, progress: int) -> None:
        if stage not in done:
            done.add(stage)
            chunks_done.append(stage)
        if checkpoint_cb is None:
            return
        try:
            # Pass a shallow copy so a buggy sink can't mutate the live dict.
            checkpoint_cb(stage=stage, progress=int(progress), partial=dict(partial))
        except Exception:
            log.exception("[generate_paper_json_chunked] checkpoint_cb failed at stage=%s", stage)

    print(
        f"[generate_paper_json_chunked] Starting (resume_state={'yes' if resume_state else 'no'}, "
        f"already_done={sorted(done) or 'none'})...",
        flush=True,
    )
    t_start = time.time()

    # ── Chunk 1: Outline ─────────────────────────────────────────────────────
    if "outline" not in done:
        _check_cancel("outline")
        print("[1/8] Generating outline...", flush=True)
        outline = _generate_outline(
            judul, custom_prompt, topic, style,
            _api_key, _base_url, _model, progress_cb,
            paper_id=paper_id, conv_id=conv_id,
        )
        partial["outline"] = outline
        partial["title"] = outline.get("title", "")
        partial["abstract"] = outline.get("abstract", "")
        partial["keywords"] = outline.get("keywords", [])
        partial.setdefault("sections", [])
        _checkpoint("outline", 10)
    else:
        outline = partial.get("outline") or {}
        partial.setdefault("sections", [])
        print("[1/8] outline already done — skipping", flush=True)

    # Reconstruct numbering state from any previously generated sections so
    # resumed runs continue numbering monotonically across the boundary.
    numbering_state = {"figure_count": 0, "table_count": 0, "equation_count": 0}
    sections = list(partial.get("sections") or [])

    def _count_items(section, item_type):
        n = 0
        if isinstance(section, dict):
            for value in section.values():
                if isinstance(value, dict):
                    if value.get("id") == item_type:
                        n += 1
                    n += _count_items(value, item_type)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            if item.get("id") == item_type:
                                n += 1
                            n += _count_items(item, item_type)
        return n

    for sec in sections:
        numbering_state["figure_count"] += _count_items(sec, "gambar")
        numbering_state["table_count"] += _count_items(sec, "tabel")
        numbering_state["equation_count"] += _count_items(sec, "rumus")

    # ── Chunks 2-6: Sections I-V ─────────────────────────────────────────────
    for i in range(1, 6):
        chunk_id = f"section_{i}"
        if chunk_id in done:
            print(f"[{i+1}/8] {chunk_id} already done — skipping", flush=True)
            continue
        _check_cancel(chunk_id)
        print(f"[{i+1}/8] Generating Section {i}...", flush=True)
        section = _generate_section(
            i, outline, sections, judul, custom_prompt,
            topic, style, _api_key, _base_url, _model,
            numbering_state, progress_cb,
            paper_id=paper_id, conv_id=conv_id,
        )
        sections.append(section)
        partial["sections"] = sections
        _checkpoint(chunk_id, 10 + i * 15)

    # ── Chunk 7: References ──────────────────────────────────────────────────
    if "references" not in done:
        _check_cancel("references")
        print("[7/8] Generating references...", flush=True)
        references = _generate_references(
            outline, sections, style,
            _api_key, _base_url, _model,
            custom_prompt=custom_prompt,
            progress_cb=progress_cb,
            paper_id=paper_id, conv_id=conv_id,
        )
        partial["references"] = references
        _checkpoint("references", 90)
    else:
        references = partial.get("references") or []
        print("[7/8] references already done — skipping", flush=True)

    # ── Chunk 8: Combine ─────────────────────────────────────────────────────
    _check_cancel("combine")
    print("[8/8] Combining...", flush=True)

    section_titles = outline.get("section_titles") or {}
    sections_array = []
    for i, sec in enumerate(sections, 1):
        sec = dict(sec) if isinstance(sec, dict) else {}
        sec.setdefault("title", section_titles.get(f"section{i}", f"SECTION {i}"))
        sections_array.append(sec)

    paper_json = {
        "title": outline.get("title", ""),
        "abstract": outline.get("abstract", ""),
        "keywords": outline.get("keywords", []),
        "authors": [
            {
                "name": "Author Name",
                "affiliation": "Department, University",
                "location": "City, Country",
                "email": "author@example.com",
            }
        ],
        "sections": sections_array,
        "acknowledgment": "",
        "references": references,
        "figures": [],
        "tables": [],
        "equations": [],
    }

    def extract_items(obj, item_type, collection):
        if isinstance(obj, dict):
            for value in obj.values():
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

    # Final checkpoint carries the fully assembled paper so callers can persist
    # the canonical shape (with sections array + extracted figures/tables/eqs)
    # without having to re-run the combine step on their side.
    partial = paper_json
    _checkpoint("combine", 100)

    elapsed = time.time() - t_start
    print(f"[generate_paper_json_chunked] Completed in {elapsed:.1f}s", flush=True)

    return paper_json
