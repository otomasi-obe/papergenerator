"""
Test Paper Generation Improvements
===================================
Tests for workflow integration, section generation, and quality validation.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from tools.editor.workflow_integration import (
    load_workflow_context,
    _format_workflow_context,
    get_paper_type_from_workflow,
    get_citation_style_from_workflow,
)
from tools.editor.quality_validator import (
    validate_paper_quality,
    validate_section_quality,
    QualityReport,
)
from tools.editor.section_generator import (
    generate_section,
    regenerate_section,
    _infer_section_name,
)


class TestWorkflowIntegration:
    """Test workflow context integration."""
    
    def test_format_workflow_context_basic(self):
        """Test basic workflow context formatting."""
        answers = {
            "field": "Computer Science",
            "paper_type": "Research Paper",
            "research_questions": "How can we improve X?",
            "methodology_approach": "Quantitative",
        }
        
        context = _format_workflow_context(answers)
        
        assert "Computer Science" in context
        assert "Research Paper" in context
        assert "How can we improve X?" in context
        assert "Quantitative" in context
        assert "RESEARCH DESIGN CONTEXT" in context
    
    def test_format_workflow_context_complete(self):
        """Test complete workflow context with all phases."""
        answers = {
            "field": "Computer Science",
            "paper_type": "Research Paper",
            "research_questions": "How can we improve X?",
            "methodology_approach": "Quantitative",
            "specific_method": "Experimental study",
            "sample_size": "100 participants",
            "data_source": "Survey data",
            "reference_count": "30-40 references",
            "target_publication": "IEEE Conference",
            "writing_tone": "Formal academic",
            "citation_style": "IEEE",
            "ethics": "IRB approved",
        }
        
        context = _format_workflow_context(answers)
        
        assert "Experimental study" in context
        assert "100 participants" in context
        assert "IEEE Conference" in context
        assert "IRB approved" in context
    
    def test_format_workflow_context_empty(self):
        """Test workflow context with empty answers."""
        answers = {}
        context = _format_workflow_context(answers)
        
        assert "RESEARCH DESIGN CONTEXT" in context
        # Should still have the header even with no answers
    
    def test_paper_type_guidance(self):
        """Test paper type specific guidance."""
        answers = {"paper_type": "Case Study"}
        context = _format_workflow_context(answers)
        
        assert "Case Study" in context
        assert "narrative structure" in context.lower() or "case description" in context.lower()
    
    @patch('paper_generation.workflow_integration.ProjectMemory')
    def test_load_workflow_context_success(self, mock_memory):
        """Test successful workflow context loading."""
        mock_query = Mock()
        mock_memory.query.filter_by.return_value = mock_query
        
        mock_mem = Mock()
        mock_mem.value = json.dumps({
            "current_phase": "5",
            "answers": {
                "field": "Computer Science",
                "paper_type": "Research Paper",
            }
        })
        mock_query.first.return_value = mock_mem
        
        context = load_workflow_context("paper123", 1)
        
        assert "Computer Science" in context
        assert "Research Paper" in context
    
    @patch('paper_generation.workflow_integration.ProjectMemory')
    def test_load_workflow_context_no_data(self, mock_memory):
        """Test workflow context loading with no data."""
        mock_query = Mock()
        mock_memory.query.filter_by.return_value = mock_query
        mock_query.first.return_value = None
        
        context = load_workflow_context("paper123", 1)
        
        assert context == ""


class TestQualityValidator:
    """Test paper quality validation."""
    
    def test_validate_paper_quality_minimal(self):
        """Test validation of minimal paper."""
        paper_data = {
            "title": "Test Paper",
            "abstract": "Short abstract",
            "sections": [
                {"title": "Introduction", "content": [{"id": "text", "text": "Intro text"}]},
            ],
            "references": ["Ref 1", "Ref 2"],
        }
        
        report = validate_paper_quality(paper_data)
        
        assert report.score < 100  # Should have issues
        assert len(report.blocking) > 0  # Too few sections and references
    
    def test_validate_paper_quality_good(self):
        """Test validation of good quality paper."""
        paper_data = {
            "title": "A Comprehensive Study of X",
            "abstract": "This is a comprehensive abstract that describes the problem, methodology, results, and conclusions in sufficient detail. " * 3,
            "sections": [
                {"title": "Introduction", "content": [{"id": "text", "text": "Introduction text " * 100}]},
                {"title": "Related Work", "content": [{"id": "text", "text": "Related work text " * 100}]},
                {"title": "Methodology", "content": [{"id": "text", "text": "Methodology text " * 100}]},
                {"title": "Results", "content": [{"id": "text", "text": "Results text " * 100}]},
                {"title": "Conclusion", "content": [{"id": "text", "text": "Conclusion text " * 100}]},
            ],
            "references": [f"Reference {i}" for i in range(1, 21)],
            "figures": [{"Title": "Figure 1: Test figure"}],
        }
        
        report = validate_paper_quality(paper_data, "Research Paper")
        
        assert report.score >= 70  # Should be good quality
        assert len(report.blocking) == 0  # No blocking issues
    
    def test_validate_imrad_structure(self):
        """Test IMRAD structure validation."""
        paper_data = {
            "title": "Test",
            "abstract": "Abstract " * 30,
            "sections": [
                {"title": "Background", "content": [{"id": "text", "text": "Text " * 50}]},
                {"title": "Analysis", "content": [{"id": "text", "text": "Text " * 50}]},
            ],
            "references": [f"Ref {i}" for i in range(15)],
        }
        
        report = validate_paper_quality(paper_data, "Research Paper")
        
        # Should warn about missing IMRAD sections
        issue_types = [issue["type"] for issue in report.issues + report.warnings]
        assert "structure" in issue_types
    
    def test_validate_section_quality_introduction(self):
        """Test section-specific validation."""
        section_data = {
            "title": "Introduction",
            "content": [
                {"id": "text", "text": "Short intro"}
            ]
        }
        
        result = validate_section_quality(section_data, "introduction")
        
        assert result["ok"] == True  # No critical issues
        assert len(result["suggestions"]) > 0  # Should suggest more content
        assert result["word_count"] < 400


class TestSectionGenerator:
    """Test section-based generation."""
    
    def test_infer_section_name(self):
        """Test section name inference from titles."""
        assert _infer_section_name("Introduction") == "introduction"
        assert _infer_section_name("PENDAHULUAN") == "introduction"
        assert _infer_section_name("Related Work") == "related_work"
        assert _infer_section_name("Literature Review") == "related_work"
        assert _infer_section_name("Methodology") == "methodology"
        assert _infer_section_name("METODE PENELITIAN") == "methodology"
        assert _infer_section_name("Results and Discussion") == "results"
        assert _infer_section_name("Conclusion") == "conclusion"
    
    @patch('paper_generation.section_generator._call_aiotomasi_with_fallback')
    @patch('paper_generation.section_generator.PROMPT_FILE')
    @patch('paper_generation.section_generator.HUMANIZE_FILE')
    def test_generate_section_basic(self, mock_humanize, mock_prompt, mock_api):
        """Test basic section generation."""
        mock_prompt.exists.return_value = True
        mock_prompt.read_text.return_value = "Base prompt"
        mock_humanize.exists.return_value = True
        mock_humanize.read_text.return_value = "Humanize rules"
        
        mock_api.return_value = ('{"title": "Introduction", "content": []}', "VIOLA-GENERATE")
        
        paper_context = {
            "title": "Test Paper",
            "abstract": "Test abstract",
            "existing_sections": [],
        }
        
        result = generate_section(
            "introduction",
            paper_context,
            api_key="test_key",
            base_url="http://test.com",
        )
        
        assert result is not None
        assert mock_api.called
    
    def test_generate_section_invalid_name(self):
        """Test section generation with invalid name."""
        with pytest.raises(ValueError, match="Invalid section name"):
            generate_section(
                "invalid_section",
                {"title": "Test"},
                api_key="test_key",
                base_url="http://test.com",
            )


class TestIntegration:
    """Integration tests for complete workflow."""
    
    @patch('paper_generation.workflow_integration.ProjectMemory')
    def test_workflow_to_generation_flow(self, mock_memory):
        """Test complete flow from workflow to generation."""
        # Setup workflow data
        mock_query = Mock()
        mock_memory.query.filter_by.return_value = mock_query
        
        mock_mem = Mock()
        mock_mem.value = json.dumps({
            "current_phase": "9",
            "answers": {
                "field": "Computer Science",
                "paper_type": "Research Paper",
                "methodology_approach": "Experimental",
                "citation_style": "IEEE",
            }
        })
        mock_query.first.return_value = mock_mem
        
        # Load workflow context
        context = load_workflow_context("paper123", 1)
        
        assert "Computer Science" in context
        assert "Research Paper" in context
        assert "Experimental" in context
        
        # Verify it can be used in generation
        assert len(context) > 100  # Should be substantial context
    
    def test_quality_validation_workflow(self):
        """Test quality validation with workflow-aware paper."""
        paper_data = {
            "title": "Machine Learning Approach for X",
            "abstract": "This paper presents a novel machine learning approach for solving problem X. " * 5,
            "sections": [
                {"title": "Introduction", "content": [{"id": "text", "text": "Intro " * 100}]},
                {"title": "Related Work", "content": [{"id": "text", "text": "Related " * 100}]},
                {"title": "Methodology", "content": [{"id": "text", "text": "Method " * 100}]},
                {"title": "Experimental Results", "content": [{"id": "text", "text": "Results " * 100}]},
                {"title": "Conclusion", "content": [{"id": "text", "text": "Conclusion " * 100}]},
            ],
            "references": [f"Reference {i}" for i in range(1, 25)],
            "figures": [{"Title": "Figure 1: System architecture"}],
        }
        
        report = validate_paper_quality(paper_data, "Research Paper")
        
        # Should pass quality checks
        assert report.score >= 80
        assert len(report.blocking) == 0
        assert report.to_dict()["ready_for_export"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
