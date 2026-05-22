# Test Plan: Electrical Engineering Student Persona

## Test Metadata

- **Test ID**: E2E-EE-001
- **Test Suite**: Persona-based E2E Tests
- **Created**: 2026-05-22
- **Last Updated**: 2026-05-22
- **Test File**: `e2e/electrical-engineering-persona.spec.js`
- **Estimated Duration**: 15-20 minutes (with full paper generation)

## Persona Profile

### Student Background
- **Name**: Ahmad (Electrical Engineering Student)
- **Department**: Teknik Elektro
- **Semester**: 8 (Final year)
- **Research Area**: Renewable Energy
- **Specialization**: Power Systems, Solar Energy

### Research Context
- **Topic**: Solar Panel Maximum Power Point Tracking (MPPT)
- **Method**: Simulation-based (MATLAB/Simulink)
- **Data Type**: Simulation data
- **Target Publication**: Jurnal Sinta 2-3 (Indonesian indexed journals)
- **Expected Content**: Heavy mathematical equations, technical diagrams, simulation results

## Test Objectives

### Primary Objectives
1. ✅ Verify paper generation workflow for technical/engineering content
2. ✅ Validate equation rendering (LaTeX/KaTeX) for complex mathematical formulas
3. ✅ Ensure technical terminology accuracy for electrical engineering domain
4. ✅ Verify figure/diagram generation for technical illustrations
5. ✅ Validate IEEE format export for engineering papers

### Secondary Objectives
1. ✅ Test literature search for domain-specific queries
2. ✅ Verify discovery question flow for engineering students
3. ✅ Validate paper structure for technical journals
4. ✅ Test AI chat interaction for technical guidance

## Test Scenarios

### Scenario 1: User Registration & Authentication
**Steps**:
1. Register new user with EE student credentials
2. Verify authentication cookies (access_token, CSRF)
3. Navigate to dashboard

**Expected Results**:
- User registered successfully
- Cookies set with proper security flags
- Dashboard shows empty state

**Assertions**:
- `expect(reg.status()).toBe(201)`
- `expect(cookies).toContain('access_token_cookie')`
- `expect(page.locator('text=No papers yet')).toBeVisible()`

---

### Scenario 2: Paper Creation
**Steps**:
1. Click "New Paper" button
2. Navigate to editor page
3. Extract paper ID from URL

**Expected Results**:
- Editor page loads successfully
- Paper ID is generated
- Title input is visible

**Assertions**:
- `await page.waitForURL(/\/editor/)`
- `expect(paperId).toBeTruthy()`
- `expect(titleInput).toBeVisible()`

---

### Scenario 3: Paper Metadata Entry
**Steps**:
1. Fill paper title: "Perancangan dan Simulasi MPPT untuk Sistem Photovoltaic"
2. Wait for auto-save
3. Verify save status

**Expected Results**:
- Title saved successfully
- "Saved" indicator appears

**Assertions**:
- `await titleInput.fill('Perancangan dan Simulasi MPPT...')`
- `expect(page.locator('text=Saved')).toBeVisible()`

---

### Scenario 4: Discovery Questions via Chat
**Steps**:
1. Open AI Chat panel
2. Send message with research context:
   - Department: Teknik Elektro
   - Topic: Solar Panel MPPT
   - Method: MATLAB simulation
   - Target: Sinta 2-3

**Expected Results**:
- Chat panel opens
- Message sent successfully
- AI responds with guidance

**Assertions**:
- `expect(chatInput).toBeVisible()`
- Message contains all discovery information

---

### Scenario 5: Literature Search (SLR)
**Steps**:
1. Navigate to Literature tab
2. Enter query: "MPPT solar panel control"
3. Click "Jalankan SLR"
4. Wait for search completion (15 seconds)

**Expected Results**:
- SLR starts successfully
- Progress indicator shows "Mencari..."
- Results populate literature table

**Assertions**:
- `expect(page.locator('text=Mencari')).toBeVisible()`
- Wait for completion with timeout

---

### Scenario 6: Paper Generation with Equations
**Steps**:
1. Open AI Chat
2. Request paper generation with specific requirements:
   - Mathematical equations for MPPT algorithms
   - Perturb & Observe (P&O) method
   - Incremental Conductance (InCond) method
   - Block diagrams
   - Simulation results

**Expected Results**:
- Generation starts
- Progress banner shows "AI sedang generate"
- Paper content populates with equations

**Assertions**:
- `expect(page.locator('text=AI sedang generate')).toBeVisible()`
- Wait 30 seconds for generation

---

### Scenario 7: Equation Rendering Verification
**Steps**:
1. Navigate to Equations tab
2. Count KaTeX rendered elements
3. Take screenshot of equations

**Expected Results**:
- Equations tab shows rendered LaTeX
- KaTeX elements are present
- Equations are properly formatted

**Assertions**:
- `const katexElements = page.locator('.katex, .katex-display')`
- `expect(count).toBeGreaterThan(0)`
- Screenshot saved: `ee-equations-tab.png`

---

### Scenario 8: Preview Content Verification
**Steps**:
1. Navigate to Preview tab
2. Verify paper structure (Abstract, sections)
3. Check for technical terms:
   - MPPT
   - photovoltaic
   - solar
   - power
   - voltage
   - current

**Expected Results**:
- Preview shows complete paper
- Abstract is visible
- Technical terms are present

**Assertions**:
- `expect(page.locator('text=Abstract')).toBeVisible()`
- Each technical term found and logged

---

### Scenario 9: Equation Formatting in Preview
**Steps**:
1. Stay in Preview tab
2. Count KaTeX elements in preview
3. Take closeup screenshot of first equation

