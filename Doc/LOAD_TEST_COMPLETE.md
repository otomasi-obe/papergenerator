# 🎯 Load Testing Suite - Complete

## ✅ Status: Ready to Use

All components have been created, verified, and are ready for execution.

---

## 📦 What You Have

### Test Infrastructure
- **10 concurrent users** simulating classroom scenario
- **3 test suites** covering different aspects
- **28 total tests** with comprehensive coverage
- **Real-time monitoring** of system resources
- **Automated analysis** with bottleneck detection

### Test Suites

#### 1. Concurrent Users (`concurrent-users.spec.js`)
**10 users performing different operations simultaneously**
- Users 1-3: Create 5 papers each → 15 papers total
- Users 4-6: Run 3 SLR jobs each → 9 jobs total  
- Users 7-8: Generate papers → 2 generation jobs
- Users 9-10: Edit papers 10 times → 20 edit operations

**Total**: ~50+ concurrent operations

#### 2. Race Conditions (`race-conditions.spec.js`)
**Tests concurrent access to shared resources**
- 5 users editing same paper simultaneously
- 3 concurrent SLR jobs on same paper
- 3 simultaneous generation requests
- Data integrity verification

**Total**: 13 race condition tests

#### 3. Queue Management (`queue-management.spec.js`)
**Tests job queue behavior under load**
- Rapid job submission (25 jobs)
- Concurrent status polling (100 polls)
- Job cancellation (9 cancellations)
- Mixed job types
- Capacity stress test (15 jobs)

**Total**: 8 queue tests

---

## 🚀 How to Run

### Option 1: Interactive Runner (Recommended)
```bash
cd frontend
./run-load-tests.sh
```

**Features**:
- Interactive menu to select test suite
- Automatic service health check
- Real-time system monitoring
- Automatic report generation
- Color-coded output

### Option 2: NPM Scripts
```bash
cd frontend

# Run all tests
npm run test:load

# Run specific suite
npm run test:load:concurrent    # 10 concurrent users
npm run test:load:race          # Race conditions
npm run test:load:queue         # Queue management

# View reports
npm run test:load:report        # HTML report
npm run test:load:analyze       # Analysis report

# Debug mode
npm run test:load:ui            # Interactive UI mode
```

### Option 3: Direct Playwright
```bash
cd frontend

# All tests
npx playwright test --config=playwright.config.load.js

# Specific test
npx playwright test --config=playwright.config.load.js e2e/load/concurrent-users.spec.js

# With headed browser (see what's happening)
npx playwright test --config=playwright.config.load.js --headed

# Debug mode
npx playwright test --config=playwright.config.load.js --debug
```

---

## 📊 Reports Generated

After running tests, you'll get:

### 1. HTML Report (Interactive)
**File**: `playwright-report-load/index.html`  
**View**: `npm run test:load:report`  
**Contains**:
- Test results with pass/fail status
- Detailed timings for each test
- Screenshots on failures
- Full browser traces for debugging
- Filterable and searchable

### 2. Analysis Report (Console)
**Command**: `npm run test:load:analyze`  
**Contains**:
- Performance summary (avg, P50, P95, P99)
- Bottleneck identification
- Scalability score (0-100) and grade (A-F)
- Actionable recommendations
- Error analysis

### 3. System Monitor Report (JSON)
**File**: `system-monitor-report.json`  
**Contains**:
- CPU usage over time
- Memory usage over time
- Process counts
- Peak and average values

### 4. Raw Results (JSON)
**File**: `load-test-results.json`  
**Contains**:
- Structured test results
- Timings for each operation
- Error details
- Test metadata

---

## 📈 Understanding Results

### Scalability Grades

| Grade | Score | What It Means | Action |
|-------|-------|---------------|--------|
| **A** | 90-100 | Excellent - handles load well | ✅ Ready for production |
| **B** | 80-89 | Good - stable with minor issues | ✅ Production ready, monitor |
| **C** | 70-79 | Fair - noticeable degradation | ⚠️ Optimize before production |
| **D** | 60-69 | Poor - struggles under load | 🚨 Fix issues before production |
| **F** | 0-59 | Critical - cannot handle load | 🚨 Major fixes required |

### Performance Benchmarks

| Metric | Excellent | Good | Acceptable | Poor |
|--------|-----------|------|------------|------|
| **P95 Response** | <1s | <2s | <5s | >5s |
| **Error Rate** | <1% | <5% | <10% | >10% |
| **Success Rate** | >99% | >95% | >90% | <90% |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Load Test Runner                         │
│                  (run-load-tests.sh)                        │
└────────────┬────────────────────────────────┬───────────────┘
             │                                │
             ▼                                ▼
    ┌────────────────┐              ┌─────────────────┐
    │   Playwright   │              │ System Monitor  │
    │   (10 workers) │              │  (CPU/Memory)   │
    └────────┬───────┘              └────────┬────────┘
             │                               │
             ▼                               ▼
    ┌─────────────────────────────────────────────────┐
    │              Test Suites                        │
    ├─────────────────────────────────────────────────┤
    │  • Concurrent Users (10 users)                  │
    │  • Race Conditions (shared resources)           │
    │  • Queue Management (job queue)                 │
    └────────┬────────────────────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────────────────────┐
    │              Backend API                        │
    ├─────────────────────────────────────────────────┤
    │  • Papers API (CRUD)                            │
    │  • SLR API (job queue)                          │
    │  • Generation API (AI jobs)                     │
    │  • Auth API (JWT)                               │
    └────────┬────────────────────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────────────────────┐
    │           Data Layer                            │
    ├─────────────────────────────────────────────────┤
    │  • PostgreSQL (papers, users, jobs)             │
    │  • Redis (job queue, progress)                  │
    └─────────────────────────────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────────────────────┐
    │              Reports                            │
    ├─────────────────────────────────────────────────┤
    │  • HTML Report (interactive)                    │
    │  • Analysis Report (bottlenecks)                │
    │  • System Monitor (resources)                   │
    │  • JSON Results (raw data)                      │
    └─────────────────────────────────────────────────┘
