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

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from json_repair import repair_json

from utils.core.env_loader import load_app_env
from utils.ai_tools.model_config import get_primary_generate_model

# Reuse existing API caller with fallback
from tools.editor.api_client import _call_aiotomasi_with_fallback

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
AIOTOMASI_MODEL = get_primary_generate_model()

# Prompt files. Two layouts can exist depending on how this module is reached:
# 1. PaperRiset/eks/paperfull/prompt/         (relative to chunked.py here)
# 2. backend/tools/paperfull/prompt/          (canonical production layout)
# Use a resolver that checks both so a missing file in one layout doesn't kill
# the whole pipeline (this was the cause of "prompt.txt not found" errors).
PROMPT_DIR_CANDIDATES: list[Path] = []
for _candidate in (
    # PaperRiset/eks/paperfull/prompt/ (file di sini)
    BASE_DIR.parent / "paperfull" / "prompt",
    # PaperRiset/tools/paperfull/prompt/
    BASE_DIR.parent.parent / "tools" / "paperfull" / "prompt",
    # backend/tools/paperfull/prompt/ (kanonik produksi)
    BASE_DIR.parent.parent.parent / "backend" / "tools" / "paperfull" / "prompt",
    # Absolute fallback — repo root (always present even if symlink changes)
    Path("/home/sirobo/papergenerator/backend/tools/paperfull/prompt"),
    Path("/home/sirobo/papergenerator/PaperRiset/eks/paperfull/prompt"),
):
    _candidate = _candidate.resolve()
    # Dedup by resolved path (Path equality compares the string repr, so
    # two resolved paths pointing to the same inode will match).
    if not any(c.resolve() == _candidate for c in PROMPT_DIR_CANDIDATES):
        PROMPT_DIR_CANDIDATES.append(_candidate)


def _resolve_prompt_file(filename: str) -> Path:
    """Return the first existing path for ``filename`` among candidate dirs.

    Raises FileNotFoundError when none of the candidates contain the file.
    Callers that treat the file as optional should catch and return a default.
    """
    tried: list[str] = []
    for d in PROMPT_DIR_CANDIDATES:
        p = d / filename
        if p.exists():
            return p
        tried.append(str(p))
    raise FileNotFoundError(
        f"prompt file '{filename}' not found in any of: {tried}"
    )


def _load_base_prompt(language: str = "id"):
    """Load the base prompt (single unified file, language injected at runtime)."""
    content = _resolve_prompt_file("prompt.txt").read_text(encoding="utf-8")
    # Inject explicit language directive at the top
    if language == "en":
        lang_instruction = "⚠️ LANGUAGE: This paper MUST be written ENTIRELY in ENGLISH. All section titles, body text, abstract, keywords, conclusion — ALL in English."
    else:
        lang_instruction = "⚠️ BAHASA: Paper ini WAJIB ditulis SELURUHNYA dalam BAHASA INDONESIA. Semua judul section, isi teks, abstrak, kata kunci, kesimpulan — SEMUA dalam Bahasa Indonesia."
    return f"{lang_instruction}\n\n{content}"


