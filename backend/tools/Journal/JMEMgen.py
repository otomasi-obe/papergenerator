"""
JMEMgen.py - generate a JMEM paper from JSON using the original JMEM.docx.

The generator copies the source template first so header/footer/package parts
remain intact, rewrites the front matter using paragraph samples taken from
the original document, then renders the manuscript body from JSON.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import string
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from docx.text.paragraph import Paragraph
from lxml import etree

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
JSON_PATH = BASE_DIR / "_PLC-MediapipeID.json"
TEMPLATE_PATH = BASE_DIR / "JMEM.docx"
JOURNAL_NAME = TEMPLATE_PATH.stem

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
MAX_FIGURE_WIDTH_CM = 14.5
EQUATION_TAB_RIGHT_PT = 450.0
CAPTION_FONT_PT = 10.0
TABLE_FONT_PT = 10.0
BODY_FONT_NAME = "Times New Roman"

XSL_CANDIDATES = [
    BASE_DIR / "MML2OMML.XSL",
    ROOT_DIR / "MML2OMML.XSL",
    Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"),
]

_XSLT = None
_DRAWING_ID_NEXT = 1
_DOC_PR_PATTERN = re.compile(r'<wp:docPr\b[^>]*\bid="(\d+)"')


@dataclass
class RenderState:
    figure_number: int = 0
    table_number: int = 0
    equation_number: int = 0


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

def _clone_ppr(paragraph: Paragraph) -> etree._Element | None:
    ppr = paragraph._p.find(qn("w:pPr"))
    return copy.deepcopy(ppr) if ppr is not None else None


def _clone_run_rpr(paragraph: Paragraph, run_index: int = 0) -> etree._Element | None:
    runs = paragraph._p.findall(qn("w:r"))
    if not runs:
        return None
    run_index = max(0, min(run_index, len(runs) - 1))
    rpr = runs[run_index].find(qn("w:rPr"))
    return copy.deepcopy(rpr) if rpr is not None else None


def _clone_run_elements(paragraph: Paragraph, indexes: list[int]) -> list[etree._Element]:
    runs = paragraph._p.findall(qn("w:r"))
    result: list[etree._Element] = []
    for index in indexes:
        if 0 <= index < len(runs):
            result.append(copy.deepcopy(runs[index]))
    return result


def _first_nonempty_run_rpr(paragraph: Paragraph) -> etree._Element | None:
    runs = paragraph._p.findall(qn("w:r"))
    for run in runs:
        texts = [node.text or "" for node in run.findall(qn("w:t"))]
        if "".join(texts).strip():
            rpr = run.find(qn("w:rPr"))
            return copy.deepcopy(rpr) if rpr is not None else None
    if runs:
        rpr = runs[0].find(qn("w:rPr"))
        return copy.deepcopy(rpr) if rpr is not None else None
    return None


def _apply_sample_ppr(paragraph: Paragraph, sample_ppr: etree._Element | None) -> None:
    current = paragraph._p.find(qn("w:pPr"))
    if current is not None:
        paragraph._p.remove(current)
    if sample_ppr is not None:
        paragraph._p.insert(0, copy.deepcopy(sample_ppr))


def _apply_sample_rpr(run, sample_rpr: etree._Element | None) -> None:
    current = run._r.find(qn("w:rPr"))
    if current is not None:
        run._r.remove(current)
    if sample_rpr is not None:
        run._r.insert(0, copy.deepcopy(sample_rpr))


def _clear_paragraph(paragraph: Paragraph) -> None:
    element = paragraph._element
    for child in list(element):
        if child.tag != qn("w:pPr"):
            element.remove(child)


def _remove_paragraph(paragraph: Paragraph) -> None:
    element = paragraph._element
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _insert_paragraph_before(
    reference_paragraph: Paragraph, sample_ppr: etree._Element | None = None
) -> Paragraph:
    paragraph_el = OxmlElement("w:p")
    reference_paragraph._p.addprevious(paragraph_el)
    paragraph = Paragraph(paragraph_el, reference_paragraph._parent)
    if sample_ppr is not None:
        _apply_sample_ppr(paragraph, sample_ppr)
    return paragraph


def _append_sample_run(
    paragraph: Paragraph,
    text: str,
    sample_rpr: etree._Element | None,
    *,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    superscript: bool = False,
):
    run = paragraph.add_run(text)
    _apply_sample_rpr(run, sample_rpr)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if underline is not None:
        run.underline = underline
    if superscript:
        run.font.superscript = True
    return run


def _append_cloned_runs(paragraph: Paragraph, run_elements: list[etree._Element]) -> None:
    for run_el in run_elements:
        paragraph._p.append(copy.deepcopy(run_el))


def _new_sampled_paragraph(doc: Document, sample_ppr: etree._Element | None) -> Paragraph:
    paragraph = doc.add_paragraph()
    if sample_ppr is not None:
        _apply_sample_ppr(paragraph, sample_ppr)
    return paragraph


def _set_run_font_name(run, font_name: str) -> None:
    run.font.name = font_name
    rpr = run._r.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), font_name)


def _format_caption_run(run, *, bold: bool = False, italic: bool = False) -> None:
    _set_run_font_name(run, BODY_FONT_NAME)
    run.font.size = Pt(CAPTION_FONT_PT)
    run.bold = bold
    run.italic = italic


def _format_table_run(run, *, bold: bool = False, italic: bool = False) -> None:
    _set_run_font_name(run, BODY_FONT_NAME)
    run.font.size = Pt(TABLE_FONT_PT)
    run.bold = bold
    run.italic = italic


def _set_cell_border(
    cell, edge: str, *, value: str = "single", size: str = "4", color: str = "000000"
) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    border = tc_borders.find(qn(f"w:{edge}"))
    if border is None:
        border = OxmlElement(f"w:{edge}")
        tc_borders.append(border)
    border.set(qn("w:val"), value)
    border.set(qn("w:sz"), size)
    border.set(qn("w:space"), "0")
    border.set(qn("w:color"), color)


def _set_full_cell_borders(cell) -> None:
    for edge in ("top", "left", "bottom", "right"):
        _set_cell_border(cell, edge)


def _normalize_text_commands(text: str) -> str:
    # Repair LLM streaming artifacts (collapsed integrals, bare math, etc.)
    try:
        from _math_omml import sanitize_llm_text_artifacts
        text = sanitize_llm_text_artifacts(text)
    except Exception:
        pass
    text = re.sub(r'\\\\n(?![a-z])', '\n', text)
    # Convert Markdown bold/italic to \b..\b / \i..\i toggle format
    text = re.sub(r"\*\*(.+?)\*\*", r"\\b\1\\b", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+?)\*", r"\\i\1\\i", text)
    return text


def _iter_rich_tokens(text: str):
    normalized = _normalize_text_commands(text)
    buffer: list[str] = []
    bold = False
    italic = False
    underline = False
    index = 0

    def flush_buffer():
        nonlocal buffer
        content = "".join(buffer)
        buffer = []
        if content:
            yield {
                "kind": "text",
                "value": content,
                "bold": bold,
                "italic": italic,
                "underline": underline,
            }

    while index < len(normalized):
        char = normalized[index]
        if char == "\n":
            yield from flush_buffer()
            yield {"kind": "linebreak"}
            index += 1
            continue
        if char == "\\" and index + 1 < len(normalized):
            command = normalized[index + 1]
            if command == "\\":
                buffer.append("\\")
                index += 2
                continue
            if command == "b":
                next_char = normalized[index + 2] if index + 2 < len(normalized) else ""
                if next_char.islower():
                    buffer.append("\b")
                    index += 2
                    continue
                yield from flush_buffer()
                bold = not bold
                index += 2
                continue
            if command == "i":
                next_char = normalized[index + 2] if index + 2 < len(normalized) else ""
                if next_char.islower():
                    buffer.append("\i")
                    index += 2
                    continue
                yield from flush_buffer()
                italic = not italic
                index += 2
                continue
            if command == "u":
                next_char = normalized[index + 2] if index + 2 < len(normalized) else ""
                if next_char.islower():
                    buffer.append("\\u")
                    index += 2
                    continue
                yield from flush_buffer()
                underline = not underline
                index += 2
                continue
        if char == "$":
            closing = normalized.find("$", index + 1)
            if closing != -1:
                yield from flush_buffer()
                formula = normalized[index + 1 : closing]
                if formula:
                    yield {"kind": "math", "value": formula}
                index = closing + 1
                continue
        buffer.append(char)
        index += 1

    yield from flush_buffer()


def _set_rpr_math_defaults(rpr: etree._Element, half_points: int = 24) -> None:
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        rfonts.set(qn(f"w:{attr}"), "Cambria Math")

    sz = rpr.find(qn("w:sz"))
    if sz is None:
        sz = OxmlElement("w:sz")
        rpr.append(sz)
    sz.set(qn("w:val"), str(half_points))

    szcs = rpr.find(qn("w:szCs"))
    if szcs is None:
        szcs = OxmlElement("w:szCs")
        rpr.append(szcs)
    szcs.set(qn("w:val"), str(half_points))


def _normalize_omml_math(omml: etree._Element, half_points: int = 24) -> etree._Element:
    for math_run in omml.findall(f".//{{{MATH_NS}}}r"):
        rpr = math_run.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            math_run.insert(0, rpr)
        _set_rpr_math_defaults(rpr, half_points=half_points)

    for ctrl_pr in omml.findall(f".//{{{MATH_NS}}}ctrlPr"):
        rpr = ctrl_pr.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            ctrl_pr.insert(0, rpr)
        _set_rpr_math_defaults(rpr, half_points=half_points)

    return omml


def _get_xslt():
    global _XSLT
    if _XSLT is not None:
        return _XSLT
    for candidate in XSL_CANDIDATES:
        try:
            if candidate.exists():
                _XSLT = etree.XSLT(etree.parse(str(candidate)))
                return _XSLT
        except Exception:
            continue
    _XSLT = False
    return _XSLT


def _latex_to_omml(latex: str):
    try:
        import latex2mathml.converter
    except Exception:
        return None
    xslt = _get_xslt()
    if not xslt:
        return None
    try:
        mathml = latex2mathml.converter.convert(latex)
        root = etree.fromstring(mathml.encode("utf-8"))
        return xslt(root).getroot()
    except Exception:
        return None


def _append_inline_math(paragraph: Paragraph, latex: str) -> bool:
    omml = _latex_to_omml(latex)
    if omml is None:
        return False
    omml = _normalize_omml_math(omml, half_points=24)
    tag = omml.tag.split("}")[-1] if "}" in omml.tag else omml.tag
    if tag in ("oMath", "oMathPara"):
        paragraph._p.append(omml)
    else:
        wrapper = etree.fromstring(f'<m:oMath xmlns:m="{MATH_NS}"/>')
        wrapper.append(omml)
        paragraph._p.append(wrapper)
    return True


def _append_rich_text(paragraph: Paragraph, text: str, sample_rpr: etree._Element | None) -> None:
    for token in _iter_rich_tokens(text):
        if token["kind"] == "linebreak":
            paragraph.add_run().add_break()
            continue
        if token["kind"] == "math":
            if not _append_inline_math(paragraph, token["value"]):
                run = _append_sample_run(paragraph, token["value"], sample_rpr)
                run.italic = True
            continue
        _append_sample_run(
            paragraph,
            token["value"],
            sample_rpr,
            bold=True if token["bold"] else None,
            italic=True if token["italic"] else None,
            underline=True if token["underline"] else None,
        )


def _split_body_blocks(text: str) -> list[str]:
    normalized = _normalize_text_commands(text).replace("\r\n", "\n").replace("\r", "\n")
    parts = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    return parts or [normalized.strip()]


def _initialize_drawing_ids(doc: Document) -> None:
    global _DRAWING_ID_NEXT
    max_id = 0
    for part in doc.part.package.parts:
        part_name = str(getattr(part, "partname", ""))
        if not part_name.endswith(".xml"):
            continue
        try:
            xml_text = part.blob.decode("utf-8", errors="ignore")
        except Exception:
            continue
        for match in _DOC_PR_PATTERN.finditer(xml_text):
            max_id = max(max_id, int(match.group(1)))
    _DRAWING_ID_NEXT = max_id + 1


def _next_drawing_id() -> int:
    global _DRAWING_ID_NEXT
    drawing_id = _DRAWING_ID_NEXT
    _DRAWING_ID_NEXT += 1
    return drawing_id


def _assign_inline_drawing_id(inline) -> None:
    drawing_id = _next_drawing_id()
    inline._inline.docPr.set("id", str(drawing_id))
    for node in inline._inline.xpath(".//*[local-name()='cNvPr']"):
        node.set("id", str(drawing_id))


def _resolve_path(path_text: str, json_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    json_relative = json_path.parent / path
    if json_relative.exists():
        return json_relative

    # Also try the image/ subdirectory next to the JSON (correct for preview: user/<username>/<paper_id>/image/)
    image_relative = json_path.parent / "image" / path
    if image_relative.exists():
        return image_relative

    # Derive paper_id correctly: json_path.parent is usually paper_dir (user/<username>/<paper_id>/)
    # But for preview/export it might be in export/ subfolder
    if json_path.parent.name == "export":
        paper_id = json_path.parent.parent.name
    else:
        paper_id = json_path.parent.name

    # Try safe_paper_image_dir for canonical user/<username>/<paper_id>/image/ location
    try:
        from tools.editor.utils import safe_paper_image_dir
        img_dir = safe_paper_image_dir(paper_id)
        if img_dir and img_dir.exists():
            # Try direct match
            candidate = img_dir / path
            if candidate.is_file():
                return candidate
            # Try with just the filename
            fname = path.name
            candidate = img_dir / fname
            if candidate.is_file():
                return candidate
            # Extension-insensitive match (JSON may say .png but disk has .jpg)
            stem = Path(fname).stem
            for ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif'):
                candidate = img_dir / (stem + ext)
                if candidate.is_file():
                    return candidate
            # Glob fallback
            for match in img_dir.glob(f"{stem}.*"):
                if match.is_file():
                    return match
            # Also try img_dir/image/ subdirectory
            if img_dir.name != "image":
                img_dir2 = img_dir / "image"
                if img_dir2.is_dir():
                    candidate = img_dir2 / path
                    if candidate.is_file():
                        return candidate
                    candidate = img_dir2 / fname
                    if candidate.is_file():
                        return candidate
                    for ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif'):
                        candidate = img_dir2 / (stem + ext)
                        if candidate.is_file():
                            return candidate
                    for match in img_dir2.glob(f"{stem}.*"):
                        if match.is_file():
                            return match
    except Exception:
        pass

    return BASE_DIR / path



def _restore_template_parts(output_path: Path, template_path: Path) -> None:
    prefixes = (
        "word/header",
        "word/footer",
        "word/_rels/header",
        "word/_rels/footer",
    )
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with (
        zipfile.ZipFile(template_path, "r") as template_zip,
        zipfile.ZipFile(output_path, "r") as output_zip,
        zipfile.ZipFile(temp_path, "w") as temp_zip,
    ):
        template_names = set(template_zip.namelist())
        for info in output_zip.infolist():
            if (
                any(info.filename.startswith(prefix) for prefix in prefixes)
                and info.filename in template_names
            ):
                data = template_zip.read(info.filename)
            else:
                data = output_zip.read(info.filename)
            temp_zip.writestr(info, data)
    temp_path.replace(output_path)


def _clean_reference_text(text: str) -> str:
    return re.sub(r"^\s*\[\d+\]\s*", "", text).strip()


def _placeholder_text(label: str) -> str:
    placeholders = {
        "title": "TITLE IS NOT PROVIDED IN THE SOURCE JSON",
        "abstract_id": "Abstrak tidak tersedia pada sumber JSON. Ganti placeholder ini dengan abstrak final dalam Bahasa Indonesia.",
        "abstract_en": "English abstract is not provided in the source JSON. Replace this placeholder with the final English abstract.",
        "keywords": "keyword-1; keyword-2; keyword-3; keyword-4; keyword-5",
        "body": "Content is not provided in the source JSON. Replace this placeholder with the final manuscript content.",
        "figure": "Figure content is not provided in the source JSON.",
        "table": "Table data is not provided in the source JSON.",
        "equation": "Equation content is not provided in the source JSON.",
        "reference": "Reference details are not provided in the source JSON.",
        "subsection": "This subsection contains the material shown below.",
    }
    return placeholders[label]


def _abstract_text_id(config: dict) -> str:
    for key in ("abstractID", "abstrak", "abstract"):
        value = str(config.get(key, "")).strip()
        if value:
            return value
    return _placeholder_text("abstract_id")


def _abstract_text_en(config: dict) -> str:
    for key in ("abstractEN", "abstractEnglish", "englishAbstract"):
        value = str(config.get(key, "")).strip()
        if value:
            return value
    return _placeholder_text("abstract_en")


def _author_entries(config: dict) -> list[dict]:
    authors = config.get("authors", [])
    if not isinstance(authors, list):
        return []

    entries = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        entries.append(
            {
                "name": str(author.get("name", "")).strip(),
                "affiliation": str(author.get("affiliation", "")).strip(),
                "location": str(author.get("location", "")).strip(),
                "email": str(author.get("email", "")).strip(),
            }
        )
    return [entry for entry in entries if entry["name"]]


def _group_affiliations(authors: list[dict]) -> tuple[list[tuple[int, str]], list[int]]:
    groups: list[tuple[int, str]] = []
    author_indexes: list[int] = []
    seen: dict[str, int] = {}
    next_index = 1

    for author in authors:
        parts = [
            part for part in (author.get("affiliation", ""), author.get("location", "")) if part
        ]
        text = (
            ", ".join(parts).strip()
            or "Affiliation information is not provided in the source JSON."
        )
        key = text.lower()
        if key not in seen:
            seen[key] = next_index
            groups.append((next_index, text))
            next_index += 1
        author_indexes.append(seen[key])

    if not groups:
        groups = [(1, "Affiliation information is not provided in the source JSON.")]
        author_indexes = [1] * max(1, len(authors))

    return groups, author_indexes


def _rewrite_prefixed_paragraph(
    paragraph: Paragraph,
    *,
    label_text: str,
    label_rpr: etree._Element | None,
    separator_runs: list[etree._Element],
    body_text: str,
    body_rpr: etree._Element | None,
) -> None:
    _clear_paragraph(paragraph)
    _append_sample_run(paragraph, label_text, label_rpr)
    _append_cloned_runs(paragraph, separator_runs)
    if not separator_runs:
        _append_sample_run(paragraph, " ", body_rpr)
    _append_rich_text(paragraph, body_text, body_rpr)


def _render_front_matter(doc: Document, config: dict, samples: dict) -> None:
    paragraphs = doc.paragraphs
    title_paragraph = paragraphs[0]
    author_paragraph = paragraphs[1]
    address_insert_before = paragraphs[5]
    address_paragraphs = [paragraphs[2], paragraphs[3], paragraphs[4]]
    email_paragraph = paragraphs[5]
    abstract_id_paragraph = paragraphs[6]
    abstract_id_extra_paragraph = paragraphs[7]
    abstract_en_paragraph = paragraphs[8]
    abstract_en_extra_paragraph = paragraphs[9]
    keywords_paragraph = paragraphs[10]

    title_text = str(config.get("title", "")).strip() or _placeholder_text("title")
    _clear_paragraph(title_paragraph)
    _append_sample_run(title_paragraph, title_text, samples["title_rpr"])

    authors = _author_entries(config)
    if not authors:
        authors = [{"name": "Author Name", "affiliation": "", "location": "", "email": ""}]

    affiliations, author_affiliation_indexes = _group_affiliations(authors)
    email_letters = [
        string.ascii_lowercase[index] if index < len(string.ascii_lowercase) else f"e{index + 1}"
        for index in range(len(authors))
    ]

    _clear_paragraph(author_paragraph)
    for author_index, author in enumerate(authors):
        if author_index > 0:
            _append_sample_run(author_paragraph, ", ", samples["author_rpr"])
        _append_sample_run(author_paragraph, author["name"], samples["author_rpr"])
        _append_sample_run(
            author_paragraph,
            str(author_affiliation_indexes[author_index]),
            samples["author_rpr"],
            superscript=True,
        )
        _append_sample_run(author_paragraph, ",", samples["author_rpr"], superscript=True)
        _append_sample_run(
            author_paragraph, email_letters[author_index], samples["author_rpr"], superscript=True
        )

    target_address_paragraphs = list(address_paragraphs)
    while len(target_address_paragraphs) < len(affiliations):
        target_address_paragraphs.append(
            _insert_paragraph_before(address_insert_before, samples["address_ppr"])
        )

    for index, paragraph in enumerate(target_address_paragraphs):
        _clear_paragraph(paragraph)
        if index < len(affiliations):
            aff_index, text = affiliations[index]
            _append_sample_run(paragraph, f"{aff_index}", samples["address_rpr"])
            _append_sample_run(paragraph, text, samples["address_rpr"])

    _clear_paragraph(email_paragraph)
    email_parts = []
    for letter, author in zip(email_letters, authors):
        email_value = author.get("email") or f"{letter}@example.com"
        email_parts.append(f"{letter} {email_value}")
    email_text = ", ".join(email_parts)
    if email_text:
        email_text += " (corresponding author)"
    _append_sample_run(
        email_paragraph,
        email_text or "a author@example.com (corresponding author)",
        samples["email_rpr"],
    )

    _rewrite_prefixed_paragraph(
        abstract_id_paragraph,
        label_text="Abstrak",
        label_rpr=samples["abstract_id_label_rpr"],
        separator_runs=samples["abstract_id_separator_runs"],
        body_text=_abstract_text_id(config),
        body_rpr=samples["abstract_id_body_rpr"],
    )
    _clear_paragraph(abstract_id_extra_paragraph)

    _rewrite_prefixed_paragraph(
        abstract_en_paragraph,
        label_text="Abstract.",
        label_rpr=samples["abstract_en_label_rpr"],
        separator_runs=samples["abstract_en_separator_runs"],
        body_text=_abstract_text_en(config),
        body_rpr=samples["abstract_en_body_rpr"],
    )
    _clear_paragraph(abstract_en_extra_paragraph)

    raw_keywords = config.get("keywords", [])
    if isinstance(raw_keywords, list):
        keywords = [str(item).strip() for item in raw_keywords if str(item).strip()]
    elif isinstance(raw_keywords, str) and raw_keywords.strip():
        keywords = [part.strip() for part in raw_keywords.split(",") if part.strip()]
    else:
        keywords = []
    keyword_text = "; ".join(keywords) if keywords else _placeholder_text("keywords")
    _rewrite_prefixed_paragraph(
        keywords_paragraph,
        label_text="Keywords:",
        label_rpr=samples["keywords_label_rpr"],
        separator_runs=samples["keywords_separator_runs"],
        body_text=keyword_text,
        body_rpr=samples["keywords_body_rpr"],
    )


def _add_section_heading(doc: Document, title: str, samples: dict) -> None:
    paragraph = _new_sampled_paragraph(doc, samples["section_heading_ppr"])
    _append_sample_run(
        paragraph, title.strip() or "Untitled Section", samples["section_heading_rpr"]
    )


def _add_first_body_paragraph(doc: Document, text: str, samples: dict) -> None:
    blocks = _split_body_blocks(text.strip() or _placeholder_text("body"))
    first = _new_sampled_paragraph(doc, samples["paragraph_first_ppr"])
    _append_rich_text(first, blocks[0], samples["paragraph_first_body_rpr"])
    for block in blocks[1:]:
        paragraph = _new_sampled_paragraph(doc, samples["paragraph_other_ppr"])
        _append_rich_text(paragraph, block, samples["paragraph_other_rpr"])


def _add_other_body_paragraph(doc: Document, text: str, samples: dict) -> None:
    for block in _split_body_blocks(text.strip() or _placeholder_text("body")):
        paragraph = _new_sampled_paragraph(doc, samples["paragraph_other_ppr"])
        _append_rich_text(paragraph, block, samples["paragraph_other_rpr"])


def _add_runin_subsection_paragraph(doc: Document, title: str, text: str, samples: dict) -> None:
    blocks = _split_body_blocks(text.strip() or _placeholder_text("subsection"))
    heading_text = title.strip() or "Untitled Subsection"
    if not heading_text.endswith((".", ":")):
        heading_text += "."

    first = _new_sampled_paragraph(doc, samples["paragraph_first_ppr"])
    _append_sample_run(first, heading_text, samples["paragraph_first_heading_rpr"])
    _append_sample_run(first, " ", samples["paragraph_first_body_rpr"])
    _append_rich_text(first, blocks[0], samples["paragraph_first_body_rpr"])

    for block in blocks[1:]:
        paragraph = _new_sampled_paragraph(doc, samples["paragraph_other_ppr"])
        _append_rich_text(paragraph, block, samples["paragraph_other_rpr"])


def _coerce_figure_number(item: dict, state: RenderState) -> str:
    raw = str(item.get("ImageNumber") or "").strip()
    if raw:
        try:
            state.figure_number = max(state.figure_number, int(raw))
        except ValueError:
            pass
        return raw
    state.figure_number += 1
    return str(state.figure_number)


def _coerce_table_number(item: dict, state: RenderState) -> str:
    raw = str(item.get("TableNumber") or "").strip()
    if raw:
        state.table_number += 1
        return raw
    state.table_number += 1
    return str(state.table_number)


def _coerce_equation_number(item: dict, state: RenderState) -> str:
    raw = str(item.get("FormulaNumber") or item.get("NumberingOrLetter") or "").strip()
    if raw:
        try:
            state.equation_number = max(state.equation_number, int(raw))
        except ValueError:
            pass
        return raw
    state.equation_number += 1
    return str(state.equation_number)


def _add_figure(doc: Document, item: dict, json_path: Path, state: RenderState) -> None:

    figure_number = _coerce_figure_number(item, state)
    title = str(item.get("Title") or "").strip() or "Untitled figure"
    path_text = str(item.get("Path") or "").strip()
    width_cm = item.get("WidthCm")
    try:
        width_cm = float(width_cm) if width_cm is not None else MAX_FIGURE_WIDTH_CM
    except (TypeError, ValueError):
        width_cm = MAX_FIGURE_WIDTH_CM
    width_cm = min(max(width_cm, 1.0), MAX_FIGURE_WIDTH_CM)

    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(3)
    paragraph.paragraph_format.space_after = Pt(3)

    image_added = False
    if path_text:
        image_path = _resolve_path(path_text, json_path)
        if image_path.is_file():
            inline = paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))
            _assign_inline_drawing_id(inline)
            image_added = True

    if not image_added:
        run = paragraph.add_run(f"[{_placeholder_text('figure')}]")
        _set_run_font_name(run, BODY_FONT_NAME)
        run.font.size = Pt(10.0)
        run.italic = True

    caption = doc.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.space_before = Pt(3)
    caption.paragraph_format.space_after = Pt(6)
    run = caption.add_run(f"Fig. {figure_number}. {title}")
    _format_caption_run(run)


def _add_equation(doc: Document, item: dict, samples: dict, state: RenderState) -> None:
    formula = str(item.get("latex") or item.get("text") or "").strip() or _placeholder_text(
        "equation"
    )
    equation_number = _coerce_equation_number(item, state)

    paragraph = _new_sampled_paragraph(doc, samples["equation_ppr"])
    paragraph.paragraph_format.space_before = Pt(3)
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.tab_stops.add_tab_stop(
        Pt(EQUATION_TAB_RIGHT_PT), WD_TAB_ALIGNMENT.RIGHT
    )

    if not _append_inline_math(paragraph, formula):
        run = _append_sample_run(paragraph, formula, samples["equation_rpr"])
        run.italic = True
    _append_sample_run(paragraph, " ", samples["equation_rpr"])
    paragraph.add_run().add_tab()
    _append_sample_run(paragraph, f"({equation_number})", samples["equation_rpr"])


def _fill_table_cell(cell, text: str, *, bold: bool = False) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    _format_table_run(run, bold=bold)
    _set_full_cell_borders(cell)


def _add_table(doc: Document, item: dict, state: RenderState) -> None:
    table_number = _coerce_table_number(item, state)
    title = str(item.get("Title") or item.get("title") or "").strip() or "Untitled table"
    headers = list(item.get("Headers", []) or item.get("headers", []))
    rows = list(item.get("Rows", []) or item.get("rows", []))

    if not headers:
        headers = ["Column 1"]
        rows = [[_placeholder_text("table")]]
    elif not rows:
        rows = [[_placeholder_text("table")] + [""] * (len(headers) - 1)]

    caption = doc.add_paragraph()
    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.space_before = Pt(6)
    caption.paragraph_format.space_after = Pt(3)
    run = caption.add_run(f"Table {table_number}. {title}")
    _format_caption_run(run, bold=True)

    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))

    _set_table_full_borders(table)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    for col_idx, header in enumerate(headers):
        _fill_table_cell(table.rows[0].cells[col_idx], str(header), bold=True)

    for row_idx, row_data in enumerate(rows, start=1):
        row_values = row_data if isinstance(row_data, list) else [str(row_data)]
        padded_values = [
            str(row_values[col_idx]) if col_idx < len(row_values) else ""
            for col_idx in range(len(headers))
        ]
        for col_idx, value in enumerate(padded_values):
            _fill_table_cell(table.rows[row_idx].cells[col_idx], value)


def _render_content_item(
    doc: Document, item: dict, json_path: Path, samples: dict, state: RenderState
) -> None:
    item_id = str(item.get("id") or "").strip().lower()
    if item_id == "text":
        return
    if item_id in {"gambar", "figure", "image"}:
        _add_figure(doc, item, json_path, state)
    elif item_id in {"rumus", "formula", "equation"}:
        _add_equation(doc, item, samples, state)
    elif item_id in {"tabel", "table"}:
        _add_table(doc, item, state)


def _render_content_sequence(
    doc: Document,
    content: list,
    json_path: Path,
    samples: dict,
    state: RenderState,
    *,
    subsection_title: str | None = None,
) -> None:
    first_text_pending = subsection_title is None
    runin_pending = subsection_title

    for item in content:
        if isinstance(item, dict) and str(item.get("id") or "").strip().lower() == "text":
            text = str(item.get("text") or "").strip() or _placeholder_text("body")
            if runin_pending is not None:
                _add_runin_subsection_paragraph(doc, runin_pending, text, samples)
                runin_pending = None
                first_text_pending = False
            elif first_text_pending:
                _add_first_body_paragraph(doc, text, samples)
                first_text_pending = False
            else:
                _add_other_body_paragraph(doc, text, samples)
            continue

        if isinstance(item, str) and item.strip():
            if runin_pending is not None:
                _add_runin_subsection_paragraph(doc, runin_pending, item, samples)
                runin_pending = None
                first_text_pending = False
            elif first_text_pending:
                _add_first_body_paragraph(doc, item, samples)
                first_text_pending = False
            else:
                _add_other_body_paragraph(doc, item, samples)
            continue

        if isinstance(item, dict):
            if runin_pending is not None:
                _add_runin_subsection_paragraph(
                    doc, runin_pending, _placeholder_text("subsection"), samples
                )
                runin_pending = None
                first_text_pending = False
            _render_content_item(doc, item, json_path, samples, state)

    if runin_pending is not None:
        _add_runin_subsection_paragraph(
            doc, runin_pending, _placeholder_text("subsection"), samples
        )
    elif first_text_pending:
        _add_first_body_paragraph(doc, _placeholder_text("body"), samples)


def _section_keys(config: dict) -> list[str]:
    return sorted(
        [key for key in config if key.startswith("section") and key[7:].isdigit()],
        key=lambda key: int(key[7:]),
    )


def _subsection_keys(section_key: str, section: dict) -> list[str]:
    return [
        key
        for key, value in section.items()
        if isinstance(value, dict) and key.startswith(section_key) and key != section_key
    ]


def _render_sections(
    doc: Document, config: dict, json_path: Path, samples: dict, state: RenderState
) -> None:
    for section_key in _section_keys(config):
        section = config.get(section_key)
        if not isinstance(section, dict):
            continue

        title = str(section.get("title") or "").strip() or "Untitled Section"
        _add_section_heading(doc, title, samples)

        content = section.get("content", [])
        if isinstance(content, list) and content:
            _render_content_sequence(doc, content, json_path, samples, state)
        elif isinstance(content, str) and content.strip():
            _render_content_sequence(doc, [content], json_path, samples, state)

        subsection_keys = _subsection_keys(section_key, section)
        for subsection_key in subsection_keys:
            subsection = section.get(subsection_key)
            if not isinstance(subsection, dict):
                continue
            subsection_title = str(subsection.get("title") or "").strip() or "Untitled Subsection"
            subsection_content = subsection.get("content", [])
            if isinstance(subsection_content, list):
                _render_content_sequence(
                    doc,
                    subsection_content,
                    json_path,
                    samples,
                    state,
                    subsection_title=subsection_title,
                )
            elif isinstance(subsection_content, str):
                _render_content_sequence(
                    doc,
                    [subsection_content],
                    json_path,
                    samples,
                    state,
                    subsection_title=subsection_title,
                )
            else:
                _render_content_sequence(
                    doc,
                    [],
                    json_path,
                    samples,
                    state,
                    subsection_title=subsection_title,
                )


def _add_references(doc: Document, config: dict, samples: dict) -> None:
    references = config.get("references", {})
    title = "References"
    items: list = []
    if isinstance(references, dict):
        title = str(references.get("title") or title).strip() or title
        items = list(references.get("content") or references.get("items") or [])

    heading = _new_sampled_paragraph(doc, samples["reference_heading_ppr"])
    _append_sample_run(heading, title, samples["reference_heading_rpr"])

    if not items:
        items = [_placeholder_text("reference")]

    for index, item in enumerate(items, start=1):
        paragraph = _new_sampled_paragraph(doc, samples["reference_item_ppr"])
        if isinstance(item, dict):
            text = str_format_reference(item)
        else:
            text = str(item).strip()
        clean_text = _clean_reference_text(text) or _placeholder_text("reference")
        _append_sample_run(paragraph, f"[{index}] ", samples["reference_item_rpr"])
        _append_rich_text(paragraph, clean_text, samples["reference_item_rpr"])


def _capture_samples(doc: Document) -> dict:
    paragraphs = doc.paragraphs
    if len(paragraphs) < 44:
        raise RuntimeError("JMEM template structure is shorter than expected.")

    return {
        "title_rpr": _first_nonempty_run_rpr(paragraphs[0]),
        "author_rpr": _first_nonempty_run_rpr(paragraphs[1]),
        "address_ppr": _clone_ppr(paragraphs[2]),
        "address_rpr": _first_nonempty_run_rpr(paragraphs[2]),
        "email_rpr": _first_nonempty_run_rpr(paragraphs[5]),
        "abstract_id_label_rpr": _clone_run_rpr(paragraphs[6], 0),
        "abstract_id_separator_runs": _clone_run_elements(paragraphs[6], [1]),
        "abstract_id_body_rpr": _clone_run_rpr(paragraphs[6], 2),
        "abstract_en_label_rpr": _clone_run_rpr(paragraphs[8], 0),
        "abstract_en_separator_runs": _clone_run_elements(paragraphs[8], [1]),
        "abstract_en_body_rpr": _clone_run_rpr(paragraphs[8], 2),
        "keywords_label_rpr": _clone_run_rpr(paragraphs[10], 0),
        "keywords_separator_runs": [],
        "keywords_body_rpr": _clone_run_rpr(paragraphs[10], 1),
        "section_heading_ppr": _clone_ppr(paragraphs[14]),
        "section_heading_rpr": _first_nonempty_run_rpr(paragraphs[14]),
        "paragraph_first_ppr": _clone_ppr(paragraphs[18]),
        "paragraph_first_heading_rpr": _clone_run_rpr(paragraphs[18], 0),
        "paragraph_first_body_rpr": _clone_run_rpr(paragraphs[18], 1),
        "paragraph_other_ppr": _clone_ppr(paragraphs[19]),
        "paragraph_other_rpr": _first_nonempty_run_rpr(paragraphs[19]),
        "equation_ppr": _clone_ppr(paragraphs[28]),
        "equation_rpr": _first_nonempty_run_rpr(paragraphs[28]),
        "reference_heading_ppr": _clone_ppr(paragraphs[33]),
        "reference_heading_rpr": _first_nonempty_run_rpr(paragraphs[33]),
        "reference_item_ppr": _clone_ppr(paragraphs[43]),
        "reference_item_rpr": _first_nonempty_run_rpr(paragraphs[43]),
    }


def build_document(
    json_path: Path = JSON_PATH,
    output_path: Path | None = None,
    template_path: Path = TEMPLATE_PATH,

) -> Path:
    config = json.loads(Path(json_path).read_text(encoding="utf-8"))
    final_output = (
        Path(output_path)
        if output_path is not None
        else Path(json_path).parent / f"{JOURNAL_NAME}_output.docx"
    )
    final_output.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy(str(template_path), str(final_output))
    doc = Document(str(final_output))
    samples = _capture_samples(doc)
    _initialize_drawing_ids(doc)

    for paragraph in list(doc.paragraphs[11:]):
        _remove_paragraph(paragraph)

    _render_front_matter(doc, config, samples)

    state = RenderState()
    _render_sections(doc, config, Path(json_path), samples, state)
    _add_references(doc, config, samples)

    doc.save(str(final_output))
    _restore_template_parts(final_output, Path(template_path))
    print(f"Generated: {final_output}")
    return final_output


def build_pdf(json_path: Path, pdf_path: Path, template_path=None) -> Path:
    """Build a PDF for this journal template from a paper JSON.

    Calls build_document() to produce a .docx, then converts to .pdf
    via LibreOffice headless.  Final PDF is written to ``pdf_path``.
    """
    from ._render_pdf import build_pdf_from_builder
    return build_pdf_from_builder(build_document, json_path, pdf_path, template_path)

def main() -> None:
    if len(sys.argv) >= 2:
        json_arg = Path(sys.argv[1])
        output_arg = Path(sys.argv[2]) if len(sys.argv) >= 3 else None
        template_arg = Path(sys.argv[3]) if len(sys.argv) >= 4 else TEMPLATE_PATH
        result = build_document(json_arg, output_arg, template_arg)
        print(f"Selesai: {result}")
        return

    json_files = sorted(
        path
        for path in BASE_DIR.glob("*.json")
        if path.name.lower() not in {"package.json", "tsconfig.json", "settings.json"}
    )
    for json_file in json_files:
        build_document(json_file)


def _set_table_full_borders(table) -> None:
    """Pastikan tabel punya border tegas/visible (val=single, sz=4 = 0.5pt).

    Dipanggil setelah doc.add_table() supaya tabel data keliatan di Word.
    Auto-injected oleh _fix_table_borders.py untuk lulus audit border check.
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tbl = table._tbl
    tbl_pr = tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        tbl.insert(0, tbl_pr)
    tbl_borders = tbl_pr.find(qn("w:tblBorders"))
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = tbl_borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tbl_borders.append(el)
        el.set(qn("w:val"), "single" if edge in ("top", "bottom", "insideH") else "nil")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")


if __name__ == "__main__":
    main()