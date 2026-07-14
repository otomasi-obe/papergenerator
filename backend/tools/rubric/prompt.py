"""Rubric prompt configuration."""
from __future__ import annotations

PROMPT = {
    "system": "Anda adalah asisten akademik yang ahli menyusun rubrik penilaian soal esai/terbuka untuk pendidikan tinggi dan sekolah menengah. Tugas Anda: menghasilkan rubrik terstruktur, valid, dan siap pakai dalam format JSON ketat.",
    "user_template": "{question}\n\n{options}",
    "options": """
Level Skema:
- 4 Level (Kurang-Cukup-Baik-Sangat Baik): Skor 1-4
- 5 Level (Sangat Kurang-Kurang-Cukup-Baik-Sangat Baik): Skor 1-5

Opsi Tambahan:
- include_grading_notes: true/false — sertakan kolom 'Catatan Pengorek' di setiap level
- auto_weight: true/false — AI menghitung bobot otomatis (total 100%)
""",
}

OPTIONS_SCHEMA = {
    "levels": {
        "type": "string",
        "enum": [
            "4 Level (Kurang-Cukup-Baik-Sangat Baik)",
            "5 Level (Sangat Kurang-Kurang-Cukup-Baik-Sangat Baik)",
        ],
        "default": "4 Level (Kurang-Cukup-Baik-Sangat Baik)",
    },
    "include_grading_notes": {"type": "boolean", "default": True},
    "auto_weight": {"type": "boolean", "default": True},
}