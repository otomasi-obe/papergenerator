# Paper Template System Analysis & Redesign Proposal

**Analysis Date:** 2026-05-22  
**Analyzed By:** Kilo AI  
**Scope:** backend/template/ directory (39 template generators)

---

## Executive Summary

The current paper template system consists of 39 independent generator scripts totaling ~34,865 lines of code. Analysis reveals **60-70% code duplication** across templates, with core functionality (text rendering, math conversion, figure/table handling) reimplemented in each file. This creates significant maintenance burden and inconsistency risks.

**Recommendation:** Refactor to a class-based architecture with shared base classes, configuration-driven templates, and a template registry system.

---

## 1. Current State Analysis

### 1.1 Template Inventory

**Total Templates:** 39 journal/conference formats  
**Total Lines of Code:** 34,865 lines  
**Average File Size:** ~894 lines per template  
**File Size Range:** 300 lines (ULTIMACOMP) to 1,385+ lines (ICOSEG)

**Template Categories:**

| Category | Count | Examples |
|----------|-------|----------|
| IEEE-style conferences | 5 | IEEE, ICOSEG, ICONIE, ICIMECE, ICET |
| Indonesian journals (Sinta) | 15 | JTMM, JNTETI, JOKI, ELKOLIND, ROTASI |
| International journals | 10 | IJECE, IJEECS, IJT, IJRED, JAMRIS |
| Regional/specialized | 9 | AEJ (ASEAN), ULTIMACOMP, UITM, CCJ |

### 1.2 Code Duplication Analysis

**Highly Duplicated Functions:**

| Function | Occurrences | Purpose |
|----------|-------------|---------|
| `_append_inline_math` | 25 files | LaTeX → OMML math rendering |
| `_append_rich_text` | 23 files | Markdown-style text formatting |
| `_iter_rich_tokens` | 19 files | Text tokenization for formatting |
| `_latex_to_omml` | 19 files | LaTeX to Office Math conversion |
| `_normalize_text_commands` | 17 files | Text preprocessing |
| `_clear_document_body` | 15+ files | Document body cleanup |
| `_resolve_path` | 15+ files | Image path resolution |
| `_add_section_heading` | 20+ files | Section heading rendering |
| `_add_figure` | 25+ files | Figure insertion |
| `_add_table` | 25+ files | Table rendering |

**Estimated Code Duplication:** 60-70% of codebase

### 1.3 Common Architecture Pattern

All templates follow this workflow:

```python
1. Copy template DOCX file → output location
2. Open with python-docx
3. Extract style samples from template (pPr, rPr elements)
4. Clear document body (preserve sectPr, styles, headers/footers)
5. Load JSON configuration
6. Render content:
   - Front matter (title, authors, abstract, keywords)
   - Sections with nested subsections
   - Content items (text, figures, tables, equations)
   - References
7. Save output DOCX
```

### 1.4 Common Dependencies

**Core Libraries:**
- `python-docx` - DOCX manipulation (all 39 files)
- `lxml` - XML processing (35+ files)
- `latex2mathml` - Math conversion (25+ files)

**Common Imports:**
```python
from docx import Document                    # 33 files
from docx.oxml import OxmlElement           # 30 files
from docx.oxml.ns import qn                 # 30 files
from docx.shared import Cm, Pt              # 16 files
from docx.enum.text import WD_ALIGN_PARAGRAPH # 15 files
```

### 1.5 Hardcoded Configuration Examples

Each template hardcodes formatting rules:

```python
# IEEEgen.py
BODY_FONT = "Times New Roman"
MAX_FIGURE_WIDTH_CM = 8.4
PAGE_WIDTH_PT = 595.3

# JTMMgen.py
BODY_FONT = "Times New Roman"
MAX_FIGURE_WIDTH_CM = 14.0
EQUATION_RIGHT_TAB_PT = 468.0

# IJECEgen.py
CFG = {
    "font_body": "Times New Roman",
    "size_body": 10,
    "size_title": 16,
    "section_heading_format": "arabic_dot",
    ...
}
```

### 1.6 Shared Module Attempt

**Finding:** Only 1 file (`ULTIMACOMPgen.py`) attempts to use a shared module:

```python
from _docx_base import (
    open_template, finalize_doc,
    build_sectpr, embed_sectpr,
    para, append_rich_text, body_paragraphs,
    render_sections, ...
)
```

**Status:** The `_docx_base.py` module does not exist in the repository. This appears to be an incomplete refactoring attempt.

---

## 2. Identified Problems

### 2.1 Maintenance Issues

1. **Bug fixes require 39 file updates** - A bug in `_append_inline_math` must be fixed in 25 separate files
2. **Feature additions are expensive** - Adding support for new content types requires modifying all templates
3. **Inconsistent implementations** - Same function has subtle differences across files
4. **Testing complexity** - No shared test suite, each template needs independent testing

