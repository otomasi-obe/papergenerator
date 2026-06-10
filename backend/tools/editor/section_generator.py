"""
Section-Based Paper Generation
===============================
Generate or regenerate individual paper sections independently.

Supports:
- Generate single section (Introduction, Methods, Results, etc.)
- Regenerate existing section with different parameters
- Section-aware context (uses other sections as context)
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from utils.core.env_loader import load_app_env
from utils.ai_tools.model_config import get_primary_generate_model
from tools.editor.api_client import _call_aiotomasi_with_fallback

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
load_app_env()

AIOTOMASI_API = os.getenv("AIOTOMASI_API")
AIOTOMASI_APIKEY = os.getenv("AIOTOMASI_APIKEY")
AIOTOMASI_MODEL = get_primary_generate_model()

PROMPT_FILE = BASE_DIR.parent / "paperfull" / "prompt" / "prompt.txt"
HUMANIZE_FILE = BASE_DIR.parent / "tools" / "paperfull" / "prompt" / "humanize.txt"


SECTION_NAMES = {
    "abstract": "Abstract",
    "introduction": "Introduction",
    "related_work": "Related Work / Literature Review",
    "methodology": "Methodology / Methods",
    "results": "Results / Findings",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
}


def generate_section(
    section_name: str,
    paper_context: Dict,
    custom_instructions: str = "",
    api_key: str = None,
    base_url: str = None,
    model: str = None,
    progress_cb=None,
) -> Dict:
    """Generate a single paper section.
    
    Args:
        section_name: Section to generate (introduction, methodology, results, etc.)
        paper_context: Context dict with:
            - title: Paper title
            - abstract: Paper abstract (if available)
            - existing_sections: List of already-generated sections
            - literature: Literature catalog
            - workflow_context: Workflow answers context
        custom_instructions: Additional generation instructions
        api_key: API key (falls back to env)
        base_url: API base URL (falls back to env)
        model: Model name (falls back to env)
        progress_cb: Progress callback
        
    Returns:
        Section dict matching prompt.txt schema
    """
    _api_key = api_key or AIOTOMASI_APIKEY
    _base_url = base_url or AIOTOMASI_API
    _model = model or AIOTOMASI_MODEL
    
    if not _api_key or not _base_url:
        raise ValueError("API key and base URL required")
    
    if section_name not in SECTION_NAMES:
        raise ValueError(f"Invalid section name: {section_name}")
    
    # Load base prompts
    base_prompt = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else ""
    humanize_rules = HUMANIZE_FILE.read_text(encoding="utf-8") if HUMANIZE_FILE.exists() else ""
    
    # Build system prompt
    system_prompt = f"""{base_prompt}

{humanize_rules}

CURRENT TASK: Generate ONLY the {SECTION_NAMES[section_name]} section.

PAPER CONTEXT:
Title: {paper_context.get('title', 'Untitled')}
Abstract: {paper_context.get('abstract', '(not yet written)')}

"""
    
    # Add existing sections as context
    existing = paper_context.get("existing_sections", [])
    if existing:
        system_prompt += "\nEXISTING SECTIONS (for context and consistency):\n"
        for sec in existing:
            sec_title = sec.get("title", "Section")
            sec_content = sec.get("content", [])
            # Extract first paragraph as summary
            if sec_content and isinstance(sec_content, list):
                first_para = sec_content[0].get("text", "")[:300] if isinstance(sec_content[0], dict) else ""
                system_prompt += f"\n**{sec_title}**: {first_para}...\n"
    
    # Add literature catalog
    if paper_context.get("literature"):
        system_prompt += f"\n{paper_context['literature']}\n"
    
    # Add workflow context
    if paper_context.get("workflow_context"):
        system_prompt += f"\n{paper_context['workflow_context']}\n"
    
    system_prompt += f"""
Return ONLY the JSON object for the {section_name} section following the schema from the base prompt.
Include appropriate subsections, figures, tables, and citations.
"""
    
    # Build user message
    user_message = f"""Generate the {SECTION_NAMES[section_name]} section for this paper.

Title: {paper_context.get('title', 'Untitled')}

{custom_instructions if custom_instructions else ''}

Return ONLY the JSON object for this section, no markdown fences."""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    
    log.info("[generate_section] Generating %s", section_name)
    
    from utils.core.retry_helper import get_retry_config
    _, timeout = get_retry_config()
    
    raw_content, model_used = _call_aiotomasi_with_fallback(
        messages, _api_key, _base_url, _model, timeout=timeout, progress_cb=progress_cb
    )
    
    log.info("[generate_section] %s completed using model=%s", section_name, model_used)
    
    # Parse response
    from tools.editor.chunked import _parse_json_response
    section_data = _parse_json_response(raw_content)
    
    return section_data


def regenerate_section(
    section_index: int,
    paper_data: Dict,
    regeneration_instructions: str,
    api_key: str = None,
    base_url: str = None,
    model: str = None,
    progress_cb=None,
) -> Dict:
    """Regenerate an existing section with new instructions.
    
    Args:
        section_index: Index of section to regenerate (0-based)
        paper_data: Full paper data dict
        regeneration_instructions: Instructions for regeneration (e.g., "make it more technical", "add more citations")
        api_key: API key
        base_url: API base URL
        model: Model name
        progress_cb: Progress callback
        
    Returns:
        New section dict
    """
    sections = paper_data.get("sections", [])
    if section_index < 0 or section_index >= len(sections):
        raise ValueError(f"Invalid section index: {section_index}")
    
    old_section = sections[section_index]
    section_title = old_section.get("title", f"Section {section_index + 1}")
    
    # Build context from other sections
    other_sections = [s for i, s in enumerate(sections) if i != section_index]
    
    paper_context = {
        "title": paper_data.get("title", ""),
        "abstract": paper_data.get("abstract", ""),
        "existing_sections": other_sections,
    }
    
    custom_instructions = f"""REGENERATION REQUEST:
Original section: {section_title}

User feedback: {regeneration_instructions}

Please regenerate this section incorporating the feedback while maintaining consistency with other sections.
"""
    
    # Map section title to section name
    section_name = _infer_section_name(section_title)
    
    return generate_section(
        section_name,
        paper_context,
        custom_instructions,
        api_key,
        base_url,
        model,
        progress_cb,
    )


def _infer_section_name(section_title: str) -> str:
    """Infer section name from title.
    
    Args:
        section_title: Section title string
        
    Returns:
        Section name key (introduction, methodology, etc.)
    """
    title_lower = section_title.lower()
    
    if "introduction" in title_lower or "pendahuluan" in title_lower:
        return "introduction"
    elif "related" in title_lower or "literature" in title_lower or "tinjauan" in title_lower:
        return "related_work"
    elif "method" in title_lower or "metod" in title_lower:
        return "methodology"
    elif "result" in title_lower or "hasil" in title_lower or "finding" in title_lower:
        return "results"
    elif "discussion" in title_lower or "pembahasan" in title_lower:
        return "discussion"
    elif "conclusion" in title_lower or "kesimpulan" in title_lower:
        return "conclusion"
    else:
        return "introduction"  # Default fallback
