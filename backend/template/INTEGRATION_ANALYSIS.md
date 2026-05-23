# Template Generator Integration Analysis

## Critical Discovery: Application Integration

The template generators are **NOT standalone scripts** - they are **Python modules** imported and used by the main Flask application (`app.py`).

### Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Flask Application (app.py)                  │
│                                                                 │
│  • Handles HTTP requests                                       │
│  • Manages user authentication                                 │
│  • Stores papers in database                                   │
│  • Dynamically loads template generators                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ importlib.import_module(f"template.{name}gen")
                     │ getattr(mod, "build_document")
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              Template Generators (template/*gen.py)             │
│                                                                 │
│  • 39 generator modules (one per journal)                      │
│  • Each exposes build_document(json_data, output_path)         │
│  • Called by app to generate formatted DOCX                    │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ imports
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Dependencies                        │
│                                                                 │
│  • python-docx (DOCX manipulation)                             │
│  • lxml (XML processing)                                       │
│  • PIL/Pillow (image generation)                               │
│  • latex2mathml + mathml2omml (math equations)                 │
└─────────────────────────────────────────────────────────────────┘
```

### Code References

**app.py line 61:**
```python
from template.IEEEgen import build_document as build_ieee_docx
```

**app.py lines 330-340:**
```python
def _get_template_builder(journal_code: str):
    """Return the build_document callable for a known template code."""
    available = _available_journals()
    m = {c.lower(): c for c in available}
    canonical = m.get(journal_code.lower())
    if not canonical:
        raise ValueError(f"Unknown journal template: {journal_code}")
    mod = importlib.import_module(f"template.{canonical}gen")
    builder = getattr(mod, "build_document", None)
    if not callable(builder):
        raise ValueError(f"Template generator missing build_document: {canonical}gen")
    return canonical, builder
```

### API Contract

Each generator module **MUST** expose:

```python
def build_document(json_data: dict, output_path: str) -> None:
    """
    Generate a formatted DOCX document from JSON data.
    
    Args:
        json_data: Paper content (title, authors, sections, etc.)
        output_path: Path where output DOCX should be saved
    """
    # Implementation...
```

### Impact on Refactoring

1. **Interface Preservation**: Any refactoring MUST preserve the `build_document()` function signature
2. **Import Compatibility**: Generators must remain importable as `template.<NAME>gen`
3. **Breaking Changes**: Changes to the API will break the main application
4. **Testing Required**: Integration tests needed to verify app ↔ generator communication

### Current Status

- **Working**: 38/39 generators can be imported (assuming they have `build_document`)
- **Broken**: ULTIMACOMPgen cannot be imported (missing `_docx_base` dependency)
- **Risk**: Refactoring without preserving API will break production

### Recommendations Updated

**Priority 1 (CRITICAL)**: Create `_docx_base.py` AND verify API compatibility
- Extract common functions to shared module
- Ensure all generators still expose `build_document()`
- Test that app.py can still import and call generators
- Fix ULTIMACOMPgen

**Priority 2 (HIGH)**: Add integration tests
- Test app.py → generator communication
- Verify `build_document()` signature across all generators
- Test dynamic import mechanism
- Ensure backward compatibility

**Priority 3 (MEDIUM)**: Standardize internal implementation
- Refactor internal functions (safe - not exposed to app)
- Reduce code duplication
- Improve maintainability
- Keep `build_document()` interface stable

---

**Generated:** 2026-05-23  
**Location:** `/home/sirobo/papergenerator/backend/template/`
