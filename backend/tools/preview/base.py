"""
Base Exporter Class
===================
Abstract base class for all export formats.
"""

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
import json


class ExportFormat(Enum):
    """Supported export formats"""
    DOCX = "docx"
    PDF = "pdf"
    LATEX = "latex"
    MARKDOWN = "markdown"


class BaseExporter(ABC):
    """
    Abstract base class for paper exporters.
    
    All exporters must implement the export() method.
    """
    
    def __init__(self, template: Optional[str] = None):
        """
        Initialize exporter.
        
        Args:
            template: Template name (e.g., 'IEEE', 'IJRED')
        """
        self.template = template or "IEEE"
        
    @abstractmethod
    def export(
        self,
        paper_data: Dict[str, Any],
        output_path: Path,
        **kwargs
    ) -> Path:
        """
        Export paper to the target format.
        
        Args:
            paper_data: Paper data dictionary containing:
                - title: Paper title
                - authors: List of author objects
                - abstract: Abstract text
                - keywords: List of keywords
                - sections: List of section objects
                - references: References object
                - images: Optional list of image paths
                - tables: Optional list of table data
                - equations: Optional list of equations
            output_path: Path where the exported file should be saved
            **kwargs: Additional format-specific options
            
        Returns:
            Path to the exported file
            
        Raises:
            ExportError: If export fails
        """
        pass
    
    def validate_paper_data(self, paper_data: Dict[str, Any]) -> bool:
        """
        Validate paper data structure.
        
        Args:
            paper_data: Paper data to validate
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['title']
        return all(field in paper_data for field in required_fields)
    
    def get_sections(self, paper_data: Dict[str, Any]) -> list:
        """
        Extract sections from paper data, handling multiple formats.
        
        Supports:
        - New format: direct section keys (section1, section2, etc.)
        - Legacy format: sections array
        - Old JTM format: Items array
        
        Args:
            paper_data: Paper data dictionary
            
        Returns:
            List of section dictionaries with 'title' and 'content'
        """
        sections = []
        
        # Check for new format with direct section keys
        section_keys = [k for k in paper_data.keys() if k.startswith('section') and k[7:].isdigit()]
        if section_keys:
            # Sort by section number
            section_keys.sort(key=lambda x: int(x[7:]))
            for key in section_keys:
                section = paper_data[key]
                if isinstance(section, dict):
                    sections.append({
                        'title': section.get('title', ''),
                        'content': section.get('content', ''),
                        'subsections': section.get('subsections', [])
                    })
        
        # Check for legacy sections array format
        elif 'sections' in paper_data and isinstance(paper_data['sections'], list):
            for section in paper_data['sections']:
                if isinstance(section, dict):
                    sections.append({
                        'title': section.get('title', ''),
                        'content': section.get('content', ''),
                        'subsections': section.get('subsections', [])
                    })
        
        # Check for old JTM format with Items
        elif 'Items' in paper_data and isinstance(paper_data['Items'], list):
            for item in paper_data['Items']:
                if isinstance(item, dict):
                    sections.append({
                        'title': item.get('title', ''),
                        'content': item.get('content', ''),
                        'subsections': item.get('subsections', [])
                    })
        
        return sections
    
    def get_references(self, paper_data: Dict[str, Any]) -> list:
        """
        Extract references from paper data.
        
        Args:
            paper_data: Paper data dictionary
            
        Returns:
            List of reference dictionaries or strings
        """
        refs = paper_data.get('references', {})
        
        # Handle different reference formats
        if isinstance(refs, dict):
            # New structured format: {"title": "...", "items": [...]}
            if 'items' in refs:
                return refs['items']
            # Legacy format: {"content": [...]}
            return refs.get('content', [])
        elif isinstance(refs, list):
            return refs
        
        return []
    
    def save_json_temp(self, paper_data: Dict[str, Any], temp_dir: Path) -> Path:
        """
        Save paper data as temporary JSON file.
        
        Args:
            paper_data: Paper data to save
            temp_dir: Temporary directory
            
        Returns:
            Path to saved JSON file
        """
        temp_dir.mkdir(parents=True, exist_ok=True)
        json_path = temp_dir / "paper_temp.json"
        json_path.write_text(json.dumps(paper_data, ensure_ascii=False, indent=2), encoding='utf-8')
        return json_path


class ExportError(Exception):
    """Exception raised when export fails"""
    pass
