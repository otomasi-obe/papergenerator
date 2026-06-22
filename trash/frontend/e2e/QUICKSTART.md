# Electrical Engineering Persona E2E Test - Quick Start

## 🎯 Test Overview

**Persona**: Mahasiswa Teknik Elektro semester 8, penelitian tentang renewable energy  
**Topic**: Solar Panel Maximum Power Point Tracking (MPPT)  
**Duration**: 15-20 minutes (with full paper generation)  
**Test File**: `frontend/e2e/electrical-engineering-persona.spec.js`

## 🚀 Quick Start

### 1. Prerequisites Check

```bash
# Check backend is running
curl http://localhost:8001/api/health

# Check frontend is running
curl http://localhost:8000

# Check Playwright is installed
cd frontend && npx playwright --version
```

### 2. Run the Test

**Option A: Using the helper script (recommended)**
```bash
cd frontend
./run-ee-test.sh
```

**Option B: Direct Playwright command**
```bash
cd frontend
npx playwright test e2e/electrical-engineering-persona.spec.js
```

**Option C: With UI mode (interactive)**
```bash
cd frontend
./run-ee-test.sh --ui
```

**Option D: Headed mode (see browser)**
```bash
cd frontend
./run-ee-test.sh --headed
```

### 3. View Results

```bash
# View HTML report
cd frontend
npx playwright show-report

# Check screenshots
ls -lh test-results/ee-*.png

# Check exported paper
ls -lh test-results/ee-paper-*.docx
```

## 📋 Test Scenarios (16 tests)

1. ✅ Register user with EE student persona
2. ✅ Navigate to dashboard and verify empty state
3. ✅ Create new paper
4. ✅ Fill paper title and basic info
5. ✅ Answer discovery questions via Chat
6. ✅ Navigate to Literature tab
7. ✅ Run literature search for MPPT
8. ✅ Request paper generation with equations emphasis
9. ✅ Navigate to Equations tab and verify LaTeX rendering
10. ✅ Navigate to Preview tab and verify content
11. ✅ Verify equations in preview are properly formatted
12. ✅ Check for figures and diagrams
13. ✅ Verify technical terminology accuracy
14. ✅ Export to DOCX (IEEE format)
15. ✅ Verify paper metadata and structure
16. ✅ Generate final assessment report

## 🎯 Focus Areas

### Equation Rendering Quality
- **What**: LaTeX/KaTeX rendering of mathematical formulas
- **How**: Count `.katex` elements, take screenshots
- **Success**: At least 1 equation rendered properly

### Technical Diagram Generation
- **What**: Figures, block diagrams, simulation results
- **How**: Search for `img[alt*="Figure"]` elements
- **Success**: Images present with proper alt text

### Citation Format (IEEE)
- **What**: IEEE-style citations and references
- **How**: Export to DOCX and verify format
- **Success**: DOCX file downloads successfully

### Formula Correctness
- **What**: Technical terminology accuracy
- **How**: Search for 8 key terms (MPPT, P&O, InCond, PV, DC-DC, duty cycle, irradiance, I-V)
- **Success**: At least 4/8 terms present

## 📊 Expected Outputs

### Screenshots
- `ee-equations-tab.png` - Equations tab full view
- `ee-preview-full.png` - Complete paper preview
- `ee-equation-closeup.png` - Closeup of first equation
- `ee-final-state.png` - Final application state

### Downloads
- `ee-paper-{timestamp}.docx` - Exported paper in IEEE format

### Console Output
```
=== TEST SUMMARY: Electrical Engineering Persona ===
✓ User registration: PASSED
✓ Paper creation: PASSED
✓ Discovery questions: PASSED
✓ Literature search (MPPT): PASSED
✓ Paper generation: PASSED
✓ Equation rendering (LaTeX/KaTeX): PASSED
✓ Technical terminology: PASSED
✓ DOCX export (IEEE format): PASSED

=== Focus Areas Assessment ===
• Equation rendering quality: Verified KaTeX elements present
• Technical diagram generation: Checked for figure elements
• Citation format (IEEE): Export completed successfully
• Formula correctness: Technical terms validated
```

