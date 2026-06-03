"""
Export System Tests
===================
Test suite for the export system.
"""

import json
from pathlib import Path
import pytest

from exports import ExportManager, ExportFormat, ExportError


# Sample paper data for testing
SAMPLE_PAPER = {
    "journal": "IEEE",
    "title": "A Comprehensive Study of Machine Learning in Academic Research",
    "authors": [
        {
            "name": "John Doe",
            "affiliation": "University of Example",
            "location": "City, Country",
            "email": "john.doe@example.edu"
        },
        {
            "name": "Jane Smith",
            "affiliation": "Institute of Technology",
            "location": "Town, Country",
            "email": "jane.smith@tech.edu"
        }
    ],
    "abstract": "This paper presents a comprehensive study of machine learning applications in academic research. We analyze various methodologies and their effectiveness in different domains.",
    "keywords": ["machine learning", "academic research", "methodology", "analysis"],
    "section1": {
        "number": "I",
        "title": "INTRODUCTION",
        "content": "Machine learning has revolutionized academic research across multiple disciplines. This study examines the current state of ML applications and their impact on research outcomes."
    },
    "section2": {
        "number": "II",
        "title": "METHODOLOGY",
        "content": "We conducted a systematic review of 150 papers published between 2020 and 2024. Our analysis focused on three key areas: data collection, model selection, and validation techniques."
    },
    "section3": {
        "number": "III",
        "title": "RESULTS",
        "content": "Our findings indicate that supervised learning remains the most common approach, accounting for 65% of studies. Deep learning techniques showed a 40% increase in adoption over the study period."
    },
    "section4": {
        "number": "IV",
        "title": "DISCUSSION",
        "content": "The results demonstrate the growing importance of machine learning in academic research. However, challenges remain in reproducibility and interpretability of ML models."
    },
    "section5": {
        "number": "V",
        "title": "CONCLUSION",
        "content": "This study provides insights into the current landscape of machine learning in academic research. Future work should focus on developing standardized evaluation frameworks."
    },
    "references": {
        "number": "VI",
        "title": "REFERENCES",
        "content": [
            {
                "authors": "Smith, J. and Brown, A.",
                "title": "Machine Learning Fundamentals",
                "venue": "Journal of AI Research",
                "volume": "15",
                "pages": "123-145",
                "year": "2023",
                "doi": "10.1234/jair.2023.001"
            },
            {
                "authors": "Johnson, M. et al.",
                "title": "Deep Learning in Academia",
                "venue": "IEEE Transactions on Education",
                "volume": "42",
                "pages": "567-589",
                "year": "2024",
                "doi": "10.1109/TE.2024.001"
            }
        ]
    }
}


def test_export_manager_initialization():
    """Test ExportManager initialization."""
    manager = ExportManager()
    assert manager.export_dir.exists()
    assert len(manager.exporters) == 4


def test_get_supported_formats():
    """Test getting supported formats."""
    manager = ExportManager()
    formats = manager.get_supported_formats()
    assert 'docx' in formats
    assert 'pdf' in formats
    assert 'latex' in formats
    assert 'markdown' in formats


def test_get_available_templates():
    """Test getting available templates."""
    manager = ExportManager()
    templates = manager.get_available_templates()
    assert isinstance(templates, list)
    assert len(templates) > 0


def test_markdown_export():
    """Test Markdown export."""
    manager = ExportManager()
    result = manager.export(SAMPLE_PAPER, 'markdown', output_filename='test_paper')
    
    assert result['success'] is True
    assert result['format'] == 'markdown'
    assert Path(result['path']).exists()
    assert Path(result['path']).suffix == '.md'
    
    # Verify content
    content = Path(result['path']).read_text()
    assert 'Machine Learning' in content
    assert 'INTRODUCTION' in content
    assert 'References' in content


def test_latex_export():
    """Test LaTeX export."""
    manager = ExportManager()
    result = manager.export(SAMPLE_PAPER, 'latex', output_filename='test_paper')
    
    assert result['success'] is True
    assert result['format'] == 'latex'
    assert Path(result['path']).exists()
    assert Path(result['path']).suffix == '.tex'
    
    # Verify .bib file was created
    if 'bib_file' in result:
        assert Path(result['bib_file']).exists()
    
    # Verify content
    content = Path(result['path']).read_text()
    assert '\\documentclass' in content
    assert '\\begin{document}' in content
    assert '\\end{document}' in content


def test_preview_markdown():
    """Test Markdown preview."""
    manager = ExportManager()
    preview = manager.preview(SAMPLE_PAPER, 'markdown')
    
    assert preview['format'] == 'markdown'
    assert len(preview['preview']) > 0
    assert 'Machine Learning' in preview['preview']


def test_preview_latex():
    """Test LaTeX preview."""
    manager = ExportManager()
    preview = manager.preview(SAMPLE_PAPER, 'latex')
    
    assert preview['format'] == 'latex'
    assert len(preview['preview']) > 0
    assert '\\documentclass' in preview['preview']


def test_export_multiple_formats():
    """Test exporting to multiple formats."""
    manager = ExportManager()
    results = manager.export_multiple(
        SAMPLE_PAPER,
        formats=['markdown', 'latex']
    )
    
    assert results['success'] is True
    assert 'markdown' in results['results']
    assert 'latex' in results['results']


def test_invalid_format():
    """Test handling of invalid format."""
    manager = ExportManager()
    
    with pytest.raises(ExportError):
        manager.export(SAMPLE_PAPER, 'invalid_format')


def test_get_export_info():
    """Test getting export system information."""
    manager = ExportManager()
    info = manager.get_export_info()
    
    assert 'export_dir' in info
    assert 'supported_formats' in info
    assert 'available_templates' in info
    assert 'exporters' in info


if __name__ == '__main__':
    # Run basic tests
    print("Testing Export System...")
    print("=" * 60)
    
    manager = ExportManager()
    
    print("\n1. System Information:")
    info = manager.get_export_info()
    print(f"   Export Directory: {info['export_dir']}")
    print(f"   Supported Formats: {', '.join(info['supported_formats'])}")
    print(f"   Available Templates: {len(info['available_templates'])} templates")
    
    print("\n2. Testing Markdown Export...")
    try:
        result = manager.export(SAMPLE_PAPER, 'markdown', output_filename='test_markdown')
        print(f"   ✓ Success: {result['filename']} ({result['size']} bytes)")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    print("\n3. Testing LaTeX Export...")
    try:
        result = manager.export(SAMPLE_PAPER, 'latex', output_filename='test_latex')
        print(f"   ✓ Success: {result['filename']} ({result['size']} bytes)")
        if 'bib_file' in result:
            print(f"   ✓ BibTeX file created: {Path(result['bib_file']).name}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    print("\n4. Testing Preview...")
    try:
        preview = manager.preview(SAMPLE_PAPER, 'markdown', max_length=500)
        print(f"   ✓ Preview generated ({preview['full_length']} chars)")
        print(f"   Preview (first 200 chars):")
        print(f"   {preview['preview'][:200]}...")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    print("\n" + "=" * 60)
    print("Testing complete!")
