# E2E Test Suite - User Persona Tests

Comprehensive Playwright test scenarios for different user types and workflows.

## Test Files

### 1. test-medical-student.spec.js
**Persona**: Medical student generating clinical research paper

**Workflow**:
- Register and login
- Create paper on diabetes management with mobile health apps
- Upload PDF references (simulated)
- Generate sections via AI chat
- Add clinical figures and tables
- Verify medical terminology (HbA1c, glycemic control, etc.)
- Verify Vancouver citation format
- Export to DOCX

**Duration**: ~3-5 minutes  
**Key Validations**: Medical terminology, citation format, section structure

---

### 2. test-engineering-student.spec.js
**Persona**: Engineering student working on IoT smart home project

**Workflow**:
- Register and login
- Create paper on IoT smart home automation with ML
- Answer discovery questions via chat
- Upload PDF references (simulated)
- Generate technical sections (Introduction, Methodology, Results)
- Add system architecture diagrams
- Add performance evaluation tables
- Verify technical terminology (IoT, MQTT, ESP32, sensors)
- Export to DOCX

**Duration**: ~3-5 minutes  
**Key Validations**: Technical terminology, methodology keywords, section structure

---

### 3. test-business-student.spec.js
**Persona**: Business student conducting qualitative research

**Workflow**:
- Register and login
- Create paper on digital marketing effectiveness in SMEs
- Provide interview transcript data
- Generate qualitative research paper
- Add thematic analysis tables
- Add informant profile tables
- Verify business terminology (ROI, engagement, conversion)
- Verify APA 7th citation format
- Verify qualitative research structure
- Export to DOCX

**Duration**: ~3-5 minutes  
**Key Validations**: Business terms, qualitative keywords, APA citations

---

### 4. test-concurrent-users.spec.js
**Scenario**: 5 users working simultaneously

**Users**:
1. **User 1**: Medical student - Create and edit paper with rapid updates
2. **User 2**: Engineering student - Create IoT paper
3. **User 3**: Business student - Create marketing paper
4. **User 4**: Race condition test - 20 rapid edits to same paper
5. **User 5**: Queue management test - Multiple SLR jobs

**Duration**: ~2-3 minutes (parallel execution)  
**Key Validations**: 
- Database concurrency
- No race conditions
- No data corruption
- Transaction isolation
- Queue integrity

---

## Prerequisites

1. **Backend running**: Ensure backend is running on `http://localhost:8001`
2. **Frontend running**: Ensure frontend is running on `http://localhost:8000`
3. **Database**: PostgreSQL with clean test data
4. **Redis**: For job queue management
5. **Playwright installed**: `npm install` in frontend directory

## Running Tests

### Run All Tests
```bash
cd frontend
npm run test:e2e
```

### Run Individual Tests

**Medical Student Test**:
```bash
npx playwright test test-medical-student.spec.js
```

**Engineering Student Test**:
```bash
npx playwright test test-engineering-student.spec.js
```

**Business Student Test**:
```bash
npx playwright test test-business-student.spec.js
```

**Concurrent Users Test**:
```bash
npx playwright test test-concurrent-users.spec.js
```

### Run with UI Mode (Interactive)
```bash
npx playwright test test-medical-student.spec.js --ui
```

### Run in Headed Mode (See Browser)
```bash
npx playwright test test-medical-student.spec.js --headed
```

### Run with Debug Mode
```bash
npx playwright test test-medical-student.spec.js --debug
```

## Test Outputs

### Screenshots
All tests save screenshots to:
- `test-results/medical-student/*.png`
- `test-results/engineering-student/*.png`
- `test-results/business-student/*.png`
- `test-results/concurrent-users/*.png`

### Videos
Video recordings saved to test result directories (on failure by default)

### Exported Papers
DOCX files saved to:
- `test-results/medical-student/medical-paper-*.docx`
- `test-results/engineering-student/iot-paper-*.docx`
- `test-results/business-student/business-paper-*.docx`

### HTML Report
```bash
npx playwright show-report
```

## Performance Metrics

Each test tracks:
- **Total execution time**
- **API call count and response times**
- **Console errors**
- **Screenshot count**
- **Generation time** (for AI paper generation)

