# Template System Refactoring - Implementation Checklist

**Project:** Paper Template System Redesign  
**Timeline:** 10 weeks  
**Team:** 2-3 developers + 1 QA  

---

## Phase 1: Foundation (Weeks 1-2)

### Week 1: Core Module Structure

#### Task 1.1: Create Directory Structure
- [ ] Create `backend/template/core/` directory
- [ ] Create `backend/template/templates/` directory
- [ ] Create `backend/template/configs/` directory
- [ ] Create `backend/template/tests/` directory
- [ ] Add `__init__.py` files to all directories

**Acceptance Criteria:**
- Directory structure matches architecture diagram
- All directories are importable Python packages
- No import errors when importing core modules

**Estimated Time:** 1 hour

---

#### Task 1.2: Implement Shared Utilities (`core/utils.py`)
- [ ] Extract `normalize_text_commands()` from existing templates
- [ ] Extract `iter_rich_tokens()` for text tokenization
- [ ] Extract `split_body_blocks()` for paragraph splitting
- [ ] Extract `append_rich_text()` for formatted text rendering
- [ ] Extract `latex_to_omml()` for math conversion
- [ ] Extract `append_inline_math()` for equation rendering
- [ ] Extract `resolve_path()` for image path resolution
- [ ] Extract `clear_document_body()` for document cleanup
- [ ] Extract `inject_template_styles()` for style preservation
- [ ] Add comprehensive docstrings to all functions
- [ ] Add type hints to all functions

**Acceptance Criteria:**
- All functions have unit tests with >90% coverage
- Functions work with sample inputs from existing templates
- No dependencies on specific template implementations
- All functions are pure (no side effects except document modification)

**Estimated Time:** 16 hours

**Test Cases:**
```python
def test_normalize_text_commands():
    assert normalize_text_commands("**bold**") == "\\bbold\\b"
    assert normalize_text_commands("*italic*") == "\\iitalic\\i"
    assert normalize_text_commands("\\n") == "\n"

def test_iter_rich_tokens():
    tokens = list(iter_rich_tokens("Hello **world**"))
    assert len(tokens) == 3
    assert tokens[0] == {"kind": "text", "value": "Hello ", "bold": False}
    assert tokens[1] == {"kind": "text", "value": "world", "bold": True}

def test_split_body_blocks():
    text = "Para 1\n\nPara 2\n\nPara 3"
    blocks = split_body_blocks(text)
    assert len(blocks) == 3
    assert blocks[0] == "Para 1"
```

---

#### Task 1.3: Implement Type Definitions (`core/types.py`)
- [ ] Define `ContentItem` dataclass (text, figure, table, equation)
- [ ] Define `Section` dataclass (number, title, content, subsections)
- [ ] Define `Author` dataclass (name, affiliation, location, email)
- [ ] Define `Reference` dataclass (id, text)
- [ ] Define `TemplateMetadata` dataclass
- [ ] Add validation methods to each type
- [ ] Add `from_dict()` factory methods

**Acceptance Criteria:**
- All types are immutable (frozen dataclasses)
- All types have validation
- All types can be created from JSON dict
- Type hints work correctly with mypy

**Estimated Time:** 8 hours

**Example:**
```python
@dataclass(frozen=True)
class ContentItem:
    id: str  # "text", "figure", "table", "equation"
    text: Optional[str] = None
    path: Optional[str] = None
    title: Optional[str] = None
    number: Optional[int] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> ContentItem:
        return cls(
            id=data.get("id", "text"),
            text=data.get("text"),
            path=data.get("Path") or data.get("path"),
            title=data.get("Title") or data.get("title"),
            number=data.get("number"),
        )
    
    def validate(self) -> list[str]:
        errors = []
        if self.id == "figure" and not self.title:
            errors.append("Figure must have title")
        return errors
```

---

#### Task 1.4: Implement Configuration System (`core/config.py`)
- [ ] Create `TemplateConfig` class
- [ ] Implement YAML/JSON loading
- [ ] Implement schema validation
- [ ] Implement default value handling
- [ ] Add configuration merging (base + overrides)
- [ ] Add helpful error messages for invalid configs
- [ ] Create sample configuration files