**Expected Results**:
- Equations render in preview
- At least 1 equation present
- Equation screenshot captured

**Assertions**:
- `expect(equationCount).toBeGreaterThan(0)`
- Screenshot saved: `ee-equation-closeup.png`

---

### Scenario 10: Figure/Diagram Verification
**Steps**:
1. Search for image elements with alt text
2. Count figures/diagrams
3. Log figure captions

**Expected Results**:
- Figures are present in paper
- Images have proper alt text
- Captions are descriptive

**Assertions**:
- `const images = page.locator('img[alt*="Figure"]')`
- Log count and captions

---

### Scenario 11: Technical Terminology Accuracy
**Steps**:
1. Extract page content
2. Search for expected technical terms:
   - MPPT (Maximum Power Point Tracking)
   - P&O (Perturb and Observe)
   - InCond (Incremental Conductance)
   - PV (Photovoltaic)
   - DC-DC converter
   - duty cycle
   - irradiance
   - I-V characteristic

**Expected Results**:
- At least 4 out of 8 terms present
- Terms used in proper context

**Assertions**:
- `expect(foundTerms.length).toBeGreaterThan(3)`
- Log coverage percentage

---

### Scenario 12: IEEE Format Export
**Steps**:
1. Click DOCX export button
2. Wait for download
3. Verify filename ends with .docx
4. Save to test-results/

**Expected Results**:
- Download starts
- File is .docx format
- File saved successfully

**Assertions**:
- `expect(download.suggestedFilename()).toMatch(/\.docx$/)`
- File saved to `test-results/ee-paper-{timestamp}.docx`

---

### Scenario 13: Paper Metadata Verification
**Steps**:
1. Fetch paper data via API
2. Verify metadata:
   - Title contains "MPPT"
   - Authors present
   - Sections present
   - Images present
   - Keywords present

**Expected Results**:
- API returns paper data
- All metadata fields populated
- Section structure is logical

**Assertions**:
- `expect(paperData.title).toContain('MPPT')`
- Log all metadata fields

---

### Scenario 14: Final Assessment
**Steps**:
1. Take final screenshot
2. Generate test summary
3. Log all test results

**Expected Results**:
- All tests passed
- Artifacts generated
- Summary report complete

**Assertions**:
- All checkmarks logged
- Focus areas assessed
- Artifacts listed

## Test Data

### Input Data
```javascript
PERSONA_USER = {
  email: `ee-student-${Date.now()}@e2e.local`,
  name: 'Ahmad Electrical Engineering',
  password: 'EEStrongPass123!',
}

DISCOVERY_ANSWERS = {
  jurusan: 'Teknik Elektro',
  topik: 'Solar Panel Maximum Power Point Tracking (MPPT)',
  metode: 'Simulasi (MATLAB/Simulink)',
  data: 'Data simulasi',
  target: 'Jurnal Sinta 2-3',
}

LITERATURE_QUERY = 'MPPT solar panel control'
```

### Expected Technical Terms
- MPPT (Maximum Power Point Tracking)
- P&O (Perturb and Observe)
- InCond (Incremental Conductance)
- PV (Photovoltaic)
- DC-DC converter
- duty cycle
- irradiance
- I-V characteristic

## Success Criteria

### Must Have (Critical)
- ✅ User can register and login
- ✅ Paper can be created
- ✅ Literature search returns results
- ✅ Paper generation completes
- ✅ Equations render with KaTeX
- ✅ DOCX export works

### Should Have (Important)
- ✅ At least 4/8 technical terms present
- ✅ At least 1 equation in preview
- ✅ Figures/diagrams generated
- ✅ Paper structure is logical

### Nice to Have (Optional)
- Multiple equation types (inline, display)
- Complex nested equations
- High-quality figures
- Proper IEEE citation format

## Test Environment

### Prerequisites
- Backend running on `http://localhost:8001`
- Frontend running on `http://localhost:8000`
- Database initialized
- Playwright installed

### Browser
- Chromium (Desktop Chrome)

### Timeouts
- Default: 30 seconds
- Expect: 5 seconds
- Paper generation: 30 seconds
- Literature search: 15 seconds

## Test Artifacts

### Screenshots
- `ee-equations-tab.png` - Equations tab view
- `ee-preview-full.png` - Full preview page
- `ee-equation-closeup.png` - Closeup of first equation
- `ee-final-state.png` - Final state of application

### Downloads
- `ee-paper-{timestamp}.docx` - Exported paper

### Reports
- `playwright-report/index.html` - HTML test report
- Console logs with test summary

## Known Issues & Limitations

### Timing Issues
- Paper generation can take 15+ minutes for complex papers
- SLR search may timeout on slow connections
- Auto-save may not complete before next action

### Workarounds
- Increase `waitForTimeout` for paper generation
- Retry SLR if it times out
- Add explicit waits for save status

### Browser-Specific
- KaTeX rendering may differ slightly between browsers
- Screenshot sizes vary by viewport

## Maintenance Notes

### Update Frequency
- Review quarterly or when major features change
- Update technical terms list as domain evolves
- Adjust timeouts based on performance metrics

### Dependencies
- Playwright version: ^1.60.0
- KaTeX library version (frontend)
- Backend API stability

## References

- Playwright Documentation: https://playwright.dev
- KaTeX Documentation: https://katex.org
- IEEE Citation Style: https://ieee-dataport.org/sites/default/files/analysis/27/IEEE%20Citation%20Guidelines.pdf
- MPPT Algorithms: Academic literature on solar panel control
