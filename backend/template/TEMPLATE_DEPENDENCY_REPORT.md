# Template Generator Dependency Map
**Generated:** 2026-05-23  
**Location:** `/home/sirobo/papergenerator/backend/template/`

## Executive Summary

This directory contains **39 template generators** that convert JSON data into formatted DOCX documents for various academic journals and conferences.

### Key Findings

1. **Self-Contained Architecture**: Each generator is a standalone Python script (800-1500 lines avg)
2. **Missing Dependency**: `ULTIMACOMPgen.py` imports from non-existent `_docx_base` module
3. **High Code Duplication**: ~30-40% of code is duplicated across generators
4. **Two JSON Schemas**: Split between `_template.json` (20) and `_PLC-MediapipeID.json` (17)

---

## Generator Inventory

### By JSON Data Source

#### _template.json (20 generators)
AEJgen, CCJgen, CERiMREgen, DJLITgen, EASRgen, El-Usrahgen, ICETgen, ICIMECEgen, ICONIEgen, IJBgen, IJECEgen, IJIMSgen, IJITEEgen, IJREDgen, IJTgen, JATgen, JCEFgen, JIEBgen, KKCKgen, UITMgen

#### _PLC-MediapipeID.json (17 generators)
AMORIgen, ELCTRICESgen, ELKOLINDgen, ENERGIUPMgen, ICOSEGgen, IJEECSgen, JAMRISgen, JEEMECSgen, JMEMgen, JNTETIgen, JOKIgen, JRCgen, JTMMgen, JTRANSIENTgen, JTUNDIPgen, MEVgen, ROTASIgen

#### Other
- IEEEgen → ieee.json
- ULTIMACOMPgen → (no JSON, broken import)

---

## Dependency Analysis

### External Dependencies

| Package | Usage | Generators |
|---------|-------|------------|
| **python-docx** | Core DOCX manipulation | 39/39 (100%) |
| **lxml** | XML processing for OOXML | 28/39 (72%) |
| **PIL (Pillow)** | Image generation | 1 (CERiMREgen) |
| **latex2mathml** | LaTeX equation conversion | 2 (IJIMSgen, KKCKgen) |
| **mathml2omml** | MathML to Office Math | 2 (IJIMSgen, KKCKgen) |

### Standard Library Dependencies
- `json` - JSON parsing (all)
- `re` - Regular expressions (all)
- `pathlib` - Path handling (all)
- `shutil` - File operations (most)
- `zipfile` - DOCX archive manipulation (many)
- `copy`/`deepcopy` - Object cloning (many)
- `dataclasses` - Data structures (some)

### Local Dependencies

**BROKEN IMPORT:**
- `ULTIMACOMPgen.py` → `from _docx_base import ...`
  - File `_docx_base.py` does NOT exist
  - Expected functions: `open_template`, `finalize_doc`, `build_sectpr`, `embed_sectpr`, `setup_main_sectpr`, `para`, `set_para_style`, `append_rich_text`, `body_paragraphs`, `render_sections`, `append_line_break`, `append_text_run`, `run_generator`, `roman`

---

## Common Function Patterns

Functions appearing in multiple generators (potential for shared utilities):

| Function Name | Occurrences | Purpose |
|---------------|-------------|---------|
| `_set_para_style` | 17 | Set paragraph style by ID |
| `load_json` | 15 | Load and parse JSON data |
| `_set_ai_prompt_color_red` | 11 | Mark AI-generated placeholders |
| `set_run_font` | 10 | Apply font formatting to runs |
| `_wq` | 8 | XML qualified name helper |
| `_strict_to_trans` | 7 | Convert strict OOXML to transitional |
| `_append_inline_math` | 7 | Insert math equations |
| `set_paragraph_spacing` | 6 | Configure paragraph spacing |
| `_clear_document_body` | 5 | Remove existing document content |
| `_strip_latex` | 5 | Clean LaTeX syntax |

---

## Template Files

Each generator references:
1. **DOCX Template**: Base document with styles, numbering, headers/footers
   - Examples: `AEJ.docx`, `IEEE.docx`, `JRC.docx`
   - Located in same directory as generator
   
2. **JSON Data**: Paper content (title, authors, sections, figures, etc.)
   - Primary: `_template.json` or `_PLC-MediapipeID.json`
   - Located in same directory (expected, may not exist)

---

## Refactoring Recommendations

### 1. Create Shared Utility Module (`_docx_base.py`)

**Priority: HIGH** - Fixes broken import in ULTIMACOMPgen

Consolidate common functions:
- Document loading/saving
- Style application
- Section management
- Paragraph/run creation
- Font/spacing utilities
- Math equation handling
- Figure/table insertion

**Estimated Impact:** Reduce codebase by 30-40%, improve maintainability

### 2. Standardize JSON Schema

**Priority: MEDIUM**

Current split:
- 20 generators use `_template.json`
- 17 generators use `_PLC-MediapipeID.json`
- 1 uses `ieee.json`

**Recommendation:** Define single canonical schema or create adapter layer

### 3. Extract Common Patterns

**Priority: MEDIUM**

Create helper modules for:
- XML namespace handling (`_strict_to_trans`, `_wq`)
- Style management (`_set_para_style`, `set_run_font`)
- Content validation (`_set_ai_prompt_color_red`)
- Math processing (`_append_inline_math`, `_strip_latex`)

---

## Architecture Overview

```
template/
├── *gen.py (39 files)          # Generator scripts
├── *.docx (39 files)           # Template documents
├── _template.json (expected)   # JSON data source (schema 1)
├── _PLC-MediapipeID.json (exp) # JSON data source (schema 2)
└── _docx_base.py (MISSING!)    # Shared utilities (needed)
```

### Generator Workflow

1. Load JSON data (`_template.json` or `_PLC-MediapipeID.json`)
2. Copy DOCX template to output file
3. Open template with python-docx
4. Clear body content (preserve styles/numbering/headers)
5. Generate content from JSON:
   - Title page (journal-specific format)
   - Authors and affiliations
   - Abstract and keywords
   - Body sections (with numbering)
   - Figures and tables
   - Equations
   - References
6. Apply journal-specific formatting
7. Save output DOCX

---

## Issues & Blockers

### Critical
- [ ] **ULTIMACOMPgen.py broken**: Missing `_docx_base` module

### High Priority
- [ ] High code duplication (30-40%)
- [ ] No shared utility library
- [ ] Inconsistent JSON schemas

### Medium Priority
- [ ] Some generators very complex (1400+ lines)
- [ ] Mixed import styles (some use `from __future__`, some don't)
- [ ] Inconsistent error handling

---

## Next Steps

1. **Create `_docx_base.py`** with common utilities
2. **Fix ULTIMACOMPgen.py** import
3. **Refactor 3-5 generators** to use shared utilities (proof of concept)
4. **Standardize JSON schema** or create adapters
5. **Add unit tests** for shared utilities
6. **Document** each generator's specific requirements

---

*Report generated by dependency analysis script*
