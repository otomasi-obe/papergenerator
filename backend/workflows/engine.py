"""
Workflow Engine for Paper Builder
==================================
Implements the 9-phase questionnaire system from Doc/worflowQuestion.md

Each phase has questions with 4 AI recommendations + 1 custom input.
Questions are connected - later questions depend on earlier answers.
"""

from typing import Any, Dict, List, Optional

import json
import re

WORKFLOW_PHASES = {
    "0": {
        "name": "Pre-Questionnaire — Status Awal",
        "description": "Onboarding cepat. Menentukan entry point & progress yang sudah ada.",
        "questions": [
            {
                "id": "0.1",
                "question": "Sejauh mana progress paper Anda?",
                "key": "progress_level",
                "options": [
                    {"label": "Masih ide/konsep", "value": "A"},
                    {"label": "Sudah ada judul & outline", "value": "B"},
                    {"label": "Sudah ada draft sebagian", "value": "C"},
                    {"label": "Draft hampir selesai", "value": "D"},
                ],
                "depends_on": [],
            },
            {
                "id": "0.2",
                "question": "Sudah punya data/hasil eksperimen?",
                "key": "data_readiness",
                "options": [
                    {"label": "Belum ada", "value": "A"},
                    {"label": "Ada data mentah", "value": "B"},
                    {"label": "Ada hasil olahan", "value": "C"},
                    {"label": "Hasil final sudah siap", "value": "D"},
                ],
                "depends_on": ["0.1"],
            },
            {
                "id": "0.3",
                "question": "Ini paper individu atau tim?",
                "key": "team_size",
                "options": [
                    {"label": "Individu (tugas akhir)", "value": "A"},
                    {"label": "Tim 2-3 orang", "value": "B"},
                    {"label": "Tim 4-5 orang", "value": "C"},
                    {"label": "Kolaborasi lintas institusi", "value": "D"},
                ],
                "depends_on": [],
            },
        ],
    },
    "1": {
        "name": "Profil Dasar Paper",
        "description": "Menentukan identitas dasar paper.",
        "questions": [
            {
                "id": "1.1",
                "question": "Bidang ilmu?",
                "key": "field",
                "options": [
                    {"label": "Ilmu Komputer & IT", "value": "A"},
                    {"label": "Teknik & Rekayasa", "value": "B"},
                    {"label": "Kedokteran & Kesehatan", "value": "C"},
                    {"label": "Sosial & Humaniora", "value": "D"},
                    {"label": "Ekonomi, Bisnis & Manajemen", "value": "E"},
                    {"label": "Sains & MIPA (Matematika, Fisika, Kimia, Biologi)", "value": "F"},
                    {"label": "Pertanian, Peternakan & Kehutanan", "value": "G"},
                    {"label": "Pendidikan & Keguruan", "value": "H"},
                    {"label": "Hukum & Ilmu Politik", "value": "I"},
                    {"label": "Seni, Desain & Budaya", "value": "J"},
                    {"label": "Psikologi", "value": "K"},
                    {"label": "Komunikasi & Media", "value": "L"},
                    {"label": "Lingkungan & Kebumian", "value": "M"},
                    {"label": "Farmasi & Bioteknologi", "value": "N"},
                ],
                "depends_on": [],
            },
            {
                "id": "1.2",
                "question": "Jenis paper?",
                "key": "paper_type",
                "options": [
                    {"label": "Literature Review", "value": "A"},
                    {"label": "Research Paper", "value": "B"},
                    {"label": "Case Study", "value": "C"},
                    {"label": "Systematic Review", "value": "D"},
                ],
                "depends_on": ["1.1"],
            },
            {
                "id": "1.3",
                "question": "Target publikasi?",
                "key": "target_publication",
                "options": [
                    {"label": "Tugas Akhir / Skripsi / Tesis", "value": "A"},
                    {"label": "Jurnal Sinta 2-6", "value": "B"},
                    {"label": "Jurnal Sinta 1", "value": "C"},
                    {"label": "Jurnal Scopus", "value": "D"},
                ],
                "depends_on": ["1.1", "1.2"],
            },
            {
                "id": "1.4",
                "question": "Judul paper (bisa provisional)?",
                "key": "title",
                "options": [],
                "depends_on": ["1.1", "1.2", "1.3"],
                "ai_generated": True,
            },
        ],
    },
    "2": {
        "name": "Topik & Research Gap",
        "description": "Menggali fokus riset secara mendalam.",
        "questions": [
            {
                "id": "2.1",
                "question": "Topik spesifik?",
                "key": "topic",
                "options": [],
                "depends_on": ["1.1", "1.4"],
                "ai_generated": True,
            },
            {
                "id": "2.2",
                "question": "Problem statement?",
                "key": "problem_statement",
                "options": [],
                "depends_on": ["2.1"],
                "ai_generated": True,
            },
            {
                "id": "2.3",
                "question": "Research gap — apa yang belum dijawab?",
                "key": "research_gap",
                "options": [],
                "depends_on": ["2.1", "2.2"],
                "ai_generated": True,
            },
            {
                "id": "2.4",
                "question": "Research question(s)?",
                "key": "research_questions",
                "options": [],
                "depends_on": ["2.2", "2.3"],
                "ai_generated": True,
            },
            {
                "id": "2.5",
                "question": "Tujuan penelitian?",
                "key": "objectives",
                "options": [],
                "depends_on": ["2.3", "2.4"],
                "ai_generated": True,
            },
            {
                "id": "2.6",
                "question": "Keywords?",
                "key": "keywords",
                "options": [],
                "depends_on": ["2.1", "2.4"],
                "ai_generated": True,
            },
        ],
    },
    "3": {
        "name": "Metodologi & Data",
        "description": "Menentukan pendekatan dan teknis penelitian.",
        "questions": [
            {
                "id": "3.1",
                "question": "Pendekatan penelitian?",
                "key": "methodology_approach",
                "options": [
                    {"label": "Kuantitatif", "value": "A"},
                    {"label": "Kualitatif", "value": "B"},
                    {"label": "Mixed-Method", "value": "C"},
                    {"label": "R&D (Research & Development)", "value": "D"},
                ],
                "depends_on": ["1.1", "1.2", "2.4"],
            },
            {
                "id": "3.2",
                "question": "Metode spesifik?",
                "key": "specific_method",
                "options": [],
                "depends_on": ["3.1", "2.1"],
                "ai_generated": True,
            },
            {
                "id": "3.3",
                "question": "Sumber data?",
                "key": "data_source",
                "options": [],
                "depends_on": ["3.1", "3.2"],
                "ai_generated": True,
            },
            {
                "id": "3.4",
                "question": "Jumlah sampel / dataset?",
                "key": "sample_size",
                "options": [],
                "depends_on": ["3.1", "3.2", "1.1"],
                "ai_generated": True,
            },
            {
                "id": "3.5",
                "question": "Tools?",
                "key": "tools",
                "options": [],
                "depends_on": ["3.2", "1.1"],
                "ai_generated": True,
            },
            {
                "id": "3.6",
                "question": "Etika penelitian?",
                "key": "ethics",
                "options": [
                    {"label": "Tidak perlu etik", "value": "A"},
                    {"label": "Butuh ethical clearance (institusi)", "value": "B"},
                    {"label": "Butuh informed consent", "value": "C"},
                    {"label": "Butuh keduanya", "value": "D"},
                ],
                "depends_on": ["3.1", "3.3", "1.1"],
            },
        ],
    },
    "4": {
        "name": "Struktur & Konten Paper",
        "description": "Menentukan kerangka dan kedalaman konten.",
        "questions": [
            {
                "id": "4.1",
                "question": "Template struktur utama?",
                "key": "template",
                "options": [
                    {"label": "IMRAD (Research Paper)", "value": "A"},
                    {"label": "IRD (Intro-Review-Discussion)", "value": "B"},
                    {"label": "Swales (Case Study)", "value": "C"},
                    {"label": "Struktur Thesis", "value": "D"},
                ],
                "depends_on": ["1.2", "1.3"],
            },
            {
                "id": "4.2",
                "question": "Kompleksitas konten?",
                "key": "complexity",
                "options": [
                    {"label": "Dasar (Tugas Akhir/Sinta 4-6)", "value": "A"},
                    {"label": "Menengah (Sinta 1-3)", "value": "B"},
                    {"label": "Tinggi (Scopus Q3-Q4)", "value": "C"},
                    {"label": "Sangat Tinggi (Scopus Q1-Q2)", "value": "D"},
                ],
                "depends_on": ["1.3", "3.1"],
            },
            {
                "id": "4.3",
                "question": "Jumlah bab/section target?",
                "key": "section_count",
                "options": [],
                "depends_on": ["4.1", "1.2"],
                "ai_generated": True,
            },
            {
                "id": "4.4",
                "question": "Bab mana yang perlu diperdalam?",
                "key": "priority_sections",
                "options": [],
                "depends_on": ["2.3", "2.4", "3.2"],
                "ai_generated": True,
            },
            {
                "id": "4.5",
                "question": "Outline detail?",
                "key": "outline",
                "options": [],
                "depends_on": ["4.1", "4.2", "4.3"],
                "ai_generated": True,
            },
        ],
    },
    "5": {
        "name": "Literatur & Sitasi",
        "description": "Membangun fondasi referensi.",
        "questions": [
            {
                "id": "5.1",
                "question": "Gaya sitasi?",
                "key": "citation_style",
                "options": [
                    {"label": "APA 7th (Sosial, Psikologi)", "value": "A"},
                    {"label": "IEEE (Teknik, CS)", "value": "B"},
                    {"label": "Vancouver (Kedokteran)", "value": "C"},
                    {"label": "Chicago (Humaniora)", "value": "D"},
                ],
                "depends_on": ["1.1"],
            },
            {
                "id": "5.2",
                "question": "Jumlah referensi target?",
                "key": "reference_count",
                "options": [
                    {"label": "15-25", "value": "A"},
                    {"label": "25-40", "value": "B"},
                    {"label": "40-60", "value": "C"},
                    {"label": "60-80+", "value": "D"},
                ],
                "depends_on": ["1.3", "4.2"],
            },
            {
                "id": "5.3",
                "question": "Key papers yang wajib disitasi?",
                "key": "key_papers",
                "options": [],
                "depends_on": ["2.1", "2.3"],
                "ai_generated": True,
            },
            {
                "id": "5.4",
                "question": "Rentang tahun referensi?",
                "key": "reference_years",
                "options": [
                    {"label": "5 tahun terakhir", "value": "A"},
                    {"label": "10 tahun terakhir", "value": "B"},
                    {"label": "Classic + terbaru", "value": "C"},
                    {"label": "Semua tahun relevan", "value": "D"},
                ],
                "depends_on": ["1.1", "2.1"],
            },
            {
                "id": "5.5",
                "question": "Tool manajemen referensi?",
                "key": "reference_tool",
                "options": [
                    {"label": "Mendeley", "value": "A"},
                    {"label": "Zotero", "value": "B"},
                    {"label": "EndNote", "value": "C"},
                    {"label": "PaperPile", "value": "D"},
                ],
                "depends_on": [],
            },
        ],
    },
    "6": {
        "name": "Data & Visualisasi",
        "description": "Conditional session based on methodology.",
        "branches": {
            "quantitative": {
                "condition": lambda answers: answers.get("methodology_approach") in ["A", "C", "Kuantitatif", "Mixed-Method"],
                "questions": [
                    {
                        "id": "6.1",
                        "question": "Jenis visualisasi utama?",
                        "key": "visualization_type",
                        "options": [
                            {"label": "Tabel statistik deskriptif", "value": "A"},
                            {"label": "Grafik batang/garis", "value": "B"},
                            {"label": "Heatmap/Confusion matrix", "value": "C"},
                            {"label": "Scatter plot/Box plot", "value": "D"},
                        ],
                        "depends_on": ["3.2", "3.4"],
                    },
                    {
                        "id": "6.2",
                        "question": "Jumlah tabel & figur target?",
                        "key": "figure_count",
                        "options": [
                            {"label": "3-5 total", "value": "A"},
                            {"label": "5-8 total", "value": "B"},
                            {"label": "8-12 total", "value": "C"},
                            {"label": ">12 total", "value": "D"},
                        ],
                        "depends_on": ["4.2"],
                    },
                    {
                        "id": "6.3",
                        "question": "Format data mentah?",
                        "key": "data_format",
                        "options": [
                            {"label": "CSV", "value": "A"},
                            {"label": "Excel", "value": "B"},
                            {"label": "JSON", "value": "C"},
                            {"label": "Database", "value": "D"},
                        ],
                        "depends_on": [],
                    },
                    {
                        "id": "6.4",
                        "question": "Platform visualisasi?",
                        "key": "visualization_platform",
                        "options": [
                            {"label": "matplotlib/Seaborn", "value": "A"},
                            {"label": "Tableau", "value": "B"},
                            {"label": "SPSS", "value": "C"},
                            {"label": "R ggplot", "value": "D"},
                        ],
                        "depends_on": ["3.5"],
                    },
                ],
            },
            "qualitative": {
                "condition": lambda answers: answers.get("methodology_approach") in ["B", "Kualitatif"],
                "questions": [
                    {
                        "id": "6.1",
                        "question": "Jenis visualisasi utama?",
                        "key": "visualization_type",
                        "options": [
                            {"label": "Thematic map", "value": "A"},
                            {"label": "Network diagram", "value": "B"},
                            {"label": "Quote matrix", "value": "C"},
                            {"label": "Timeline chart", "value": "D"},
                        ],
                        "depends_on": ["3.2", "3.3"],
                    },
                    {
                        "id": "6.2",
                        "question": "Jumlah tabel & figur target?",
                        "key": "figure_count",
                        "options": [
                            {"label": "2-4 total", "value": "A"},
                            {"label": "4-6 total", "value": "B"},
                            {"label": "6-8 total", "value": "C"},
                            {"label": ">8 total", "value": "D"},
                        ],
                        "depends_on": ["4.2"],
                    },
                    {
                        "id": "6.3",
                        "question": "Coding framework?",
                        "key": "coding_framework",
                        "options": [
                            {"label": "Deductive coding", "value": "A"},
                            {"label": "Inductive coding", "value": "B"},
                            {"label": "Hybrid", "value": "C"},
                            {"label": "Template analysis", "value": "D"},
                        ],
                        "depends_on": ["3.2"],
                    },
                    {
                        "id": "6.4",
                        "question": "Platform analisis?",
                        "key": "visualization_platform",
                        "options": [
                            {"label": "NVivo", "value": "A"},
                            {"label": "ATLAS.ti", "value": "B"},
                            {"label": "MAXQDA", "value": "C"},
                            {"label": "Dedoose", "value": "D"},
                        ],
                        "depends_on": ["3.5"],
                    },
                ],
            },
            "literature": {
                "condition": lambda answers: answers.get("paper_type") in ["A", "D", "Literature Review", "Systematic Review"],
                "questions": [
                    {
                        "id": "6.1",
                        "question": "Jenis visualisasi utama?",
                        "key": "visualization_type",
                        "options": [
                            {"label": "PRISMA flowchart", "value": "A"},
                            {"label": "Bibliometric map", "value": "B"},
                            {"label": "Synthesis matrix", "value": "C"},
                            {"label": "Concept map", "value": "D"},
                        ],
                        "depends_on": ["1.2", "2.3"],
                    },
                    {
                        "id": "6.2",
                        "question": "Jumlah tabel & figur target?",
                        "key": "figure_count",
                        "options": [
                            {"label": "3-5 total", "value": "A"},
                            {"label": "5-8 total", "value": "B"},
                            {"label": "8-10 total", "value": "C"},
                            {"label": ">10 total", "value": "D"},
                        ],
                        "depends_on": ["4.2"],
                    },
                    {
                        "id": "6.3",
                        "question": "Screening strategy?",
                        "key": "screening_strategy",
                        "options": [
                            {"label": "PRISMA 2020", "value": "A"},
                            {"label": "SWiM", "value": "B"},
                            {"label": "ENTREQ", "value": "C"},
                            {"label": "Mixed-method", "value": "D"},
                        ],
                        "depends_on": ["2.1"],
                    },
                    {
                        "id": "6.4",
                        "question": "Tool review?",
                        "key": "visualization_platform",
                        "options": [
                            {"label": "Covidence", "value": "A"},
                            {"label": "Rayyan", "value": "B"},
                            {"label": "VosViewer", "value": "C"},
                            {"label": "ASReview", "value": "D"},
                        ],
                        "depends_on": [],
                    },
                ],
            },
        },
        "questions": [],  # Legacy field, kept for backward compatibility
    },
    "7": {
        "name": "Output & Preferensi Penulisan",
        "description": "Menyesuaikan gaya dan bahasa output.",
        "questions": [
            {
                "id": "7.1",
                "question": "Bahasa?",
                "key": "language",
                "options": [
                    {"label": "Indonesia", "value": "A"},
                    {"label": "Inggris", "value": "B"},
                    {"label": "Inggris (American)", "value": "C"},
                    {"label": "Bilingual", "value": "D"},
                ],
                "depends_on": ["1.3"],
            },
            {
                "id": "7.2",
                "question": "Tone / gaya penulisan?",
                "key": "writing_tone",
                "options": [
                    {"label": "Formal akademik baku", "value": "A"},
                    {"label": "Semi-formal", "value": "B"},
                    {"label": "Kritis-argumentatif", "value": "C"},
                    {"label": "Deskriptif-ekspositori", "value": "D"},
                ],
                "depends_on": ["1.3", "1.2"],
            },
            {
                "id": "7.3",
                "question": "Spesifikasi gaya tambahan?",
                "key": "voice_style",
                "options": [
                    {"label": "Pasif voice (scientific standard)", "value": "A"},
                    {"label": "Aktif diperbolehkan", "value": "B"},
                    {"label": "First-person allowed", "value": "C"},
                    {"label": "Impersonal", "value": "D"},
                ],
                "depends_on": ["1.3"],
            },
            {
                "id": "7.4",
                "question": "Prioritas?",
                "key": "priority",
                "options": [
                    {"label": "Kecepatan (draft cepat)", "value": "A"},
                    {"label": "Kualitas (rapi dari awal)", "value": "B"},
                    {"label": "Originalitas tinggi", "value": "C"},
                    {"label": "Keseimbangan", "value": "D"},
                ],
                "depends_on": [],
            },
            {
                "id": "7.5",
                "question": "Butuh parafrase/plagiarisme checking?",
                "key": "plagiarism_check",
                "options": [
                    {"label": "Ya, otomatis", "value": "A"},
                    {"label": "Tidak, saya cek manual", "value": "B"},
                    {"label": "Nanti di tahap final", "value": "C"},
                    {"label": "Tidak perlu", "value": "D"},
                ],
                "depends_on": ["7.4"],
            },
        ],
    },
    "8": {
        "name": "Supplementary & Production Readiness",
        "description": "Hal-hal yang sering terlambat disiapkan.",
        "questions": [
            {
                "id": "8.1",
                "question": "Tim penulis & kontribusi?",
                "key": "authors",
                "options": [
                    {"label": "Single author", "value": "A"},
                    {"label": "Daftar kontribusi CRediT", "value": "B"},
                    {"label": "Equal contribution", "value": "C"},
                    {"label": "First & corresponding ditentukan", "value": "D"},
                ],
                "depends_on": ["0.3"],
            },
            {
                "id": "8.2",
                "question": "Supplementary statements?",
                "key": "statements",
                "options": [
                    {"label": "Conflict of Interest", "value": "A"},
                    {"label": "Data Availability", "value": "B"},
                    {"label": "Funding statement", "value": "C"},
                    {"label": "Semuanya", "value": "D"},
                ],
                "depends_on": ["1.3"],
            },
            {
                "id": "8.3",
                "question": "Apakah ada biaya yang perlu dianggarkan?",
                "key": "budget",
                "options": [],
                "depends_on": ["1.3", "8.2"],
                "ai_generated": True,
            },
            {
                "id": "8.4",
                "question": "Timeline & milestone?",
                "key": "timeline",
                "options": [
                    {"label": "1 minggu (sprint)", "value": "A"},
                    {"label": "2-4 minggu", "value": "B"},
                    {"label": "1-3 bulan", "value": "C"},
                    {"label": ">3 bulan", "value": "D"},
                ],
                "depends_on": ["0.1", "4.2"],
            },
            {
                "id": "8.5",
                "question": "Siapa reviewer internal?",
                "key": "reviewer",
                "options": [
                    {"label": "Dosen pembimbing", "value": "A"},
                    {"label": "Rekan sejawat", "value": "B"},
                    {"label": "Proofreader profesional", "value": "C"},
                    {"label": "Tidak ada (self-review)", "value": "D"},
                ],
                "depends_on": [],
            },
            {
                "id": "8.6",
                "question": "Format pengiriman akhir?",
                "key": "final_format",
                "options": [
                    {"label": "PDF", "value": "A"},
                    {"label": "DOCX (template jurnal)", "value": "B"},
                    {"label": "LaTeX", "value": "C"},
                    {"label": "Markdown+export", "value": "D"},
                ],
                "depends_on": ["1.3"],
            },
        ],
    },
    "9": {
        "name": "Validasi & Finalisasi",
        "description": "Cross-check menyeluruh & backward adjustment.",
        "questions": [],
    },
}

