# CS Student IoT Paper E2E Test

## Overview

Comprehensive end-to-end test simulating a Computer Science student (semester 7) generating a thesis paper about IoT Smart Home Automation.

**Test File**: `cs-student-iot.spec.js`

## Persona

- **Name**: Budi Computer Science
- **Program**: Teknik Informatika semester 7
- **Research Topic**: IoT Smart Home Automation
- **Research Method**: Kuantitatif (eksperimen)
- **Data**: Ada data hasil eksperimen
- **Target**: Tugas akhir / skripsi

## Test Scenario

The test covers the complete paper generation workflow:

1. **User Registration** - Register new test user with CS student persona
2. **Dashboard Navigation** - Verify empty state and UI
3. **Paper Creation** - Create new paper project
4. **Title Input** - Fill paper title about IoT smart home
5. **Discovery Questions** - Answer AI questions about research context
6. **Literature Tab** - Navigate to literature management
7. **PDF Upload** - Upload IoT-related papers (simulated)
8. **SLR Execution** - Run Systematic Literature Review with query "IoT smart home automation"
9. **SLR Completion** - Wait for SLR to complete (max 5 minutes)
10. **Paper Generation** - Request full paper with 20 SLR references
11. **Preview Verification** - Check paper appears in preview
12. **Section Validation** - Verify all sections present:
    - Introduction
    - Related Work
    - Methodology
    - Results
    - Conclusion
13. **Content Validation** - Check IoT-specific terminology:
    - IoT, smart home, sensor, actuator, automation
    - MQTT, ESP32, Arduino, WiFi, mobile app
14. **Citation Check** - Verify references and citations
15. **DOCX Export** - Export paper to Word format
16. **API Verification** - Check paper metadata via API
17. **Final Report** - Generate comprehensive test report

## Constraints

- **Timeout**: 10 minutes maximum (600,000ms)
- **Mode**: Headless (no GUI)
- **Screenshots**: Saved to `test-results/cs-student/`
- **Network Logging**: All requests logged
- **Console Monitoring**: Errors captured

## Prerequisites

### 1. Servers Running

```bash
# Backend (port 8001)
cd backend
python -m uvicorn main:app --port 8001

# Frontend (port 8000)
cd frontend
npm run dev
```

Or use PM2:

```bash
pm2 start ecosystem.config.cjs
pm2 logs
```

### 2. Dependencies Installed

```bash
cd frontend
npm install
npx playwright install chromium
```

### 3. Database Accessible

Ensure the database is running and migrations are applied.

## Running the Test

### Option 1: Using Helper Script (Recommended)

```bash
cd frontend
./run-cs-iot-test.sh
```

The script will:
- Check if servers are running
- Clean previous test results
- Run the test with full logging
- Display execution summary
- Show paths to test artifacts

### Option 2: Direct Playwright Command

```bash
cd frontend
npx playwright test --project=cs-student-iot
```

### Option 3: With UI Mode (for debugging)

```bash
cd frontend
npx playwright test cs-student-iot.spec.js --ui
```

### Option 4: Run Specific Test Step

```bash
cd frontend
npx playwright test cs-student-iot.spec.js -g "Run SLR"
```

## Test Artifacts

After test execution, the following artifacts are generated:

### Screenshots (18 total)

```
test-results/cs-student/
├── 01-dashboard-empty.png
├── 02-editor-new.png
├── 03-title-filled.png
├── 04-discovery-input.png
├── 05-discovery-response.png
├── 06-literature-tab.png
├── 07-upload-section.png
├── 08-slr-query-input.png
├── 09-slr-started.png
├── 10-slr-progress-*.png (multiple)
├── 11-slr-completed.png
├── 12-generation-request.png
├── 13-generation-in-progress.png
├── 14-preview-full.png
├── 15-section-*.png (5 sections)
├── 16-references-section.png
├── 17-export-completed.png
└── 18-final-state.png
```

### Exported Paper

```
test-results/cs-student/
└── cs-iot-paper-{timestamp}.docx
```

### Test Reports

```
playwright-report/
├── index.html          # Interactive HTML report
├── results.json        # Machine-readable results
└── trace.zip          # Full execution trace
```

## Viewing Results

