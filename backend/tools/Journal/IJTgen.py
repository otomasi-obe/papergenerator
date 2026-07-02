"""
IJTgen.py — Generator DOCX untuk IJTech journal.
Template pakai custom styles: IJTechTITLE, IJTechaffiliation, IJTECHAbstract,
IJTechKeyword, IJTechHeadingSection, IJTechSubheading, IJTechText.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

BASE = Path(__file__).resolve().parent
TEMPLATE_DOCX = BASE / "IJT.docx"
TEMPLATE_JSON = BASE / "_template.json"
OUTPUT_DOCX = BASE / "IJT_output.docx"

def _format_reference(item) -> str:
    """Format a reference dict into a citation string."""
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return str(item).strip()
    text = item.get("text") or item.get("Text") or item.get("value")
    if text:
        return str(text).strip()
    parts = []
    authors = item.get("authors", [])
    if authors:
        parts.append(", ".join(str(a) for a in authors) if isinstance(authors, list) else str(authors))
    year = item.get("year")
    if year:
        parts.append(f"({year})")
    title = item.get("title", "")
    if title:
        parts.append(f'"{title},"')
    jname = item.get("journal") or item.get("conference") or ""
    if jname:
        parts.append(str(jname) + ",")
    vol = item.get("volume", "")
    if vol:
        parts.append(f"vol. {vol},")
    issue = item.get("issue", "")
    if issue:
        parts.append(f"no. {issue},")
    pages = item.get("pages", "")
    if pages:
        parts.append(f"pp. {pages},")
    doi = item.get("doi", "")
    if doi:
        parts.append(f"doi: {doi}.")
    url = item.get("url", "")
    if url:
        accessed = item.get("accessed", "")
        parts.append(f"[Online]. Available: {url}" + (f" [Accessed: {accessed}]." if accessed else "."))
    publisher = item.get("publisher", "")
    if publisher and not jname:
        location = item.get("location", "")
        parts.append(f"{location}: {publisher}." if location else f"{publisher}.")
    result = " ".join(str(p) for p in parts if p).strip()
    result = result.replace(" , ", ", ").replace(" .", ".")
    if result.endswith(","):
        result = result[:-1] + "."
    if not result.endswith("."):
        result = result + "."
    return result

def _roman_to_int(s: str) -> int:
    """Convert Roman numeral string to integer. Returns 0 on failure."""
    if not s:
        return 0
    values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    s = s.strip().upper()
    if not all(c in values for c in s):
        try:
            return int(s)
        except ValueError:
            return 0
    total = 0
    prev = 0
    for c in reversed(s):
        v = values[c]
        if v < prev:
            total -= v
        else:
            total += v
        prev = v
    return total


def _convert_roman_table_refs(text: str) -> str:
    """Convert Roman numeral table/figure refs in body text to Arabic.
    'Tabel I' → 'Table 1', 'Figure II' → 'Figure 2', 'Fig. III' → 'Figure 3'"""
    if not text:
        return text
    def _replace_roman(m):
        prefix = m.group(1).capitalize()
        if prefix in ('Tabel',):
            prefix = 'Table'
        elif prefix in ('Gambar', 'Fig'):
            prefix = 'Figure'
        roman = m.group(2).upper()
        num = _roman_to_int(roman)
        if num == 0:
            return m.group(0)
        return f"{prefix} {num}"
    # Match: Table/Tabel/Figure/Gambar/Fig/Fig. + Roman
    text = re.sub(r'\b(Table|Tabel|Figure|Gambar|Fig)[\.]?\s+([IVXLCDM]+)\b', _replace_roman, text, flags=re.IGNORECASE)
    return text


STYLE_TITLE = "IJTechTITLE"
STYLE_AUTHORS = "IJTechaffiliation"
STYLE_ABSTRACT = "IJTECHAbstract"
STYLE_KEYWORDS = "IJTechKeyword"
STYLE_HEAD1 = "IJTechHeadingSection"
STYLE_HEAD2 = "IJTechSubheading"
STYLE_BODY = "IJTechText"
STYLE_TBL_CAPTION = "IJTechText"
STYLE_FIG_CAPTION = "IJTechText"
STYLE_REFS = "IJTechText"
STYLE_AFFIL = "IJTechaffiliation"


def _is_book_ref(ref_text: str) -> bool:
    """Detect if a reference is a book (no journal vol/no/pp, has publisher/edition)."""
    has_journal = bool(re.search(r'\b(?:vol\.|vol\s|no\.|pp\.|pages?)\b', ref_text, re.IGNORECASE))
    has_publisher = bool(re.search(r'\b(?:Wiley|Springer|Press|Elsevier|CRC|MIT|Oxford|McGraw|Pearson|Prentice|IET|IEEE\s*Press|Publishing|Hall)\b', ref_text, re.IGNORECASE))
    has_edition = bool(re.search(r'(?:\d+(?:st|nd|rd|th)\s*ed|edition)', ref_text, re.IGNORECASE))
    return (has_publisher or has_edition) and not has_journal


def _parse_harvard_from_ieee(ref_text: str) -> dict:
    """Parse IEEE reference string → {author_short, year, doi, harvard_formatted}."""
    if not ref_text:
        return {"author_short": "", "year": "", "doi": "", "harvard_formatted": ""}

    # Strip IEEE numbering prefix like [1] or [12]
    ref_text = re.sub(r'^\[\d+\]\s*', '', ref_text.strip())

    # Extract year (4-digit). Look for standalone year near end,
    # avoiding page numbers (2036-2048) and DOI suffixes.
    # Use finditer to get accurate positions (rfind on duplicates broken)
    years_data = [(m.start(), m.group(0)) for m in re.finditer(r'(?:19|20)\d{2}', ref_text)]
    # Filter out years that are part of DOI suffixes or page ranges
    doi_pos = ref_text.lower().find('doi:') if 'doi:' in ref_text.lower() else len(ref_text)
    valid_years = []
    for pos, y in years_data:
        # Skip if year appears after 'doi:'
        if pos >= doi_pos:
            continue
        # Skip if year is part of a page range like "2036-2048"
        before = ref_text[max(0,pos-1):pos]
        after = ref_text[pos+4:pos+5] if pos+4 < len(ref_text) else ''
        if before == '-' or after == '-':
            continue
        valid_years.append((pos, y))
    if valid_years:
        year = sorted(valid_years)[-1][1]
    elif years_data:
        year = sorted(years_data)[-1][1]
    else:
        year = ""

    # Extract DOI
    doi_match = re.search(r'(?:doi[:\s]*\s*)?(10\.\d{4,}/[^\s,;"\']+)', ref_text, re.IGNORECASE)
    doi = doi_match.group(1).rstrip('.') if doi_match else ""

    # Extract first author surname
    # Pattern: "C. Lugaresi et al." or "M. A. Green et al." or "IRENA"
    m = re.match(r'^([A-Z]\.\s+)*(\w+)', ref_text)
    if m:
        first_author = m.group(2)
    else:
        first_author = ref_text.split(',')[0].strip().split()[-1] if ref_text else ""

    # Check for "et al."
    has_etal = "et al" in ref_text[:150]
    author_short = f"{first_author} et al." if has_etal else first_author

    # Build Harvard format: Surname, I. et al. (Year) 'Title', Journal, vol, pp. doi:...
    title_match = re.search(r'["\u201c](.+?)["\u201d]', ref_text)
    if title_match:
        raw_title = title_match.group(1).rstrip('.,')
        # Guard: if quoted text looks like author names, use no-quotes fallback
        if re.match(r'^[A-Z]\.\s+[A-Z]\.', raw_title) or len(raw_title) < 8:
            # Quoted text is probably an author name fragment, not a title
            # Strip all quote characters before splitting
            stripped = re.sub(r'["\u201c\u201d]', '', ref_text)
            parts = stripped.split(', ')
            # Detect multi-author: if parts[1] looks like author initials (with or without surname)
            if len(parts) > 2 and re.match(r'^[A-Z]\.\s*[A-Z]\.?\s*(\w+)?$', parts[1].strip()):
                before_title = f"{parts[0].strip()}, {parts[1].strip()}"
                title = parts[2].strip().rstrip('.,') if len(parts) > 2 else ""
                after_title = ', '.join(parts[3:]) if len(parts) > 3 else ""
            else:
                title = parts[1].strip().rstrip('.,') if len(parts) > 1 else ""
                before_title = parts[0].strip()
                after_title = ', '.join(parts[2:]) if len(parts) > 2 else ""
        else:
            title = raw_title
            before_title = ref_text[:title_match.start()].rstrip(', ')
            after_title = ref_text[title_match.end():]
    else:
        # No quotes found — use comma-separated fallback
        parts = ref_text.split(', ')
        # Detect multi-author via comma: parts[1] looks like author initials (with or without surname)
        if len(parts) > 2 and re.match(r'^[A-Z]\.\s*[A-Z]\.?\s*(\w+)?$', parts[1].strip()):
            before_title = f"{parts[0].strip()}, {parts[1].strip()}"
            title = parts[2].strip().rstrip('.,') if len(parts) > 2 else ""
            after_title = ', '.join(parts[3:]) if len(parts) > 3 else ""
        else:
            title = parts[1].strip().rstrip('.,') if len(parts) > 1 else ""
            before_title = parts[0].strip()
            after_title = ', '.join(parts[2:]) if len(parts) > 2 else ""

    # Format authors for Harvard — handle multi-author "X and Y" patterns
    author_match = re.match(r'^((?:[A-Z]\.\s*)+)(\w+)', before_title)
    if author_match:
        initials = author_match.group(1).strip()
        surname = author_match.group(2)
        authors_harvard = f"{surname}, {initials}"
        # Check for additional authors after first surname
        remaining = before_title[author_match.end():].strip()
        if remaining.startswith('and ') or remaining.startswith(' dan '):
            second_author = remaining[4:].strip()
            sa_match = re.match(r'^((?:[A-Z]\.\s*)+)(\w+)', second_author)
            if sa_match:
                sa_initials = sa_match.group(1).strip()
                sa_surname = sa_match.group(2)
                authors_harvard = f"{surname}, {initials} and {sa_surname}, {sa_initials}"
            else:
                authors_harvard = f"{surname}, {initials} and {second_author}"
        elif remaining.startswith(', '):
            # Multi-author with comma: "S. M. Sze, K. K. Ng"
            second_author = remaining[2:].strip()
            sa_match = re.match(r'^((?:[A-Z]\.\s*)+)(\w+)', second_author)
            if sa_match:
                sa_initials = sa_match.group(1).strip()
                sa_surname = sa_match.group(2)
                authors_harvard = f"{surname}, {initials} and {sa_surname}, {sa_initials}"
            else:
                authors_harvard = f"{surname}, {initials} and {second_author}"
    else:
        authors_harvard = before_title.rstrip('.')

    if has_etal and 'et al' not in authors_harvard.lower():
        authors_harvard += ' et al.'

    # Build journal part
    # Build journal part from after title
    journal_part = after_title.lstrip(', ').strip()
    # Remove DOI first, then remove trailing year
    journal_part = re.sub(r'doi[:\s]*10\.\d{4,}/[^\s,;"\']+\.?\s*', '', journal_part, flags=re.IGNORECASE).strip().rstrip('.,')
    journal_part = re.sub(r',?\s*(?:19|20)\d{2}\.?\s*$', '', journal_part).strip().rstrip('.,')

    # Build Harvard formatted reference
    is_book = _is_book_ref(ref_text)
    harvard_parts = [authors_harvard]
    if year:
        harvard_parts.append(f"({year})")
    if title:
        if is_book:
            harvard_parts.append(title)  # no quotes for books
        else:
            harvard_parts.append(f"'{title}'")  # quotes for journal articles
    if journal_part:
        harvard_parts.append(journal_part)
    if doi:
        harvard_parts.append(f"doi: {doi}")

    harvard_formatted = ' '.join(harvard_parts)
    if harvard_formatted.endswith(' .'):
        harvard_formatted = harvard_formatted[:-2] + '.'
    if not harvard_formatted.endswith('.'):
        harvard_formatted += '.'

    return {
        "author_short": author_short,
        "year": year,
        "doi": doi,
        "harvard_formatted": harvard_formatted,
    }


def _build_ref_index(references: list) -> dict:
    """Build index → harvard info map from reference list."""
    idx_map = {}
    for i, ref in enumerate(references, 1):
        text = ref if isinstance(ref, str) else (ref.get("text") or ref.get("Text") or "")
        idx_map[i] = _parse_harvard_from_ieee(text.strip())
    return idx_map


def _convert_citations_to_harvard(text: str, ref_index: dict) -> str:
    """Replace IEEE [N] citations with Harvard (Author, Year) format."""
    if not text or not ref_index:
        return text

    def _replace_cite(m):
        # Parse numbers from citation like [1], [1, 2, 3], [1-3]
        nums_str = m.group(1)
        nums = []
        for part in re.split(r'[,\s]+', nums_str):
            part = part.strip()
            if '-' in part:
                try:
                    a, b = part.split('-', 1)
                    nums.extend(range(int(a), int(b) + 1))
                except ValueError:
                    pass
            else:
                try:
                    nums.append(int(part))
                except ValueError:
                    pass

        harvard_parts = []
        for n in nums:
            info = ref_index.get(n)
            if info and info["author_short"]:
                if info["year"]:
                    harvard_parts.append(f"{info['author_short']}, {info['year']}")
                else:
                    harvard_parts.append(info["author_short"])
            else:
                harvard_parts.append(f"[{n}]")

        return "(" + "; ".join(harvard_parts) + ")"

    # Match [N], [N, M], [N-M] patterns
    text = re.sub(r'\[([\d,\s\-]+)\]', _replace_cite, text)

    # Merge consecutive citations: (A, Y), (B, Y) → (A, Y; B, Y)
    while ")(" in text:
        text = re.sub(r'\)\s*,\s*\(', '; ', text)
        text = re.sub(r'\)\s*\(', '; ', text)

    # Fix double parentheses: ((Author, Year)) → (Author, Year)
    text = re.sub(r'\(\((.*?)\)\)', r'(\1)', text)

    # Fix: a period right before citation should stay before, not inside
    # ([1].) → (Author, Year). — period after citation
    # Handle remaining double parens safely
    while '))' in text:
        text = re.sub(r'\((\([^()]*?\))\)', r'\1', text)

    return text


def _strip_latex(text: str) -> str:
    # Repair LLM streaming artifacts (collapsed integrals, bare math, etc.)
    try:
        from _math_omml import sanitize_llm_text_artifacts
        text = sanitize_llm_text_artifacts(text)
    except Exception:
        pass
    text = re.sub(r"\\\[.*?\\\]", "", text)
    text = re.sub(r"\\\(.*?\\\)", "", text)
    text = re.sub(r"\$([^$]*)\$", r"\1", text)
    text = re.sub(r"\\(mathrm|mathbf|mathit|text|mathsf|mathtt)\{([^}]*)\}", r"\2", text)
    text = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\\sqrt\{([^}]*)\}", r"√(\1)", text)
    text = re.sub(r"_\{([^}]*)\}", r"_\1", text)
    text = re.sub(r"\^\{([^}]*)\}", r"^\1", text)
    # Underscore/superscript before digits (e.g. X_1 → X₁, ^2 → ²)
    _sup_map = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
                '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹'}
    _sub_map = {'0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
                '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉'}
    text = re.sub(r'_(\d)', lambda m: _sub_map.get(m.group(1), m.group(0)), text)
    text = re.sub(r'\^(\d)', lambda m: _sup_map.get(m.group(1), m.group(0)), text)
    replacements = {
        r"\\approx": "≈",
        r"\\times": "×",
        r"\\cdot": "·",
        r"\\leq": "≤",
        r"\\geq": "≥",
        r"\\neq": "≠",
        r"\\infty": "∞",
        r"\\pm": "±",
        r"\\circ": "°",
        r"\\rightarrow": "→",
        r"\\leftarrow": "←",
        r"\\Rightarrow": "⇒",
        r"\\Leftarrow": "⇐",
        # Greek letters (all)
        r"\\alpha": "α", r"\\Alpha": "Α",
        r"\\beta": "β", r"\\Beta": "Β",
        r"\\gamma": "γ", r"\\Gamma": "Γ",
        r"\\delta": "δ", r"\\Delta": "Δ",
        r"\\epsilon": "ε", r"\\varepsilon": "ε",
        r"\\zeta": "ζ", r"\\Zeta": "Ζ",
        r"\\eta": "η", r"\\Eta": "Η",
        r"\\theta": "θ", r"\\vartheta": "ϑ", r"\\Theta": "Θ",
        r"\\iota": "ι", r"\\Iota": "Ι",
        r"\\kappa": "κ", r"\\Kappa": "Κ",
        r"\\lambda": "λ", r"\\Lambda": "Λ",
        r"\\mu": "μ", r"\\Mu": "Μ",
        r"\\nu": "ν", r"\\Nu": "Ν",
        r"\\xi": "ξ", r"\\Xi": "Ξ",
        r"\\pi": "π", r"\\varpi": "ϖ", r"\\Pi": "Π",
        r"\\rho": "ρ", r"\\varrho": "ϱ", r"\\Rho": "Ρ",
        r"\\sigma": "σ", r"\\varsigma": "ς", r"\\Sigma": "Σ",
        r"\\tau": "τ", r"\\Tau": "Τ",
        r"\\upsilon": "υ", r"\\Upsilon": "Υ",
        r"\\phi": "φ", r"\\varphi": "ϕ", r"\\Phi": "Φ",
        r"\\chi": "χ", r"\\Chi": "Χ",
        r"\\psi": "ψ", r"\\Psi": "Ψ",
        r"\\omega": "ω", r"\\Omega": "Ω",
        # Math operators
        r"\\sum": "Σ",
        r"\\int": "∫",
        r"\\partial": "∂",
        # Spacing
        r"\\quad": "  ",
        r"\\qquad": "    ",
        r"\\dots": "...",
        r"\\ldots": "...",
        r"\\left": "",
        r"\\right": "",
        r"\\overline": "",
        r"\\underline": "",
        r"\\hat": "",
        r"\\vec": "",
        r"\\bar": "",
        r"\\dot": "",
        r"\\displaystyle": "",
        r"\\,": " ",
        r"\\begin\{[^}]*\}": "",
        r"\\end\{[^}]*\}": "",
    }
    for pat, repl in replacements.items():
        text = re.sub(pat, repl, text)
    # LaTeX spacing → remove or space
    text = re.sub(r'\\;', '', text)
    text = re.sub(r'\\,', '', text)
    text = re.sub(r'\\:', '', text)
    text = re.sub(r'\\!', '', text)
    # Math function names → preserve content
    text = re.sub(r'\\cos\^\{(-?\d+)\}', r'cos\1', text)
    text = re.sub(r'\\cos\^(-?\d+)', r'cos\1', text)
    text = re.sub(r'\\cos\\b', 'cos', text)
    text = re.sub(r'\\sin\^\{(-?\d+)\}', r'sin\1', text)
    text = re.sub(r'\\sin\^(-?\d+)', r'sin\1', text)
    text = re.sub(r'\\sin\\b', 'sin', text)
    text = re.sub(r'\\tan\^\{(-?\d+)\}', r'tan\1', text)
    text = re.sub(r'\\tan\^(-?\d+)', r'tan\1', text)
    text = re.sub(r'\\tan\\b', 'tan', text)
    text = re.sub(r'\\log\^\{(-?\d+)\}', r'log\1', text)
    text = re.sub(r'\\log\^(-?\d+)', r'log\1', text)
    text = re.sub(r'\\log\\b', 'log', text)
    text = re.sub(r'\\exp\^\{(-?\d+)\}', r'exp\1', text)
    text = re.sub(r'\\exp\\b', 'exp', text)
    text = re.sub(r'\\max\\b', 'max', text)
    text = re.sub(r'\\min\\b', 'min', text)
    text = re.sub(r'\\lim\\b', 'lim', text)
    text = re.sub(r'\\det\\b', 'det', text)
    text = re.sub(r'\\operatorname\{([^}]*)\}', r'\1', text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"[{}]", "", text)
    return text


def load_json() -> dict:
    return json.loads(TEMPLATE_JSON.read_text(encoding="utf-8"))


def clear_body_keep_sectprs(doc):
    """Hapus body content tapi PRESERVE semua sectPr (inline + final).
    SectPr inline ada di pPr dari paragraf - kita keep paragraf yang
    punya sectPr saja.
    """
    body = doc.element.body
    preserved_inline_sectprs = []
    for child in list(body):
        if child.tag == qn("w:p"):
            ppr = child.find(qn("w:pPr"))
            if ppr is not None:
                sectpr_inline = ppr.find(qn("w:sectPr"))
                if sectpr_inline is not None:
                    # Preserve sectPr inline (extract dari pPr, simpan sebagai
                    # paragraf kosong dengan pPr yang punya sectPr)
                    preserved_inline_sectprs.append(child)
                    # Hapus runs dari paragraf ini, keep pPr+sectPr
                    for run in child.findall(qn("w:r")):
                        child.remove(run)
                    continue
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)
    return preserved_inline_sectprs


def insert_before_sectpr(doc, sectpr_para):
    """Helper untuk insert paragraph baru SEBELUM paragraf yang punya sectPr inline."""
    new_p = OxmlElement("w:p")
    sectpr_para.addprevious(new_p)
    return new_p


def _set_para_style(paragraph, style_name: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    for old in ppr.findall(qn("w:pStyle")):
        ppr.remove(old)
    pstyle = OxmlElement("w:pStyle")
    pstyle.set(qn("w:val"), style_name)
    ppr.insert(0, pstyle)


def _add_run(
    paragraph,
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    superscript: bool = False,
    font: str = None,
    size_pt: float = None,
):
    run = paragraph.add_run(text)
    if bold:
        run.bold = True
    if italic:
        run.italic = True
    if superscript:
        run.font.superscript = True
        # Also set smaller size to ensure visual rendering
        run.font.size = Pt(6.5)
    if font:
        run.font.name = font
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.append(rFonts)
        rFonts.set(qn("w:ascii"), font)
        rFonts.set(qn("w:hAnsi"), font)
        rFonts.set(qn("w:cs"), font)
    if size_pt:
        run.font.size = Pt(size_pt)
    return run


def _embed_inline_sectpr(doc, num_cols: int, col_space_tw: int = 288):
    """Embed sectPr inline (untuk transition antar section layout)."""
    p = doc.add_paragraph()
    ppr = p._p.get_or_add_pPr()
    sectpr = OxmlElement("w:sectPr")
    pgsz = OxmlElement("w:pgSz")
    pgsz.set(qn("w:w"), "11907")
    pgsz.set(qn("w:h"), "16839")
    sectpr.append(pgsz)
    pgmar = OxmlElement("w:pgMar")
    pgmar.set(qn("w:top"), "1008")
    pgmar.set(qn("w:right"), "936")
    pgmar.set(qn("w:bottom"), "1008")
    pgmar.set(qn("w:left"), "936")
    pgmar.set(qn("w:header"), "187")
    pgmar.set(qn("w:footer"), "141")
    pgmar.set(qn("w:gutter"), "0")
    sectpr.append(pgmar)
    cols = OxmlElement("w:cols")
    if num_cols > 1:
        cols.set(qn("w:num"), str(num_cols))
        cols.set(qn("w:space"), str(col_space_tw))
    else:
        cols.set(qn("w:space"), "720")
    sectpr.append(cols)
    ppr.append(sectpr)


def add_title(doc, data):
    title_text = (data.get("title") or "Paper Title Goes Here").strip()
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_TITLE)
    _add_run(p, title_text, bold=True)


def add_authors(doc, data):
    authors = data.get("authors") or [
        {"name": "Author Name", "affiliation": "Department, University"}
    ]
    corr_author = data.get("corresponding_author") or {}
    # Auto-fallback: if no explicit corresponding_author, use first author
    if not corr_author and authors:
        first = authors[0]
        corr_author = {
            "name": first.get("name", ""),
            "email": first.get("email", data.get("email", "")),
            "phone": first.get("phone", data.get("phone", "")),
            "fax": first.get("fax", data.get("fax", "")),
        }
        # Only use if at least name + email present
        if not corr_author.get("email"):
            corr_author = {}

    # Default phone/fax for IJT template (Diponegoro University)
    DEFAULT_PHONE = "+62-24-7055-1111"
    DEFAULT_FAX = "+62-24-7055-2222"
    if corr_author:
        if not corr_author.get("phone"):
            corr_author["phone"] = DEFAULT_PHONE
        if not corr_author.get("fax"):
            corr_author["fax"] = DEFAULT_FAX

    affil_map = {}
    for author in authors:
        affil = (author.get("affiliation") or "").strip()
        if affil and affil not in affil_map:
            affil_map[affil] = len(affil_map) + 1

    p = doc.add_paragraph()
    _set_para_style(p, STYLE_AUTHORS)
    for i, author in enumerate(authors):
        if i > 0:
            connector = ", and " if i == len(authors) - 1 else ", "
            _add_run(p, connector)
        name = (author.get("name") or "Author Name").strip()
        _add_run(p, name)
        idx = affil_map.get((author.get("affiliation") or "").strip())
        if idx:
            _add_run(p, str(idx), superscript=True)

    # Affiliation lines
    for affil, idx in sorted(affil_map.items(), key=lambda x: x[1]):
        p = doc.add_paragraph()
        _set_para_style(p, STYLE_AFFIL)
        _add_run(p, f"{idx}. {affil}")

    # Corresponding author details
    if corr_author:
        p = doc.add_paragraph()
        _set_para_style(p, STYLE_AFFIL)
        parts = []
        if corr_author.get("name"):
            parts.append(f"*Corresponding author: {corr_author['name']}")
        if corr_author.get("email"):
            parts.append(f"Email: {corr_author['email']}")
        if corr_author.get("phone"):
            parts.append(f"Tel: {corr_author['phone']}")
        if corr_author.get("fax"):
            parts.append(f"Fax: {corr_author['fax']}")
        if parts:
            _add_run(p, "; ".join(parts))


def add_abstract(doc, data):
    abstract = (data.get("abstract") or "Abstract text goes here.").strip()
    abstract = _strip_latex(abstract)

    # Ensure structured abstract labels are present
    labels = ["Background", "Purpose", "Methods?", "Results?", "Conclusion"]
    # Only add labels if none are already present
    if not any(f"({i+1}) {lbl}" in abstract for i, lbl in enumerate(labels) if lbl != "Methods?"):
        # Try to insert labels before common transition phrases
        abstract = _structure_abstract(abstract)

    p = doc.add_paragraph()
    _set_para_style(p, STYLE_ABSTRACT)
    _add_run(p, "Abstract ", bold=True)
    _add_run(p, abstract)


def _structure_abstract(text: str) -> str:
    """Insert structured labels into an abstract paragraph.

    Approach: search for semantic patterns to find position of each label,
    then insert labels in order. If pattern not found, fall back to
    even sentence distribution.
    """
    all_labels = ['(1) Background:', '(2) Purpose/Aim:', '(3) Methods:', '(4) Results:', '(5) Conclusions:']

    # 1. Strip all existing labels from text
    clean = re.sub(r'\(\d+\)\s*[^:]+\s*:\s*', '', text).strip()
    for lbl in all_labels:
        bare = lbl.split(')', 1)[-1].strip().rstrip(':')
        clean = re.sub(r'(?:\s+|^)' + re.escape(bare) + r'\s*:\s*', ' ', clean).strip()
    if not clean:
        return text

    # 2. Find positions for each label using patterns
    patterns = {
        '(2) Purpose/Aim:': r'(?i)\b(?:This\s+(?:study|paper|research|work)\s+(?:aims|proposes|presents|introduces|investigates|focuses|examines)|Kami\s+(?:membangun|mengusulkan|mengembangkan|bertujuan|merancang)|Penelitian\s+(?:ini|bertujuan|mengusulkan|membangun)|Research\s+gap|Knowledge\s+gap)',
        '(3) Methods:': r'(?i)\b(?:Metode?\s+(?:yang\s+)?(?:digunakan|diterapkan|meliputi|mencakup)|Metodologi|Pendekatan\s+penelitian|(?:Sistem|Arsitektur)\s+(?:yang\s+)?(?:dibangun|diusulkan|digunakan)|Kami\s+(?:menggunakan|menerapkan|melakukan|mengadopsi|menjalankan)|(?:The\s+(?:method|methodology|approach|system|framework|model|process))|We\s+(?:employ|use|develop|design|propose|implement|conduct|adopt))',
        '(4) Results:': r'(?i)\b(?:Hasil\s+(?:menunjukkan|uji\s+coba|eksperimen|simulasi|pengujian)|(?:Hasil|Pengujian|Eksperimen|Evaluasi)\s+(?:menunjukkan|mengungkapkan|mendapatkan|mencatat|memperoleh)|(?:Skor|Akurasi|F1|Presisi|Latensi)\s+(?:mencapai|rata-rata|tercatat)|The\s+(?:results|findings|outcome|simulation|experiment|evaluation|analysis)\s+(?:show|demonstrate|indicate|reveal|confirm|suggest|yield))',
        '(5) Conclusions:': r'(?i)\b(?:Kesimpulan(?:nya)?|Sebagai\s+(?:kesimpulan|penutup)|(?:Dampak|Implikasi)\s+(?:dari\s+)?(?:penelitian|studi)\s+(?:ini)|(?:Penelitian|Paper|Studi|Pekerjaan)\s+(?:ini\s+)?(?:menyimpulkan|menunjukkan|membuktikan|membuka\s+jalan|berkontribusi)|In\s+(?:conclusion|summary)|The\s+(?:study|paper|research|work|finding)\s+(?:concludes|suggests|demonstrates))',
    }

    matches = {}
    for label, pattern in patterns.items():
        m = re.search(pattern, clean)
        if m:
            matches[label] = m.start()

    # 3. Insert labels at sentence boundaries only
    result = '(1) Background: '
    search_start = 0

    for i, label in enumerate(all_labels[1:], 2):
        if label in matches:
            raw_pos = matches[label]
            if raw_pos > search_start:
                # Find the nearest sentence boundary AFTER the match position
                # This ensures labels never split a sentence mid-word
                sentence_starts = [m.end() for m in re.finditer(r'(?<=[.!?])\s+', clean)]
                label_pos = raw_pos
                for sp in sentence_starts:
                    if sp >= raw_pos:
                        label_pos = sp
                        break
                if label_pos > search_start and label_pos <= len(clean):
                    result += clean[search_start:label_pos]
                    result += f'{label} '
                    search_start = label_pos

    # Append remaining text
    if search_start < len(clean):
        result += clean[search_start:]

    # 4. Add missing labels by distributing to unlabeled sentences
    missing = [lbl for lbl in all_labels if lbl not in result]
    if missing:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', result) if s.strip()]
        labeled_indices = {i for i, s in enumerate(sentences) if re.match(r'^\(\d+\)', s)}
        unlabeled_idx = [i for i, s in enumerate(sentences) if i not in labeled_indices]
        if unlabeled_idx and len(unlabeled_idx) >= len(missing):
            step = max(1, len(unlabeled_idx) // len(missing))
            new_sentences = []
            mi = 0
            for i, s in enumerate(sentences):
                if i in labeled_indices:
                    new_sentences.append(s)
                elif mi < len(missing):
                    if i % max(1, step) == 0:
                        new_sentences.append(f'{missing[min(mi, len(missing)-1)]} {s}')
                        mi += 1
                    else:
                        new_sentences.append(s)
                else:
                    new_sentences.append(s)
            result = ' '.join(new_sentences)
        else:
            result = result + ' ' + ' '.join(missing)

    return result


def add_keywords(doc, data):
    kw = data.get("keywords") or []
    if not kw:
        return
    # IJT template: Keywords:, max 5, alphabetical, capitalize first letter, semicolons
    kw = [k.strip() for k in kw if k.strip()][:5]
    kw = sorted(kw, key=str.lower)
    kw = [k[0].upper() + k[1:] if k else k for k in kw]
    text = "; ".join(kw)
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_KEYWORDS)
    _add_run(p, "Keywords:", bold=True, italic=True)
    _add_run(p, " " + text, italic=True)


def add_section_heading(doc, title: str):
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_HEAD1)
    _add_run(p, title.upper())


def add_subsection_heading(doc, title: str):
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_HEAD2)
    _add_run(p, title)


def add_body_text(doc, text: str, ref_index: dict = None):
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_BODY)
    # First-line indent 0.5 cm via XML (paragraph_format gets overridden by style)
    ppr = p._p.get_or_add_pPr()
    existing_ind = ppr.find(qn("w:ind"))
    if existing_ind is None:
        ind = OxmlElement("w:ind")
        ppr.append(ind)
    else:
        ind = existing_ind
    ind.set(qn("w:firstLine"), "283")  # 0.5 cm in half-points → ~0.5cm
    text = _strip_latex(text)
    text = _convert_roman_table_refs(text)
    if ref_index:
        text = _convert_citations_to_harvard(text, ref_index)
    _add_run(p, text)


def _set_table_borders(table, pattern="full"):
    tbl = table._tbl
    tbl_pr = tbl.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    existing = tbl_pr.find(qn("w:tblBorders"))
    if existing is not None:
        tbl_pr.remove(existing)
    tbl_borders = OxmlElement("w:tblBorders")
    if pattern == "full":
        visible = {"top", "left", "bottom", "right", "insideH", "insideV"}
    elif pattern == "horizontal":
        visible = {"top", "bottom", "insideH"}
    else:
        visible = set()
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        if side in visible:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "4")
        else:
            el.set(qn("w:val"), "nil")
        tbl_borders.append(el)
    tbl_pr.append(tbl_borders)


def add_table(doc, table_data: dict):
    num_raw = str(table_data.get("TableNumber") or "1").strip()
    # Convert Roman numeral or Arabic
    num = _roman_to_int(num_raw) if num_raw else 1
    if num == 0:
        num = num_raw  # fallback to raw string if conversion fails
    num_str = str(num)
    title = (table_data.get("Title") or "Table title").strip()
    headers = table_data.get("Headers") or ["Col1", "Col2"]
    rows = table_data.get("Rows") or [["Data", "Data"]]

    cap = doc.add_paragraph()
    _set_para_style(cap, STYLE_TBL_CAPTION)
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(cap, f"Table {num_str}", bold=True)
    _add_run(cap, ". " + title)

    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(table, pattern="full")

    for col_idx, header in enumerate(headers):
        cell = table.rows[0].cells[col_idx]
        cell.text = ""
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(para, str(header), bold=True)

    for row_idx, row_data in enumerate(rows, start=1):
        for col_idx, value in enumerate(row_data[: len(headers)]):
            cell = table.rows[row_idx].cells[col_idx]
            cell.text = ""
            para = cell.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_run(para, str(value))


def add_figure(doc, fig_data: dict):
    image_number = str(fig_data.get("ImageNumber") or "1").strip()
    title = (fig_data.get("Title") or "").strip()
    prompt = (fig_data.get("Prompt") or "").strip()
    path_text = (fig_data.get("Path") or "").strip()

    image_path = None
    if path_text:
        cand = Path(path_text)
        if not cand.is_absolute():
            cand = BASE / path_text
        if cand.is_file():
            image_path = cand

    if image_path:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(image_path), width=Cm(7.5))
    else:
        prompt_body = prompt if prompt else f"Figure {image_number}"
        if title:
            placeholder_text = f"[PROMPT UNTUK AI GAMBAR: {title}. {prompt_body}]"
        else:
            placeholder_text = f"[PROMPT UNTUK AI GAMBAR: {prompt_body}]"
        table = doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = table.cell(0, 0)
        cell.text = ""
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(para, placeholder_text, italic=True)

    if title:
        cap = doc.add_paragraph()
        _set_para_style(cap, STYLE_FIG_CAPTION)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(cap, f"Figure {image_number}. ", bold=True)
        _add_run(cap, title)


def add_formula(doc, formula_data: dict):
    num = str(formula_data.get("FormulaNumber") or "").strip()
    text = (formula_data.get("text") or formula_data.get("latex") or "E = mc^2").strip()
    p = doc.add_paragraph()
    _set_para_style(p, STYLE_BODY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _omml_done = False
    try:
        from _math_omml import append_omml_math as _omml_fn
        _lx = (formula_data.get("latex") or "")
        _omml_done = bool(str(_lx or "").strip()) and _omml_fn(p, _lx)
    except Exception:
        _omml_done = False
    if not _omml_done:
        _add_run(p, _strip_latex(text), italic=True)
    if num:
        _add_run(p, f"\t({num})")


def process_content_item(doc, item: dict, ref_index: dict = None):
    if not isinstance(item, dict):
        return
    item_id = (item.get("id") or "").lower()
    if item_id in ("text", ""):
        text = (item.get("text") or "").strip()
        if text:
            add_body_text(doc, text, ref_index)
    elif item_id in ("gambar", "image", "figure"):
        add_figure(doc, item)
    elif item_id in ("tabel", "table"):
        add_table(doc, item)
    elif item_id in ("rumus", "formula", "equation"):
        add_formula(doc, item)


def process_section(doc, section_data: dict, top_level: bool = True, ref_index: dict = None):
    if not isinstance(section_data, dict):
        return
    title = (section_data.get("title") or "").strip()
    if title:
        if top_level:
            add_section_heading(doc, title)
        else:
            add_subsection_heading(doc, title)

    content = section_data.get("content")
    if isinstance(content, list):
        for item in content:
            process_content_item(doc, item, ref_index)

    for key in section_data:
        if key in ("title", "content"):
            continue
        if key.startswith("section"):
            process_section(doc, section_data[key], top_level=False, ref_index=ref_index)


def add_references(doc, data, ref_index: dict = None):
    refs = data.get("references") or {}
    if isinstance(refs, list):
        refs = {"title": "REFERENCES", "content": refs}
    title = (refs.get("title") or "REFERENCES").strip()
    items = [_format_reference(r) for r in (refs.get("content") or refs.get("items") or [])]
    items = [t for t in items if t] or ["Author, A., Title of Article. Journal Name, vol. X, no. Y, pp. Z, Year. doi:10.xxxx/xxxxx"]

    # Build original index → ref text mapping for proper lookup
    orig_ref_map = {i + 1: items[i] for i in range(len(items))}

    # Sort alphabetically by first author surname
    if ref_index:
        def _sort_key(ref_text):
            # Find original index via orig_ref_map
            for orig_i, orig_ref in orig_ref_map.items():
                if orig_ref == ref_text:
                    info = ref_index.get(orig_i, {})
                    return info.get("author_short", ref_text).lower()
            return ref_text.lower()
        try:
            items = sorted(items, key=_sort_key)
        except (ValueError, TypeError):
            pass

    # Build original index for each item (stable across sort)
    item_orig_idx = {}
    for ref in items:
        for orig_i, orig_ref in orig_ref_map.items():
            if ref == orig_ref and orig_i not in item_orig_idx.values():
                item_orig_idx[ref] = orig_i
                break

    p_title = doc.add_paragraph()
    _set_para_style(p_title, STYLE_HEAD1)
    _add_run(p_title, title.upper())

    # IJT minimum 36 references warning
    if len(items) < 36:
        warn_p = doc.add_paragraph()
        _set_para_style(warn_p, STYLE_REFS)
        _add_run(warn_p, f"[⚠️ Note: Only {len(items)} references provided. IJT requires minimum 36 references for Regular Article. Add {36 - len(items)} more references to comply with template requirements.]", italic=True)

    for ref in items:
        # Use Harvard formatted version from ref_index if available
        ref_out = ref
        if ref_index:
            orig_i = item_orig_idx.get(ref, 0)
            info = ref_index.get(orig_i, {})
            harvard = info.get("harvard_formatted", "")
            if harvard:
                ref_out = harvard
            elif "doi" not in ref_out.lower():
                doi = info.get("doi", "")
                if doi and doi not in ref_out:
                    ref_out = ref_out.rstrip('.') + f". doi: {doi}"
        else:
            # Remove IEEE numbering if no ref_index
            ref_out = re.sub(r'^\[\d+\]\s*', '', ref_out)
        rp = doc.add_paragraph()
        _set_para_style(rp, STYLE_REFS)
        _add_run(rp, str(ref_out))


def add_required_sections(doc):
    """Add IJT-mandated sections after References."""
    sections = [
        ("ACKNOWLEDGEMENTS",
         "The authors would like to express their gratitude to [institution/funding body] for their support in this research."),
        ("Author Contributions",
         "Author 1 contributed to conceptualization, methodology, and writing – original draft. "
         "Author 2 contributed to data curation, formal analysis, and visualization. "
         "All authors have read and agreed to the published version of the manuscript."),
        ("Conflict of Interest",
         "The authors declare no conflict of interest."),
        ("Supplementary Materials",
         "Not applicable."),
        ("Declaration of AI",
         "The authors declare that no generative AI or AI-assisted technologies were used in the writing of this manuscript."),
    ]
    for title, text in sections:
        p_title = doc.add_paragraph()
        _set_para_style(p_title, STYLE_HEAD1)
        _add_run(p_title, title.upper())

        rp = doc.add_paragraph()
        _set_para_style(rp, STYLE_BODY)
        _add_run(rp, text)


def generate():
    shutil.copy2(TEMPLATE_DOCX, OUTPUT_DOCX)
    doc = Document(str(OUTPUT_DOCX))

    # Preserve inline sectPrs (yang punya headerReference/footerReference dari template)
    clear_body_keep_sectprs(doc)

    data = load_json()

    # Build Harvard citation index from references
    ref_raw = data.get("references") or {}
    if isinstance(ref_raw, list):
        ref_items = [t for t in ref_raw if t]
    else:
        ref_items = [_format_reference(r) for r in (ref_raw.get("content") or ref_raw.get("items") or [])]
        ref_items = [t for t in ref_items if t]
    ref_index = _build_ref_index(ref_items)

    # Section 0 (sebelum sectPr inline #0): Title, Authors, Abstract, Keywords
    add_title(doc, data)
    add_authors(doc, data)
    add_abstract(doc, data)
    add_keywords(doc, data)

    # Body content (akan masuk antara preserved sectprs atau setelah-nya)
    for i in range(1, 30):
        key = f"section{i}"
        if key in data:
            process_section(doc, data[key], top_level=True, ref_index=ref_index)

    # References — sorted alphabetically, Harvard style
    add_references(doc, data, ref_index)

    # Required sections per IJT template
    add_required_sections(doc)

    doc.save(str(OUTPUT_DOCX))
    print(f"Generated: {OUTPUT_DOCX}")
    return str(OUTPUT_DOCX)


def build_document(json_path: str, output_path: str) -> str:
    """Wrapper for external calls."""
    global TEMPLATE_JSON, OUTPUT_DOCX
    import shutil
    # Copy input JSON to template location
    shutil.copy(json_path, str(TEMPLATE_JSON))
    OUTPUT_DOCX = Path(output_path)
    return generate()

if __name__ == "__main__":
    generate()