**Acceptance Criteria:**
- Can load YAML and JSON configs
- Validates all required fields
- Provides clear error messages for invalid configs
- Supports configuration inheritance
- Has comprehensive tests

**Estimated Time:** 12 hours

**Example:**
```python
class TemplateConfig:
    def __init__(self, data: dict):
        self.template_id = data["template"]["id"]
        self.template_name = data["template"]["name"]
        self.fonts = data.get("fonts", {})
        self.sizes = data.get("sizes", {})
        # ... more fields
    
    @classmethod
    def from_file(cls, path: Path) -> TemplateConfig:
        if path.suffix == ".yaml":
            import yaml
            data = yaml.safe_load(path.read_text())
        else:
            import json
            data = json.loads(path.read_text())
        return cls(data)
    
    def validate(self) -> tuple[bool, list[str]]:
        errors = []
        if not self.template_id:
            errors.append("template.id is required")
        if not self.fonts.get("body"):
            errors.append("fonts.body is required")
        return len(errors) == 0, errors
```

---

### Week 2: Base Template Class

#### Task 2.1: Implement BaseTemplate Abstract Class (`core/base_template.py`)
- [ ] Define abstract methods (render_title, render_authors, etc.)
- [ ] Implement common rendering methods (render_section, render_content_items)
- [ ] Implement document lifecycle (prepare, render, save)
- [ ] Implement style extraction from template DOCX
- [ ] Implement state management (figure/table/equation counters)
- [ ] Add comprehensive docstrings
- [ ] Add type hints

**Acceptance Criteria:**
- All abstract methods are clearly defined
- Common methods work with mock implementations
- Document lifecycle is complete and tested
- Style extraction works with sample DOCX files
- Code is well-documented

**Estimated Time:** 20 hours

---

#### Task 2.2: Implement Template Registry (`core/registry.py`)
- [ ] Create `TemplateRegistry` class
- [ ] Implement `register()` method
- [ ] Implement `get()` method
- [ ] Implement `list_templates()` method
- [ ] Implement category filtering
- [ ] Implement metadata storage
- [ ] Add auto-discovery of templates
- [ ] Create global registry instance

**Acceptance Criteria:**
- Can register and retrieve templates
- Can list templates with metadata
- Can filter by category
- Thread-safe for concurrent access
- Has comprehensive tests

**Estimated Time:** 8 hours

---

#### Task 2.3: Create Test Suite for Core Modules
- [ ] Write unit tests for `utils.py` (>90% coverage)
- [ ] Write unit tests for `types.py` (>90% coverage)
- [ ] Write unit tests for `config.py` (>90% coverage)
- [ ] Write unit tests for `base_template.py` (>80% coverage)
- [ ] Write unit tests for `registry.py` (>90% coverage)
- [ ] Set up pytest configuration
- [ ] Set up coverage reporting
- [ ] Add CI/CD integration

**Acceptance Criteria:**
- All tests pass
- Coverage meets targets
- Tests run in <10 seconds
- CI/CD pipeline runs tests automatically

**Estimated Time:** 16 hours

---

## Phase 2: Pilot Templates (Weeks 3-4)

### Week 3: IEEE Template Migration

#### Task 3.1: Create IEEE Template Class
- [ ] Create `templates/ieee_template.py`
- [ ] Implement `render_title()` method
- [ ] Implement `render_authors()` method
- [ ] Implement `render_abstract()` method
- [ ] Implement section heading formatting
- [ ] Implement figure/table/equation rendering
- [ ] Implement references rendering
- [ ] Add IEEE-specific helper methods

**Acceptance Criteria:**
- All abstract methods implemented
- Code is clean and well-documented
- Uses inherited utilities where possible
- No hardcoded values (use config)

**Estimated Time:** 16 hours

---

#### Task 3.2: Create IEEE Configuration
- [ ] Create `configs/IEEE.yaml`
- [ ] Define all fonts and sizes
- [ ] Define section heading formats
- [ ] Define figure/table caption formats
- [ ] Define page layout settings
- [ ] Add validation rules
- [ ] Test configuration loading

**Acceptance Criteria:**
- Configuration is complete and valid
- All formatting rules are captured
- No hardcoded values remain in code

