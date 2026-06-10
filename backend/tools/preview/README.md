# Export System Documentation

## Overview

The Paper Generator Export System provides a unified interface for exporting academic papers to multiple formats with proper formatting, images, graphs, tables, and citations.

## Supported Formats

### 1. DOCX (Microsoft Word)
- **Status**: ✅ Fully Implemented
- **Features**:
  - Template-specific formatting (IEEE, IJRED, JNTETI, etc.)
  - Proper styles and spacing
  - Images and figures with captions
  - Tables with formatting
  - Citations and bibliography
  - Multi-column layouts
  - Equation support (MathML to OMML)
- **Implementation**: Wraps existing template generators (`IEEEgen.py`, etc.)

### 2. PDF (Portable Document Format)
- **Status**: ✅ Fully Implemented
- **Features**:
  - High-quality rendering
  - Proper page layout
  - Images and graphics
  - Hyperlinks for citations
  - Multiple generation methods
- **Methods**:
  1. **LibreOffice** (Recommended): Converts DOCX to PDF with best quality
  2. **docx2pdf** (Windows): Native Windows conversion
  3. **ReportLab** (Fallback): Direct PDF generation with basic formatting

### 3. LaTeX
- **Status**: ✅ Fully Implemented
- **Features**:
  - Proper LaTeX document structure
  - Template-specific document classes (IEEEtran, article, etc.)
  - BibTeX bibliography management
  - Figure and table environments
  - Equation formatting
  - Automatic character escaping
- **Output**: `.tex` file + `.bib` file (optional)

### 4. Markdown
- **Status**: ✅ Fully Implemented
- **Features**:
  - Clean, readable format
  - Proper heading hierarchy
  - Formatted citations
  - Tables and lists
  - Easy editing and version control
- **Output**: `.md` file

## Architecture

```
exports/
├── __init__.py           # Package initialization
├── base.py               # BaseExporter abstract class
├── docx_exporter.py      # DOCX export implementation
├── pdf_exporter.py       # PDF export implementation
├── latex_exporter.py     # LaTeX export implementation
├── markdown_exporter.py  # Markdown export implementation
├── manager.py            # ExportManager - unified interface
└── test_exports.py       # Test suite
```

## Usage

### Basic Export

```python
from exports import ExportManager

# Initialize manager
manager = ExportManager()

# Export to Markdown
result = manager.export(
    paper_data=paper_dict,
    format='markdown',
    template='IEEE'
)

print(f"Exported to: {result['path']}")
```

### Export to Multiple Formats

```python
# Export to multiple formats at once
results = manager.export_multiple(
    paper_data=paper_dict,
    formats=['docx', 'pdf', 'latex', 'markdown'],
    template='IEEE'
)

for format, result in results['results'].items():
    print(f"{format}: {result['filename']}")
```

### Preview Export

```python
# Generate preview without creating file
preview = manager.preview(
    paper_data=paper_dict,
    format='markdown',
    max_length=1000
)

print(preview['preview'])
```

### Get Available Templates

```python
templates = manager.get_available_templates()
print(f"Available templates: {', '.join(templates)}")
```

## Paper Data Structure

The export system expects paper data in the following format:

```json
{
  "journal": "IEEE",
  "title": "Paper Title",
  "authors": [
    {
      "name": "Author Name",
      "affiliation": "University",
      "location": "City, Country",
      "email": "author@example.edu"
    }
  ],
  "abstract": "Abstract text...",
  "keywords": ["keyword1", "keyword2"],
  "section1": {
    "number": "I",
    "title": "INTRODUCTION",
    "content": "Section content..."
  },
  "references": {
    "number": "VI",
    "title": "REFERENCES",
    "content": [
      {
        "authors": "Smith, J.",
        "title": "Paper Title",
        "venue": "Journal Name",
        "year": "2024",
        "doi": "10.1234/example"
      }
    ]
  }
}
```

### Supported Section Formats

The system handles multiple section formats:

1. **New format**: Direct section keys (`section1`, `section2`, etc.)
2. **Legacy format**: `sections` array
3. **Old JTM format**: `Items` array

