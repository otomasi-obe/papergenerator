"""
DOCX Exporter
=============
Exports papers to Microsoft Word DOCX format using template generators.
"""

import importlib
from pathlib import Path
from typing import Any, Dict, Optional
import uuid

from .base import BaseExporter, ExportError


class DOCXExporter(BaseExporter):
    """
    DOCX exporter using existing template system.
    
    Wraps the template-specific generators (IEEEgen.py, IJREDgen.py, etc.)
    to provide a unified export interface.
    """
    
    def __init__(self, template: Optional[str] = None):
        """
        Initialize DOCX exporter.
        
        Args:
            template: Template name (e.g., 'IEEE', 'IJRED')
        """
        super().__init__(template)
        self.template_dir = Path(__file__).parent.parent / "templates"
        
    def get_available_templates(self) -> list:
        """
        Get list of available DOCX templates.
        
        Returns:
            List of template names
        """
        templates = []
        try:
            for docx_path in self.template_dir.glob("*.docx"):
                code = docx_path.stem
                gen_path = self.template_dir / f"{code}gen.py"
                if gen_path.exists():
                    templates.append(code)
        except Exception:
            pass
        return sorted(set(templates), key=str.lower)
    
    def get_template_builder(self, template_name: str):
        """
        Get the build_document function for a template.
        
        Args:
            template_name: Template name (e.g., 'IEEE')
            
        Returns:
            Tuple of (canonical_name, builder_function)
            
        Raises:
            ExportError: If template not found or invalid
        """
        available = self.get_available_templates()
        
        # Case-insensitive match
        template_map = {t.lower(): t for t in available}
        canonical = template_map.get(template_name.lower())
        
        if not canonical:
            raise ExportError(
                f"Unknown template: {template_name}. "
                f"Available templates: {', '.join(available)}"
            )
        
        try:
            # Import the template generator module
            mod = importlib.import_module(f"templates.{canonical}gen")
            builder = getattr(mod, "build_document", None)
            
            if not callable(builder):
                raise ExportError(
                    f"Template generator missing build_document function: {canonical}gen"
                )
            
            return canonical, builder
            
        except ImportError as e:
            raise ExportError(f"Failed to import template generator: {canonical}gen - {e}")
    
    def export(
        self,
        paper_data: Dict[str, Any],
        output_path: Path,
        **kwargs
    ) -> Path:
        """
        Export paper to DOCX format.
        
        Args:
            paper_data: Paper data dictionary
            output_path: Path where DOCX should be saved
            **kwargs: Additional options:
                - template_override: Override template from paper_data
                
        Returns:
            Path to exported DOCX file
            
        Raises:
            ExportError: If export fails
        """
        if not self.validate_paper_data(paper_data):
            raise ExportError("Invalid paper data: missing required fields")
        
        # Determine template to use
        template_name = kwargs.get('template_override') or paper_data.get('journal') or self.template
        
        try:
            # Get template builder
            canonical_name, builder = self.get_template_builder(template_name)
            
            # Create temporary JSON file
            temp_dir = output_path.parent / f"_temp_{uuid.uuid4().hex[:8]}"
            json_path = self.save_json_temp(paper_data, temp_dir)
            
            try:
                # Ensure output directory exists
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Call template builder
                result_path = builder(json_path, output_path)
                
                return Path(result_path)
                
            finally:
                # Cleanup temporary files
                try:
                    if json_path.exists():
                        json_path.unlink()
                    if temp_dir.exists():
                        temp_dir.rmdir()
                except Exception:
                    pass
                    
        except ExportError:
            raise
        except Exception as e:
            raise ExportError(f"DOCX export failed: {e}")
    
    def export_with_template_info(
        self,
        paper_data: Dict[str, Any],
        output_path: Path,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Export paper and return metadata about the export.
        
        Args:
            paper_data: Paper data dictionary
            output_path: Path where DOCX should be saved
            **kwargs: Additional options
            
        Returns:
            Dictionary with:
                - path: Path to exported file
                - template: Template name used
                - format: 'docx'
                - size: File size in bytes
        """
        result_path = self.export(paper_data, output_path, **kwargs)
        
        return {
            'path': str(result_path),
            'template': self.template,
            'format': 'docx',
            'size': result_path.stat().st_size if result_path.exists() else 0,
            'mimetype': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