### 2.2 Code Quality Issues

1. **No abstraction** - Core logic mixed with formatting rules
2. **No inheritance** - Each template reimplements everything
3. **Hardcoded values** - Formatting rules embedded in code
4. **No validation** - Templates don't validate their configuration
5. **Poor discoverability** - No registry or metadata system

### 2.3 Scalability Issues

1. **Adding new templates is slow** - Must copy ~800 lines of boilerplate
2. **No template variants** - Can't easily create "IEEE 2-column" vs "IEEE 1-column"
3. **No composition** - Can't mix features from different templates

---

## 3. Proposed Architecture

### 3.1 Class Hierarchy

```
BaseTemplate (abstract)
├── Core rendering logic
├── Common utilities (math, rich text, paths)
├── Template lifecycle (load, render, save)
└── Configuration validation

├─ IEEETemplate
│  ├── IEEE conference format
│  └── Variants: IEEE_TwoColumn, IEEE_Journal
│
├─ SintaTemplate (Indonesian journals)
│  ├── Common Sinta formatting
│  └── Variants: JTMM, JNTETI, ELKOLIND, etc.
│
├─ InternationalJournalTemplate
│  ├── Common international journal format
│  └── Variants: IJECE, IJEECS, IJT, etc.
│
└─ ConferenceTemplate
   ├── Common conference format
   └── Variants: ICOSEG, ICONIE, ICET, etc.
```

### 3.2 Configuration-Driven Templates

**Template Configuration Format (YAML/JSON):**

```yaml
template:
  id: "IEEE"
  name: "IEEE Conference Paper"
  version: "2024"
  base_template: "IEEE.docx"
  
page:
  width_pt: 595.3
  height_pt: 841.9
  margins:
    top: 54.0
    bottom: 72.0
    left: 44.65
    right: 44.65
  columns: 2
  column_gap: 18.0

fonts:
  body: "Times New Roman"
  heading: "Times New Roman"
  title: "Arial"
  
sizes:
  body: 10
  title: 14
  heading1: 10
  heading2: 10
  caption: 9
  
formatting:
  section_heading: "roman_upper"  # I. INTRODUCTION
  subsection_heading: "letter"     # A. Subsection
  figure_caption: "Fig. {n}. {title}"
  table_caption: "TABLE {roman}. {title}"
  
content:
  max_figure_width_cm: 8.4
  table_borders: "partial"  # top, bottom, insideH, insideV
  equation_numbering: "right_aligned"
```

### 3.3 Shared Utilities Module

**File:** `backend/template/core/utils.py`

```python
# Text processing
def normalize_text_commands(text: str) -> str
def iter_rich_tokens(text: str) -> Iterator[Token]
def split_body_blocks(text: str) -> list[str]

# Math rendering
def latex_to_omml(latex: str, xslt_path: Path) -> Element
def append_inline_math(paragraph, latex: str) -> bool

# Path resolution
def resolve_path(path_text: str, json_path: Path, base_dir: Path) -> Path

# Document manipulation
def clear_document_body(doc: Document) -> None
def inject_template_styles(doc: Document, template_path: Path) -> None
def apply_sample_ppr(paragraph, sample_ppr: Element) -> None
def apply_sample_rpr(run, sample_rpr: Element) -> None
```

### 3.4 Base Template Class

**File:** `backend/template/core/base_template.py`

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

class BaseTemplate(ABC):
    """Base class for all paper templates."""
    
    def __init__(self, config_path: Path):
        self.config = self.load_config(config_path)
        self.validate_config()
        
    @abstractmethod
    def render_front_matter(self, doc: Document, data: dict) -> None:
        """Render title, authors, abstract, keywords."""
        pass
    
    @abstractmethod
    def render_section_heading(self, doc: Document, section: dict) -> None:
        """Render section heading with proper numbering."""
        pass
    
    def render_content_item(self, doc: Document, item: dict) -> None:
        """Render a content item (text, figure, table, equation)."""
        item_type = item.get("id", "").lower()
        
        if item_type == "text":
            self.render_text(doc, item)
        elif item_type in ("gambar", "image", "figure"):
            self.render_figure(doc, item)
        elif item_type in ("tabel", "table"):
            self.render_table(doc, item)
        elif item_type in ("rumus", "formula", "equation"):
            self.render_equation(doc, item)
    
    def build_document(self, json_path: Path, output_path: Path) -> Path:
        """Main entry point: load JSON, render document, save."""
        data = self.load_json(json_path)
        doc = self.prepare_document()
        
        self.render_front_matter(doc, data)
        self.render_sections(doc, data, json_path)
        self.render_references(doc, data)
        
        self.finalize_document(doc)
        doc.save(str(output_path))
        return output_path