```

---

## 🔧 Configuration

### Adjust Concurrency
Edit `playwright.config.load.js`:
```javascript
workers: 10,  // Change to 5, 20, 50, etc.
```

### Adjust Timeouts
```javascript
timeout: 300_000,        // Test timeout (5 minutes)
expect: { timeout: 10_000 },  // Assertion timeout (10 seconds)
```

### Change Base URL
```bash
E2E_BASE_URL=http://staging.example.com npm run test:load
```

### Adjust Test Iterations
Edit test files:
```javascript
// In concurrent-users.spec.js
for (let paperNum = 1; paperNum <= 5; paperNum++) {  // Change 5 to 10, 20, etc.
```

---

## 🎯 Test Scenarios Explained

### Scenario 1: Classroom Load (10 Students)
**Simulates**: 10 students in a class using the system simultaneously

**User 1-3** (Paper Creators):
- Register new account
- Create 5 papers with different titles
- Verify each paper was created
- List all papers

**User 4-6** (Researchers):
- Register new account
- Create a paper for literature review
- Submit 3 SLR jobs with different queries
- Poll job status

**User 7-8** (AI Users):
- Register new account
- Create a paper
- Request AI generation
- Monitor generation progress

**User 9-10** (Editors):
- Register new account
- Create a paper
- Perform 10 rapid edits
- Verify final state

### Scenario 2: Race Conditions
**Simulates**: Multiple users accessing same resources

**Concurrent Edits**:
- 5 users edit the same paper simultaneously
- Tests optimistic locking
- Verifies data integrity

**Concurrent Jobs**:
- 3 users submit SLR jobs on same paper
- Tests job queue handling
- Verifies no job loss

**Concurrent Generation**:
- 3 users request generation on same paper
- Tests single-active-job constraint
- Verifies proper rejection

### Scenario 3: Queue Stress
**Simulates**: Heavy job queue usage

**Rapid Submission**:
- 5 users submit 5 jobs each (25 total)
- Tests queue capacity
- Measures submission latency

**Status Polling**:
- 20 rapid status checks per job
- Tests read scalability
- Measures polling overhead

**Cancellation**:
- Cancel jobs while queued/running
- Tests cancellation logic
- Verifies cleanup

---

## 📋 Prerequisites Checklist

- [x] Backend running on port 8000
- [x] PostgreSQL database accessible
- [x] Redis running (for job queue)
- [x] Node.js installed
- [x] npm dependencies installed
- [x] Playwright browsers installed

**Verify with**:
```bash
cd frontend
./verify-load-test-setup.sh
```

---

## 🐛 Troubleshooting

### Tests Fail to Start
```bash
# Check services
curl http://localhost:8000/api/health

# Check Playwright
npx playwright --version

# Reinstall if needed
npm install
npx playwright install chromium
```

### High Error Rates
```bash
# Check backend logs
tail -f ../backend/app.log

# Check database connections
psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Check Redis
redis-cli ping
```

### Slow Performance
```bash
# Check system resources
top
free -h

# Check database performance
# Review slow query log

# Check connection pool
# Review backend/app.py pool settings
```

### Tests Timeout
```bash
# Increase timeout in config
# Edit playwright.config.load.js
timeout: 600_000,  # 10 minutes

# Or run with more time
npx playwright test --config=playwright.config.load.js --timeout=600000
```

---

## 📚 Documentation

- **Full Guide**: `frontend/e2e/load/README.md`
- **Quick Reference**: `LOAD_TEST_QUICK_REF.md`
- **Deliverable Summary**: `LOAD_TEST_DELIVERABLE.md`
- **Sample Output**: `LOAD_TEST_SAMPLE_OUTPUT.md`

---

## 🎓 Next Steps

### 1. Run Baseline Test
```bash
cd frontend
npm run test:load:concurrent
```

### 2. Review Results
```bash
npm run test:load:report
npm run test:load:analyze
```

### 3. Increase Load
Edit `playwright.config.load.js`:
```javascript
workers: 20,  // Double the load
```

### 4. Test Longer Duration
Edit test files to run more iterations:
```javascript
for (let i = 0; i < 100; i++) {  // More iterations
```

### 5. Production Testing
- Test on staging environment
- Use production-like data volume
- Monitor real system resources
- Set up alerting

---

## ✅ Verification

Run the verification script to confirm everything is ready:

```bash
cd frontend
./verify-load-test-setup.sh
```

**Expected output**:
```
✅ All checks passed! Ready to run load tests.

Quick start:
  ./run-load-tests.sh

Or use npm:
  npm run test:load
```

---

## 🎉 You're Ready!

Everything is set up and verified. Start with:

```bash
cd frontend
./run-load-tests.sh
```

Select option 1 (All tests) to run the full suite, or choose a specific test suite to start smaller.

Good luck with your load testing! 🚀
