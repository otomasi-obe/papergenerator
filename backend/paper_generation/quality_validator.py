"""
Academic Paper Quality Validation
==================================
Validates paper quality across multiple dimensions:
- Structure (IMRAD compliance, section completeness)
- Citations (count, distribution, validity)
- Content (abstract quality, methodology clarity)
- Formatting (consistency, academic style)
"""

import logging
import re
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


class QualityReport:
    """Quality validation report."""
    
    def __init__(self):
        self.score = 0  # 0-100
        self.issues = []  # List of issues found
        self.warnings = []  # List of warnings
        self.suggestions = []  # List of improvement suggestions
        self.blocking = []  # Blocking issues that prevent publication
        
    def to_dict(self):
        return {
            "score": self.score,
            "issues": self.issues,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "blocking": self.blocking,
            "ready_for_export": len(self.blocking) == 0,
        }


def validate_paper_quality(paper_data: Dict, paper_type: Optional[str] = None) -> QualityReport:
    """Validate paper quality across all dimensions.
    
    Args:
        paper_data: Paper data dict with sections, references, etc.
        paper_type: Optional paper type (Research Paper, Case Study, etc.)
        
    Returns:
        QualityReport with score and issues
    """
    report = QualityReport()
    
    # Run all validation checks
    _validate_structure(paper_data, paper_type, report)
    _validate_abstract(paper_data, report)
    _validate_sections(paper_data, report)
    _validate_citations(paper_data, report)
    _validate_references(paper_data, report)
    _validate_figures_tables(paper_data, report)
    
    # Calculate overall score
    report.score = _calculate_score(report)
    
    return report


def _validate_structure(paper_data: Dict, paper_type: Optional[str], report: QualityReport):
    """Validate paper structure."""
    sections = paper_data.get("sections", [])
    
    # Check minimum sections
    if len(sections) < 4:
        report.blocking.append({
            "type": "structure",
            "severity": "critical",
            "message": f"Paper has only {len(sections)} sections (minimum 4 required)",
        })
    
    # Check IMRAD structure for research papers
    if paper_type in ["Research Paper", "Technical Paper", None]:
        section_titles = [s.get("title", "").lower() for s in sections]
        
        has_intro = any("introduction" in t or "pendahuluan" in t for t in section_titles)
        has_method = any("method" in t or "metod" in t for t in section_titles)
        has_results = any("result" in t or "hasil" in t or "finding" in t for t in section_titles)
        has_discussion = any("discussion" in t or "pembahasan" in t or "conclusion" in t or "kesimpulan" in t for t in section_titles)
        
        if not has_intro:
            report.issues.append({
                "type": "structure",
                "severity": "high",
                "message": "Missing Introduction section (IMRAD structure)",
            })
        
        if not has_method:
            report.warnings.append({
                "type": "structure",
                "severity": "medium",
                "message": "Missing Methodology section (IMRAD structure)",
            })
        
        if not has_results:
            report.warnings.append({
                "type": "structure",
                "severity": "medium",
                "message": "Missing Results section (IMRAD structure)",
            })
        
        if not has_discussion:
            report.warnings.append({
                "type": "structure",
                "severity": "medium",
                "message": "Missing Discussion/Conclusion section (IMRAD structure)",
            })


def _validate_abstract(paper_data: Dict, report: QualityReport):
    """Validate abstract quality."""
    abstract = paper_data.get("abstract", "")
    
    if not abstract or len(abstract.strip()) < 50:
        report.blocking.append({
            "type": "abstract",
            "severity": "critical",
            "message": "Abstract is missing or too short (minimum 150 words recommended)",
        })
        return
    
    word_count = len(abstract.split())
    
    if word_count < 150:
        report.warnings.append({
            "type": "abstract",
            "severity": "medium",
            "message": f"Abstract is short ({word_count} words, 150-250 recommended)",
        })
    elif word_count > 300:
        report.warnings.append({
            "type": "abstract",
            "severity": "low",
            "message": f"Abstract is long ({word_count} words, 150-250 recommended)",
        })
    
    # Check for common abstract issues
    if abstract.lower().startswith("this paper") or abstract.lower().startswith("this study"):
        report.suggestions.append({
            "type": "abstract",
            "message": "Consider starting abstract with the problem/context rather than 'This paper...'",
        })


def _validate_sections(paper_data: Dict, report: QualityReport):
    """Validate section content quality."""
    sections = paper_data.get("sections", [])
    
    for i, section in enumerate(sections):
        section_title = section.get("title", f"Section {i+1}")
        content = section.get("content", [])
        
        if not content:
            report.issues.append({
                "type": "content",
                "severity": "high",
                "message": f"Section '{section_title}' has no content",
                "section_index": i,
            })
            continue
        
        # Count words in section
        word_count = 0
        for item in content:
            if isinstance(item, dict) and item.get("id") == "text":
                word_count += len(item.get("text", "").split())
        
        # Check minimum content
        if word_count < 200:
            report.warnings.append({
                "type": "content",
                "severity": "medium",
                "message": f"Section '{section_title}' is short ({word_count} words)",
                "section_index": i,
            })