# Keys whose options are fixed (non-AI). Their full label can always be
# resolved straight from WORKFLOW_PHASES, so we never need to snapshot the
# presented options into the persisted workflow_state for them. This keeps
# the stored state "data only" and avoids bloating the AI context window.
#
# The list is computed once at import time by walking every phase (including
# Phase 6 branches) and collecting the keys of questions that have static
# options and are NOT flagged ``ai_generated``.
def _compute_static_option_keys() -> set:
    keys = set()

    def _scan(questions):
        for q in questions or []:
            if q.get("ai_generated"):
                continue
            if q.get("options"):
                keys.add(q.get("key"))

    for phase_data in WORKFLOW_PHASES.values():
        _scan(phase_data.get("questions"))
        for branch in (phase_data.get("branches") or {}).values():
            _scan(branch.get("questions"))
    return keys

STATIC_OPTION_KEYS = _compute_static_option_keys()

# Onboarding = the deterministic identity questions asked the moment a user
# starts "from zero". These have fixed options and need NO LLM call, so they
# are batched and answered fully offline before any dynamic (AI) phase runs.
# Phase 0 (status) + Phase 1 static profile fields (field / type / target).
ONBOARDING_QUESTION_IDS = ["0.1", "0.2", "0.3", "1.1", "1.2", "1.3"]

