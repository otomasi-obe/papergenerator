"""
Workflow Engine for Paper Builder
==================================
Implements the 9-phase questionnaire system from Doc/worflowQuestion.md

Each phase has questions with 4 AI recommendations + 1 custom input.
Questions are connected - later questions depend on earlier answers.
"""

import json
from typing import Dict, List, Optional, Any


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
                "depends_on": []
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
                "depends_on": ["0.1"]
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
                "depends_on": []
            }
        ]
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
                ],
                "depends_on": []
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
                "depends_on": ["1.1"]
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
                "depends_on": ["1.1", "1.2"]
            },
            {
                "id": "1.4",
                "question": "Judul paper (bisa provisional)?",
                "key": "title",
                "options": [],
                "depends_on": ["1.1", "1.2", "1.3"],
                "ai_generated": True
            }
        ]
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
                "ai_generated": True
            },
            {
                "id": "2.2",
                "question": "Problem statement?",
                "key": "problem_statement",
                "options": [],
                "depends_on": ["2.1"],
                "ai_generated": True
            },
            {
                "id": "2.3",
                "question": "Research gap — apa yang belum dijawab?",
                "key": "research_gap",
                "options": [],
                "depends_on": ["2.1", "2.2"],
                "ai_generated": True
            },
            {
                "id": "2.4",
                "question": "Research question(s)?",
                "key": "research_questions",
                "options": [],
                "depends_on": ["2.2", "2.3"],
                "ai_generated": True
            },
            {
                "id": "2.5",
                "question": "Tujuan penelitian?",
                "key": "objectives",
                "options": [],
                "depends_on": ["2.3", "2.4"],
                "ai_generated": True
            },
            {
                "id": "2.6",
                "question": "Keywords?",
                "key": "keywords",
                "options": [],
                "depends_on": ["2.1", "2.4"],
                "ai_generated": True
            }
        ]
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
                "depends_on": ["1.1", "1.2", "2.4"]
            },
            {
                "id": "3.2",
                "question": "Metode spesifik?",
                "key": "specific_method",
                "options": [],
                "depends_on": ["3.1", "2.1"],
                "ai_generated": True
            },
            {
                "id": "3.3",
                "question": "Sumber data?",
                "key": "data_source",
                "options": [],
                "depends_on": ["3.1", "3.2"],
                "ai_generated": True
            },
            {
                "id": "3.4",
                "question": "Jumlah sampel / dataset?",
                "key": "sample_size",
                "options": [],
                "depends_on": ["3.1", "3.2", "1.1"],
                "ai_generated": True
            },
            {
                "id": "3.5",
                "question": "Tools?",
                "key": "tools",
                "options": [],
                "depends_on": ["3.2", "1.1"],
                "ai_generated": True
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
                "depends_on": ["3.1", "3.3", "1.1"]
            }
        ]
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
                "depends_on": ["1.2", "1.3"]
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
                "depends_on": ["1.3", "3.1"]
            },
            {
                "id": "4.3",
                "question": "Jumlah bab/section target?",
                "key": "section_count",
                "options": [],
                "depends_on": ["4.1", "1.2"],
                "ai_generated": True
            },
            {
                "id": "4.4",
                "question": "Bab mana yang perlu diperdalam?",
                "key": "priority_sections",
                "options": [],
                "depends_on": ["2.3", "2.4", "3.2"],
                "ai_generated": True
            },
            {
                "id": "4.5",
                "question": "Outline detail?",
                "key": "outline",
                "options": [],
                "depends_on": ["4.1", "4.2", "4.3"],
                "ai_generated": True
            }
        ]
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
                "depends_on": ["1.1"]
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
                "depends_on": ["1.3", "4.2"]
            },
            {
                "id": "5.3",
                "question": "Key papers yang wajib disitasi?",
                "key": "key_papers",
                "options": [],
                "depends_on": ["2.1", "2.3"],
                "ai_generated": True
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
                "depends_on": ["1.1", "2.1"]
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
                "depends_on": []
            }
        ]
    },
    "6": {
        "name": "Data & Visualisasi",
        "description": "Conditional session based on methodology.",
        "questions": [
            {
                "id": "6.1",
                "question": "Jenis visualisasi utama?",
                "key": "visualization_type",
                "options": [],
                "depends_on": ["3.2", "3.4"],
                "ai_generated": True,
                "conditional": True
            },
            {
                "id": "6.2",
                "question": "Jumlah tabel & figuur target?",
                "key": "figure_count",
                "options": [],
                "depends_on": ["4.2"],
                "ai_generated": True,
                "conditional": True
            },
            {
                "id": "6.3",
                "question": "Format/platform?",
                "key": "visualization_platform",
                "options": [],
                "depends_on": ["3.5"],
                "ai_generated": True,
                "conditional": True
            }
        ]
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
                "depends_on": ["1.3"]
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
                "depends_on": ["1.3", "1.2"]
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
                "depends_on": ["1.3"]
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
                "depends_on": []
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
                "depends_on": ["7.4"]
            }
        ]
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
                "depends_on": ["0.3"]
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
                "depends_on": ["1.3"]
            },
            {
                "id": "8.3",
                "question": "Apakah ada biaya yang perlu dianggarkan?",
                "key": "budget",
                "options": [],
                "depends_on": ["1.3", "8.2"],
                "ai_generated": True
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
                "depends_on": ["0.1", "4.2"]
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
                "depends_on": []
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
                "depends_on": ["1.3"]
            }
        ]
    },
    "9": {
        "name": "Validasi & Finalisasi",
        "description": "Cross-check menyeluruh & backward adjustment.",
        "questions": []
    }
}


