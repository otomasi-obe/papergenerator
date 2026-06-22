"""
Template Registry System for Paper Generator

Provides centralized metadata, categorization, and validation for all journal templates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set


class TemplateField(Enum):
    COMPUTER_SCIENCE = "Computer Science"
    ENGINEERING = "Engineering"
    ELECTRICAL_ENGINEERING = "Electrical Engineering"
    MECHANICAL_ENGINEERING = "Mechanical Engineering"
    INFORMATION_SYSTEMS = "Information Systems"
    LIBRARY_SCIENCE = "Library Science"
    ISLAMIC_STUDIES = "Islamic Studies"
    ENERGY = "Energy"
    MULTIDISCIPLINARY = "Multidisciplinary"
    GENERAL = "General"


class CitationStyle(Enum):
    IEEE = "IEEE"
    APA = "APA"
    ACM = "ACM"
    VANCOUVER = "Vancouver"
    HARVARD = "Harvard"
    CHICAGO = "Chicago"
    MLA = "MLA"
    NUMBERED = "Numbered"
    AUTHOR_YEAR = "Author-Year"


class TemplateType(Enum):
    JOURNAL = "Journal Article"
    CONFERENCE = "Conference Paper"
    THESIS = "Thesis"
    REPORT = "Technical Report"


@dataclass
class TemplateMetadata:
    code: str
    name: str
    full_name: str
    template_type: TemplateType
    fields: List[TemplateField]
    citation_style: CitationStyle
    
    publisher: Optional[str] = None
    country: Optional[str] = None
    language: str = "English"
    
    columns: int = 2
    page_size: str = "A4"
    
    requires_abstract: bool = True
    requires_keywords: bool = True
    min_keywords: int = 3
    max_keywords: int = 8
    
    max_title_words: Optional[int] = None
    abstract_word_limit: Optional[int] = None
    
    section_numbering: str = "roman"
    subsection_numbering: str = "letter"
    
    supports_equations: bool = True
    supports_figures: bool = True
    supports_tables: bool = True
    
    special_sections: List[str] = field(default_factory=list)
    
    notes: str = ""
    
    def __post_init__(self):
        if isinstance(self.template_type, str):
            self.template_type = TemplateType(self.template_type)
        if isinstance(self.citation_style, str):
            self.citation_style = CitationStyle(self.citation_style)
        self.fields = [
            f if isinstance(f, TemplateField) else TemplateField(f)
            for f in self.fields
        ]


TEMPLATE_REGISTRY: Dict[str, TemplateMetadata] = {
    "IEEE": TemplateMetadata(
        code="IEEE",
        name="IEEE",
        full_name="IEEE Transactions Standard Format",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.COMPUTER_SCIENCE, TemplateField.ELECTRICAL_ENGINEERING],
        citation_style=CitationStyle.IEEE,
        publisher="IEEE",
        country="USA",
        columns=2,
        page_size="US Letter",
        abstract_word_limit=250,
        max_title_words=12,
        section_numbering="roman",
        subsection_numbering="letter",
        notes="Standard IEEE format with two-column layout, numbered references"
    ),
    
    "ACM": TemplateMetadata(
        code="ACM",
        name="ACM",
        full_name="ACM Conference Proceedings Format",
        template_type=TemplateType.CONFERENCE,
        fields=[TemplateField.COMPUTER_SCIENCE],
        citation_style=CitationStyle.ACM,
        publisher="ACM",
        country="USA",
        columns=2,
        abstract_word_limit=150,
        section_numbering="arabic",
        notes="ACM SIGCONF format for conference papers"
    ),
    
    "Springer": TemplateMetadata(
        code="Springer",
        name="Springer",
        full_name="Springer Journal Article Format",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.MULTIDISCIPLINARY],
        citation_style=CitationStyle.NUMBERED,
        publisher="Springer Nature",
        country="Germany",
        columns=1,
        abstract_word_limit=250,
        section_numbering="arabic",
        notes="Springer Nature journal format with single-column layout"
    ),
    
    "Elsevier": TemplateMetadata(
        code="Elsevier",
        name="Elsevier",
        full_name="Elsevier Journal Article Format",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.MULTIDISCIPLINARY],
        citation_style=CitationStyle.NUMBERED,
        publisher="Elsevier",
        country="Netherlands",
        columns=1,
        abstract_word_limit=300,
        section_numbering="arabic",
        special_sections=["Highlights"],
        notes="Elsevier journal format with highlights section"
    ),
    
    "APA": TemplateMetadata(
        code="APA",
        name="APA",
        full_name="APA 7th Edition Format",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.MULTIDISCIPLINARY],
        citation_style=CitationStyle.APA,
        publisher="American Psychological Association",
        country="USA",
        columns=1,
        abstract_word_limit=250,
        section_numbering="arabic",
        notes="APA 7th edition for psychology and social sciences"
    ),
    
    "MDPI": TemplateMetadata(
        code="MDPI",
        name="MDPI",
        full_name="MDPI Open Access Journal Format",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.MULTIDISCIPLINARY],
        citation_style=CitationStyle.NUMBERED,
        publisher="MDPI",
        country="Switzerland",
        columns=1,
        abstract_word_limit=200,
        section_numbering="arabic",
        notes="MDPI open access journal format"
    ),
    
    "IJECE": TemplateMetadata(
        code="IJECE",
        name="IJECE",
        full_name="International Journal of Electrical and Computer Engineering",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.ELECTRICAL_ENGINEERING, TemplateField.COMPUTER_SCIENCE],
        citation_style=CitationStyle.IEEE,
        publisher="IAES",
        country="Indonesia",
        columns=2,
        abstract_word_limit=200,
        notes="Indonesian journal following IEEE citation style"
    ),
    
    "IJEECS": TemplateMetadata(
        code="IJEECS",
        name="IJEECS",
        full_name="Indonesian Journal of Electrical Engineering and Computer Science",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.ELECTRICAL_ENGINEERING, TemplateField.COMPUTER_SCIENCE],
        citation_style=CitationStyle.IEEE,
        publisher="IAES",
        country="Indonesia",
        columns=2,
        notes="Sister journal to IJECE"
    ),
    
    "JNTETI": TemplateMetadata(
        code="JNTETI",
        name="JNTETI",
        full_name="Jurnal Nasional Teknik Elektro dan Teknologi Informasi",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.ELECTRICAL_ENGINEERING, TemplateField.INFORMATION_SYSTEMS],
        citation_style=CitationStyle.IEEE,
        publisher="UGM",
        country="Indonesia",
        language="Indonesian/English",
        columns=2,
        notes="National journal from Universitas Gadjah Mada"
    ),
    
    "JOKI": TemplateMetadata(
        code="JOKI",
        name="JOKI",
        full_name="Jurnal Online Informatika",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.COMPUTER_SCIENCE, TemplateField.INFORMATION_SYSTEMS],
        citation_style=CitationStyle.IEEE,
        country="Indonesia",
        language="Indonesian/English",
        columns=1,
        notes="Single-column format"
    ),
    
    "DJLIT": TemplateMetadata(
        code="DJLIT",
        name="DJLIT",
        full_name="DESIDOC Journal of Library & Information Technology",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.LIBRARY_SCIENCE, TemplateField.INFORMATION_SYSTEMS],
        citation_style=CitationStyle.VANCOUVER,
        publisher="DESIDOC",
        country="India",
        columns=1,
        notes="Library and information science journal"
    ),
    
    "ICET": TemplateMetadata(
        code="ICET",
        name="ICET",
        full_name="International Conference on Electrical Engineering and Technology",
        template_type=TemplateType.CONFERENCE,
        fields=[TemplateField.ELECTRICAL_ENGINEERING],
        citation_style=CitationStyle.IEEE,
        columns=2,
        notes="Conference proceedings format"
    ),
    
    "ICOSEG": TemplateMetadata(
        code="ICOSEG",
        name="ICOSEG",
        full_name="International Conference on Smart Energy and Grid",
        template_type=TemplateType.CONFERENCE,
        fields=[TemplateField.ELECTRICAL_ENGINEERING, TemplateField.ENERGY],
        citation_style=CitationStyle.IEEE,
        columns=2,
        notes="Energy and smart grid conference"
    ),
    
    "JRC": TemplateMetadata(
        code="JRC",
        name="JRC",
        full_name="Journal of Robotics and Control",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.ENGINEERING, TemplateField.COMPUTER_SCIENCE],
        citation_style=CitationStyle.IEEE,
        country="Indonesia",
        columns=2,
        notes="Robotics and control systems journal"
    ),
    
    "ROTASI": TemplateMetadata(
        code="ROTASI",
        name="ROTASI",
        full_name="Rotasi - Jurnal Teknik Mesin",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.MECHANICAL_ENGINEERING],
        citation_style=CitationStyle.IEEE,
        country="Indonesia",
        language="Indonesian/English",
        columns=2,
        notes="Mechanical engineering journal"
    ),
    
    "ENERGIUPM": TemplateMetadata(
        code="ENERGIUPM",
        name="ENERGIUPM",
        full_name="ENERGI & KELISTRIKAN",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.ELECTRICAL_ENGINEERING, TemplateField.ENERGY],
        citation_style=CitationStyle.IEEE,
        country="Indonesia",
        language="Indonesian/English",
        columns=2,
        notes="Energy and electricity journal"
    ),

    "PST": TemplateMetadata(
        code="PST",
        name="PST",
        full_name="Plant Science Today",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.MULTIDISCIPLINARY],
        citation_style=CitationStyle.VANCOUVER,
        publisher="Horizon e-Publishing",
        country="India",
        columns=1,
        page_size="A4",
        abstract_word_limit=250,
        section_numbering="arabic",
        notes="Plant Science Today - single column, Vancouver style, Times New Roman 12pt"
    ),
    
    "MURHUM": TemplateMetadata(
        code="MURHUM",
        name="Murhum",
        full_name="Jurnal Murhum: Jurnal Pendidikan Anak Usia Dini",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.MULTIDISCIPLINARY],
        citation_style=CitationStyle.APA,
        country="Indonesia",
        language="Indonesian",
        columns=1,
        page_size="A4",
        abstract_word_limit=250,
        section_numbering="arabic",
        notes="Jurnal Sinta 3 PAUD. Single column, APA style."
    ),
    "OBSESI": TemplateMetadata(
        code="OBSESI",
        name="Obsesi",
        full_name="Jurnal Obsesi: Jurnal Pendidikan Anak Usia Dini",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.MULTIDISCIPLINARY],
        citation_style=CitationStyle.APA,
        country="Indonesia",
        language="Indonesian/English",
        columns=1,
        page_size="A4",
        abstract_word_limit=250,
        section_numbering="arabic",
        notes="Jurnal Sinta 2 PAUD. Single column, APA style."
    ),
    "PAUDIA": TemplateMetadata(
        code="PAUDIA",
        name="PAUDIA",
        full_name="Jurnal PAUDIA: Jurnal Penelitian dalam Bidang Pendidikan Anak Usia Dini",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.MULTIDISCIPLINARY],
        citation_style=CitationStyle.APA,
        country="Indonesia",
        language="Indonesian",
        columns=1,
        page_size="A4",
        abstract_word_limit=250,
        section_numbering="arabic",
        notes="Jurnal Sinta 3 PAUD (UPGRIS). Single column, APA style."
    ),
    "PGPAUDTrunojoyo": TemplateMetadata(
        code="PGPAUDTrunojoyo",
        name="PGPAUDTrunojoyo",
        full_name="Jurnal PG-PAUD Trunojoyo: Jurnal Pendidikan Guru Pendidikan Anak Usia Dini",
        template_type=TemplateType.JOURNAL,
        fields=[TemplateField.MULTIDISCIPLINARY],
        citation_style=CitationStyle.APA,
        country="Indonesia",
        language="Indonesian",
        columns=1,
        page_size="A4",
        abstract_word_limit=250,
        section_numbering="arabic",
        notes="Jurnal PG-PAUD Trunojoyo. Single column, APA style. TNR 12pt body, 16pt title, 10pt abstract."
    ),
}

for code in [
    "AEJ", "AMORI", "CCJ", "CERiMRE", "EASR", "ELCTRICES", "ELKOLIND",
    "El-Usrah", "ICIMECE", "ICONIE", "IJB", "IJIMS", "IJITEE", "IJRED",
    "IJT", "JAMRIS", "JAT", "JCEF", "JEEMECS", "JIEB", "JMEM",
    "JTMM", "JTRANSIENT", "JTUNDIP", "KKCK", "MEV", "PST", "UITM", "ULTIMACOMP"
]:
    if code not in TEMPLATE_REGISTRY:
        TEMPLATE_REGISTRY[code] = TemplateMetadata(
            code=code,
            name=code,
            full_name=f"{code} Journal Format",
            template_type=TemplateType.JOURNAL,
            fields=[TemplateField.MULTIDISCIPLINARY],
            citation_style=CitationStyle.IEEE,
            columns=2,
            notes="Template metadata to be completed"
        )


# ── MDPI Journal Sub-Templates (148+ journals) ──────────────────────────
def _load_mdpi_journals() -> dict:
    """Load MDPI journal metadata from journals.json and register as sub-templates."""
    import json as _json
    from pathlib import Path as _Path
    
    _journals_path = _Path(__file__).resolve().parent / "journals.json"
    if not _journals_path.exists():
        return {}
    
    _data = _json.loads(_journals_path.read_text(encoding="utf-8"))
    
    for key, info in _data.items():
        code = f"MDPI_{key}".upper()  # Uppercase for consistent lookup
        short = info.get("short_name", key)
        year = info.get("year", 2025)
        volume = info.get("volume", 1)
        
        TEMPLATE_REGISTRY[code] = TemplateMetadata(
            code=code,
            name=f"MDPI {short}",
            full_name=f"MDPI {short} ({year}, Vol. {volume})",
            template_type=TemplateType.JOURNAL,
            fields=[TemplateField.MULTIDISCIPLINARY],
            citation_style=CitationStyle.NUMBERED,
            publisher="MDPI",
            country="Switzerland",
            columns=1,
            page_size="A4",
            abstract_word_limit=200,
            section_numbering="arabic",
            notes=f"MDPI {short} open access journal format",
        )
    
    return _data

MDPI_JOURNALS = _load_mdpi_journals()


def get_mdpi_journal_info(key: str) -> dict | None:
    """Get MDPI sub-journal metadata (short_name, year, volume, logo)."""
    return MDPI_JOURNALS.get(key)


def resolve_template_journal(code: str) -> tuple[str, str | None]:
    """Resolve template code: returns (base_code, mdpi_sub_key or None).
    
    'MDPI_ACOUSTICS' → ('MDPI', 'acoustics')
    'MDPI_acoustics' → ('MDPI', 'acoustics')
    'IEEE' → ('IEEE', None)
    """
    upper = code.upper()
    if upper.startswith('MDPI_') and len(upper) > 5:
        return ('MDPI', upper[5:].lower())
    return (code.upper(), None)


def get_template(code: str) -> Optional[TemplateMetadata]:
    return TEMPLATE_REGISTRY.get(code.upper())


def list_templates(
    field: Optional[TemplateField] = None,
    template_type: Optional[TemplateType] = None,
    citation_style: Optional[CitationStyle] = None,
) -> List[TemplateMetadata]:
    templates = list(TEMPLATE_REGISTRY.values())
    
    if field:
        templates = [t for t in templates if field in t.fields]
    
    if template_type:
        templates = [t for t in templates if t.template_type == template_type]
    
    if citation_style:
        templates = [t for t in templates if t.citation_style == citation_style]
    
    return sorted(templates, key=lambda t: t.name)


def get_templates_by_field(field: TemplateField) -> List[TemplateMetadata]:
    return list_templates(field=field)


def get_templates_by_citation_style(style: CitationStyle) -> List[TemplateMetadata]:
    return list_templates(citation_style=style)


def validate_paper_for_template(paper_data: dict, template_code: str) -> List[str]:
    template = get_template(template_code)
    if not template:
        return [f"Unknown template: {template_code}"]
    
    errors = []
    
    if template.requires_abstract and not paper_data.get("abstract"):
        errors.append("Abstract is required for this template")
    
    if template.requires_keywords:
        keywords = paper_data.get("keywords", [])
        if not keywords:
            errors.append("Keywords are required for this template")
        elif len(keywords) < template.min_keywords:
            errors.append(f"Minimum {template.min_keywords} keywords required (found {len(keywords)})")
        elif len(keywords) > template.max_keywords:
            errors.append(f"Maximum {template.max_keywords} keywords allowed (found {len(keywords)})")
    
    if template.abstract_word_limit:
        abstract = paper_data.get("abstract", "")
        word_count = len(abstract.split())
        if word_count > template.abstract_word_limit:
            errors.append(
                f"Abstract exceeds word limit: {word_count} words "
                f"(limit: {template.abstract_word_limit})"
            )
    
    if template.max_title_words:
        title = paper_data.get("title", "")
        word_count = len(title.split())
        if word_count > template.max_title_words:
            errors.append(
                f"Title exceeds word limit: {word_count} words "
                f"(limit: {template.max_title_words})"
            )
    
    return errors


def get_template_info(template_code: str) -> dict:
    template = get_template(template_code)
    if not template:
        return {}
    
    return {
        "code": template.code,
        "name": template.name,
        "full_name": template.full_name,
        "type": template.template_type.value,
        "fields": [f.value for f in template.fields],
        "citation_style": template.citation_style.value,
        "publisher": template.publisher,
        "country": template.country,
        "language": template.language,
        "columns": template.columns,
        "page_size": template.page_size,
        "requirements": {
            "abstract": template.requires_abstract,
            "keywords": template.requires_keywords,
            "min_keywords": template.min_keywords,
            "max_keywords": template.max_keywords,
            "max_title_words": template.max_title_words,
            "abstract_word_limit": template.abstract_word_limit,
        },
        "formatting": {
            "section_numbering": template.section_numbering,
            "subsection_numbering": template.subsection_numbering,
        },
        "features": {
            "equations": template.supports_equations,
            "figures": template.supports_figures,
            "tables": template.supports_tables,
        },
        "notes": template.notes,
    }


def get_all_templates_info() -> List[dict]:
    return [get_template_info(code) for code in sorted(TEMPLATE_REGISTRY.keys())]