```

### 3.5 Template Registry

**File:** `backend/template/core/registry.py`

```python
class TemplateRegistry:
    """Central registry for all available templates."""
    
    def __init__(self):
        self._templates: dict[str, type[BaseTemplate]] = {}
        self._metadata: dict[str, dict] = {}
    
    def register(self, template_id: str, template_class: type[BaseTemplate], 
                 metadata: dict) -> None:
        """Register a template class."""
        self._templates[template_id] = template_class
        self._metadata[template_id] = metadata
    
    def get(self, template_id: str) -> type[BaseTemplate]:
        """Get template class by ID."""
        return self._templates[template_id]
    
    def list_templates(self, category: str = None) -> list[dict]:
        """List all available templates with metadata."""
        templates = []
        for tid, meta in self._metadata.items():
            if category is None or meta.get("category") == category:
                templates.append({
                    "id": tid,
                    "name": meta.get("name"),
                    "category": meta.get("category"),
                    "description": meta.get("description"),
                })
        return templates

# Global registry instance
registry = TemplateRegistry()
```

### 3.6 Example Refactored Template

**File:** `backend/template/templates/ieee_template.py`

```python
from ..core.base_template import BaseTemplate
from ..core.utils import append_rich_text, append_inline_math
from ..core.registry import registry

class IEEETemplate(BaseTemplate):
    """IEEE conference paper template."""
    
    def render_front_matter(self, doc: Document, data: dict) -> None:
        # Title
        title_para = self.add_paragraph(doc, style="paper title")
        append_rich_text(title_para, data.get("title", "Untitled"))
        
        # Authors
        self.render_authors(doc, data.get("authors", []))
        
        # Abstract
        self.render_abstract(doc, data.get("abstract", ""))
        
        # Keywords
        self.render_keywords(doc, data.get("keywords", []))
    
    def render_section_heading(self, doc: Document, section: dict) -> None:
        number = section.get("number", 1)
        title = section.get("title", "").upper()
        
        para = self.add_paragraph(doc, style="heading 1")
        append_rich_text(para, f"{self.roman(number)}. {title}")