def get_phase_questions(phase: str, previous_answers: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Get questions for a specific phase, with AI-generated options where needed.
    
    Args:
        phase: Phase number (0-9)
        previous_answers: Dictionary of all previous answers
        
    Returns:
        List of questions with options
    """
    if phase not in WORKFLOW_PHASES:
        return []
    
    phase_data = WORKFLOW_PHASES[phase]
    questions = []
    
    for q in phase_data["questions"]:
        question = q.copy()
        
        if q.get("ai_generated"):
            question["options"] = generate_ai_options(q, previous_answers)
        
        questions.append(question)
    
    return questions


def generate_ai_options(question: Dict[str, Any], previous_answers: Dict[str, str]) -> List[Dict[str, str]]:
    """
    Generate 4 AI recommendations based on previous answers.
    This is a placeholder - in production, this would call an AI model.
    
    Args:
        question: Question definition
        previous_answers: All previous answers
        
    Returns:
        List of 4 option dictionaries
    """
    q_id = question["id"]
    key = question["key"]
    
    if q_id == "1.4":
        field = previous_answers.get("field", "")
        paper_type = previous_answers.get("paper_type", "")
        return [
            {"label": f"Analisis {field} menggunakan metode modern", "value": "A"},
            {"label": f"Studi {paper_type} pada {field}", "value": "B"},
            {"label": f"Implementasi sistem {field} berbasis AI", "value": "C"},
            {"label": f"Evaluasi pendekatan baru dalam {field}", "value": "D"},
        ]
    
    elif q_id == "2.1":
        field = previous_answers.get("field", "")
        return [
            {"label": f"Machine Learning dalam {field}", "value": "A"},
            {"label": f"Optimasi sistem {field}", "value": "B"},
            {"label": f"Analisis data {field}", "value": "C"},
            {"label": f"Pengembangan framework {field}", "value": "D"},
        ]
    
    return [
        {"label": "Opsi 1 (AI generated)", "value": "A"},
        {"label": "Opsi 2 (AI generated)", "value": "B"},
        {"label": "Opsi 3 (AI generated)", "value": "C"},
        {"label": "Opsi 4 (AI generated)", "value": "D"},
    ]


def validate_workflow(answers: Dict[str, str]) -> Dict[str, Any]:
    """
    Validate workflow consistency (Phase 9).
    
    Args:
        answers: All workflow answers
        
    Returns:
        Validation report with warnings and suggestions
    """
    warnings = []
    
    methodology = answers.get("methodology_approach", "")
    research_questions = answers.get("research_questions", "")
    
    if "Kualitatif" in methodology and "berapa" in research_questions.lower():
        warnings.append({
            "type": "RQ vs Metode",
            "message": "RQ kuantitatif ('berapa besar') tapi metode Kualitatif",
            "suggestion": "Pertimbangkan ubah metode ke Kuantitatif atau ubah RQ"
        })
    
    sample_size = answers.get("sample_size", "")
    if "20" in sample_size and "SVM" in answers.get("specific_method", ""):
        warnings.append({
            "type": "Sampel vs Metode",
            "message": "Sampel terlalu kecil untuk SVM",
            "suggestion": "Tingkatkan jumlah sampel minimal 100 instance"
        })
    
    return {
        "valid": len(warnings) == 0,
        "warnings": warnings,
        "summary": generate_executive_summary(answers)
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
            "produksi": bool(answers.get("timeline"))
        }
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