Example output:
```
================================================================================
MEDICAL STUDENT TEST - PERFORMANCE REPORT
================================================================================
Total execution time: 187.45s
Paper generation time: 180.23s
Total API calls: 47
Console errors: 0
Screenshots taken: 8
Average API response time: 234ms
Max API response time: 1823ms
================================================================================
```

## Concurrent Test Report

The concurrent users test provides detailed analysis:

```
================================================================================
CONCURRENT USERS TEST - FINAL REPORT
================================================================================
Total execution time: 125.34s
Total users: 5
Total API calls: 156
Total errors: 0

=== User Results ===

User 1: concurrent-medical-1234@test.local
  Papers created: 1
  Edits made: 5
  Jobs queued: 0
  Execution time: 45.23s
  Status: ✓ PASS

User 2: concurrent-engineering-1234@test.local
  Papers created: 1
  Edits made: 2
  Jobs queued: 0
  Execution time: 38.12s
  Status: ✓ PASS

User 3: concurrent-business-1234@test.local
  Papers created: 1
  Edits made: 2
  Jobs queued: 0
  Execution time: 42.56s
  Status: ✓ PASS

User 4: concurrent-race-1234@test.local
  Papers created: 1
  Edits made: 20
  Jobs queued: 0
  Execution time: 12.34s
  Status: ✓ PASS

User 5: concurrent-queue-1234@test.local
  Papers created: 1
  Edits made: 0
  Jobs queued: 3
  Execution time: 8.45s
  Status: ✓ PASS

=== Data Integrity Check ===
Total papers created: 5
Total edits performed: 29
Total jobs queued: 3
Data corruption detected: NO ✓

=== Performance Metrics ===
Average API response time: 187ms
Slow API calls (>5s): 0
================================================================================
```

## Troubleshooting

### Test Timeout
If tests timeout, increase timeout in `playwright.config.js`:
```javascript
timeout: 600_000, // 10 minutes
```

### Rate Limiting
If you hit rate limits during registration:
- Wait 65 seconds between test runs
- Or use different email prefixes
- Or clear rate limit cache in Redis

### Database Conflicts
If tests fail due to existing data:
```bash
# Reset test database
cd backend
python reset_test_db.py
```

### Port Conflicts
Ensure services are running on correct ports:
- Frontend: `http://localhost:8000`
- Backend: `http://localhost:8001`

Check with:
```bash
curl http://localhost:8000
curl http://localhost:8001/api/health
```

## CI/CD Integration

### GitHub Actions Example
```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '18'
      
      - name: Install dependencies
        run: |
          cd frontend
          npm install
          npx playwright install --with-deps
      
      - name: Start services
        run: |
          docker-compose up -d
          sleep 10
      
      - name: Run E2E tests
        run: |
          cd frontend
          npm run test:e2e
      
      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: frontend/playwright-report/
```

## Test Configuration

Tests use configuration from `playwright.config.js`:
- **Base URL**: `http://localhost:8000`
- **Timeout**: 600 seconds (10 minutes)
- **Workers**: 1 (for concurrent test, uses parallel mode)
- **Retries**: 0 (local), 2 (CI)
- **Screenshots**: On failure
- **Videos**: On failure
- **Trace**: On failure

## Best Practices

1. **Run tests in order**: Medical → Engineering → Business → Concurrent
2. **Clean database** between full test runs
3. **Monitor backend logs** during tests
4. **Check Redis queue** for job processing
5. **Review screenshots** on failures
6. **Analyze performance metrics** for bottlenecks

## Known Issues

1. **PDF Upload**: Currently simulated (no actual file upload)
2. **Generation Time**: Can vary based on AI API response time
3. **SLR Jobs**: May not complete within test timeout (expected)
4. **Rate Limiting**: May trigger on rapid test runs

## Future Enhancements

- [ ] Add actual PDF file uploads
- [ ] Add figure/table content verification
- [ ] Add citation format validation
- [ ] Add accessibility tests
- [ ] Add mobile viewport tests
- [ ] Add performance benchmarks
- [ ] Add visual regression tests

## Support

For issues or questions:
- Check `playwright-report/index.html` for detailed results
- Review `test-results/` for screenshots and videos
- Check backend logs for API errors
- Review Redis queue for job status
