"""
Workflow Integration for Paper Generation
==========================================
Integrates 9-phase workflow answers into paper generation prompts.

This module extracts workflow answers from ProjectMemory and formats them
into structured context blocks that guide the AI to generate papers matching
the user's research design, methodology, and target publication.
"""

import json
import logging
from typing import Dict, Optional

log = logging.getLogger(__name__)


def load_workflow_context(paper_id: str, user_id: int) -> str:
    """Load workflow answers and format as context for paper generation.
    
    Args:
        paper_id: Paper ID
        user_id: User ID
        
    Returns:
        Formatted workflow context string for injection into generation prompts.
        Returns empty string if no workflow state exists.
    """
    try:
        from database.models import ProjectMemory
        
        mem = ProjectMemory.query.filter_by(
            paper_id=paper_id,
            user_id=user_id,
            key="workflow_state"
        ).first()
        
        if not mem:
            return ""
        
        state = json.loads(mem.value)
        answers = state.get("answers", {})
        
        if not answers:
            return ""
        
        return _format_workflow_context(answers)
        
    except Exception as e:
        log.warning("[load_workflow_context] failed: %s", e)
        return ""


def _format_workflow_context(answers: Dict[str, str]) -> str:
    """Format workflow answers into structured context block.
    
    Args:
        answers: Dictionary of workflow answers (key -> value)
        
    Returns:
        Formatted context string
    """
    lines = ["## RESEARCH DESIGN CONTEXT (from workflow questionnaire)"]
    lines.append("")
    
    # Phase 0-1: Field and Paper Type
    if answers.get("field"):
        lines.append(f"**Research Field**: {answers['field']}")
    
    if answers.get("paper_type"):
        paper_type = answers["paper_type"]
        lines.append(f"**Paper Type**: {paper_type}")
        lines.append(_get_paper_type_guidance(paper_type))
    
    # Phase 2: Research Questions
    if answers.get("research_questions"):
        lines.append("")
        lines.append("**Research Questions**:")
        lines.append(answers["research_questions"])
    
    # Phase 3: Methodology
    if answers.get("methodology_approach"):
        lines.append("")
        lines.append(f"**Methodology Approach**: {answers['methodology_approach']}")
    
    if answers.get("specific_method"):
        lines.append(f"**Specific Method**: {answers['specific_method']}")
    
    if answers.get("sample_size"):
        lines.append(f"**Sample Size**: {answers['sample_size']}")
    
    if answers.get("data_source"):
        lines.append(f"**Data Source**: {answers['data_source']}")
    
    # Phase 4: Results and Analysis
    if answers.get("analysis_type"):
        lines.append("")
        lines.append(f"**Analysis Type**: {answers['analysis_type']}")
    
    if answers.get("expected_findings"):
        lines.append(f"**Expected Findings**: {answers['expected_findings']}")
    
    # Phase 5: References
    if answers.get("reference_count"):
        lines.append("")
        lines.append(f"**Target Reference Count**: {answers['reference_count']}")
    
    if answers.get("key_references"):
        lines.append(f"**Key References to Include**: {answers['key_references']}")
    
    # Phase 6: Target Publication
    if answers.get("target_publication"):
        lines.append("")
        lines.append(f"**Target Publication**: {answers['target_publication']}")
    
    if answers.get("publication_requirements"):
        lines.append(f"**Publication Requirements**: {answers['publication_requirements']}")
    
    # Phase 7: Writing Style
    if answers.get("writing_tone"):
        lines.append("")
        lines.append(f"**Writing Tone**: {answers['writing_tone']}")
    
    if answers.get("citation_style"):
        lines.append(f"**Citation Style**: {answers['citation_style']}")
    
    # Phase 8: Ethics and Constraints
    if answers.get("ethics"):
        lines.append("")
        lines.append(f"**Ethics Considerations**: {answers['ethics']}")
    
    if answers.get("budget"):
        lines.append(f"**Budget Constraints**: {answers['budget']}")
    
    if answers.get("timeline"):
        lines.append(f"**Timeline**: {answers['timeline']}")
    
    # Additional context
    if answers.get("novelty"):
        lines.append("")
        lines.append(f"**Novelty/Innovation**: {answers['novelty']}")
    
    if answers.get("limitations"):
        lines.append(f"**Known Limitations**: {answers['limitations']}")
    
    lines.append("")
    lines.append("**INSTRUCTION**: Use the above research design context to guide paper structure, methodology description, and results presentation. Ensure the generated paper aligns with the specified paper type, methodology, and target publication requirements.")
    
    return "\n".join(lines)


def _get_paper_type_guidance(paper_type: str) -> str:
    """Get structure guidance for specific paper types.
    
    Args:
        paper_type: Paper type from workflow
        
    Returns:
        Structure guidance string
    """
    guidance_map = {
        "Research Paper": "Use IMRAD structure (Introduction, Methods, Results, Discussion). Focus on empirical findings and data analysis.",
        "Case Study": "Use narrative structure with Background, Case Description, Analysis, Discussion, Lessons Learned. Focus on detailed context and practical insights.",
        "Literature Review": "Use thematic structure with Introduction, Thematic Sections, Synthesis, Research Gaps, Conclusion. Focus on comprehensive coverage and critical analysis.",
        "Systematic Review": "Use PRISMA structure with Protocol, Search Strategy, Screening, Data Extraction, Synthesis, Quality Assessment. Include PRISMA flow diagram.",
        "Technical Paper": "Use IEEE structure with Abstract, Introduction, System Architecture, Implementation, Evaluation, Conclusion. Focus on technical details and reproducibility.",
        "Position Paper": "Use argumentative structure with Introduction, Background, Position Statement, Supporting Arguments, Counter-arguments, Conclusion. Focus on clear stance and persuasive reasoning.",
        "Survey Paper": "Use comprehensive structure with Introduction, Taxonomy, Detailed Survey by Category, Comparative Analysis, Open Challenges, Conclusion. Focus on breadth and classification.",
    }
    
    return guidance_map.get(paper_type, "")


def get_paper_type_from_workflow(paper_id: str, user_id: int) -> Optional[str]:
    """Extract paper type from workflow answers.
    
    Args:
        paper_id: Paper ID
        user_id: User ID
        
    Returns:
        Paper type string or None if not found
    """
    try:
        from database.models import ProjectMemory
        
        mem = ProjectMemory.query.filter_by(
            paper_id=paper_id,
            user_id=user_id,
            key="workflow_state"
        ).first()
        
        if not mem:
            return None
        
        state = json.loads(mem.value)
        answers = state.get("answers", {})
        
        return answers.get("paper_type")
        
    except Exception as e:
        log.warning("[get_paper_type_from_workflow] failed: %s", e)
        return None


def get_citation_style_from_workflow(paper_id: str, user_id: int) -> Optional[str]:
    """Extract citation style from workflow answers.
    
    Args:
        paper_id: Paper ID
        user_id: User ID
        
    Returns:
        Citation style string (APA, IEEE, etc.) or None if not found
    """
    try:
        from database.models import ProjectMemory
        
        mem = ProjectMemory.query.filter_by(
            paper_id=paper_id,
            user_id=user_id,
            key="workflow_state"
        ).first()
        
        if not mem:
            return None
        
        state = json.loads(mem.value)
        answers = state.get("answers", {})
        
        return answers.get("citation_style")
        
    except Exception as e:
        log.warning("[get_citation_style_from_workflow] failed: %s", e)
        return None