## API Integration

### Flask Route Example

```python
from exports import ExportManager, ExportError

@app.route("/api/export/<format>", methods=["POST"])
@jwt_required()
def export_paper(format):
    try:
        data = request.get_json()
        paper_data = data.get("paper", data)
        
        manager = ExportManager()
        result = manager.export(
            paper_data=paper_data,
            format=format,
            template=data.get("template")
        )
        
        return send_file(
            result['path'],
            as_attachment=True,
            download_name=result['filename']
        )
        
    except ExportError as e:
        return jsonify({"error": str(e)}), 400
```

## Export Options

### DOCX Export Options

```python
result = manager.export(
    paper_data=paper_dict,
    format='docx',
    template='IEEE',
    template_override='IJRED'  # Override template from paper_data
)
```

### PDF Export Options

```python
result = manager.export(
    paper_data=paper_dict,
    format='pdf',
    method='libreoffice',  # or 'docx2pdf', 'reportlab', 'auto'
    keep_docx=True         # Keep intermediate DOCX file
)
```

### LaTeX Export Options

```python
result = manager.export(
    paper_data=paper_dict,
    format='latex',
    include_bibtex=True    # Generate separate .bib file
)
```

## Testing

Run the test suite:

```bash
cd /home/sirobo/papergenerator/backend/exports
python test_exports.py
```

Or with pytest:

```bash
pytest test_exports.py -v
```

## Dependencies

### Required
- `python-docx`: DOCX generation
- `lxml`: XML processing for DOCX
- `pathlib`: File path handling

### Optional
- `reportlab`: Direct PDF generation (fallback)
- `docx2pdf`: DOCX to PDF conversion (Windows)
- LibreOffice: DOCX to PDF conversion (recommended)

### Installation

```bash
pip install python-docx lxml reportlab
```

For PDF conversion (optional):
```bash
# Ubuntu/Debian
sudo apt-get install libreoffice

# macOS
brew install libreoffice

# Windows
# Download from https://www.libreoffice.org/
```

## Error Handling

All exporters raise `ExportError` on failure:

```python
from exports import ExportManager, ExportError

try:
    result = manager.export(paper_data, 'pdf')
except ExportError as e:
    print(f"Export failed: {e}")
```

## Performance Considerations

- **DOCX**: Fast (uses existing template system)
- **Markdown**: Very fast (text generation)
- **LaTeX**: Fast (text generation)
- **PDF (LibreOffice)**: Moderate (requires external process)
- **PDF (ReportLab)**: Fast (direct generation, basic formatting)

## Cleanup

Remove old export files:

```python
# Delete exports older than 7 days
deleted = manager.cleanup_old_exports(days=7)
print(f"Deleted {deleted} old files")
```

## Troubleshooting

### PDF Export Fails

1. Check if LibreOffice is installed: `libreoffice --version`
2. Try fallback method: `method='reportlab'`
3. Check logs for detailed error messages

### DOCX Template Not Found

1. Verify template exists: `manager.get_available_templates()`
2. Check template files in `backend/templates/`
3. Ensure both `.docx` and `*gen.py` files exist

### LaTeX Special Characters

The system automatically escapes special LaTeX characters (`&`, `%`, `$`, etc.). If you need raw LaTeX in content, it will be escaped.

## Future Enhancements

Potential improvements:

1. **HTML Export**: Web-friendly format
2. **EPUB Export**: E-book format
3. **Image Embedding**: Better image handling in all formats
4. **Table Support**: Enhanced table formatting
5. **Equation Rendering**: Better equation support in PDF/Markdown
6. **Batch Export**: Export multiple papers at once
7. **Export Templates**: Customizable export templates
8. **Progress Tracking**: Real-time export progress

## Contributing

When adding new export formats:

1. Create new exporter class inheriting from `BaseExporter`
2. Implement `export()` method
3. Add to `ExportManager.exporters` dictionary
4. Add tests to `test_exports.py`
5. Update documentation

## License

Part of the Paper Generator system.
