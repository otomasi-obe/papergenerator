"""
PaperFull - Full Paper Generation Tool
========================================
Program utama untuk generate paper lengkap dari prompt.
Menggunakan prompt dari tools/paperfull/prompt/
Memanggil editor/chunked.py atau editor/single.py sesuai mode.

Fitur:
- Generate paper dari topik/judul
- Support topic + citation style + mode (single/chunked)
- Memanggil AI API untuk generate
- Simpan hasil ke user storage
- Export ke DOCX via tools/Journal templates
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Base paths
BASE_DIR = Path(__file__).parent
PROMPT_DIR = BASE_DIR / "prompt"
BACKEND_DIR = BASE_DIR.parent
JOURNAL_DIR = BASE_DIR.parent.parent / "tools" / "Journal"

# Prompt file paths (single unified files, language injected at runtime)
PROMPT_FILE = PROMPT_DIR / "prompt.txt"
HUMANIZE_FILE = PROMPT_DIR / "humanize.txt"


def get_available_styles():
    """Dapatkan daftar style yang tersedia."""
    style_dir = PROMPT_DIR / "style"
    if not style_dir.exists():
        return []
    return sorted(p.stem for p in style_dir.glob("*.txt") if not p.stem.startswith("_"))


def get_available_topics():
    """Dapatkan daftar topik yang tersedia."""
    topic_dir = PROMPT_DIR / "topic"
    if not topic_dir.exists():
        return []
    return sorted(p.stem for p in topic_dir.glob("*.txt") if not p.stem.startswith("_"))


def get_available_journals():
    """Dapatkan daftar template jurnal yang tersedia."""
    codes = []
    if JOURNAL_DIR.exists():
        for docx_path in JOURNAL_DIR.glob("*.docx"):
            code = docx_path.stem
            gen_path = JOURNAL_DIR / f"{code}gen.py"
            if gen_path.exists():
                codes.append(code)
    return sorted(set(codes), key=str.lower)


def load_system_prompt(language: str = "id"):
    """Load system prompt (single unified file, language injected at runtime)."""
    if PROMPT_FILE.exists():
        content = PROMPT_FILE.read_text(encoding="utf-8")
        if language == "en":
            return f"⚠️ LANGUAGE: This paper MUST be written ENTIRELY in ENGLISH.\n\n{content}"
        else:
            return f"⚠️ BAHASA: Paper ini WAJIB ditulis SELURUHNYA dalam BAHASA INDONESIA.\n\n{content}"
    log.warning("System prompt not found at %s", PROMPT_FILE)
    return ""


def load_humanize_prompt(language: str = "id"):
    """Load humanizer prompt (single unified file)."""
    if HUMANIZE_FILE.exists():
        return HUMANIZE_FILE.read_text(encoding="utf-8")
    log.warning("Humanize prompt not found at %s", HUMANIZE_FILE)
    return ""


def load_style_guide(style_slug: str) -> Optional[str]:
    """Load citation style guide."""
    style_file = PROMPT_DIR / "style" / f"{style_slug}.txt"
    if style_file.exists():
        return style_file.read_text(encoding="utf-8")
    return None


def load_topic_guide(topic_slug: str) -> Optional[str]:
    """Load topic guide."""
    topic_file = PROMPT_DIR / "topic" / f"{topic_slug}.txt"
    if topic_file.exists():
        return topic_file.read_text(encoding="utf-8")
    return None


def generate_paper(
    judul: str,
    topic: Optional[str] = None,
    style: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    paper_id: Optional[str] = None,
    conv_id: Optional[str] = None,
    job_id: Optional[str] = None,
    user_id: Optional[int] = None,
    mode: str = "single",
    language: str = "id",
    checkpoint_fn=None,
    cancel_fn=None,
):
    """
    Generate paper lengkap.

    Args:
        judul: Topik/judul paper
        topic: Slug topik guide (opsional)
        style: Slug citation style (opsional)
        custom_prompt: Prompt tambahan
        paper_id: ID paper (untuk integrasi)
        conv_id: ID conversation (untuk logging)
        job_id: ID job (untuk progress tracking)
        user_id: ID user
        mode: "single" atau "chunked"
        language: "id" untuk Bahasa Indonesia, "en" untuk English
        checkpoint_fn: Callback fn(stage, progress) untuk progress
        cancel_fn: Callback fn() -> bool untuk cek cancel

    Returns:
        dict: Paper data dalam format JSON standar
    """
    from tools.editor.single import generate_paper_json_single
    from tools.editor.chunked import generate_paper_json_chunked, GenerationCancelled

    log.info("generate_full: mode=%s, judul=%r, topic=%s, style=%s", mode, judul[:60], topic, style)

    # Build extra context
    extra_parts = []
    if custom_prompt:
        extra_parts.append(custom_prompt)

    topic_guide = load_topic_guide(topic) if topic else None
    if topic_guide:
        extra_parts.append(f"[TOPIC GUIDE]\n{topic_guide}")

    style_guide = load_style_guide(style) if style else None
    if style_guide:
        extra_parts.append(f"[CITATION STYLE GUIDE]\n{style_guide}")

    extra = "\n\n".join(extra_parts).strip()

    t_start = time.time()

    if mode == "chunked":
        # Map external callback names to chunked's expected names
        def _checkpoint_cb(stage, progress, partial):
            if checkpoint_fn:
                checkpoint_fn(stage, progress)

        def _cancel_check():
            if cancel_fn:
                return cancel_fn()
            return False

        paper_data = generate_paper_json_chunked(
            judul=judul,
            custom_prompt=extra,
            topic=topic,
            style=style,
            language=language,
            paper_id=paper_id,
            conv_id=conv_id,
            user_id=user_id,
            checkpoint_cb=_checkpoint_cb,
            cancel_check=_cancel_check,
        )
    else:
        if cancel_fn and cancel_fn():
            raise GenerationCancelled("start")
        paper_data = generate_paper_json_single(
            judul=judul,
            custom_prompt=extra,
            topic=topic,
            style=style,
            language=language,
            paper_id=paper_id,
            conv_id=conv_id,
            job_id=job_id,
            user_id=user_id,
        )

    elapsed = time.time() - t_start
    log.info("generate_full: DONE in %.1fs", elapsed)

    # ── Post-process: fix mojibake + clean LaTeX artifacts ────
    from tools.paperfull.text_cleaner import clean_paper_data
    paper_data = clean_paper_data(paper_data)
    log.info("[paperfull] Applied mojibake fix + LaTeX cleanup to paper_data")

    # ── Post-process: programmatic humanization (anti-Turnitin) ────
    try:
        from tools.humanizer.humanizer import TextHumanizer
        _humanizer = TextHumanizer()
        
        def _humanize_text(text):
            """Run programmatic humanizer on a text string (no LLM, fast)."""
            if not isinstance(text, str) or not text.strip():
                return text
            return _humanizer.humanize_program(text, option="Standard", intensity="medium")
        
        def _humanize_paper_data(data):
            """Recursively humanize all text content fields in paper data.
            
            Skips structural fields (authors, references metadata, figure/table
            captions are included since they're prose).
            """
            if isinstance(data, dict):
                result = {}
                for k, v in data.items():
                    # Skip reference metadata, author info, structural fields
                    if k in ('doi', 'url', 'year', 'volume', 'issue', 'pages',
                             'email', 'affiliation', 'institution', 'city',
                             'country', 'location', 'index', 'type', 'format',
                             'file', 'caption_ref', 'source'):
                        result[k] = v
                    else:
                        result[k] = _humanize_paper_data(v)
                return result
            elif isinstance(data, list):
                return [_humanize_paper_data(item) for item in data]
            elif isinstance(data, str):
                # Only humanize text longer than 20 words (skip labels, short metadata)
                if len(data.split()) > 20:
                    return _humanize_text(data)
                return data
            return data
        
        paper_data = _humanize_paper_data(paper_data)
        log.info("generate_full: post-generation humanization applied (programmatic)")
    except ImportError as e:
        log.warning("generate_full: humanizer not available, skipping post-processing: %s", e)
    except Exception as e:
        log.warning("generate_full: humanization failed, continuing without it: %s", e)

    # Ensure defaults
    paper_data.setdefault("authors", [{
        "name": "Author Name",
        "affiliation": "Department, University",
        "location": "City, Country",
        "email": "author@example.com",
    }])
    paper_data.setdefault("keywords", [])
    paper_data.setdefault("sections", [])
    paper_data.setdefault("acknowledgment", "")
    paper_data.setdefault("references", [])
    paper_data.setdefault("figures", [])
    paper_data.setdefault("tables", [])
    paper_data.setdefault("equations", [])

    return paper_data


def export_docx(paper_data: dict, journal_code: str = "IEEE", citation_style: Optional[str] = None) -> Optional[Path]:
    """
    Export paper ke DOCX menggunakan template jurnal.

    Args:
        paper_data: Paper data dict
        journal_code: Kode template jurnal (IEEE, APA, dll)
        citation_style: Citation style slug untuk memformat referensi
                        (ieee, apa, harvard, chicago, vancouver, mla, acs).
                        Jika None, default ke journal_code.lower().

    Returns:
        Path ke file DOCX yang dihasilkan
    """
    import importlib
    import tempfile

    available = get_available_journals()
    m = {c.lower(): c for c in available}
    canonical = m.get(journal_code.lower())
    if not canonical:
        log.error("Unknown journal template: %s (available: %s)", journal_code, available)
        return None

    try:
        mod = importlib.import_module(f"tools.Journal.{canonical}gen")
    except ImportError as e:
        log.error("Failed to import template %sgen: %s", canonical, e)
        return None

    builder = getattr(mod, "build_document", None)
    if not callable(builder):
        gen_fn = getattr(mod, "generate", None)
        if callable(gen_fn):
            from main import _make_generate_adapter  # noqa: E402  # lazy import
            builder = _make_generate_adapter(mod, gen_fn)
        else:
            log.error("Template generator missing build_document/generate: %sgen", canonical)
            return None

    # Pre-process structured references into formatted strings
    # so generators that expect string references continue to work.
    paper_data = _preprocess_references(paper_data, citation_style or journal_code.lower())

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(paper_data, f, ensure_ascii=False, indent=2)
        json_path = Path(f.name)

    try:
        output_path = json_path.with_suffix(".docx")
        builder(json_path, output_path)
        log.info("Exported DOCX: %s", output_path)
        return output_path
    except Exception as e:
        log.error("Export failed: %s", e)
        return None
    finally:
        json_path.unlink(missing_ok=True)


def _preprocess_references(paper_data: dict, style: str) -> dict:
    """Convert structured reference objects into formatted strings.

    If references are already strings (legacy format), returns paper_data unchanged.
    This ensures backward compatibility with all journal generators.
    """
    refs = paper_data.get("references", [])

    # Handle dict-wrapped references (new format: {"title": "...", "items": [...]})
    if isinstance(refs, dict):
        items = refs.get("items", refs.get("content", []))
    elif isinstance(refs, list):
        items = refs
    else:
        return paper_data

    # If items are already strings, nothing to do
    if not items or not isinstance(items[0], dict):
        return paper_data

    # Check if items are structured objects (have "authors", "title", etc.)
    # vs. already-formatted dicts with a "text" key
    first = items[0]
    if "text" in first and "authors" not in first:
        return paper_data  # Already formatted dict with "text" key

    # Format structured objects into strings
    try:
        from tools.preview.reference_formatter import format_reference
        formatted = []
        for i, ref in enumerate(items, 1):
            if isinstance(ref, dict) and "authors" in ref:
                formatted.append(format_reference(ref, style=style, index=i))
            elif isinstance(ref, dict) and "text" in ref:
                formatted.append(ref["text"])
            elif isinstance(ref, str):
                formatted.append(ref)
            else:
                formatted.append(str(ref))
        paper_data["references"] = formatted
    except ImportError:
        log.warning("reference_formatter not available, keeping raw references")

    return paper_data


if __name__ == "__main__":
    """CLI: python -m tools.paperfull.generate_full "judul paper" [topic] [style] [single|chunked]"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m tools.paperfull.generate_full 'judul paper' [topic] [style] [mode]")
        print(f"  Topics: {get_available_topics()}")
        print(f"  Styles: {get_available_styles()}")
        print(f"  Journals: {get_available_journals()}")
        sys.exit(1)

    judul = sys.argv[1]
    topic = sys.argv[2] if len(sys.argv) > 2 else None
    style = sys.argv[3] if len(sys.argv) > 3 else None
    mode = sys.argv[4] if len(sys.argv) > 4 else "single"

    result = generate_paper(judul=judul, topic=topic, style=style, mode=mode)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
