"""
Export Manager
==============
Unified interface for managing all export formats.
"""

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseExporter, ExportFormat, ExportError
from .docx_exporter import DOCXExporter
from .pdf_exporter import PDFExporter
from .latex_exporter import LaTeXExporter
from .markdown_exporter import MarkdownExporter


class ExportManager:
    """
    Central manager for all export operations.
    
    Provides a unified interface to export papers to multiple formats:
    - DOCX (Microsoft Word)
    - PDF (Portable Document Format)
    - LaTeX (with BibTeX)
    - Markdown (for editing)
    """
    
    def __init__(self, export_dir: Optional[Path] = None):
        """
        Initialize export manager.
        
        Args:
            export_dir: Base directory for exports (default: backend/data/exports)
        """
        if export_dir:
            self.export_dir = Path(export_dir)
        else:
            self.export_dir = Path(__file__).parent.parent / "data" / "exports"
        
        self.export_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize exporters
        self.exporters = {
            ExportFormat.DOCX: DOCXExporter(),
            ExportFormat.PDF: PDFExporter(),
            ExportFormat.LATEX: LaTeXExporter(),
            ExportFormat.MARKDOWN: MarkdownExporter(),
        }
    
    def get_exporter(self, format: ExportFormat, template: Optional[str] = None) -> BaseExporter:
        """
        Get exporter for a specific format.
        
        Args:
            format: Export format
            template: Template name (optional)
            
        Returns:
            Exporter instance
            
        Raises:
            ExportError: If format not supported
        """
        if format not in self.exporters:
            raise ExportError(f"Unsupported export format: {format}")
        
        exporter = self.exporters[format]
        if template:
            exporter.template = template
        
        return exporter
    
    def export(
        self,
        paper_data: Dict[str, Any],
        format: str,
        template: Optional[str] = None,
        output_filename: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Export paper to specified format.
        
        Args:
            paper_data: Paper data dictionary
            format: Export format ('docx', 'pdf', 'latex', 'markdown')
            template: Template name (e.g., 'IEEE', 'IJRED')
            output_filename: Custom output filename (without extension)
            **kwargs: Format-specific options
            
        Returns:
            Dictionary with export metadata:
                - path: Path to exported file
                - format: Export format
                - template: Template used (if applicable)
                - size: File size in bytes
                - success: True if successful
                
        Raises:
            ExportError: If export fails
        """
        # Parse format
        try:
            export_format = ExportFormat(format.lower())
        except ValueError:
            raise ExportError(
                f"Invalid format: {format}. "
                f"Supported formats: {', '.join([f.value for f in ExportFormat])}"
            )
        
        # Determine template
        if not template:
            template = paper_data.get('journal', 'IEEE')
        
        # Generate output filename
        if not output_filename:
            title = paper_data.get('title', 'paper')
            # Sanitize filename
            safe_title = ''.join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)
            safe_title = safe_title[:60].strip('_')
            output_filename = f"{template}_{safe_title}_{uuid.uuid4().hex[:8]}"
        
        # Determine file extension
        extension_map = {
            ExportFormat.DOCX: '.docx',
            ExportFormat.PDF: '.pdf',
            ExportFormat.LATEX: '.tex',
            ExportFormat.MARKDOWN: '.md',
        }
        extension = extension_map[export_format]
        
        # Create output path
        output_path = self.export_dir / f"{output_filename}{extension}"
        
        # Get exporter and export
        exporter = self.get_exporter(export_format, template)
        
        try:
            result_path = exporter.export(paper_data, output_path, **kwargs)
            
            # Collect metadata
            metadata = {
                'path': str(result_path),
                'format': format,
                'template': template,
                'size': result_path.stat().st_size if result_path.exists() else 0,
                'success': True,
                'filename': result_path.name,
            }
            
            # Add format-specific metadata
            if export_format == ExportFormat.LATEX:
                # Check if .bib file was created
                bib_path = result_path.with_suffix('.bib')
                if bib_path.exists():
                    metadata['bib_file'] = str(bib_path)
            
            return metadata
            
        except Exception as e:
            raise ExportError(f"Export failed: {e}")
    
    def export_multiple(
        self,
        paper_data: Dict[str, Any],
        formats: List[str],
        template: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Export paper to multiple formats.
        
        Args:
            paper_data: Paper data dictionary
            formats: List of format strings
            template: Template name
            **kwargs: Format-specific options
            
        Returns:
            Dictionary mapping format to export metadata
        """
        results = {}
        errors = {}
        
        for format in formats:
            try:
                result = self.export(paper_data, format, template, **kwargs)
                results[format] = result
            except ExportError as e:
                errors[format] = str(e)
        
        return {
            'results': results,
            'errors': errors,
            'success': len(errors) == 0
        }
    
    def get_available_templates(self) -> List[str]:
        """
        Get list of available templates.
        
        Returns:
            List of template names
        """
        docx_exporter = self.exporters[ExportFormat.DOCX]
        return docx_exporter.get_available_templates()
    
    def get_supported_formats(self) -> List[str]:
        """
        Get list of supported export formats.
        
        Returns:
            List of format strings
        """
        return [f.value for f in ExportFormat]
    
    def preview(
        self,
        paper_data: Dict[str, Any],
        format: str,
        template: Optional[str] = None,
        max_length: int = 1000
    ) -> Dict[str, Any]:
        """
        Generate a preview of the export without creating a file.
        
        Args:
            paper_data: Paper data dictionary
            format: Export format
            template: Template name
            max_length: Maximum preview length in characters
            
        Returns:
            Dictionary with preview data:
                - format: Export format
                - preview: Preview text (truncated)
                - full_length: Full document length
                - truncated: Whether preview was truncated
        """
        try:
            export_format = ExportFormat(format.lower())
        except ValueError:
            raise ExportError(f"Invalid format: {format}")
        
        # Generate preview based on format
        if export_format == ExportFormat.MARKDOWN:
            exporter = self.get_exporter(export_format, template)
            full_content = exporter.generate_markdown_document(paper_data)
            
        elif export_format == ExportFormat.LATEX:
            exporter = self.get_exporter(export_format, template)
            full_content = exporter.generate_latex_document(paper_data)
            
        else:
            # For DOCX and PDF, we can't easily generate text preview
            # Return metadata instead
            return {
                'format': format,
                'preview': f"Preview not available for {format} format. Export to view full document.",
                'full_length': 0,
                'truncated': False,
                'template': template or paper_data.get('journal', 'IEEE')
            }
        
        # Truncate if needed
        truncated = len(full_content) > max_length
        preview = full_content[:max_length] if truncated else full_content
        
        if truncated:
            preview += "\n\n... (truncated)"
        
        return {
            'format': format,
            'preview': preview,
            'full_length': len(full_content),
            'truncated': truncated,
            'template': template or paper_data.get('journal', 'IEEE')
        }
    
    def cleanup_old_exports(self, days: int = 7) -> int:
        """
        Clean up old export files.
        
        Args:
            days: Delete files older than this many days
            
        Returns:
            Number of files deleted
        """
        import time
        
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        deleted_count = 0
        
        for file_path in self.export_dir.glob('*'):
            if file_path.is_file():
                if file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except Exception:
                        pass
        
        return deleted_count
    
    def get_export_info(self) -> Dict[str, Any]:
        """
        Get information about the export system.
        
        Returns:
            Dictionary with system information
        """
        return {
            'export_dir': str(self.export_dir),
            'supported_formats': self.get_supported_formats(),
            'available_templates': self.get_available_templates(),
            'exporters': {
                format.value: type(exporter).__name__
                for format, exporter in self.exporters.items()
            }
        }
