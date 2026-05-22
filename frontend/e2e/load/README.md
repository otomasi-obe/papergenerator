# Load Testing Suite - Concurrent Users

## Overview

Comprehensive Playwright-based load testing suite that simulates 10 concurrent users (classroom scenario) to test system behavior under load.

## Test Scenarios

### 1. Concurrent Users Test (`concurrent-users.spec.js`)
Simulates 10 students using the system simultaneously:
- **Users 1-3**: Creating multiple papers (5 papers each)
- **Users 4-6**: Running SLR jobs (3 jobs each)
- **Users 7-8**: Generating papers with AI
- **Users 9-10**: Editing existing papers (10 rapid edits each)

### 2. Race Condition Test (`race-conditions.spec.js`)
Tests concurrent access to shared resources:
- Multiple users editing the same paper simultaneously
- Concurrent SLR jobs on the same paper
- Simultaneous paper generation requests
- Data integrity verification after concurrent operations

### 3. Queue Management Test (`queue-management.spec.js`)
Tests job queue behavior:
- Rapid job submission (5 jobs per user)
- Concurrent status polling (20 polls per job)
- Job cancellation under load
- Mixed job types (SLR + Generation)
- Queue capacity stress test (15 jobs)

## Monitoring

### Performance Metrics
- Response times (avg, min, max, P50, P95, P99)
- Error rates
- Success rates
- Operation counts

### System Resources
- CPU usage (total, Python, Node.js)
- Memory usage (total, used, available)
- Process counts
- Database connections

## Setup

### Prerequisites
```bash
# Install dependencies
cd frontend
npm install

# Install Playwright browsers
npx playwright install chromium
```

### Start Services
```bash
# Terminal 1: Start backend
cd backend
source .venv/bin/activate
python app.py

# Terminal 2: Start frontend (if not using PM2)
cd frontend
npm run dev
```

## Running Tests

### Quick Start
```bash
cd frontend
./run-load-tests.sh
```

The script will:
1. Check if services are running
2. Ask which test suite to run
3. Start system resource monitoring
4. Run the selected tests
5. Generate comprehensive reports

### Manual Execution

#### Run all tests
```bash
npx playwright test --config=playwright.config.load.js
```

#### Run specific test suite
```bash
# Concurrent users only
npx playwright test --config=playwright.config.load.js e2e/load/concurrent-users.spec.js

# Race conditions only
npx playwright test --config=playwright.config.load.js e2e/load/race-conditions.spec.js

# Queue management only
npx playwright test --config=playwright.config.load.js e2e/load/queue-management.spec.js
```

#### With UI mode (for debugging)
```bash
npx playwright test --config=playwright.config.load.js --ui
```

#### With headed browser (see what's happening)
```bash
npx playwright test --config=playwright.config.load.js --headed
```

## Reports

### HTML Report
Interactive HTML report with test results, screenshots, and traces:
```bash
npx playwright show-report playwright-report-load
```

### JSON Results
Raw test results in JSON format:
- `load-test-results.json` - Playwright test results

### System Monitor Report
System resource usage during tests:
- `system-monitor-report.json` - CPU, memory, process counts
- `system-monitor.log` - Real-time monitoring log

### Analysis Report
Automated analysis with bottleneck identification:
```bash
node e2e/load/analyzer.js
```

## Understanding Results

### Performance Metrics

**Response Times:**
- **P50 (Median)**: 50% of requests complete within this time
- **P95**: 95% of requests complete within this time (key SLA metric)
- **P99**: 99% of requests complete within this time

**Acceptable Ranges:**
- P95 < 1000ms: Excellent
- P95 < 2000ms: Good
- P95 < 5000ms: Acceptable
- P95 > 5000ms: Needs optimization

**Error Rate:**
- < 1%: Excellent
- < 5%: Good
- < 10%: Acceptable
- > 10%: Critical issues

### Scalability Score

The analyzer generates a scalability score (0-100) and grade (A-F):

- **A (90-100)**: System handles concurrent load excellently
- **B (80-89)**: System is stable with minor issues
- **C (70-79)**: Noticeable performance degradation
- **D (60-69)**: System struggles under load
- **F (0-59)**: Critical scalability issues

### Bottleneck Types

**HIGH_FAILURE_RATE**: Too many requests failing
- Check database connection pool
- Review error logs
- Verify resource limits

**SLOW_RESPONSE_TIME**: Requests taking too long
- Add database indexes
- Optimize queries
- Implement caching

**HIGH_VARIANCE**: Inconsistent response times
- Investigate outlier operations
- Check for resource contention
- Review background job processing

## Troubleshooting

### Tests Timing Out
- Increase timeout in `playwright.config.load.js`
- Check if backend is overloaded
- Verify database performance

### Connection Errors
- Ensure backend is running on port 8000
- Check database connection pool settings
- Verify Redis is running (for job queue)

### High Error Rates
- Check backend logs: `backend/app.log`
- Review database connection pool size
- Verify API rate limits

### Memory Issues
- Monitor system resources during tests
- Check for memory leaks in backend
- Adjust worker count if needed

## Configuration

### Adjust Concurrency
Edit `playwright.config.load.js`:
```javascript
workers: 10,  // Change to desired number of concurrent users
```

### Adjust Timeouts
```javascript
timeout: 300_000,  // Test timeout (5 minutes)
expect: { timeout: 10_000 },  // Assertion timeout (10 seconds)
```

### Change Base URL
```bash
E2E_BASE_URL=http://localhost:3000 npx playwright test --config=playwright.config.load.js
```

## Best Practices

1. **Run on staging environment**: Don't run load tests on production
2. **Clean database**: Start with a clean database for consistent results
3. **Monitor resources**: Watch CPU, memory, and database connections
4. **Baseline first**: Run tests with 1 worker to establish baseline
5. **Incremental load**: Test with 2, 5, 10, 20 workers to find limits
6. **Repeat tests**: Run multiple times to account for variance

## Next Steps

### Increase Load
Test with more concurrent users:
```javascript
// playwright.config.load.js
workers: 20,  // or 50, 100
```

### Longer Duration
Extend test duration to find memory leaks:
```javascript
// In test files
for (let i = 0; i < 100; i++) {  // More iterations
  // ... operations
}
```

### Production-Like Data
Seed database with realistic data volume before testing.

### CI/CD Integration
Add to GitHub Actions or GitLab CI:
```yaml
- name: Run load tests
  run: |
    cd frontend
    npx playwright test --config=playwright.config.load.js
```

## Support

For issues or questions:
- Check `playwright-report-load/index.html` for detailed test results
- Review `system-monitor.log` for resource usage
- Check backend logs: `backend/app.log`
- Run analyzer: `node e2e/load/analyzer.js`
