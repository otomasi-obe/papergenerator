# E2E Tests for PaperFull

## Overview

This directory contains end-to-end tests for the PaperFull paper generation system using Playwright.

## Test Files

### 1. `smoke.spec.js`
Basic smoke tests for public endpoints and pages:
- Landing page rendering
- Login page accessibility
- Health endpoints
- API security headers
- OpenAPI documentation

**Run:** `npm run test:e2e -- smoke.spec.js`

### 2. `auth.spec.js`
Authentication flow tests:
- User registration
- Cookie management (httpOnly, CSRF)
- Token refresh
- Logout
- Protected endpoints

**Run:** `npm run test:e2e -- auth.spec.js`

### 3. `complete-workflow.spec.js` ⭐
**Complete end-to-end workflow test** covering the entire paper generation process:

#### Test Scenario
Simulates a student (mahasiswa) following the complete happy path from start to finish.

#### Workflow Phases
1. **Registration & Login** - Create account and authenticate
2. **Create New Paper** - Initialize a new paper project
3. **Discovery Questions** - Answer AI-guided questions via chat (9 phases)
4. **File Upload** - Upload 3 PDF research papers
5. **SLR Execution** - Request systematic literature review
6. **Paper Generation** - AI generates complete paper structure
7. **Monitor Progress** - Wait for generation with progress tracking
8. **Review Paper** - Verify generated content quality
9. **Edit Sections** - Make 2-3 manual edits to content
10. **Add References** - Add custom citations
11. **Generate Charts** - Request AI-generated figures
12. **Preview Paper** - Review final formatted output
13. **Export to DOCX** - Download final paper

#### Metrics Tracked
- ⏱️ Total time from start to download
- 🖱️ Number of clicks required
- 🤖 Number of AI interactions
- 📁 Files uploaded
- ✏️ Sections edited
- 📚 References added
- 📊 Charts generated

#### Quality Verification
- ✅ All sections present
- ✅ References formatted correctly
- ✅ Figures/tables included
- ✅ No placeholder text
- ✅ Proper academic language

#### Video Recording
This test **always records video** regardless of pass/fail status for:
- User experience analysis
- Workflow optimization
- Bug reproduction
- Demo purposes

**Run:** `./e2e/run-workflow-test.sh`

## Prerequisites

### 1. Install Dependencies
```bash
cd frontend
npm install
```

### 2. Install Playwright Browsers
```bash
npx playwright install chromium
```

### 3. Start the Server
```bash
cd /home/sirobo/papergenerator
./server.sh
```

The server should be running on:
- Frontend: http://localhost:8000
- Backend: http://localhost:8001

### 4. Verify Server Health
```bash
curl http://localhost:8000/api/health
# Should return: {"status":"ok"}
```

## Running Tests

### Run All Tests
```bash
cd frontend
npm run test:e2e
```

### Run Specific Test
```bash
npm run test:e2e -- smoke.spec.js
npm run test:e2e -- auth.spec.js
```

### Run Complete Workflow Test (Recommended)
```bash
./e2e/run-workflow-test.sh
```

This script:
- ✅ Checks server availability
- ✅ Creates sample PDF files
- ✅ Runs the test with video recording
- ✅ Shows results location

### Run with UI Mode (Interactive)
```bash
npm run test:e2e:ui
```

### Run with Debug Mode
```bash
npx playwright test --debug
```

## Test Configuration

Configuration is in `playwright.config.js`:

```javascript
{
  testDir: './e2e',
  timeout: 600_000,        // 10 minutes for workflow test
  workers: 1,              // Sequential execution (shared DB)
  video: 'retain-on-failure', // Default
  trace: 'retain-on-failure',
  screenshot: 'only-on-failure',
}
```

### Special Project: `workflow-with-video`
The complete workflow test uses a dedicated project with:
- ✅ Video: Always on
- ✅ Trace: Always on
- ✅ Screenshots: Always on

## Viewing Results

### HTML Report
```bash
cd frontend
npx playwright show-report
```

Opens an interactive HTML report with:
- Test results
- Screenshots
- Videos
- Traces
- Network logs