**Estimated Time:** 4 hours

---

#### Task 3.3: Validate IEEE Template Output
- [ ] Generate test documents with new template
- [ ] Compare with original IEEEgen.py output
- [ ] Document any differences
- [ ] Fix any regressions
- [ ] Create regression test suite
- [ ] Verify all test cases pass

**Acceptance Criteria:**
- Output matches original (or differences documented)
- All test cases pass
- No visual differences in rendered DOCX
- Performance is equal or better

**Estimated Time:** 12 hours

---

### Week 4: JTMM and IJECE Templates

#### Task 4.1: Create JTMM Template (Indonesian Journal)
- [ ] Create `templates/jtmm_template.py`
- [ ] Implement all abstract methods
- [ ] Create `configs/JTMM.yaml`
- [ ] Validate output against original
- [ ] Create regression tests

**Estimated Time:** 16 hours

---

#### Task 4.2: Create IJECE Template (International Journal)
- [ ] Create `templates/ijece_template.py`
- [ ] Implement all abstract methods
- [ ] Create `configs/IJECE.yaml`
- [ ] Validate output against original
- [ ] Create regression tests

**Estimated Time:** 16 hours

---

#### Task 4.3: Identify Common Patterns
- [ ] Compare IEEE, JTMM, IJECE implementations
- [ ] Extract common patterns to base class
- [ ] Refactor pilot templates to use common code
- [ ] Update documentation with patterns

**Estimated Time:** 8 hours

---

## Phase 3: Category Base Classes (Week 5)

#### Task 5.1: Create IEEETemplate Base Class
- [ ] Extract common IEEE formatting to base class
- [ ] Create variants: IEEE_Conference, IEEE_Journal
- [ ] Migrate ICOSEG, ICONIE, ICIMECE, ICET
- [ ] Validate all outputs

**Estimated Time:** 16 hours

---

#### Task 5.2: Create SintaTemplate Base Class
- [ ] Extract common Indonesian journal formatting
- [ ] Create base class for Sinta journals
- [ ] Migrate 3-4 Sinta templates
- [ ] Validate all outputs

**Estimated Time:** 16 hours

---

#### Task 5.3: Create InternationalJournalTemplate Base Class
- [ ] Extract common international journal formatting
- [ ] Create base class
- [ ] Migrate 3-4 international journal templates
- [ ] Validate all outputs

**Estimated Time:** 16 hours

---

## Phase 4: Full Migration (Weeks 6-8)

### Week 6: Migrate 12 Templates
- [ ] AEJ, AMORI, CCJ, CERiMRE
- [ ] DJLIT, EASR, ELCTRICES, ELKOLIND
- [ ] El-Usrah, ENERGIUPM, ICET, ICIMECE
- [ ] Create configs for all
- [ ] Validate all outputs
- [ ] Create regression tests

**Estimated Time:** 40 hours (3-4 hours per template)

---

### Week 7: Migrate 12 Templates
- [ ] ICONIE, IJB, IJEECS, IJIMS
- [ ] IJITEE, IJRED, IJT, JAMRIS
- [ ] JAT, JCEF, JEEMECS, JIEB
- [ ] Create configs for all
- [ ] Validate all outputs
- [ ] Create regression tests

**Estimated Time:** 40 hours

---

### Week 8: Migrate Remaining 12 Templates
- [ ] JMEM, JNTETI, JOKI, JRC
- [ ] JTRANSIENT, JTUNDIP, KKCK, MEV
- [ ] ROTASI, UITM, ULTIMACOMP
- [ ] Create configs for all
- [ ] Validate all outputs
- [ ] Create regression tests

**Estimated Time:** 40 hours

---

## Phase 5: Cleanup & Polish (Weeks 9-10)

### Week 9: Cleanup

#### Task 9.1: Archive Legacy Code
- [ ] Create `backend/template/legacy/` directory
- [ ] Move all original *gen.py files to legacy/
- [ ] Update all imports throughout codebase
- [ ] Add deprecation warnings to legacy code
- [ ] Test that nothing breaks

**Estimated Time:** 8 hours

---