# Recommended default option per onboarding question (by question id). These
# are sensible starter picks for someone building a paper "from zero", surfaced
# pre-selected in the card so the user can accept the whole batch in one tap.
# Purely a UI hint — the user can change any answer freely.
ONBOARDING_RECOMMENDED = {
    "0.1": "A",  # Masih ide/konsep
    "0.2": "A",  # Belum ada data
    "0.3": "A",  # Individu (tugas akhir)
    "1.1": "A",  # Ilmu Komputer & IT
    "1.2": "B",  # Research Paper
    "1.3": "B",  # Jurnal Sinta 2-6
}

# First dynamic phase to enter once offline onboarding is complete. Phase 1
# still has one AI-generated question (1.4 title); its static fields (field /
# type / target) are already collected offline and get skipped automatically.
FIRST_DYNAMIC_PHASE = "1"

def _append_free_text(options: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Append a "Ceritakan sendiri..." free-text option with a non-colliding value.

    Most questions use A–D, so the free-text value is "E". But questions with
    more options (e.g. ``field`` uses A–N) would collide with a hardcoded "E",
    so we pick the first letter after the last used one instead.
    """
    used = {str(o.get("value")) for o in options}
    candidate = "E"
    if candidate in used:
        # Walk the alphabet from the char after the highest single-letter value.
        letters = [v for v in used if len(v) == 1 and v.isalpha()]
        start = max((ord(v.upper()) for v in letters), default=ord("D")) + 1
        candidate = chr(start)
        while candidate in used and candidate <= "Z":
            candidate = chr(ord(candidate) + 1)
    return list(options) + [{"label": "Ceritakan sendiri...", "value": candidate}]

def get_offline_onboarding_questions() -> List[Dict[str, Any]]:
    """Return the static onboarding questions as one offline batch.

    These are pulled verbatim from WORKFLOW_PHASES (fixed options, no AI).
    The caller renders them with the normal multi_question card and resolves
    answers via :func:`resolve_static_label` — so no option snapshot needs to
    be persisted. A free-text "Ceritakan sendiri..." fallback is appended so
    the user can always deviate.
    """
    by_id = {}
    for phase_data in WORKFLOW_PHASES.values():
        for q in phase_data.get("questions", []) or []:
            qid = q.get("id")
            if qid:
                by_id[qid] = q

    result = []
    for qid in ONBOARDING_QUESTION_IDS:
        q = by_id.get(qid)
        if not q:
            continue
        question = q.copy()
        if question.get("options"):
            # Deep-copy each option dict so flagging the recommended pick never
            # mutates the shared WORKFLOW_PHASES definition.
            recommended_value = ONBOARDING_RECOMMENDED.get(qid)
            options = []
            for opt in _append_free_text(question["options"]):
                opt = dict(opt)
                if recommended_value is not None and opt.get("value") == recommended_value:
                    opt["recommended"] = True
                options.append(opt)
            question["options"] = options
        result.append(question)
    return result

def resolve_static_label(key: str, value: str) -> Optional[str]:
    """Resolve an A/B/C... answer code to its full label for a STATIC question.

    Searches every phase (and Phase 6 branches) for a question matching ``key``
    that has fixed options. Returns the matching option label, or ``None`` when
    the key isn't a static question (i.e. it's AI-generated / free-text and must
    be resolved from the presented-options snapshot instead).
    """
    def _find(questions):
        for q in questions or []:
            if q.get("key") != key or q.get("ai_generated"):
                continue
            for opt in q.get("options", []) or []:
                if opt.get("value") == value:
                    return opt.get("label", value)
            # Key matched a static question but value is custom/free-text.
            return value
        return None

    for phase_data in WORKFLOW_PHASES.values():
        hit = _find(phase_data.get("questions"))
        if hit is not None:
            return hit
        for branch in (phase_data.get("branches") or {}).values():
            hit = _find(branch.get("questions"))
            if hit is not None:
                return hit
    return None

def get_phase_questions(phase: str, previous_answers: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Get questions for a specific phase, with AI-generated options where needed.
    Handles Phase 6 conditional branching based on methodology.

    Args:
        phase: Phase number (0-9)
        previous_answers: Dictionary of all previous answers

    Returns:
        List of questions with options
    """
    if phase not in WORKFLOW_PHASES:
        return []

    phase_data = WORKFLOW_PHASES[phase]

    # Handle Phase 6 conditional branching
    if phase == "6" and "branches" in phase_data:
        branches = phase_data["branches"]

        # Try each branch condition in order: quantitative, qualitative, literature
        for branch_name in ["quantitative", "qualitative", "literature"]:
            if branch_name in branches:
                branch = branches[branch_name]
                condition = branch.get("condition")
                if condition and condition(previous_answers):
                    questions = branch.get("questions", [])
                    break
        else:
            # Default to quantitative if no condition matches
            questions = branches.get("quantitative", {}).get("questions", [])
    else:
        questions = phase_data.get("questions", [])

    _FREE_TEXT_E = {"label": "Ceritakan sendiri...", "value": "E"}

    result = []
    for q in questions:
        question = q.copy()

        if q.get("ai_generated"):
            ai_opts = generate_ai_options(q, previous_answers)
            # Always append a free-text option so user can deviate from AI suggestions
            question["options"] = ai_opts + [_FREE_TEXT_E]
        elif question.get("options"):
            # Append free-text fallback with a non-colliding value (questions
            # like `field` use A–N, so a hardcoded "E" would clash).
            question["options"] = _append_free_text(question["options"])
        # Questions with no options at all are pure free-text → leave as-is

        result.append(question)

    return result