### Video Files
Located in: `frontend/test-results/*/video.webm`

### Trace Files
Located in: `frontend/test-results/*/trace.zip`

View traces:
```bash
npx playwright show-trace test-results/*/trace.zip
```

## Test Data

### Sample PDF Files
The workflow test creates sample PDF files in `/tmp/kilo/test-pdfs/`:
- `paper1.pdf`
- `paper2.pdf`
- `paper3.pdf`

These are minimal valid PDF files for testing upload functionality.

### Test Users
Each test run creates a unique test user:
- Email: `workflow-{timestamp}@e2e.local`
- Password: `WorkflowTest123!`

Users are not automatically cleaned up (left for backend cleanup job).

## Troubleshooting

### Server Not Running
```
❌ Server is not running on http://localhost:8000
```
**Solution:** Start the server with `./server.sh`

### Test Timeout
```
Test timeout of 600000ms exceeded
```
**Solution:** 
- Check if AI generation is working
- Increase timeout in `playwright.config.js`
- Check backend logs for errors

### File Upload Fails
```
Error: File not found
```
**Solution:** Run `./e2e/run-workflow-test.sh` which creates sample files

### Video Not Recording
**Solution:** 
- Use the `workflow-with-video` project
- Or run: `npx playwright test complete-workflow.spec.js --project=workflow-with-video`

### Database Conflicts
```
Error: UNIQUE constraint failed
```
**Solution:** 
- Tests use unique timestamps for user emails
- If persists, reset test database

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run E2E Tests
  run: |
    cd frontend
    npx playwright test
  env:
    E2E_BASE_URL: http://localhost:8000

- name: Upload Test Results
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: playwright-report
    path: frontend/playwright-report/
```

## Performance Benchmarks

### Expected Timings (Complete Workflow)
- ⚡ Fast: < 3 minutes (excellent)
- ✅ Normal: 3-5 minutes (good)
- ⚠️ Slow: 5-10 minutes (acceptable)
- ❌ Timeout: > 10 minutes (investigate)

### Bottlenecks
1. **AI Generation** (60-80% of time)
   - Paper generation: 1-3 minutes
   - SLR analysis: 30-60 seconds
   - Chart generation: 20-40 seconds

2. **File Upload** (5-10% of time)
   - 3 PDFs: 5-15 seconds

3. **User Interactions** (10-15% of time)
   - Navigation, clicks, typing

## Best Practices

### ✅ Do
- Run tests against local server first
- Check server health before running
- Use the provided run script for workflow test
- Review video recordings for UX insights
- Keep test data in `/tmp/kilo/`

### ❌ Don't
- Run tests against production
- Run multiple tests in parallel (workers: 1)
- Commit test videos to git (too large)
- Hardcode user credentials
- Skip server health checks

## Metrics & Analytics

The complete workflow test tracks:

```javascript
METRICS = {
  startTime: 0,
  endTime: 0,
  clicks: 0,              // User interactions
  aiInteractions: 0,      // AI chat messages
  filesUploaded: 0,       // PDF uploads
  sectionsEdited: 0,      // Manual edits
  referencesAdded: 0,     // Custom citations
  chartsGenerated: 0,     // AI-generated figures
}
```

These metrics help identify:
- 🎯 User experience friction points
- ⚡ Performance bottlenecks
- 🔄 Workflow optimization opportunities
- 📊 Feature usage patterns

## Future Enhancements

- [ ] Add visual regression testing
- [ ] Add accessibility (a11y) tests
- [ ] Add mobile viewport tests
- [ ] Add performance metrics (Core Web Vitals)
- [ ] Add API response time tracking
- [ ] Add multi-user collaboration tests
- [ ] Add paper sharing tests
- [ ] Add version history tests

## Support

For issues or questions:
1. Check test output and logs
2. Review video recordings
3. Inspect trace files
4. Check backend logs
5. Report issues with video evidence

---

**Last Updated:** 2026-05-22  
**Playwright Version:** 1.60.0  
**Test Coverage:** Landing → Login → Dashboard → Editor → Export
