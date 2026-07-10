"""
Shared OMML formula helper for all journal generators.
Usage:
    from _formula_omml import add_omml_formula
    add_omml_formula(doc, latex="...", number="1", CFG=None)
"""
import re
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from lxml import etree


def add_omml_formula(doc, latex, number="", CFG=None,
                     before_pt=10, after_pt=8, alignment="center",
                     font_body="Times New Roman", size_body=11,
                     max_width_cm=None, line_spacing_tw=360,
                     font_cs=None, font_eastAsia=None):
    """Insert formula as OMML (real Word equation object) + optional (number).
    Falls back to plain text if conversion fails.
    
    If max_width_cm is provided, auto-scales font size so formula fits within target width.
    Target: 70% of column width (user-specified for formulas).
    """
    if not latex:
        return False

    # Strip $...$ delimiters
    cleaned = re.sub(r'\$([^$]+)\$', r'\1', latex)
    cleaned = cleaned.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    cleaned = cleaned.strip()
    if not cleaned:
        return False

    # Auto-scale font if formula would overflow column width
    effective_size = size_body
    if max_width_cm is not None and max_width_cm > 0:
        # Estimate formula width: chars * size * 0.38 / 28.35 (Cambria Math, tight)
        est_cm = len(cleaned) * size_body * 0.38 / 28.35
        if est_cm > max_width_cm:
            # Reduce font size proportionally (with 10% padding)
            scale = (max_width_cm / est_cm) * 0.9
            effective_size = max(3.0, size_body * scale)  # minimum 3pt
    effective_halfpt = int(effective_size * 2)

    try:
        from latex2mathml.converter import convert as latex2mathml
        from mathml2omml import convert as mathml2omml

        mathml_str = latex2mathml(cleaned)
        omml_str = mathml2omml(mathml_str)

        # Fix mathml2omml bug: groupChrPr incorrectly closed by </m:groupChr>
        omml_str = re.sub(r'(<m:groupChrPr>.*?</m:)groupChr>', r'\1groupChrPr>', omml_str)

        MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
        omml_wrapped = f'<m:oMathPara xmlns:m="{MATH_NS}">{omml_str}</m:oMathPara>'
        oMathPara = etree.fromstring(omml_wrapped)

        body = doc._element.body
        final_sectpr = body.find(qn("w:sectPr"))

        # Build paragraph element
        p_elem = etree.Element(qn("w:p"))
        pPr = etree.SubElement(p_elem, qn("w:pPr"))

        # Default run properties (inherited by formula runs for sizing)
        para_rPr = etree.SubElement(pPr, qn("w:rPr"))
        rFonts = etree.SubElement(para_rPr, qn("w:rFonts"))
        rFonts.set(qn("w:ascii"), font_body)
        rFonts.set(qn("w:hAnsi"), font_body)
        sz = etree.SubElement(para_rPr, qn("w:sz"))
        sz.set(qn("w:val"), str(effective_halfpt))
        szCs = etree.SubElement(para_rPr, qn("w:szCs"))
        szCs.set(qn("w:val"), str(effective_halfpt))

        # Alignment
        jc = etree.SubElement(pPr, qn("w:jc"))
        jc.set(qn("w:val"), alignment)

        # Spacing
        spacing = etree.SubElement(pPr, qn("w:spacing"))
        spacing.set(qn("w:before"), str(int(before_pt * 20)))   # twips
        spacing.set(qn("w:after"), str(int(after_pt * 20)))     # twips
        spacing.set(qn("w:line"), str(line_spacing_tw))
        spacing.set(qn("w:lineRule"), "auto")

        # Insert OMML
        p_elem.append(oMathPara)

        # Number
        if number:
            run = etree.SubElement(p_elem, qn("w:r"))
            rPr = etree.SubElement(run, qn("w:rPr"))
            rFonts = etree.SubElement(rPr, qn("w:rFonts"))
            rFonts.set(qn("w:ascii"), font_body)
            rFonts.set(qn("w:hAnsi"), font_body)
            if font_cs:
                rFonts.set(qn("w:cs"), font_cs)
            if font_eastAsia:
                rFonts.set(qn("w:eastAsia"), font_eastAsia)
            sz = etree.SubElement(rPr, qn("w:sz"))
            sz.set(qn("w:val"), str(int(size_body * 2)))
            szCs = etree.SubElement(rPr, qn("w:szCs"))
            szCs.set(qn("w:val"), str(int(size_body * 2)))
            t = etree.SubElement(run, qn("w:t"))
            t.set(qn("xml:space"), "preserve")
            t.text = f"    ({number})"

        # Insert before final sectPr (or append)
        if final_sectpr is not None:
            final_sectpr.addprevious(p_elem)
        else:
            body.append(p_elem)

        return True

    except Exception as e:
        # Fallback: plain text (checker will flag as missing but at least visible)
        p = doc.add_paragraph()
        if alignment == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif alignment == "right":
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        display = cleaned
        if number:
            display = f"{cleaned}    ({number})"
        run = p.add_run(display)
        run.font.name = "Cambria Math"
        if CFG:
            run.font.size = Pt(CFG.get("size_body", size_body))
        else:
            run.font.size = Pt(size_body)
        run.font.italic = True
        return False