#### Task 9.2: Code Review and Refactoring
- [ ] Review all template implementations
- [ ] Extract additional common patterns
- [ ] Optimize performance bottlenecks
- [ ] Improve error messages
- [ ] Add logging and debugging support

**Estimated Time:** 16 hours

---

#### Task 9.3: Documentation
- [ ] Write developer guide
- [ ] Write template configuration reference
- [ ] Write migration guide for custom templates
- [ ] Create API documentation
- [ ] Add inline code examples
- [ ] Create video tutorials (optional)

**Estimated Time:** 16 hours

---

### Week 10: Testing and Release

#### Task 10.1: Comprehensive Testing
- [ ] Run full regression test suite
- [ ] Performance benchmarking
- [ ] Load testing
- [ ] Edge case testing
- [ ] User acceptance testing

**Estimated Time:** 16 hours

---

#### Task 10.2: Release Preparation
- [ ] Create release notes
- [ ] Update CHANGELOG
- [ ] Tag release version
- [ ] Deploy to staging
- [ ] Deploy to production
- [ ] Monitor for issues

**Estimated Time:** 8 hours

---

#### Task 10.3: Post-Release
- [ ] Monitor error logs
- [ ] Fix any critical issues
- [ ] Gather user feedback
- [ ] Plan next iteration
- [ ] Celebrate! 🎉

**Estimated Time:** 16 hours

---

## Testing Strategy

### Unit Tests
- **Target:** >80% coverage for all modules
- **Tools:** pytest, pytest-cov
- **Run Frequency:** On every commit (CI/CD)

### Integration Tests
- **Target:** All templates generate valid DOCX
- **Tools:** pytest, python-docx validation
- **Run Frequency:** Daily

### Regression Tests
- **Target:** Output matches original generators
- **Tools:** Custom comparison scripts
- **Run Frequency:** Before each release

### Performance Tests
- **Target:** Generation time ≤ original
- **Tools:** pytest-benchmark
- **Run Frequency:** Weekly

---

## Risk Management

### High Risk Items
1. **Output differences** - Mitigate with byte-level comparison
2. **Performance regression** - Mitigate with benchmarking
3. **Breaking changes** - Mitigate with backward compatibility

### Medium Risk Items
1. **Configuration complexity** - Mitigate with validation and docs
2. **Team availability** - Mitigate with clear task breakdown
3. **Scope creep** - Mitigate with strict phase boundaries

### Low Risk Items
1. **Tool compatibility** - All tools are mature and stable
2. **Infrastructure** - Existing CI/CD can be reused
3. **Dependencies** - No new external dependencies

---

## Success Metrics

### Code Quality
- [ ] Code duplication < 10%
- [ ] Test coverage > 80%
- [ ] No critical bugs in production
- [ ] All linting checks pass

### Performance
- [ ] Generation time ≤ original
- [ ] Memory usage ≤ original
- [ ] Startup time < 100ms

### Developer Experience
- [ ] New template creation < 2 hours
- [ ] Bug fix propagation to 1 file
- [ ] Documentation completeness > 90%

### User Experience
- [ ] Output quality = original
- [ ] Error messages are helpful
- [ ] Template discovery is easy

---

## Daily Standup Template

**What did I do yesterday?**
- Completed tasks: [list]
- Blockers encountered: [list]

**What will I do today?**
- Planned tasks: [list]
- Expected completion: [time]

**Any blockers?**
- Technical: [list]
- Resource: [list]
- Other: [list]

---

## Weekly Review Template

**Week [N] Summary**

**Completed:**
- [ ] Task 1
- [ ] Task 2

**In Progress:**
- [ ] Task 3 (50% complete)

**Blocked:**
- [ ] Task 4 (waiting for X)

**Metrics:**
- Lines of code: [number]
- Tests written: [number]
- Coverage: [percentage]
- Templates migrated: [number]

**Next Week:**
- Focus: [area]
- Goals: [list]

---

## Contact Information

**Project Lead:** [Name]  
**Tech Lead:** [Name]  
**QA Lead:** [Name]  

**Slack Channel:** #template-refactoring  
**Issue Tracker:** [URL]  
**Documentation:** [URL]  

---

**End of Checklist**
