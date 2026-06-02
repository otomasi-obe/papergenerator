#!/usr/bin/env python3
"""
End-to-end terminal paper generation → IEEE DOCX.

Combines:
  * the full-text workflow_state answers (scenario 30, proven by
    test_full_workflow_e2e.py)
  * real author data
  * SLR reference material extracted from a real PDF
  * the production prompt (prompt/prompt.txt) + humanize (prompt/humanize.txt)
    + IEEE citation style guide
  * the production single-shot generator generate_paper_json_single()
  * the production IEEE template builder (templates/IEEEgen.build_document)

No Flask / DB is required: paper_id/user_id are left None and all context is
inlined into custom_prompt, exactly the way chat_tools._generate_full_paper
assembles it.

Usage:
    python generate_ieee_e2e.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND.parent / ".env")
except ImportError:
    pass

# ── 1. Full-text workflow answers (from the proven scenario-30 run) ──────────
WORKFLOW_ANSWERS = {
    "progress_level": "Masih ide/konsep",
    "data_readiness": "Belum ada",
    "team_size": "Individu (tugas akhir)",
    "field": "Ilmu Komputer & IT",
    "paper_type": "Research Paper",
    "target_publication": "Jurnal Scopus",
    "title": "Deep Learning untuk Prediksi Mortalitas Pasien ICU Menggunakan Data EHR Multivariate",
    "topic": "Prediksi mortalitas pasien ICU menggunakan rekam medis elektronik",
    "problem_statement": "Model tradisional tidak bisa tangani data time-series multivariate ICU",
    "research_gap": "Belum ada model yang gabungkan LSTM dan attention untuk ICU lokal Indonesia",
    "research_questions": "Bagaimana LSTM-Attention meningkatkan akurasi prediksi mortalitas ICU?",
    "objectives": "Bandingkan LSTM, GRU, Transformer pada dataset MIMIC-III",
    "keywords": "ICU mortality prediction, deep learning, EHR, LSTM, attention mechanism",
    "methodology_approach": "Kuantitatif",
    "specific_method": "LSTM dengan self-attention dan dropout regularization",
    "data_source": "MIMIC-III critical care database (PhysioNet)",
    "sample_size": "53.000 pasien ICU, 17 variabel vital sign + lab",
    "tools": "Python, TensorFlow, scikit-learn, pandas",
    "ethics": "Tidak perlu etik",
    "template": "IMRAD (Research Paper)",
    "complexity": "Tinggi (Scopus Q3-Q4)",
    "section_count": "5 bab (IMRAD standar)",
    "priority_sections": "Discussion - implikasi dan kontribusi",
    "outline": "Introduction, Related Work, Methodology, Experiments, Conclusion",
    "citation_style": "IEEE (Teknik, CS)",
    "reference_count": "40-60",
    "key_papers": "Paper kunci: Harutyunyan et al. 2019 MIMIC benchmarks",
    "reference_years": "5 tahun terakhir",
    "reference_tool": "Zotero",
    "visualization_type": "Tabel statistik deskriptif",
    "figure_count": "5-8 total",
    "data_format": "CSV",
    "visualization_platform": "matplotlib/Seaborn",
    "language": "Inggris",
    "writing_tone": "Formal akademik baku",
    "voice_style": "Pasif voice (scientific standard)",
    "priority": "Kualitas (rapi dari awal)",
    "plagiarism_check": "Ya, otomatis",
    "authors": "Ahmad Fauzan, Muhammad Rizky",
    "statements": "Tidak ada konflik kepentingan, data MIMIC-III sudah licensed",
    "budget": "Rp 0 (tugas akhir, no APC)",
    "timeline": "2-4 minggu",
    "reviewer": "Rekan sejawat",
    "final_format": "DOCX (template jurnal)",
}

# ── 2. Real author data ──────────────────────────────────────────────────────
REAL_AUTHORS = [
    {
        "name": "Ahmad Fauzan",
        "affiliation": "Department of Informatics, Institut Teknologi Sepuluh Nopember",
        "location": "Surabaya, Indonesia",
        "email": "ahmad.fauzan@its.ac.id",
    },
    {
        "name": "Muhammad Rizky",
        "affiliation": "Department of Informatics, Institut Teknologi Sepuluh Nopember",
        "location": "Surabaya, Indonesia",
        "email": "m.rizky@its.ac.id",
    },
]

# ── 3. SLR reference PDF (real file on disk) ─────────────────────────────────
SLR_PDF = BACKEND / "data/uploads/fb43769e6867/files/5286329f07d3410b8a5fd422abdaf78c.pdf"


def _extract_slr_text() -> str:
    try:
        from paper_generation.extract_pdfs import _extract_filtered_text
        pages, _ = _extract_filtered_text(str(SLR_PDF))
        return "\n".join(p for p in pages if p)[:4000]
    except Exception as e:
        return f"(SLR extraction failed: {e})"


def _format_workflow_block() -> str:
    a = WORKFLOW_ANSWERS
    lines = ["## RESEARCH DESIGN CONTEXT (from workflow questionnaire — source of truth)", ""]
    for k, label in [
        ("field", "Research field"),
        ("paper_type", "Paper type"),
        ("target_publication", "Target publication"),
        ("topic", "Topic"),
        ("problem_statement", "Problem statement"),
        ("research_gap", "Research gap"),
        ("research_questions", "Research questions"),
        ("objectives", "Objectives"),
        ("keywords", "Keywords"),
        ("methodology_approach", "Methodology approach"),
        ("specific_method", "Specific method"),
        ("data_source", "Data source"),
        ("sample_size", "Sample size"),
        ("tools", "Tools"),
        ("template", "Structure template"),
        ("complexity", "Complexity target"),
        ("outline", "Outline"),
        ("citation_style", "Citation style"),
        ("reference_count", "Target reference count"),
        ("language", "Output language"),
        ("writing_tone", "Writing tone"),
        ("voice_style", "Voice"),
    ]:
        if a.get(k):
            lines.append(f"- {label}: {a[k]}")
    return "\n".join(lines)


def _build_custom_prompt() -> str:
    parts = [_format_workflow_block()]

    # Authors block
    auth_lines = ["## AUTHORS (use exactly these, in this order)"]
    for au in REAL_AUTHORS:
        auth_lines.append(
            f"- {au['name']}, {au['affiliation']}, {au['location']}, {au['email']}"
        )
    parts.append("\n".join(auth_lines))

    # Reference documents block — presence of [REFERENCE DOCUMENTS] makes the
    # single-shot generator skip its own DB file load.
    slr = _extract_slr_text()
    parts.append(
        "[REFERENCE DOCUMENTS]\n"
        "The following is extracted source material to ground the paper "
        "(treat as background/SLR reference):\n\n" + slr
    )

    # Output settings
    parts.append(
        "## Output settings\n"
        "- CITATION STYLE: IEEE (numeric [1], [2] in-text; IEEE reference list).\n"
        "- OUTPUT LANGUAGE: English.\n"
        "\n## CRITICAL COMPLETENESS CONSTRAINTS (must obey to fit token budget)\n"
        "- Return a COMPLETE, well-formed JSON object. It MUST include the "
        "`references` array as the LAST key, populated with 6-10 IEEE-formatted "
        "entries. Never stop before the references list is closed.\n"
        "- Produce EXACTLY 5 main sections: Introduction, Related Work, "
        "Methodology, Results and Discussion, Conclusion.\n"
        "- Keep prose concise: 2-3 short paragraphs per section (and per "
        "subsection). Prioritise structural completeness over length so the "
        "whole paper, including references, fits within the output budget.\n"
        "- Include at most 2 figures and 2 tables total."
    )
    return "\n\n".join(parts)


def main() -> int:
    from paper_generation.chunked import generate_paper_json_chunked

    title = WORKFLOW_ANSWERS["title"]
    custom_prompt = _build_custom_prompt()

    out_dir = BACKEND / "output" / "terminal_e2e"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("STEP 1 — Generate paper JSON (chunked: per-section + references)")
    print("=" * 64)
    print(f"Title       : {title}")
    print(f"custom_prompt: {len(custom_prompt)} chars")
    print(f"SLR PDF      : {SLR_PDF.name} (exists={SLR_PDF.exists()})")
    print("Calling chunked generator (per-section calls; takes several min)...")

    def _progress(stage, progress, partial):
        try:
            nsec = len(partial.get("sections", []) or [])
            nref = len(partial.get("references", []) or [])
            print(f"    · checkpoint {stage:12s} {progress:3d}%  "
                  f"(sections={nsec} refs={nref})")
        except Exception:
            pass

    t0 = time.time()
    paper = generate_paper_json_chunked(
        judul=title,
        custom_prompt=custom_prompt,
        style="IEEE",
        checkpoint_cb=_progress,
    )
    elapsed = time.time() - t0

    # Force the real author data into the paper (don't trust placeholder).
    paper["authors"] = REAL_AUTHORS
    if not (paper.get("title") or "").strip():
        paper["title"] = title
    paper["journal"] = "IEEE"

    json_path = out_dir / "paper.json"
    json_path.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")

    n_sections = len(paper.get("sections", []))
    n_refs = len(paper.get("references", []))
    print(f"\n✓ Generated in {elapsed:.1f}s | sections={n_sections} "
          f"refs={n_refs} abstract={len(paper.get('abstract',''))} chars")
    print(f"  paper.json → {json_path}")

    print("\n" + "=" * 64)
    print("STEP 2 — Export to IEEE DOCX (templates/IEEEgen.build_document)")
    print("=" * 64)

    from exports.docx_exporter import DOCXExporter

    exporter = DOCXExporter(template="IEEE")
    docx_path = out_dir / "paper_IEEE.docx"
    info = exporter.export_with_template_info(paper, docx_path, template_override="IEEE")

    print(f"✓ DOCX written")
    print(f"  path  : {info['path']}")
    print(f"  size  : {info['size']:,} bytes")
    print(f"  format: {info['format']} | template: {info.get('template')}")

    ok = Path(info["path"]).exists() and info["size"] > 0
    print("\n" + "=" * 64)
    print("✓ END-TO-END SUCCESS" if ok else "✗ END-TO-END FAILED")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
