"""
LaTeX Exporter
==============
Exports papers to LaTeX format with proper structure, BibTeX, and formatting.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseExporter, ExportError


class LaTeXExporter(BaseExporter):
    """
    LaTeX exporter for academic papers.
    
    Generates .tex files with:
    - Proper document structure
    - BibTeX bibliography
    - Figure and table environments
    - Equation formatting
    - Template-specific document classes
    """
    
    TEMPLATE_CLASSES = {
        'IEEE': 'IEEEtran',
        'ACM': 'acmart',
        'SPRINGER': 'svjour3',
        'ELSEVIER': 'elsarticle',
        'DEFAULT': 'article'
    }
    
    def __init__(self, template: Optional[str] = None):
        """
        Initialize LaTeX exporter.
        
        Args:
            template: Template name (e.g., 'IEEE', 'ACM')
        """
        super().__init__(template)
        
    def get_document_class(self) -> str:
        """
        Get LaTeX document class for template.
        
        Returns:
            Document class name
        """
        template_upper = self.template.upper()
        for key, doc_class in self.TEMPLATE_CLASSES.items():
            if key in template_upper:
                return doc_class
        return self.TEMPLATE_CLASSES['DEFAULT']
    
    def escape_latex(self, text: str) -> str:
        """
        Escape special LaTeX characters.
        
        Args:
            text: Text to escape
            
        Returns:
            Escaped text
        """
        if not text:
            return ''
        
        # Special characters that need escaping
        replacements = {
            '\\': r'\textbackslash{}',
            '&': r'\&',
            '%': r'\%',
            '$': r'\$',
            '#': r'\#',
            '_': r'\_',
            '{': r'\{',
            '}': r'\}',
            '~': r'\textasciitilde{}',
            '^': r'\textasciicircum{}',
        }
        
        result = text
        for char, replacement in replacements.items():
            result = result.replace(char, replacement)
        
        return result
    
    def format_authors_latex(self, authors: List[Dict[str, Any]]) -> str:
        """
        Format authors for LaTeX.
        
        Args:
            authors: List of author dictionaries
            
        Returns:
            LaTeX author string
        """
        if not authors:
            return ''
        
        author_lines = []
        for author in authors:
            if not isinstance(author, dict):
                continue
            
            name = self.escape_latex(author.get('name', ''))
            affiliation = self.escape_latex(author.get('affiliation', ''))
            email = author.get('email', '')
            
            if name:
                author_lines.append(f"\\author{{{name}}}")
                if affiliation:
                    author_lines.append(f"\\affiliation{{{affiliation}}}")
                if email:
                    author_lines.append(f"\\email{{{email}}}")
        
        return '\n'.join(author_lines)
    
    def format_section_latex(self, section: Dict[str, Any], level: int = 1) -> str:
        """
        Format a section in LaTeX.
        
        Args:
            section: Section dictionary
            level: Section level (1=section, 2=subsection, etc.)
            
        Returns:
            LaTeX section string
        """
        lines = []
        
        title = section.get('title', '')
        content = section.get('content', '')
        
        if title:
            section_cmd = ['section', 'subsection', 'subsubsection'][min(level-1, 2)]
            lines.append(f"\\{section_cmd}{{{self.escape_latex(title)}}}")
            lines.append('')
        
        if content:
            # Process content for LaTeX
            processed_content = self.process_content_latex(content)
            lines.append(processed_content)
            lines.append('')
        
        # Handle subsections
        subsections = section.get('subsections', [])
        if subsections:
            for subsection in subsections:
                if isinstance(subsection, dict):
                    lines.append(self.format_section_latex(subsection, level + 1))
        
        return '\n'.join(lines)
    
    def process_content_latex(self, content: str) -> str:
        """
        Process content text for LaTeX formatting.
        
        Handles:
        - Paragraphs
        - Citations
        - Equations
        - Lists
        
        Args:
            content: Raw content text
            
        Returns:
            LaTeX-formatted content
        """
        if not content:
            return ''
        
        # Escape special characters
        text = self.escape_latex(content)
        
        # Convert citations [1] to \cite{ref1}
        text = re.sub(r'\[(\d+)\]', r'\\cite{ref\1}', text)
        
        # Convert inline equations $...$ (if already marked)
        # Keep them as-is since they're already in LaTeX format
        
        # Split into paragraphs
        paragraphs = text.split('\n\n')
        processed_paragraphs = []
        
        for para in paragraphs:
            para = para.strip()
            if para:
                processed_paragraphs.append(para)
        
        return '\n\n'.join(processed_paragraphs)
    
    def format_references_bibtex(self, references: List[Dict[str, Any]]) -> str:
        """
        Format references as BibTeX entries.
        
        Args:
            references: List of reference dictionaries
            
        Returns:
            BibTeX string
        """
        if not references:
            return ''
        
        bibtex_entries = []
        
        for i, ref in enumerate(references, 1):
            if not isinstance(ref, dict):
                continue
            
            # Determine entry type
            entry_type = 'article'  # Default
            if ref.get('type'):
                entry_type = ref['type'].lower()
            
            # Create BibTeX entry
            entry_lines = [f"@{entry_type}{{ref{i},"]
            
            # Add fields
            if ref.get('title'):
                entry_lines.append(f"  title = {{{ref['title']}}},")
            
            if ref.get('authors'):
                entry_lines.append(f"  author = {{{ref['authors']}}},")
            
            if ref.get('year'):
                entry_lines.append(f"  year = {{{ref['year']}}},")
            
            if ref.get('venue') or ref.get('journal'):
                venue = ref.get('venue') or ref.get('journal')
                entry_lines.append(f"  journal = {{{venue}}},")
            
            if ref.get('volume'):
                entry_lines.append(f"  volume = {{{ref['volume']}}},")
            
            if ref.get('pages'):
                entry_lines.append(f"  pages = {{{ref['pages']}}},")
            
            if ref.get('doi'):
                entry_lines.append(f"  doi = {{{ref['doi']}}},")
            
            entry_lines.append("}")
            bibtex_entries.append('\n'.join(entry_lines))
        
        return '\n\n'.join(bibtex_entries)
    
    def generate_latex_document(self, paper_data: Dict[str, Any]) -> str:
        """
        Generate complete LaTeX document.
        
        Args:
            paper_data: Paper data dictionary
            
        Returns:
            Complete LaTeX document string
        """
        lines = []
        
        # Document class
        doc_class = self.get_document_class()
        lines.append(f"\\documentclass[conference]{{IEEEtran}}")
        lines.append("")
        
        # Packages
        lines.append("% Packages")
        lines.append("\\usepackage[utf8]{inputenc}")
        lines.append("\\usepackage{graphicx}")
        lines.append("\\usepackage{amsmath}")
        lines.append("\\usepackage{amssymb}")
        lines.append("\\usepackage{cite}")
        lines.append("\\usepackage{hyperref}")
        lines.append("\\usepackage{booktabs}")
        lines.append("")
        
        # Title and authors
        lines.append("% Title and authors")
        title = paper_data.get('title', 'Untitled Paper')
        lines.append(f"\\title{{{self.escape_latex(title)}}}")
        lines.append("")
        
        # Authors
        authors = paper_data.get('authors', [])
        if authors:
            lines.append(self.format_authors_latex(authors))
            lines.append("")
        
        # Begin document
        lines.append("\\begin{document}")
        lines.append("")
        lines.append("\\maketitle")
        lines.append("")
        
        # Abstract
        abstract = paper_data.get('abstract', '')
        if abstract:
            lines.append("\\begin{abstract}")
            lines.append(self.escape_latex(abstract))
            lines.append("\\end{abstract}")
            lines.append("")
        
        # Keywords
        keywords = paper_data.get('keywords', [])
        if keywords:
            kw_text = ', '.join(keywords) if isinstance(keywords, list) else str(keywords)
            lines.append("\\begin{IEEEkeywords}")
            lines.append(self.escape_latex(kw_text))
            lines.append("\\end{IEEEkeywords}")
            lines.append("")
        
        # Sections
        sections = self.get_sections(paper_data)
        for section in sections:
            lines.append(self.format_section_latex(section))
        
        # References
        references = self.get_references(paper_data)
        if references:
            lines.append("\\bibliographystyle{IEEEtran}")
            lines.append("\\bibliography{references}")
        
        # End document
        lines.append("")
        lines.append("\\end{document}")
        
        return '\n'.join(lines)
    
    def export(
        self,
        paper_data: Dict[str, Any],
        output_path: Path,
        **kwargs
    ) -> Path:
        """
        Export paper to LaTeX format.
        
        Args:
            paper_data: Paper data dictionary
            output_path: Path where .tex file should be saved
            **kwargs: Additional options:
                - include_bibtex: Generate separate .bib file (default: True)
                
        Returns:
            Path to exported .tex file
            
        Raises:
            ExportError: If export fails
        """
        if not self.validate_paper_data(paper_data):
            raise ExportError("Invalid paper data: missing required fields")
        
        try:
            # Generate LaTeX document
            latex_content = self.generate_latex_document(paper_data)
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write .tex file
            output_path.write_text(latex_content, encoding='utf-8')
            
            # Generate BibTeX file if requested
            include_bibtex = kwargs.get('include_bibtex', True)
            if include_bibtex:
                references = self.get_references(paper_data)
                if references:
                    bibtex_content = self.format_references_bibtex(references)
                    bib_path = output_path.with_suffix('.bib')
                    bib_path.write_text(bibtex_content, encoding='utf-8')
            
            return output_path
            
        except Exception as e:
            raise ExportError(f"LaTeX export failed: {e}")