### HTML Report

```bash
cd frontend
npx playwright show-report
```

Opens interactive report in browser with:
- Test execution timeline
- Screenshots at each step
- Network requests
- Console logs
- Trace viewer

### Trace Viewer

```bash
cd frontend
npx playwright show-trace playwright-report/trace.zip
```

Provides detailed execution trace with:
- DOM snapshots at each action
- Network activity
- Console messages
- Action timeline

## Expected Results

### Success Criteria

- ✓ User registration completes
- ✓ Paper created with valid ID
- ✓ Discovery questions answered
- ✓ SLR completes within 5 minutes
- ✓ Paper generation completes within 3 minutes
- ✓ At least 3 of 5 sections present
- ✓ At least 4 IoT terms found
- ✓ DOCX export succeeds
- ✓ Total execution < 10 minutes

### Quality Metrics

- **Section Coverage**: 5/5 sections (Introduction, Related Work, Methodology, Results, Conclusion)
- **IoT Terminology**: 10 key terms validated
- **Citation Quality**: References section present
- **Export Functionality**: DOCX generated successfully

### Performance Benchmarks

- User registration: < 5s
- Paper creation: < 3s
- SLR execution: 60-300s (depends on API)
- Paper generation: 60-180s (depends on AI)
- Total execution: 300-600s

## Troubleshooting

### Test Timeout

If test exceeds 10 minutes:
- Check backend API response times
- Verify SLR service is responding
- Check AI generation service status

### SLR Not Completing

If SLR hangs:
- Check backend logs for errors
- Verify external API keys (Semantic Scholar, etc.)
- Check network connectivity

### Paper Generation Fails

If generation doesn't complete:
- Check AI service (OpenAI/Anthropic) API keys
- Verify rate limits not exceeded
- Check backend logs for errors

### Screenshots Not Saved

If screenshots missing:
- Verify `test-results/cs-student/` directory exists
- Check file permissions
- Ensure sufficient disk space

### DOCX Export Fails

If export doesn't work:
- Check backend document generation service
- Verify python-docx library installed
- Check file write permissions

## Debugging

### Run with Debug Mode

```bash
DEBUG=pw:api npx playwright test cs-student-iot.spec.js
```

### Run with Headed Browser

```bash
npx playwright test cs-student-iot.spec.js --headed --project=chromium
```

### Run with Slow Motion

```bash
npx playwright test cs-student-iot.spec.js --headed --slow-mo=1000
```

### Inspect Specific Step

```bash
npx playwright test cs-student-iot.spec.js --debug -g "Run SLR"
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: E2E CS Student IoT Test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  e2e-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 18
      - name: Install dependencies
        run: |
          cd frontend
          npm ci
          npx playwright install --with-deps chromium
      - name: Start services
        run: |
          pm2 start ecosystem.config.cjs
          sleep 10
      - name: Run CS IoT test
        run: |
          cd frontend
          ./run-cs-iot-test.sh
      - name: Upload artifacts
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: cs-iot-test-results
          path: |
            frontend/test-results/cs-student/
            frontend/playwright-report/
```

## Related Tests

- `electrical-engineering-persona.spec.js` - EE student with equations
- `medical-student.spec.js` - Medical student with clinical data
- `business-student-qualitative.spec.js` - Business student qualitative research
- `beginner-first-time.spec.js` - First-time user experience

## Maintenance

### Updating Test Data

To modify persona or test parameters, edit constants at top of `cs-student-iot.spec.js`:

```javascript
const PERSONA_USER = { ... };
const DISCOVERY_ANSWERS = { ... };
const LITERATURE_QUERY = '...';
const SLR_PAPER_COUNT = 20;
```

### Adding New Validation Steps

Add new test cases in the `test.describe` block following the numbered sequence.

### Adjusting Timeouts

Modify timeouts in `playwright.config.js` or individual test steps:

```javascript
await page.waitForTimeout(5000); // 5 seconds
await expect(element).toBeVisible({ timeout: 10000 }); // 10 seconds
```

## Support

For issues or questions:
- Check backend logs: `pm2 logs backend`
- Check frontend logs: `pm2 logs frontend`
- Review Playwright docs: https://playwright.dev
- Open issue in project repository