def _load_humanize_rules(language: str = "id"):
    """Load humanize rules (single unified file)."""
    try:
        return _resolve_prompt_file("humanize.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _load_style_guide(style: str = None):
    """Load optional style guide."""
    if not style:
        return ""
    try:
        return _resolve_prompt_file(f"style/{style}.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _load_topic_guide(topic: str = None):
    """Load optional topic guide."""
    if not topic:
        return ""
    try:
        return _resolve_prompt_file(f"topic/{topic}.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _load_language_template(language: Optional[str] = None):
    """Load language-specific section title template (en.json or id.json).

    Returns the JSON template as a string to be prepended to the system prompt,
    instructing the AI to use the correct section titles for the language.
    """
    if not language:
        return ""
    try:
        return _resolve_prompt_file(f"{language}.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


# ── Helper: Detect paper review mode ─────────────────────────────────────────
def _detect_paper_review_mode(judul: str, custom_prompt: str) -> bool:
    """Return True if user is requesting a paper/literature review.
    
    Detection keywords (case-insensitive):
    - "paper review", "literature review", "tinjauan pustaka"
    - "systematic review", "narrative review", "scoping review"
    - "review paper", "review artikel", "review literatur"
    """
    text = (judul or "") + " " + (custom_prompt or "")
    text_lower = text.lower()
    review_keywords = [
        "paper review", "literature review", "tinjauan pustaka",
        "systematic review", "narrative review", "scoping review",
        "review paper", "review artikel", "review literatur",
        "studi pustaka", "kajian pustaka", "bibliometric review",
        "meta-analysis", "meta analysis"
    ]
    return any(kw in text_lower for kw in review_keywords)


# ── Helper: Literature catalog extraction ────────────────────────────────────
_LIT_HEADING_RE = re.compile(r"^##\s*Literature catalog\b.*$", re.IGNORECASE | re.MULTILINE)
_LIT_LINE_RE = re.compile(r"^\[L(\d+)\]\s*(.+?)\s*$", re.MULTILINE)


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
    tail = custom_prompt[match.end() :]
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
def _load_full_context(
    paper_id, conv_id=None, max_files=50, max_lit=20, history_msgs=10, custom_prompt=None, review_mode=False, user_id=None
):
    """Build a context block with chat history + literature + files for injection.

    Per user requirement (perintah.txt 2026-05-22): inject full context into
    chunked generation to restore quality lost by slim prompts.

    Args:
        paper_id: Required. The paper being generated.
        conv_id: Optional. Conversation ID for chat history.
        max_files: Max attached files to include (default 5).
        max_lit: Max literature items to include (default 20, 100 for review mode).
        history_msgs: Max recent chat messages to include (default 10).
        custom_prompt: Optional caller-supplied prompt. When it already
            contains a ``[REFERENCE DOCUMENTS]`` marker the file injection
            block is skipped to avoid duplicating attached PDFs that were
            inlined upstream by ``app._run_generate_full_job``.
        review_mode: If True, increase max_lit to 100 to inject all SLR papers.

    Returns:
        String under 30KB with chat history + literature + files context.
    """
    from utils.database.models import ChatMessage, LiteratureItem, PaperFile, db

    skip_files = bool(custom_prompt and "[REFERENCE DOCUMENTS]" in custom_prompt)

    # For paper review mode: increase max_lit to 100 to inject all SLR papers
    if review_mode:
        max_lit = max(max_lit, 100)

    lines = []
    total_chars = 0
    max_context_size = 150_000  # 150KB budget — supports 50 files

    # ── Chat history ──────────────────────────────────────────────────────────
    if conv_id:
        try:
            messages = (
                db.session.query(ChatMessage)
                .filter_by(conversation_id=conv_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(history_msgs)
                .all()
            )
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
            items = (
                db.session.query(LiteratureItem)
                .filter_by(paper_id=paper_id, user_id=user_id)
                .order_by(
                    LiteratureItem.pinned.desc(),
                    LiteratureItem.must_read.desc(),
                    LiteratureItem.score_total.desc(),
                )
                .limit(max_lit)
                .all()
            )
            if items:
                lit_count = len(items)
                lines.append(f"## Literature catalog (authoritative reference list — EXACTLY {lit_count} items; do NOT add, remove, or fabricate any references)")
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
            files = (
                db.session.query(PaperFile)
                .filter_by(paper_id=paper_id)
                .order_by(PaperFile.created_at.desc())
                .limit(max_files)
                .all()
            )
            if files:
                lines.append("## Attached files (reference materials)")
                for f in files:
                    text = (f.extracted_text or "")[:5000]  # Cap per file
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
        result = result[:max_context_size] + "\n... [context truncated]"

    return result


# ── Helper: Parse JSON response ───────────────────────────────────────────────
def _parse_json_response(raw_content: str) -> dict:
    """Parse JSON from API response, with repair fallback."""
    # Strip markdown fences
    clean = re.sub(r"^```(?:json)?\s*", "", raw_content.strip(), flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)

    # Check for empty response
    if not clean or not clean.strip():
        preview = raw_content[:200] if raw_content else "(empty)"
        log.error("[_parse_json_response] Empty response after cleaning. Raw preview: %s", preview)
        raise ValueError(f"AI returned empty response. Raw preview: {preview}")

    # Try direct parse first
    try:
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            return parsed
        elif isinstance(parsed, list):
            log.warning("[_parse_json_response] AI returned list instead of dict, attempting to extract")
            # Find all dicts in the list
            dicts = [item for item in parsed if isinstance(item, dict)]
            if len(dicts) == 1:
                log.info("[_parse_json_response] Extracted single dict from list")
                return dicts[0]
            elif len(dicts) > 1:
                # Multiple dicts - take the largest one (most likely the actual response)
                largest = max(dicts, key=lambda d: len(json.dumps(d)))
                log.info("[_parse_json_response] Extracted largest dict from list with %d dicts", len(dicts))
                return largest
            else:
                raise ValueError(f"AI returned list with {len(parsed)} items but no dict found")
        else:
            raise ValueError(f"AI returned {type(parsed).__name__}, expected dict")
    except json.JSONDecodeError as e1:
        # Fallback to json_repair
        log.warning("[_parse_json_response] JSON parse failed, trying json_repair: %s", str(e1)[:100])
        # Detect likely truncation: content doesn't end with } and has open brackets
        truncated_hint = (not clean.rstrip().endswith('}')) or (clean.count('[') > clean.count(']'))
        try:
            repaired = repair_json(clean, return_objects=True)
            if isinstance(repaired, dict) and repaired:
                if truncated_hint:
                    log.warning(
                        "[_parse_json_response] json_repair used on TRUNCATED response "
                        "(content did not end with '}' or unmatched brackets). "
                        "Some fields may be incomplete. Original error: %s", str(e1)[:200]
                    )
                else:
                    log.info("[_parse_json_response] json_repair successfully returned dict")
                return repaired
            elif isinstance(repaired, list):
                log.warning("[_parse_json_response] json_repair returned list with %d items", len(repaired))
                # Find all dicts in the repaired list
                dicts = [item for item in repaired if isinstance(item, dict)]
                if len(dicts) == 1:
                    log.info("[_parse_json_response] Extracted single dict from repaired list")
                    return dicts[0]
                elif len(dicts) > 1:
                    # Multiple dicts - take the largest one
                    largest = max(dicts, key=lambda d: len(json.dumps(d)))
                    log.info("[_parse_json_response] Extracted largest dict from repaired list with %d dicts", len(dicts))
                    return largest
                elif len(repaired) > 0:
                    preview = str(repaired)[:200]
                    raise ValueError(f"json_repair returned list with {len(repaired)} items but no dict found. Preview: {preview}")
                else:
                    raise ValueError("json_repair returned empty list")
            else:
                raise ValueError(f"json_repair returned {type(repaired).__name__}, expected dict")
        except Exception as e2:
            clean_preview = clean[:300] if len(clean) > 300 else clean
            log.error("[_parse_json_response] Both json.loads and json_repair failed. Clean preview: %s", clean_preview)
            raise ValueError(f"JSON parse failed: {e1} | repair: {e2} | Preview: {clean_preview}")


# ── Chunk 1: Generate Outline ─────────────────────────────────────────────────
def _generate_outline(
    judul: str,
    custom_prompt: str,
    topic: Optional[str],
    style: Optional[str],
    language: Optional[str],
    api_key: str,
    base_url: str,
    model: str,
    progress_cb=None,
    paper_id=None,
    conv_id=None,
    user_id=None,
) -> dict:
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
            },
            "review_mode": bool  # Added: True if paper review detected
        }
    """
    # Per user requirement (perintah.txt 2026-05-22): use full prompt+humanize for quality
    full_prompt = _load_base_prompt(language or "id")
    humanize_rules = _load_humanize_rules(language or "id")

    # Detect paper review mode
    is_review = _detect_paper_review_mode(judul, custom_prompt)
    log.info("[_generate_outline] Paper review mode: %s", is_review)

    # Load full context: chat history + literature + files
    # For review mode: inject all SLR papers (max_lit=100)
    context_block = _load_full_context(
        paper_id, conv_id, max_files=50, max_lit=20, history_msgs=10, 
        custom_prompt=custom_prompt, review_mode=is_review, user_id=user_id
    )

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

    # Auto-inject review topic guide if paper review mode detected
    if is_review:
        review_guide = _load_topic_guide("review")
        if review_guide:
            system_prompt += f"\n\nTOPIC GUIDE (PAPER REVIEW MODE):\n{review_guide}"
            log.info("[_generate_outline] Injected review topic guide")

    if style:
        style_guide = _load_style_guide(style)
        if style_guide:
            system_prompt += f"\n\nCITATION STYLE GUIDE:\n{style_guide}"

    # Add language template for section titles
    if language:
        lang_template = _load_language_template(language)
        if lang_template:
            system_prompt = f"""USE THIS JSON TEMPLATE STRUCTURE FOR SECTION TITLES:
{lang_template}

The section titles above MUST be used exactly as shown (in the specified language).
Adapt content to the specific topic, but keep section titles in the correct language.

---

{system_prompt}"""

    # Inject full context
    if context_block:
        system_prompt += f"\n\nCONTEXT FROM PROJECT:\n{context_block}"

    # Inject workflow context
    if paper_id and user_id:
        try:
            from PaperRiset.eks.editor.workflow_integration import load_workflow_context
            workflow_ctx = load_workflow_context(paper_id, user_id)
            if workflow_ctx:
                system_prompt += f"\n\n{workflow_ctx}"
                log.info("[_generate_outline] Injected workflow context")
        except Exception as e:
            log.warning("[_generate_outline] Failed to load workflow context: %s", e)

    user_message = f"""Topic description: {judul}

Additional instructions: {custom_prompt if custom_prompt else "(none)"}

Generate the paper outline following the schema above.
IMPORTANT: If this is a paper review / literature review, follow the review structure:
- section1: PENDAHULUAN
- section2: METODOLOGI REVIEW  
- section3+: PEMBAHASAN TOPIK 1, TOPIK 2, TOPIK 3, dst (minimal 3 topik)
- section TERAKHIR: KESIMPULAN
Return the section_titles with actual number of sections needed."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Log prompt size for observability
    prompt_size_kb = len(system_prompt.encode("utf-8")) / 1024
    log.info("outline prompt size: %.1f KB", prompt_size_kb)

    from utils.core.retry_helper import get_retry_config
    _, timeout = get_retry_config()
    
    raw_content, model_used = _call_aiotomasi_with_fallback(
        messages, api_key, base_url, model, timeout=timeout, progress_cb=progress_cb
    )
    log.info("[_generate_outline] succeeded using model=%s", model_used)

    return _parse_json_response(raw_content)


# ── Chunk 2-6: Generate Section ───────────────────────────────────────────────
def _generate_section(
    section_num: int,
    outline: dict,
    previous_sections: list,
    judul: str,
    custom_prompt: str,
    topic: str,
    style: str,
    api_key: str,
    base_url: str,
    model: str,
    numbering_state: dict,
    progress_cb=None,
    paper_id=None,
    conv_id=None,
    user_id=None,
    language: str = "id",
) -> dict:
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
        language: "id" for Indonesian, "en" for English

    Returns:
        Section dict matching the schema from prompt.txt
    """
    # Per user requirement (perintah.txt 2026-05-22): use full prompt+humanize for quality
    full_prompt = _load_base_prompt(language)
    humanize_rules = _load_humanize_rules(language)

    # Detect paper review mode
    is_review = _detect_paper_review_mode(judul, custom_prompt)

    # Load full context: chat history + literature + files
    # For review mode: inject all SLR papers (max_lit=100)
    context_block = _load_full_context(
        paper_id, conv_id, max_files=50, max_lit=20, history_msgs=10,
        custom_prompt=custom_prompt, review_mode=is_review, user_id=user_id
    )

    # Extract section-specific schema from full prompt
    # This is a simplified approach - in production, you'd parse the prompt more carefully
    section_key = f"section{section_num}"
    section_title = outline.get("section_titles", {}).get(section_key, f"SECTION {section_num}")

    # Determine total section count from outline (flexible for review papers)
    _stitles = outline.get("section_titles", {}) or {}
    _total_sections = max(5, len(_stitles))

    # Build context from outline and previous sections
    context_parts = [
        "PAPER OUTLINE:",
        f"Title: {outline.get('title', '')}",
        f"Abstract: {outline.get('abstract', '')}",
        f"Keywords: {', '.join(outline.get('keywords', []))}",
        "",
        "SECTION TITLES:",
    ]
    for i in range(1, _total_sections + 1):
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
                first_para = (
                    content[0].get("text", "")[:200] if isinstance(content[0], dict) else ""
                )
                context_parts.append(f"  Section {i} ({sec_title}): {first_para}...")

    # Add numbering state
    context_parts.append("\nCURRENT NUMBERING STATE:")
    context_parts.append(f"  Next Figure: {numbering_state['figure_count'] + 1}")
    context_parts.append(f"  Next Table: {numbering_state['table_count'] + 1}")
    context_parts.append(f"  Next Equation: {numbering_state['equation_count'] + 1}")

    context = "\n".join(context_parts)

    # Detect no-data mode: if no experimental data in context
    no_data = True
    if custom_prompt and any(kw in custom_prompt.lower() for kw in ["data", "tabel", "grafik", "hasil eksperimen", "data sumber", "angka persis", "extracted from"]):
        no_data = False
    if context_block and any(kw in context_block.lower() for kw in ["## data items", "hasil eksperimen", "data sumber", "## data sumber"]):
        no_data = False

    # Paper review mode: no experimental data, BUT may use reference data
    # Only force no-data if there's genuinely no data in references either
    if is_review and no_data:
        # Check if references contain data/metrics that should be used
        ref_has_data = False
        if context_block and any(kw in context_block.lower() for kw in ["hasil", "result", "accuracy", "precision", "recall", "f1", "metric", "performa", "performance"]):
            ref_has_data = True
        if custom_prompt and any(kw in custom_prompt.lower() for kw in ["hasil", "result", "accuracy", "precision", "recall", "f1", "metric", "performa", "performance"]):
            ref_has_data = True
        if not ref_has_data:
            no_data = True
        # If references have data, keep no_data=False so LLM uses real values
    
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
    
    # Add no-data mode reminder for equations/tables
    if no_data:
        system_prompt += """
⚠️ NO-DATA MODE — PAPER TANPA DATA EKSPERIMEN:
- SEMUA rumus/persamaan WAJIB pakai VARIABEL PLACEHOLDER: X1, X2, X3 (hasil), a1, a2, b1, b2 (parameter), Y1, Y2, Y3 (perbandingan)
- JANGAN pernah tulis angka spesifik (3.2, 94%, 0.075) di rumus atau tabel
- Contoh rumus BENAR: "latex": "X_1 = \\\\frac{a_1 + a_2}{b_1}"
- Contoh rumus SALAH: "latex": "v = \\\\frac{0.15 + 0.20}{0.075}"  ← JANGAN
- Tabel: gunakan variabel di sel data ["Proposed", "a1", "a2", "a3"]
- Narasi WAJIB jelaskan arti setiap variabel yang dipakai
"""

    if topic:
        topic_guide = _load_topic_guide(topic)
        if topic_guide:
            system_prompt += f"\n\nTOPIC GUIDE:\n{topic_guide}"

    # Auto-inject review topic guide if paper review mode detected
    if is_review:
        review_guide = _load_topic_guide("review")
        if review_guide:
            system_prompt += f"\n\nTOPIC GUIDE (PAPER REVIEW MODE):\n{review_guide}"

    if style:
        style_guide = _load_style_guide(style)
        if style_guide:
            system_prompt += f"\n\nCITATION STYLE GUIDE:\n{style_guide}"

    # Inject full context (history + literature + files)
    if context_block:
        system_prompt += f"\n\nCONTEXT FROM PROJECT:\n{context_block}"

    # ── REFERENCE INTEGRITY ENFORCEMENT ──────────────────────────────────────
    # When literature catalog is present (either in context_block or custom_prompt),
    # inject an explicit hard constraint that overrides the "MINIMUM 20" rule.
    lit_block_in_section = _extract_literature_block(custom_prompt)
    lit_entries_in_section = _parse_literature_entries(lit_block_in_section)
    if not lit_entries_in_section and paper_id:
        try:
            from utils.database.models import LiteratureItem, db
            _lit_items = (
                db.session.query(LiteratureItem)
                .filter_by(paper_id=paper_id, user_id=user_id)
                .order_by(
                    LiteratureItem.pinned.desc(),
                    LiteratureItem.must_read.desc(),
                    LiteratureItem.score_total.desc(),
                )
                .all()  # Load ALL user refs — exact count matters, no limit
            )
            if _lit_items:
                lit_entries_in_section = [
                    (i, f"{it.title} — {', '.join((it.authors or [])[:3])} ({it.year or '?'}) DOI: {it.doi or 'N/A'}")
                    for i, it in enumerate(_lit_items, 1)
                ]
        except Exception as e:
            log.warning("[_generate_section] Failed to load literature from DB: %s", e)
    if lit_entries_in_section:
        _lit_count = len(lit_entries_in_section)
        system_prompt += f"""

⚠️⚠️⚠️ REFERENCE CONSTRAINT (OVERRIDES ALL OTHER REFERENCE RULES) ⚠️⚠️⚠️
User has provided {_lit_count} references via Literature catalog.
• Output EXACTLY {_lit_count} references in the references section — NO MORE, NO LESS.
• Use ONLY those {_lit_count} references. Do NOT fabricate or add any extra references.
• Every citation [N] in the text MUST correspond to one of the {_lit_count} provided references.
• Do NOT invent DOIs, authors, titles, or venues. Use the EXACT metadata from the catalog.
• If a reference lacks a DOI in the catalog, leave "doi" as empty string "". NEVER fabricate a DOI.
This is a HARD CONSTRAINT. Violating it produces fabricated references which is unacceptable.
"""
        log.info("[_generate_section] Section %d: Injected ref constraint — %d user refs, no fabrication allowed", section_num, _lit_count)

    # Inject workflow context
    if paper_id and user_id:
        try:
            from PaperRiset.eks.editor.workflow_integration import load_workflow_context
            workflow_ctx = load_workflow_context(paper_id, user_id)
            if workflow_ctx:
                system_prompt += f"\n\n{workflow_ctx}"
                log.info("[_generate_section] Section %d: Injected workflow context", section_num)
        except Exception as e:
            log.warning("[_generate_section] Section %d: Failed to load workflow context: %s", section_num, e)

    user_message = f"""Topic: {judul}

Additional instructions: {custom_prompt if custom_prompt else "(none)"}

Generate Section {section_num} ({section_title}) following the schema and context above.
Ensure figure/table/equation numbering continues from the current state.
Return ONLY the JSON object for section{section_num}."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Log prompt size for observability (per user requirement)
    prompt_size_kb = len(system_prompt.encode("utf-8")) / 1024
    log.info("section %d prompt size: %.1f KB", section_num, prompt_size_kb)

    from utils.core.retry_helper import get_retry_config
    _, timeout = get_retry_config()
    
    raw_content, model_used = _call_aiotomasi_with_fallback(
        messages, api_key, base_url, model, timeout=timeout, progress_cb=progress_cb
    )
    log.info("[_generate_section] Section %d succeeded using model=%s", section_num, model_used)

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
def _generate_references(
    outline: dict,
    all_sections: list,
    style: str,
    api_key: str,
    base_url: str,
    model: str,
    custom_prompt: str = "",
    progress_cb=None,
    paper_id=None,
    conv_id=None,
    user_id=None,
    language: str = "id",
) -> list:
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
            matches = re.findall(r"\[(\d+)\]", obj)
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
            from utils.database.models import LiteratureItem, db

            items = (
                db.session.query(LiteratureItem)
                .filter_by(paper_id=paper_id, user_id=user_id)
                .order_by(
                    LiteratureItem.pinned.desc(),
                    LiteratureItem.must_read.desc(),
                    LiteratureItem.score_total.desc(),
                )
                .all()  # Load ALL user refs — exact count matters, no limit
            )
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

    # Language directive for reference prompts
    if language == "en":
        _ref_lang = "⚠️ LANGUAGE: This paper MUST be written ENTIRELY in ENGLISH.\n\n"
    else:
        _ref_lang = "⚠️ BAHASA: Paper ini WAJIB ditulis SELURUHNYA dalam BAHASA INDONESIA.\n\n"

    if lit_entries:
        num_refs = len(lit_entries)
        lit_inline = _format_lit_for_refs(lit_entries)

        system_prompt = f"""{_ref_lang}Kamu mengkonversi daftar literatur terkurasi menjadi daftar pustaka terstruktur untuk paper akademik.

⚠️⚠️⚠️ MODE A: USER MEMBERIKAN REFERENSI — ATURAN KETAT ⚠️⚠️⚠️
Gunakan HANYA entri di bawah sebagai referensi. JANGAN mengarang, membuat, atau menambahkan referensi yang tidak ada di daftar. Cocokkan style sitasi yang diminta. Jika teks paper menggunakan penanda [N] melebihi ukuran katalog, abaikan.

KONTEKS PAPER:
Judul: {outline.get('title', '')}
Abstrak: {outline.get('abstract', '')}
Kata kunci: {', '.join(outline.get('keywords', []))}

CITATION STYLE:
{style_guide if style_guide else "Gunakan format IEEE bernomor: [1], [2], dst."}

DAFTAR LITERATUR TERKURASI (otoritatif — gunakan persis {num_refs} entri ini, dalam urutan ini):
{lit_inline}

ATURAN (WAJIB DIIKUTI — PELANGGARAN = REFERENSI FIKTIF):
1. Output PERSIS {num_refs} referensi — BUKAN lebih, BUKAN kurang.
2. Format setiap entri sebagai objek JSON terstruktur dengan field metadata LENGKAP.
3. JANGAN menambah, menghapus, menggabungkan, atau mengarang referensi.
4. DOI INTEGRITY:
   - Jika entri sumber MEMILIKI DOI → gunakan PERSIS DOI tersebut.
   - Jika entri sumber TIDAK memiliki DOI → set "doi": "" (string kosong).
   - JANGAN PERNAH mengarang/membuat DOI baru yang tidak ada di entri sumber.
   - JANGAN mengasosiasikan DOI dari paper lain ke entri yang berbeda.
5. METADATA INTEGRITY:
   - Jika volume/issue/pages tidak ada di entri sumber → set "" (string kosong).
   - JANGAN mengarang volume, issue, atau halaman.
6. Pertahankan nama penulis, tahun, dan venue PERSIS seperti yang diberikan.
   JANGAN ubah ejaan, inisial, atau format nama.
7. Jika entri memiliki URL → pertahankan PERSIS di field "url".

SKEMA OUTPUT:
{{
  "references": [
    {{
      "authors": ["Nama Belakang1, Inisial1", "Nama Belakang2, Inisial2"],
      "year": 2023,
      "title": "Judul lengkap artikel",
      "type": "journal|conference|book|book_chapter|thesis|website",
      "journal": "Nama Jurnal (untuk journal)",
      "conference": "Nama Konferensi (untuk conference)",
      "volume": "XX",
      "issue": "Y",
      "pages": "AAA-BBB",
      "doi": "10.XXXX/XXXXXXX",
      "publisher": "Nama Penerbit (untuk book/thesis)",
      "location": "Kota, Negara (untuk book/thesis)",
      "url": "https://... (untuk website)",
      "accessed": "DD Mon YYYY (untuk website)",
      "institution": "Nama Universitas (untuk thesis)"
    }}
  ]
}}

Hanya sertakan field yang relevan untuk tipe referensi. Kembalikan HANYA objek JSON, tanpa pagar markdown."""

        user_message = f"""Format ulang {num_refs} entri literatur terkurasi di atas menjadi objek referensi terstruktur untuk paper ini.
Topik: {outline.get('title', '')}

Kembalikan referensi sebagai objek JSON dengan array "references" berisi {num_refs} item."""

    else:
        # Fallback: no curated literature — generate references based on actual citations.
        # If sections cite [1]-[5], generate exactly 5 refs (no hard floor of 20).
        num_refs = max(citations) if citations else 0
        if num_refs == 0:
            # No citations at all — generate 20 as reasonable default
            num_refs = 20

        system_prompt = f"""{_ref_lang}Kamu menghasilkan referensi untuk paper akademik.

TUGAS: Hasilkan {num_refs} referensi dalam format JSON terstruktur.

KONTEKS PAPER:
Judul: {outline.get('title', '')}
Abstrak: {outline.get('abstract', '')}
Kata kunci: {', '.join(outline.get('keywords', []))}

CITATION STYLE:
{style_guide if style_guide else "Gunakan format IEEE bernomor: [1], [2], dst."}

ATURAN:
- Hasilkan persis {num_refs} referensi
- Setiap referensi WAJIB berupa objek JSON terstruktur dengan field metadata
- Semua referensi harus realistis dan masuk akal untuk topik ini
- Gunakan nama penulis realistis, judul yang masuk akal, nama venue yang benar
- Tahun 2010-2025
- Setiap referensi harus relevan dengan topik paper

SKEMA OUTPUT:
{{
  "references": [
    {{
      "authors": ["Nama Belakang1, Inisial1", "Nama Belakang2, Inisial2"],
      "year": 2023,
      "title": "Judul lengkap artikel",
      "type": "journal|conference|book|book_chapter|thesis|website",
      "journal": "Nama Jurnal (untuk journal)",
      "conference": "Nama Konferensi (untuk conference)",
      "volume": "XX",
      "issue": "Y",
      "pages": "AAA-BBB",
      "doi": "10.XXXX/XXXXXXX",
      "publisher": "Nama Penerbit (untuk book/thesis)",
      "location": "Kota, Negara (untuk book/thesis)",
      "url": "https://... (untuk website)",
      "accessed": "DD Mon YYYY (untuk website)",
      "institution": "Nama Universitas (untuk thesis)"
    }}
  ]
}}

Hanya sertakan field yang relevan untuk tipe referensi. Kembalikan HANYA objek JSON."""

        user_message = f"""Hasilkan {num_refs} referensi terstruktur untuk paper ini mengikuti style sitasi di atas.
Paper tentang: {outline.get('title', '')}

Kembalikan referensi sebagai objek JSON dengan array "references"."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Log prompt size for observability
    prompt_size_kb = len(system_prompt.encode("utf-8")) / 1024
    log.info("references prompt size: %.1f KB", prompt_size_kb)

    from utils.core.retry_helper import get_retry_config
    _, timeout = get_retry_config()
    
    raw_content, model_used = _call_aiotomasi_with_fallback(
        messages, api_key, base_url, model, timeout=timeout, progress_cb=progress_cb
    )
    mode = "literature-aware" if lit_entries else "fallback-plausible"
    log.info(
        "[_generate_references] succeeded using model=%s mode=%s count=%d",
        model_used,
        mode,
        num_refs,
    )

    refs_data = _parse_json_response(raw_content)
    return refs_data.get("references", [])


# ── Main Orchestrator ─────────────────────────────────────────────────────────
def generate_paper_json_chunked(
    judul: str,
    custom_prompt: str = "",
    api_key: str = None,
    base_url: str = None,
    model: str = None,
    topic: Optional[str] = None,
    style: Optional[str] = None,
    language: Optional[str] = None,
    progress_cb=None,
    *,
    checkpoint_cb=None,
    cancel_check=None,
    resume_state=None,
    paper_id=None,
    conv_id=None,
    user_id=None,
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

    log.info(
        "[generate_paper_json_chunked] Starting (resume_state=%s, already_done=%s)",
        "yes" if resume_state else "no",
        sorted(done) or "none",
    )
    t_start = time.time()

    # ── Chunk 1: Outline ─────────────────────────────────────────────────────
    if "outline" not in done:
        _check_cancel("outline")
        log.info("[1/8] Generating outline...")
        outline = _generate_outline(
            judul,
            custom_prompt,
            topic,
            style,
            language,
            _api_key,
            _base_url,
            _model,
            progress_cb,
            paper_id=paper_id,
            conv_id=conv_id,
            user_id=user_id,
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
        log.info("[1/8] outline already done — skipping")

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

    # ── Chunks 2-N: Sections I to N (flexible count) ─────────────────────────────
    # Detect number of sections from outline (default 5 for regular paper)
    section_titles = outline.get("section_titles") or {}
    num_sections = max(5, len(section_titles))  # At least 5, but follow outline if more
    log.info("[generate_paper_json_chunked] Generating %d sections (from outline: %s)", 
             num_sections, sorted(section_titles.keys()))
    
    for i in range(1, num_sections + 1):
        chunk_id = f"section_{i}"
        if chunk_id in done:
            log.info("[chunk] %s already done — skipping", chunk_id)
            continue
        _check_cancel(chunk_id)
        log.info("[chunk] Generating Section %d/%d...", i, num_sections)
        section = _generate_section(
            i,
            outline,
            sections,
            judul,
            custom_prompt,
            topic,
            style,
            _api_key,
            _base_url,
            _model,
            numbering_state,
            progress_cb,
            paper_id=paper_id,
            conv_id=conv_id,
            user_id=user_id,
            language=language or "id",
        )
        sections.append(section)
        partial["sections"] = sections
        # Dynamic progress: 10% for outline, 80% distributed across sections, 10% for refs
        section_progress = 10 + int(80 * i / num_sections)
        _checkpoint(chunk_id, section_progress)

    # ── Chunk 7: References ──────────────────────────────────────────────────
    if "references" not in done:
        _check_cancel("references")
        log.info("[7/8] Generating references...")
        references = _generate_references(
            outline,
            sections,
            style,
            _api_key,
            _base_url,
            _model,
            custom_prompt=custom_prompt,
            progress_cb=progress_cb,
            paper_id=paper_id,
            conv_id=conv_id,
            user_id=user_id,
            language=language or "id",
        )
        partial["references"] = references
        _checkpoint("references", 90)
    else:
        references = partial.get("references") or []
        log.info("[7/8] references already done — skipping")

    # ── Chunk 8: Combine ─────────────────────────────────────────────────────
    _check_cancel("combine")
    log.info("[8/8] Combining...")

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
            if obj.get("id") == item_type:
                collection.append(obj)
            for value in obj.values():
                extract_items(value, item_type, collection)
        elif isinstance(obj, list):
            for item in obj:
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
    log.info("[generate_paper_json_chunked] Completed in %.1fs", elapsed)

    return paper_json
