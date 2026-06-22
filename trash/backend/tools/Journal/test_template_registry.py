"""
Test suite for template registry system
"""
import pytest
from template_registry import (
    get_template,
    list_templates,
    validate_paper_for_template,
    get_template_info,
    get_all_templates_info,
    TemplateField,
    TemplateType,
    CitationStyle,
)


def test_get_template():
    """Test getting a template by code"""
    template = get_template("IEEE")
    assert template is not None
    assert template.code == "IEEE"
    assert template.name == "IEEE"
    assert TemplateField.COMPUTER_SCIENCE in template.fields


def test_get_template_case_insensitive():
    """Test that template lookup is case-insensitive"""
    template = get_template("ieee")
    assert template is not None
    assert template.code == "IEEE"


def test_get_nonexistent_template():
    """Test getting a template that doesn't exist"""
    template = get_template("NONEXISTENT")
    assert template is None


def test_list_all_templates():
    """Test listing all templates"""
    templates = list_templates()
    assert len(templates) >= 44
    assert all(hasattr(t, 'code') for t in templates)


def test_list_templates_by_field():
    """Test filtering templates by field"""
    cs_templates = list_templates(field=TemplateField.COMPUTER_SCIENCE)
    assert len(cs_templates) > 0
    assert all(TemplateField.COMPUTER_SCIENCE in t.fields for t in cs_templates)


def test_list_templates_by_type():
    """Test filtering templates by type"""
    journal_templates = list_templates(template_type=TemplateType.JOURNAL)
    assert len(journal_templates) > 0
    assert all(t.template_type == TemplateType.JOURNAL for t in journal_templates)


def test_list_templates_by_citation_style():
    """Test filtering templates by citation style"""
    ieee_style = list_templates(citation_style=CitationStyle.IEEE)
    assert len(ieee_style) > 0
    assert all(t.citation_style == CitationStyle.IEEE for t in ieee_style)


def test_validate_paper_valid():
    """Test validating a valid paper"""
    paper_data = {
        "title": "Test Paper",
        "abstract": "This is a test abstract with enough words.",
        "keywords": ["test", "paper", "validation"],
    }
    errors = validate_paper_for_template(paper_data, "IEEE")
    assert len(errors) == 0


def test_validate_paper_missing_abstract():
    """Test validation fails when abstract is missing"""
    paper_data = {
        "title": "Test Paper",
        "keywords": ["test", "paper"],
    }
    errors = validate_paper_for_template(paper_data, "IEEE")
    assert len(errors) > 0
    assert any("abstract" in err.lower() for err in errors)


def test_validate_paper_insufficient_keywords():
    """Test validation fails with too few keywords"""
    paper_data = {
        "title": "Test Paper",
        "abstract": "Test abstract",
        "keywords": ["one", "two"],
    }
    errors = validate_paper_for_template(paper_data, "IEEE")
    assert len(errors) > 0
    assert any("keyword" in err.lower() for err in errors)


def test_validate_paper_abstract_too_long():
    """Test validation fails when abstract exceeds word limit"""
    long_abstract = " ".join(["word"] * 300)
    paper_data = {
        "title": "Test Paper",
        "abstract": long_abstract,
        "keywords": ["test", "paper", "validation"],
    }
    errors = validate_paper_for_template(paper_data, "IEEE")
    assert len(errors) > 0
    assert any("abstract" in err.lower() and "limit" in err.lower() for err in errors)


def test_get_template_info():
    """Test getting template info as dict"""
    info = get_template_info("IEEE")
    assert info is not None
    assert info["code"] == "IEEE"
    assert "full_name" in info
    assert "requirements" in info
    assert "formatting" in info


def test_get_all_templates_info():
    """Test getting all templates info"""
    all_info = get_all_templates_info()
    assert len(all_info) >= 44
    assert all(isinstance(info, dict) for info in all_info)
    assert all("code" in info for info in all_info)


def test_major_templates_exist():
    """Test that all major templates are registered"""
    major_templates = ["IEEE", "ACM", "Springer", "Elsevier", "APA", "MDPI"]
    for code in major_templates:
        template = get_template(code)
        assert template is not None, f"Template {code} not found"


def test_template_metadata_completeness():
    """Test that templates have complete metadata"""
    template = get_template("IEEE")
    assert template.code
    assert template.name
    assert template.full_name
    assert template.template_type
    assert len(template.fields) > 0
    assert template.citation_style
    assert template.columns > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
