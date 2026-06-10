"""
Markdown Exporter
=================
Exports papers to Markdown format for easy editing and version control.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseExporter, ExportError


class MarkdownExporter(BaseExporter):
    """
    Markdown exporter for papers.
    
    Generates clean, readable Markdown files with:
    - Proper heading hierarchy
    - Formatted citations
    - Tables and lists
    - Code blocks for equations
    """
    
    def __init__(self, template: Optional[str] = None):
        """
        Initialize Markdown exporter.
        
        Args:
            template: Template name (not used for Markdown, but kept for consistency)
        """
        super().__init__(template)
        
    def format_authors_markdown(self, authors: List[Dict[str, Any]]) -> str:
        """
        Format authors for Markdown.
        
        Args:
            authors: List of author dictionaries
            
        Returns:
            Markdown author string
        """
        if not authors:
            return ''
        
        author_lines = []
        for author in authors:
            if not isinstance(author, dict):
                continue
            
            name = author.get('name', '')
            affiliation = author.get('affiliation', '')
            email = author.get('email', '')
            
            parts = [name]
            if affiliation:
                parts.append(f"*{affiliation}*")
            if email:
                parts.append(f"<{email}>")
            
            if parts:
                author_lines.append(' - '.join(parts))
        
        return '\n\n'.join(author_lines)
    
    def format_section_markdown(self, section: Dict[str, Any], level: int = 2) -> str:
        """
        Format a section in Markdown.
        
        Args:
            section: Section dictionary
            level: Heading level (1-6)
            
        Returns:
            Markdown section string
        """
        lines = []
        
        title = section.get('title', '')
        content = section.get('content', '')
        
        if title:
            heading_prefix = '#' * min(level, 6)
            lines.append(f"{heading_prefix} {title}")
            lines.append('')
        
        if content:
            lines.append(content)
            lines.append('')
        
        # Handle subsections
        subsections = section.get('subsections', [])
        if subsections:
            for subsection in subsections:
                if isinstance(subsection, dict):
                    lines.append(self.format_section_markdown(subsection, level + 1))
        
        return '\n'.join(lines)
    
    def format_references_markdown(self, references: List[Dict[str, Any]]) -> str:
        """
        Format references for Markdown.
        
        Args:
            references: List of reference dictionaries
            
        Returns:
            Markdown references string
        """
        if not references:
            return ''
        
        lines = []
        
        for i, ref in enumerate(references, 1):
            if not isinstance(ref, dict):
                # Handle string references
                lines.append(f"{i}. {ref}")
                continue
            
            # Build reference string
            parts = []
            
            if ref.get('authors'):
                parts.append(ref['authors'])
            
            if ref.get('title'):
                parts.append(f"**{ref['title']}**")
            
            if ref.get('venue') or ref.get('journal'):
                venue = ref.get('venue') or ref.get('journal')
                parts.append(f"*{venue}*")
            
            if ref.get('volume'):
                parts.append(f"vol. {ref['volume']}")
            
            if ref.get('pages'):
                parts.append(f"pp. {ref['pages']}")
            
            if ref.get('year'):
                parts.append(f"({ref['year']})")
            
            if ref.get('doi'):
                parts.append(f"DOI: [{ref['doi']}](https://doi.org/{ref['doi']})")
            
            ref_text = ', '.join(parts)
            lines.append(f"{i}. {ref_text}")
        
        return '\n'.join(lines)
    
    def generate_markdown_document(self, paper_data: Dict[str, Any]) -> str:
        """
        Generate complete Markdown document.
        
        Args:
            paper_data: Paper data dictionary
            
        Returns:
            Complete Markdown document string
        """
        lines = []
        
        # Title
        title = paper_data.get('title', 'Untitled Paper')
        lines.append(f"# {title}")
        lines.append('')
        
        # Authors
        authors = paper_data.get('authors', [])
        if authors:
            lines.append(self.format_authors_markdown(authors))
            lines.append('')
        
        # Metadata
        lines.append('---')
        lines.append('')
        
        # Abstract
        abstract = paper_data.get('abstract', '')
        if abstract:
            lines.append('## Abstract')
            lines.append('')
            lines.append(abstract)
            lines.append('')
        
        # Keywords
        keywords = paper_data.get('keywords', [])
        if keywords:
            kw_text = ', '.join(keywords) if isinstance(keywords, list) else str(keywords)
            lines.append(f'**Keywords:** {kw_text}')
            lines.append('')
        
        lines.append('---')
        lines.append('')
        
        # Sections
        sections = self.get_sections(paper_data)
        for section in sections:
            lines.append(self.format_section_markdown(section))
        
        # References
        references = self.get_references(paper_data)
        if references:
            lines.append('## References')
            lines.append('')
            lines.append(self.format_references_markdown(references))
            lines.append('')
        
        return '\n'.join(lines)
    
    def export(
        self,
        paper_data: Dict[str, Any],
        output_path: Path,
        **kwargs
    ) -> Path:
        """
        Export paper to Markdown format.
        
        Args:
            paper_data: Paper data dictionary
            output_path: Path where .md file should be saved
            **kwargs: Additional options (currently unused)
                
        Returns:
            Path to exported .md file
            
        Raises:
            ExportError: If export fails
        """
        if not self.validate_paper_data(paper_data):
            raise ExportError("Invalid paper data: missing required fields")
        
        try:
            # Generate Markdown document
            markdown_content = self.generate_markdown_document(paper_data)
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write .md file
            output_path.write_text(markdown_content, encoding='utf-8')
            
            return output_path
            
        except Exception as e:
            raise ExportError(f"Markdown export failed: {e}")