# Register template
registry.register("IEEE", IEEETemplate, {
    "name": "IEEE Conference Paper",
    "category": "conference",
    "description": "Standard IEEE conference paper format",
    "base_template": "IEEE.docx",
})
```

---

## 4. Migration Strategy

### Phase 1: Foundation (Week 1-2)

1. **Create core module structure:**
   ```
   backend/template/core/
   ├── __init__.py
   ├── base_template.py      # BaseTemplate abstract class
   ├── utils.py              # Shared utilities
   ├── registry.py           # Template registry
   ├── config.py             # Configuration loader/validator
   └── types.py              # Type definitions
   ```

2. **Extract common utilities:**
   - Move duplicated functions to `utils.py`
   - Add comprehensive tests
   - Document all functions

3. **Create BaseTemplate class:**
   - Define abstract interface
   - Implement common rendering logic
   - Add configuration validation

### Phase 2: Template Categories (Week 3-4)

1. **Create category base classes:**
   ```
   backend/template/templates/
   ├── __init__.py
   ├── ieee_template.py      # IEEETemplate base
   ├── sinta_template.py     # SintaTemplate base
   ├── journal_template.py   # InternationalJournalTemplate
   └── conference_template.py # ConferenceTemplate
   ```

2. **Migrate 2-3 templates per category:**
   - Start with simplest templates
   - Validate output matches original
   - Create regression tests

### Phase 3: Configuration System (Week 5)

1. **Create template configurations:**
   ```
   backend/template/configs/
   ├── IEEE.yaml
   ├── JTMM.yaml
   ├── IJECE.yaml
   └── ...
   ```

2. **Implement configuration loader:**
   - YAML/JSON parsing
   - Schema validation
   - Default value handling

### Phase 4: Full Migration (Week 6-8)

1. **Migrate remaining templates:**
   - 5-7 templates per week
   - Parallel testing with original generators
   - Document any differences

2. **Create template registry UI:**
   - List available templates
   - Show template metadata
   - Template selection interface

### Phase 5: Cleanup & Documentation (Week 9-10)

1. **Remove old template files:**
   - Archive original generators
   - Update imports throughout codebase
   - Remove deprecated code

2. **Documentation:**
   - Template developer guide
   - Configuration reference
   - Migration guide for custom templates

---

## 5. Benefits

### 5.1 Maintenance

- **Bug fixes:** Fix once in base class, applies to all templates
- **Feature additions:** Add to base class, available to all templates
- **Consistency:** Shared code ensures consistent behavior
- **Testing:** Shared test suite, template-specific tests only for unique features

### 5.2 Development Speed

- **New templates:** 50-100 lines vs 800+ lines
- **Template variants:** Inherit and override specific methods
- **Rapid prototyping:** Configuration changes without code changes

### 5.3 Code Quality

- **Reduced duplication:** From 60-70% to <10%
- **Better abstraction:** Clear separation of concerns
- **Type safety:** Proper type hints and validation
- **Testability:** Isolated, testable components

### 5.4 User Experience

- **Template discovery:** Browse available templates with metadata
- **Template validation:** Catch configuration errors early
- **Better error messages:** Context-aware error reporting

---

## 6. Risks & Mitigations

### Risk 1: Output Differences

**Risk:** Refactored templates produce slightly different output  
**Mitigation:**
- Byte-level comparison of generated DOCX files
- Visual regression testing
- Parallel running of old and new generators during migration

### Risk 2: Breaking Changes

**Risk:** Existing code depends on specific template file structure  
**Mitigation:**
- Maintain backward compatibility layer
- Gradual migration with deprecation warnings
- Comprehensive integration tests

### Risk 3: Configuration Complexity

**Risk:** YAML configs become too complex or hard to maintain  
**Mitigation:**
- Start with simple configs, add complexity gradually
- Provide config validation and helpful error messages
- Create config generator tool

### Risk 4: Performance Regression

**Risk:** Abstraction layers slow down generation  
**Mitigation:**
- Profile before and after
- Optimize hot paths
- Cache compiled configurations

---

## 7. Success Metrics

1. **Code Reduction:** Reduce total lines from 34,865 to <15,000 (57% reduction)
2. **Duplication:** Reduce code duplication from 60-70% to <10%
3. **Development Speed:** New template creation time from 8 hours to <2 hours
4. **Bug Fix Time:** Bug fix propagation from 39 files to 1 file
5. **Test Coverage:** Achieve >80% test coverage for core modules
6. **Output Accuracy:** 100% output match with original generators

---

## 8. Recommended Next Steps

1. **Immediate (This Week):**
   - Review and approve this proposal
   - Select 3 pilot templates for initial refactoring (suggest: IEEE, JTMM, IJECE)
   - Set up core module structure

2. **Short Term (Next 2 Weeks):**
   - Implement BaseTemplate and core utilities
   - Migrate 3 pilot templates
   - Create regression test suite

3. **Medium Term (Next 2 Months):**
   - Migrate all 39 templates
   - Implement template registry
   - Create configuration system

4. **Long Term (Next 3 Months):**
   - Remove legacy code
   - Complete documentation
   - Add template management UI

---

## Appendix A: Template Categorization

### IEEE-Style (5 templates)
- IEEE, ICOSEG, ICONIE, ICIMECE, ICET
- **Common:** 2-column, Times New Roman, Roman numeral sections

### Indonesian Journals - Sinta (15 templates)
- JTMM, JNTETI, JOKI, JTRANSIENT, JTUNDIP, ROTASI, MEV, ELKOLIND, ELCTRICES, JEEMECS, JMEM, JRC, JCEF, JIEB, KKCK
- **Common:** Bilingual abstract, Indonesian formatting standards

### International Journals (10 templates)
- IJECE, IJEECS, IJT, IJRED, IJITEE, IJIMS, IJB, JAMRIS, JAT, DJLIT
- **Common:** Single column, numbered sections, standard citation format

### Regional/Specialized (9 templates)
- AEJ (ASEAN), ULTIMACOMP, UITM, CCJ, CERiMRE, EASR, ENERGIUPM, AMORI, El-Usrah
- **Common:** Varied formats, specific regional requirements

---

## Appendix B: Code Duplication Examples

### Example 1: `_normalize_text_commands` (17 files)

**Identical implementation in:**
- IEEEgen.py (lines 253-258)
- JTMMgen.py (lines 134-139)
- IJECEgen.py (lines 294-299)
- ICOSEGgen.py (lines 234-239)
- ELKOLINDgen.py (lines 315-320)
- ... 12 more files

**Estimated duplicate lines:** 17 files × 6 lines = 102 lines

### Example 2: `_append_inline_math` (25 files)

**Similar implementation with minor variations in:**
- IEEEgen.py (lines 224-237)
- JTMMgen.py (lines 243-254)
- IJECEgen.py (lines 125-157)
- ... 22 more files

**Estimated duplicate lines:** 25 files × 15 lines = 375 lines

### Example 3: `_add_figure` (25 files)

**Similar structure, different formatting in:**
- IEEEgen.py (lines 875-910)
- JTMMgen.py (lines 580-622)
- IJECEgen.py (lines 531-570)
- ... 22 more files

**Estimated duplicate lines:** 25 files × 40 lines = 1,000 lines

**Total estimated duplicate lines from these 3 functions alone:** 1,477 lines (4.2% of codebase)

---

**End of Analysis**