def _validate_citations(paper_data: Dict, report: QualityReport):
    """Validate citation usage and distribution."""
    sections = paper_data.get("sections", [])
    
    # Extract all citations from sections
    citations = set()
    section_citations = {}
    
    for i, section in enumerate(sections):
        section_title = section.get("title", f"Section {i+1}")
        section_cites = set()
        
        content = section.get("content", [])
        for item in content:
            if isinstance(item, dict) and item.get("id") == "text":
                text = item.get("text", "")
                # Find [N] style citations
                matches = re.findall(r"\[(\d+)\]", text)
                for m in matches:
                    citations.add(int(m))
                    section_cites.add(int(m))
        
        section_citations[section_title] = section_cites
    
    # Check citation count
    if len(citations) < 10:
        report.warnings.append({
            "type": "citations",
            "severity": "medium",
            "message": f"Low citation count ({len(citations)} unique citations, 15+ recommended)",
        })
    
    # Check citation distribution
    for section_title, cites in section_citations.items():
        if "introduction" in section_title.lower() or "related" in section_title.lower() or "literature" in section_title.lower():
            if len(cites) < 5:
                report.warnings.append({
                    "type": "citations",
                    "severity": "low",
                    "message": f"Section '{section_title}' has few citations ({len(cites)})",
                })


def _validate_references(paper_data: Dict, report: QualityReport):
    """Validate reference list quality."""
    references = paper_data.get("references", [])
    
    if len(references) < 10:
        report.blocking.append({
            "type": "references",
            "severity": "critical",
            "message": f"Too few references ({len(references)}, minimum 10 required)",
        })
    
    # Check for placeholder/invalid references
    invalid_count = 0
    for ref in references:
        if isinstance(ref, str):
            ref_lower = ref.lower()
            if "author name" in ref_lower or "untitled" in ref_lower or "example.com" in ref_lower:
                invalid_count += 1
    
    if invalid_count > 0:
        report.issues.append({
            "type": "references",
            "severity": "high",
            "message": f"Found {invalid_count} placeholder/invalid references",
        })


def _validate_figures_tables(paper_data: Dict, report: QualityReport):
    """Validate figures and tables."""
    figures = paper_data.get("figures", [])
    tables = paper_data.get("tables", [])
    
    # Check for figures
    if len(figures) == 0:
        report.suggestions.append({
            "type": "figures",
            "message": "Consider adding figures to illustrate key concepts or results",
        })
    
    # Validate figure captions
    for i, fig in enumerate(figures):
        if not fig.get("Title") or len(fig.get("Title", "")) < 10:
            report.warnings.append({
                "type": "figures",
                "severity": "low",
                "message": f"Figure {i+1} has short or missing caption",
            })


def _calculate_score(report: QualityReport) -> int:
    """Calculate overall quality score (0-100).
    
    Args:
        report: QualityReport with issues/warnings
        
    Returns:
        Score from 0-100
    """
    score = 100
    
    # Deduct points for issues
    score -= len(report.blocking) * 20  # Critical issues: -20 each
    score -= len(report.issues) * 10    # High issues: -10 each
    score -= len(report.warnings) * 5   # Medium issues: -5 each
    
    # Ensure score is in valid range
    return max(0, min(100, score))


def validate_section_quality(section_data: Dict, section_name: str) -> Dict:
    """Validate quality of a single section.
    
    Args:
        section_data: Section data dict
        section_name: Section name (introduction, methodology, etc.)
        
    Returns:
        Validation result dict with issues and suggestions
    """
    issues = []
    suggestions = []
    
    content = section_data.get("content", [])
    
    if not content:
        issues.append({
            "severity": "critical",
            "message": "Section has no content",
        })
        return {"ok": False, "issues": issues, "suggestions": suggestions}
    
    # Count words
    word_count = 0
    for item in content:
        if isinstance(item, dict) and item.get("id") == "text":
            word_count += len(item.get("text", "").split())
    
    # Section-specific validation
    if section_name == "introduction":
        if word_count < 400:
            suggestions.append("Introduction should be at least 400 words to properly set context")
    
    elif section_name == "methodology":
        if word_count < 500:
            suggestions.append("Methodology should be detailed enough for reproducibility (500+ words)")
    
    elif section_name == "results":
        figures = [item for item in content if isinstance(item, dict) and item.get("id") == "gambar"]
        tables = [item for item in content if isinstance(item, dict) and item.get("id") == "tabel"]
        
        if len(figures) == 0 and len(tables) == 0:
            suggestions.append("Results section should include figures or tables to present findings")
    
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "suggestions": suggestions,
        "word_count": word_count,
    }