## 🐛 Troubleshooting

### Test times out
```bash
# Increase timeout in the test file
test.setTimeout(180000); // 3 minutes
```

### Backend not responding
```bash
# Check PM2 status
pm2 status

# Restart backend
pm2 restart backend

# Check logs
pm2 logs backend --lines 50
```

### Browser not installed
```bash
cd frontend
npx playwright install chromium
```

### Paper generation takes too long
- **Normal**: 15-20 minutes for complex papers with equations
- **Workaround**: Increase `waitForTimeout` values in test
- **Check**: AI service availability and backend logs

### Screenshots not generated
- Check `test-results/` directory exists
- Ensure write permissions
- Run with `--headed` to see what's happening

## 📈 Performance Benchmarks

| Metric | Value |
|--------|-------|
| Total test duration | 3-5 min (without generation) |
| With paper generation | 15-20 min |
| Number of tests | 16 |
| Screenshots generated | 4 |
| DOCX file size | 500 KB - 2 MB |
| Screenshot total size | 5-10 MB |

## 🔧 Advanced Usage

### Run specific test
```bash
npx playwright test -g "Verify equations in preview"
```

### Run with trace
```bash
npx playwright test --trace on
```

### View trace
```bash
npx playwright show-trace test-results/trace.zip
```

### Run in debug mode
```bash
npx playwright test --debug
```

### Generate report only
```bash
npx playwright show-report
```

## 📝 Test Data

### User Credentials
- **Email**: `ee-student-{timestamp}@e2e.local`
- **Name**: Ahmad Electrical Engineering
- **Password**: EEStrongPass123!

### Discovery Answers
- **Jurusan**: Teknik Elektro
- **Topik**: Solar Panel Maximum Power Point Tracking (MPPT)
- **Metode**: Simulasi (MATLAB/Simulink)
- **Data**: Data simulasi
- **Target**: Jurnal Sinta 2-3

### Literature Query
- **Query**: "MPPT solar panel control"
- **Top K**: 20 papers

### Expected Technical Terms
1. MPPT (Maximum Power Point Tracking)
2. P&O (Perturb and Observe)
3. InCond (Incremental Conductance)
4. PV (Photovoltaic)
5. DC-DC converter
6. duty cycle
7. irradiance
8. I-V characteristic

## 🎓 Understanding the Test

### Why This Persona?
Electrical Engineering students working on power systems need:
- Heavy mathematical equations (MPPT algorithms)
- Technical diagrams (block diagrams, I-V curves)
- Simulation results (MATLAB/Simulink)
- IEEE citation format (standard for engineering)

### What Makes This Test Comprehensive?
1. **Full workflow**: Registration → Paper creation → Generation → Export
2. **Domain-specific**: Technical terms, equations, diagrams
3. **Quality checks**: Equation rendering, terminology accuracy
4. **Real-world scenario**: Actual research topic (MPPT)
5. **Multiple verification points**: 16 test scenarios

### Key Assertions
- User authentication works
- Paper creation flow is smooth
- Literature search returns relevant results
- AI generates domain-appropriate content
- Equations render properly with KaTeX
- Technical terms are accurate
- Export produces valid DOCX

## 📚 Related Documentation

- **Full Test Plan**: `frontend/e2e/TEST_PLAN.md`
- **E2E README**: `frontend/e2e/README.md`
- **Playwright Config**: `frontend/playwright.config.js`
- **Other Tests**: `frontend/e2e/smoke.spec.js`, `frontend/e2e/auth.spec.js`

## 🤝 Contributing

To add more persona tests:
1. Copy `electrical-engineering-persona.spec.js`
2. Modify persona details and discovery answers
3. Adjust technical terms for the domain
4. Update expected outputs
5. Add to test suite

## 📞 Support

If tests fail:
1. Check `test-results/` for screenshots
2. View HTML report: `npx playwright show-report`
3. Run in headed mode: `./run-ee-test.sh --headed`
4. Check backend logs: `pm2 logs backend`
5. Review test plan: `TEST_PLAN.md`

---

**Last Updated**: 2026-05-22  
**Test Version**: 1.0.0  
**Playwright Version**: 1.60.0
