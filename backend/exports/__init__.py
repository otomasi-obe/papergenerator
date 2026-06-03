"""
Export System for Paper Generator
==================================
Unified export system supporting multiple formats: DOCX, PDF, LaTeX, Markdown.

Usage:
    from exports import ExportManager
    
    manager = ExportManager()
    output_path = manager.export(paper_data, format='pdf', template='IEEE')
"""

from .manager import ExportManager
from .base import BaseExporter, ExportFormat
from .docx_exporter import DOCXExporter
from .pdf_exporter import PDFExporter
from .latex_exporter import LaTeXExporter
from .markdown_exporter import MarkdownExporter

__all__ = [
    'ExportManager',
    'BaseExporter',
    'ExportFormat',
    'DOCXExporter',
    'PDFExporter',
    'LaTeXExporter',
    'MarkdownExporter',
]