def _extract_json_array(content: str) -> Optional[list]:
    """Best-effort extraction of a JSON array of strings from an LLM reply.

    The chat model frequently decorates its output, so a bare json.loads is too
    fragile. We handle, in order:
      1. A clean array (fast path).
      2. A ```json ... ``` (or plain ```) fenced block.
      3. A <think>...</think> prefix (DeepSeek-style) before the real answer.
      4. The first bracketed [...] span anywhere in the text.

    Returns the parsed list, or None if nothing array-shaped is found.
    """
    if not content:
        return None

    text = content.strip()

    # Drop a leading <think>…</think> block if the model emitted one.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

    # 1) Fast path: the whole thing is already a JSON array.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # 2) Strip a fenced code block (```json … ``` or ``` … ```).
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        inner = fence.group(1).strip()
        try:
            parsed = json.loads(inner)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            text = inner  # fall through to the bracket scan below

    # 3) Grab the first [...] span anywhere in the remaining text.
    bracket = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if bracket:
        try:
            parsed = json.loads(bracket.group(0))
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def generate_ai_options(
    question: Dict[str, Any], previous_answers: Dict[str, str]
) -> List[Dict[str, str]]:
    """
    Generate 4 AI recommendations based on previous answers.
    Calls LLM to generate contextual recommendations.

    Args:
        question: Question definition
        previous_answers: All previous answers

    Returns:
        List of 4 option dictionaries
    """
    import os

    import requests

    q_id = question["id"]
    key = question["key"]
    q_text = question["question"]
    depends_on = question.get("depends_on", [])

    # Get API configuration
    base = (os.getenv("AIOTOMASI_API") or "").rstrip("/")
    api_key = os.getenv("AIOTOMASI_APIKEY") or ""
    model = os.getenv("MODELCHAT") or "VIOLA-CHAT"

    if not (base and api_key):
        # Fallback to generic options if API not configured
        return [
            {"label": f"Opsi 1 untuk {key}", "value": "A"},
            {"label": f"Opsi 2 untuk {key}", "value": "B"},
            {"label": f"Opsi 3 untuk {key}", "value": "C"},
            {"label": f"Opsi 4 untuk {key}", "value": "D"},
        ]

    # Build context from dependencies
    context_parts = []
    for dep_key in depends_on:
        if dep_key in previous_answers:
            context_parts.append(f"- {dep_key}: {previous_answers[dep_key]}")

    context_text = "\n".join(context_parts) if context_parts else "No previous context"

    # Build prompt based on question type
    system_prompt = (
        "You are an academic paper planning assistant. Generate 4 specific, "
        "contextual recommendations for the given question based on previous answers. "
        "Each recommendation should be:\n"
        "- Specific and actionable (not generic)\n"
        "- Relevant to the academic field and paper type\n"
        "- Different from each other\n"
        "- 5-15 words long\n\n"
        "Return ONLY a JSON array of 4 strings, nothing else. Example:\n"
        '["Recommendation 1", "Recommendation 2", "Recommendation 3", "Recommendation 4"]'
    )

    user_prompt = (
        f"Question: {q_text}\n"
        f"Question ID: {q_id}\n"
        f"Question key: {key}\n\n"
        f"Previous answers:\n{context_text}\n\n"
        f"Generate 4 specific recommendations for this question."
    )

    try:
        resp = requests.post(
            base + "/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "max_tokens": 500,
                "temperature": 0.7,
            },
            timeout=30,
        )

        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Parse the JSON array from the response. The model (VIOLA-CHAT,
            # DeepSeek-style) frequently wraps the array in ```json fences,
            # prepends a <think> block, or adds a sentence of prose — all of
            # which break a naive json.loads. _extract_json_array tolerates
            # those shapes so we don't needlessly fall back to generic options.
            recommendations = _extract_json_array(content)
            if isinstance(recommendations, list) and len(recommendations) >= 4:
                labels = [str(r).strip() for r in recommendations if str(r).strip()]
                if len(labels) >= 4:
                    return [
                        {"label": labels[0], "value": "A"},
                        {"label": labels[1], "value": "B"},
                        {"label": labels[2], "value": "C"},
                        {"label": labels[3], "value": "D"},
                    ]
    except Exception:
        pass

    # Fallback to question-specific defaults if API call fails
    return _get_fallback_options(q_id, key, previous_answers)


def _get_fallback_options(q_id: str, key: str, previous_answers: Dict[str, str]) -> List[Dict[str, str]]:
    """
    Provide fallback options when AI generation fails.
    Returns contextual defaults based on question ID and previous answers.
    """
    field = previous_answers.get("field", "bidang ilmu")
    paper_type = previous_answers.get("paper_type", "paper")
    methodology = previous_answers.get("methodology_approach", "")

    # Question-specific fallbacks
    fallbacks = {
        "1.4": [  # Title
            f"Analisis {field} menggunakan metode modern",
            f"Studi {paper_type} pada {field}",
            f"Implementasi sistem {field} berbasis AI",
            f"Evaluasi pendekatan baru dalam {field}",
        ],
        "2.1": [  # Topic
            f"Machine Learning dalam {field}",
            f"Optimasi sistem {field}",
            f"Analisis data {field}",
            f"Pengembangan framework {field}",
        ],
        "2.2": [  # Problem statement
            "Kurangnya metode efisien untuk menyelesaikan masalah X",
            "Keterbatasan pendekatan existing dalam konteks Y",
            "Kebutuhan akan solusi yang lebih akurat dan cepat",
            "Gap antara teori dan implementasi praktis",
        ],
        "2.3": [  # Research gap
            "Belum ada penelitian yang mengkombinasikan metode A dan B",
            "Studi existing belum mempertimbangkan faktor X",
            "Pendekatan terkini belum divalidasi pada konteks lokal",
            "Literatur kurang membahas aspek implementasi praktis",
        ],
        "2.4": [  # Research questions
            "Bagaimana metode X dapat meningkatkan performa Y?",
            "Apa faktor-faktor yang mempengaruhi efektivitas Z?",
            "Seberapa besar kontribusi pendekatan A terhadap B?",
            "Bagaimana membandingkan metode X dengan metode Y?",
        ],
        "2.5": [  # Objectives
            "Mengembangkan metode baru untuk menyelesaikan masalah X",
            "Menganalisis performa sistem Y dalam konteks Z",
            "Membandingkan efektivitas pendekatan A dan B",
            "Mengimplementasikan dan mengevaluasi solusi C",
        ],
        "2.6": [  # Keywords
            f"{field}, machine learning, optimization, analysis",
            f"{field}, deep learning, performance, evaluation",
            f"{field}, algorithm, implementation, comparison",
            f"{field}, system design, methodology, validation",
        ],
        "3.2": [  # Specific method
            "Support Vector Machine (SVM)" if "Kuantitatif" in methodology else "Grounded Theory",
            "Random Forest" if "Kuantitatif" in methodology else "Thematic Analysis",
            "Neural Network" if "Kuantitatif" in methodology else "Case Study",
            "Regression Analysis" if "Kuantitatif" in methodology else "Ethnography",
        ],
        "3.3": [  # Data source
            "Dataset publik (Kaggle, UCI, dll)",
            "Data primer dari survei/eksperimen",
            "Data sekunder dari institusi",
            "Data hasil simulasi",
        ],
        "3.4": [  # Sample size
            "100-500 instance" if "Kuantitatif" in methodology else "20-50 responden",
            "500-1000 instance" if "Kuantitatif" in methodology else "10-20 partisipan",
            "1000-5000 instance" if "Kuantitatif" in methodology else "5-10 kasus",
            ">5000 instance" if "Kuantitatif" in methodology else "3-5 kasus mendalam",
        ],
        "3.5": [  # Tools
            "Python (scikit-learn, TensorFlow)",
            "R (caret, ggplot2)",
            "MATLAB",
            "SPSS / Stata",
        ],
        "4.3": [  # Section count
            "5 bab (IMRAD standar)",
            "6 bab (dengan bab tambahan)",
            "7 bab (struktur lengkap)",
            "8+ bab (thesis/disertasi)",
        ],
        "4.4": [  # Priority sections
            "Methodology - detail teknis implementasi",
            "Results - analisis mendalam hasil eksperimen",
            "Literature Review - state-of-the-art terkini",
            "Discussion - implikasi dan kontribusi",
        ],
        "4.5": [  # Outline
            "Outline standar IMRAD dengan 5 bab utama",
            "Outline extended dengan bab preliminary",
            "Outline thesis dengan 7-8 bab",
            "Outline custom sesuai kebutuhan",
        ],
        "5.3": [  # Key papers
            "Paper foundational di bidang ini (cari di Google Scholar)",
            "Survey paper terbaru (2020-2024)",
            "Paper dengan metode serupa",
            "Paper dari jurnal target publikasi",
        ],
        "6.1": [  # Visualization type
            "Tabel statistik deskriptif",
            "Grafik perbandingan (bar/line chart)",
            "Confusion matrix / heatmap",
            "Scatter plot / box plot",
        ],
        "6.2": [  # Figure count
            "3-5 tabel dan figur",
            "5-8 tabel dan figur",
            "8-12 tabel dan figur",
            ">12 tabel dan figur",
        ],
        "6.3": [  # Visualization platform
            "Python (matplotlib, seaborn)",
            "R (ggplot2)",
            "Tableau / Power BI",
            "Excel / Google Sheets",
        ],
        "8.3": [  # Budget
            "Rp 0 (tugas akhir, no APC)",
            "Rp 1-3 juta (Sinta 2-6 APC)",
            "Rp 3-5 juta (Sinta 1 APC)",
            "Rp 5-15 juta (Scopus APC + editing)",
        ],
    }

    options = fallbacks.get(q_id, [
        f"Opsi 1 untuk {key}",
        f"Opsi 2 untuk {key}",
        f"Opsi 3 untuk {key}",
        f"Opsi 4 untuk {key}",
    ])

    return [
        {"label": options[0], "value": "A"},
        {"label": options[1], "value": "B"},
        {"label": options[2], "value": "C"},
        {"label": options[3], "value": "D"},
    ]


def validate_workflow(answers: Dict[str, str]) -> Dict[str, Any]:
    """
    Validate workflow consistency (Phase 9).
    Implements all 7 validation checks from specification.

    Args:
        answers: All workflow answers

    Returns:
        Validation report with warnings and suggestions
    """
    warnings = []

    # 1. RQ vs Method compatibility
    methodology = answers.get("methodology_approach", "")
    research_questions = answers.get("research_questions", "")

    if "Kualitatif" in methodology and any(word in research_questions.lower() for word in ["berapa", "seberapa besar", "jumlah"]):
        warnings.append(
            {
                "type": "RQ vs Metode",
                "message": "RQ kuantitatif ('berapa besar') tapi metode Kualitatif",
                "suggestion": "Pertimbangkan ubah metode ke Kuantitatif atau ubah RQ",
                "severity": "high",
            }
        )

    # 2. Sample size vs Method adequacy
    sample_size = answers.get("sample_size", "")
    specific_method = answers.get("specific_method", "")

    if "SVM" in specific_method or "Neural Network" in specific_method or "Random Forest" in specific_method:
        # Extract number from sample size string
        import re
        numbers = re.findall(r'\d+', sample_size)
        if numbers and int(numbers[0]) < 100:
            warnings.append(
                {
                    "type": "Sampel vs Metode",
                    "message": f"Sampel terlalu kecil untuk {specific_method}",
                    "suggestion": "Tingkatkan jumlah sampel minimal 100-500 instance",
                    "severity": "high",
                }
            )

    # 3. Citation count vs Target publication
    reference_count = answers.get("reference_count", "")
    target_publication = answers.get("target_publication", "")

    if target_publication in ["D", "Jurnal Scopus"]:
        # Scopus journals typically need 40+ references
        if reference_count in ["A", "15-25"]:
            warnings.append(
                {
                    "type": "Sitasi vs Target",
                    "message": "Jumlah referensi terlalu sedikit untuk jurnal Scopus",
                    "suggestion": "Tingkatkan target referensi minimal 40-60 untuk Scopus",
                    "severity": "medium",
                }
            )
    elif target_publication in ["C", "Jurnal Sinta 1"]:
        if reference_count in ["A", "15-25"]:
            warnings.append(
                {
                    "type": "Sitasi vs Target",
                    "message": "Jumlah referensi kurang untuk Sinta 1",
                    "suggestion": "Tingkatkan target referensi minimal 25-40 untuk Sinta 1",
                    "severity": "medium",
                }
            )

    # 4. Tone vs Target publication
    writing_tone = answers.get("writing_tone", "")
    if target_publication in ["D", "Jurnal Scopus", "C", "Jurnal Sinta 1"]:
        if writing_tone in ["B", "Semi-formal"]:
            warnings.append(
                {
                    "type": "Tone vs Target",
                    "message": "Tone semi-formal kurang sesuai untuk jurnal bereputasi",
                    "suggestion": "Gunakan tone 'Formal akademik baku' untuk publikasi Scopus/Sinta 1",
                    "severity": "low",
                }
            )

    # 5. Ethics vs Subject type
    ethics = answers.get("ethics", "")
    data_source = answers.get("data_source", "")

    if any(word in data_source.lower() for word in ["survei", "wawancara", "responden", "partisipan", "subjek"]):
        if ethics in ["A", "Tidak perlu etik"]:
            warnings.append(
                {
                    "type": "Etika vs Subjek",
                    "message": "Penelitian melibatkan manusia tapi tidak ada ethical clearance",
                    "suggestion": "Pertimbangkan ethical clearance atau informed consent",
                    "severity": "high",
                }
            )

    # 6. Budget vs Target (APC costs)
    budget = answers.get("budget", "")
    if target_publication in ["D", "Jurnal Scopus"]:
        if "Rp 0" in budget or "no APC" in budget:
            warnings.append(
                {
                    "type": "Anggaran vs Target",
                    "message": "Jurnal Scopus umumnya memerlukan APC (Article Processing Charge)",
                    "suggestion": "Siapkan budget Rp 5-15 juta untuk APC Scopus + editing/proofreading",
                    "severity": "medium",
                }
            )
    elif target_publication in ["C", "Jurnal Sinta 1"]:
        if "Rp 0" in budget:
            warnings.append(
                {
                    "type": "Anggaran vs Target",
                    "message": "Sinta 1 mungkin memerlukan APC",
                    "suggestion": "Siapkan budget Rp 3-5 juta untuk kemungkinan APC",
                    "severity": "low",
                }
            )

    # 7. Timeline vs Complexity
    timeline = answers.get("timeline", "")
    complexity = answers.get("complexity", "")

    if complexity in ["C", "Tinggi (Scopus Q3-Q4)", "D", "Sangat Tinggi (Scopus Q1-Q2)"]:
        if timeline in ["A", "1 minggu (sprint)", "B", "2-4 minggu"]:
            warnings.append(
                {
                    "type": "Timeline vs Kompleksitas",
                    "message": "Timeline terlalu singkat untuk kompleksitas tinggi",
                    "suggestion": "Paper kompleksitas tinggi memerlukan minimal 1-3 bulan",
                    "severity": "high",
                }
            )

    return {
        "valid": len(warnings) == 0,
        "warnings": warnings,
        "summary": generate_executive_summary(answers),
    }


def generate_executive_summary(answers: Dict[str, str]) -> Dict[str, Any]:
    """
    Generate executive summary of all workflow answers.

    Args:
        answers: All workflow answers

    Returns:
        Executive summary dictionary
    """
    return {
        "title": answers.get("title", "Untitled"),
        "field": answers.get("field", ""),
        "paper_type": answers.get("paper_type", ""),
        "target": answers.get("target_publication", ""),
        "topic": answers.get("topic", ""),
        "research_questions": answers.get("research_questions", ""),
        "methodology": answers.get("methodology_approach", ""),
        "method": answers.get("specific_method", ""),
        "keywords": answers.get("keywords", ""),
        "checklist": {
            "profil": bool(answers.get("field")),
            "topik": bool(answers.get("topic")),
            "metode": bool(answers.get("methodology_approach")),
            "struktur": bool(answers.get("template")),
            "referensi": bool(answers.get("citation_style")),
            "visualisasi": bool(answers.get("visualization_type")),
            "output": bool(answers.get("language")),
            "produksi": bool(answers.get("timeline")),
        },
    }


def get_next_phase(current_phase: str, answers: Dict[str, str]) -> Optional[str]:
    """
    Determine next phase based on current phase and answers.

    Args:
        current_phase: Current phase number
        answers: All answers so far

    Returns:
        Next phase number or None if complete
    """
    phase_order = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]

    try:
        current_idx = phase_order.index(current_phase)
        if current_idx < len(phase_order) - 1:
            return phase_order[current_idx + 1]
    except ValueError:
        pass

    return None
