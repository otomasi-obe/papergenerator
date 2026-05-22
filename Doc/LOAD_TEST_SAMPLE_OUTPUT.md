# Load Test Sample Output

This document shows example outputs from the load testing suite.

---

## 1. Test Execution Output

```
==========================================
PaperFull Load Testing Suite
==========================================

🔍 Checking if services are running...
✓ Services are running

==========================================
Test Configuration
==========================================
Workers: 10 concurrent users
Base URL: http://localhost:8000
Timeout: 300s per test

Select test suite to run:
1) All tests (concurrent users + race conditions + queue management)
2) Concurrent users only
3) Race conditions only
4) Queue management only
5) Custom selection
Enter choice [1-5]: 1

==========================================
Starting Load Tests
==========================================

📊 Starting system resource monitor...
Monitor PID: 12345

🚀 Running load tests...

Running 28 tests using 10 workers

  ✓  1 [chromium] › e2e/load/concurrent-users.spec.js:25:5 › User 1: Create multiple papers (12.3s)
  ✓  2 [chromium] › e2e/load/concurrent-users.spec.js:25:5 › User 2: Create multiple papers (13.1s)
  ✓  3 [chromium] › e2e/load/concurrent-users.spec.js:25:5 › User 3: Create multiple papers (12.8s)
  ✓  4 [chromium] › e2e/load/concurrent-users.spec.js:68:5 › User 4: Run SLR jobs (15.2s)
  ✓  5 [chromium] › e2e/load/concurrent-users.spec.js:68:5 › User 5: Run SLR jobs (14.9s)
  ✓  6 [chromium] › e2e/load/concurrent-users.spec.js:68:5 › User 6: Run SLR jobs (15.4s)
  ✓  7 [chromium] › e2e/load/concurrent-users.spec.js:125:5 › User 7: Generate papers (18.7s)
  ✓  8 [chromium] › e2e/load/concurrent-users.spec.js:125:5 › User 8: Generate papers (19.2s)
  ✓  9 [chromium] › e2e/load/concurrent-users.spec.js:175:5 › User 9: Edit papers repeatedly (8.4s)
  ✓ 10 [chromium] › e2e/load/concurrent-users.spec.js:175:5 › User 10: Edit papers repeatedly (8.7s)
  ✓ 11 [chromium] › e2e/load/race-conditions.spec.js:45:5 › Race 1: Concurrent edits to same paper (2.1s)
  ✓ 12 [chromium] › e2e/load/race-conditions.spec.js:45:5 › Race 2: Concurrent edits to same paper (2.3s)
  ✓ 13 [chromium] › e2e/load/race-conditions.spec.js:45:5 › Race 3: Concurrent edits to same paper (2.2s)
  ✓ 14 [chromium] › e2e/load/race-conditions.spec.js:45:5 › Race 4: Concurrent edits to same paper (2.4s)
  ✓ 15 [chromium] › e2e/load/race-conditions.spec.js:45:5 › Race 5: Concurrent edits to same paper (2.1s)
  ✓ 16 [chromium] › e2e/load/race-conditions.spec.js:72:5 › Race 1: Concurrent SLR jobs on same paper (3.2s)
  ✓ 17 [chromium] › e2e/load/race-conditions.spec.js:72:5 › Race 2: Concurrent SLR jobs on same paper (3.1s)
  ✓ 18 [chromium] › e2e/load/race-conditions.spec.js:72:5 › Race 3: Concurrent SLR jobs on same paper (3.3s)
  ✓ 19 [chromium] › e2e/load/queue-management.spec.js:28:5 › Queue 1: Rapid job submission (6.8s)
  ✓ 20 [chromium] › e2e/load/queue-management.spec.js:28:5 › Queue 2: Rapid job submission (7.1s)
  ✓ 21 [chromium] › e2e/load/queue-management.spec.js:28:5 › Queue 3: Rapid job submission (6.9s)
  ✓ 22 [chromium] › e2e/load/queue-management.spec.js:28:5 › Queue 4: Rapid job submission (7.2s)
  ✓ 23 [chromium] › e2e/load/queue-management.spec.js:28:5 › Queue 5: Rapid job submission (7.0s)
  ✓ 24 [chromium] › e2e/load/queue-management.spec.js:65:5 › Queue: Concurrent status polling (4.5s)
  ✓ 25 [chromium] › e2e/load/queue-management.spec.js:98:5 › Queue 1: Job cancellation (5.2s)
  ✓ 26 [chromium] › e2e/load/queue-management.spec.js:98:5 › Queue 2: Job cancellation (5.4s)
  ✓ 27 [chromium] › e2e/load/queue-management.spec.js:98:5 › Queue 3: Job cancellation (5.1s)
  ✓ 28 [chromium] › e2e/load/queue-management.spec.js:135:5 › Queue: Mixed job types (8.3s)

  28 passed (2.5m)

User 1 avg submission time: 245.32ms
User 2 avg submission time: 267.18ms
Average poll time: 156.42ms
Submitted 4 mixed jobs
Capacity test: 15 succeeded, 0 failed

================================================================================
LOAD TEST PERFORMANCE REPORT
================================================================================
Total Requests: 247
Total Errors: 3
Error Rate: 1.21%

Operation Statistics:
--------------------------------------------------------------------------------

register:
  Count: 28
  Avg: 423.45ms
  Min: 312.12ms
  Max: 678.34ms
  P50: 401.23ms
  P95: 589.12ms
  P99: 645.67ms

create_paper:
  Count: 43
  Avg: 287.56ms
  Min: 156.23ms
  Max: 892.45ms
  P50: 267.34ms
  P95: 534.12ms
  P99: 723.89ms

update_paper:
  Count: 20
  Avg: 198.34ms
  Min: 123.45ms
  Max: 456.78ms
  P50: 189.12ms
  P95: 345.67ms
  P99: 412.34ms

enqueue_slr:
  Count: 48
  Avg: 312.67ms
  Min: 234.56ms
  Max: 567.89ms
  P50: 298.45ms
  P95: 478.23ms
  P99: 523.45ms

enqueue_generation:
  Count: 6
  Avg: 456.78ms
  Min: 389.12ms
  Max: 678.90ms
  P50: 445.67ms
  P95: 612.34ms
  P99: 656.78ms

================================================================================
ERRORS:
================================================================================

1. update_paper (Status: 409)
   Concurrent modification conflict

2. enqueue_slr (Status: 429)
   Rate limit exceeded

3. concurrent_edit (Status: 409)
   Optimistic lock failure

================================================================================

✓ Tests completed successfully

==========================================
Generating Reports
==========================================

🛑 Stopping system monitor...

📈 Analyzing test results...
```

---

## 2. Analysis Report Output

```
================================================================================
LOAD TEST ANALYSIS REPORT
================================================================================

📊 SUMMARY
--------------------------------------------------------------------------------
Total Tests: 28
Passed: 28
Failed: 0
Success Rate: 100.00%

⚡ PERFORMANCE METRICS
--------------------------------------------------------------------------------
Total Duration: 150.34s
Average: 5369.21ms
Min: 2134.56ms
Max: 19234.78ms
P50: 4567.89ms
P95: 15234.56ms
P99: 17890.12ms

🚨 BOTTLENECKS IDENTIFIED
--------------------------------------------------------------------------------

1. 🟡 MODERATE_RESPONSE_TIME (medium)
   P95 response time is 15234.56ms
   → Consider caching frequently accessed data

2. 🟡 HIGH_VARIANCE (medium)
   Max response time (19234.78ms) is 3.6x the average
   → Some operations are significantly slower - investigate outliers

📈 SCALABILITY ASSESSMENT
--------------------------------------------------------------------------------
Score: 82.5/100 (Grade: B)
Assessment: Good - System is stable with minor performance issues

💡 RECOMMENDATIONS
--------------------------------------------------------------------------------
1. Consider caching frequently accessed data
2. Some operations are significantly slower - investigate outliers
3. Add monitoring and alerting for slow requests
4. System is performing well - continue monitoring
5. Consider testing with higher concurrency levels

================================================================================
```

---

## 3. System Monitor Report

```
[0.0s] CPU: 12.3% | Mem: 2456MB/16384MB | Processes: Py=4 Node=2
[1.0s] CPU: 45.7% | Mem: 2678MB/16384MB | Processes: Py=4 Node=2
[2.0s] CPU: 67.8% | Mem: 2891MB/16384MB | Processes: Py=6 Node=2
[3.0s] CPU: 78.9% | Mem: 3124MB/16384MB | Processes: Py=8 Node=2
[4.0s] CPU: 82.3% | Mem: 3456MB/16384MB | Processes: Py=10 Node=2
[5.0s] CPU: 79.4% | Mem: 3678MB/16384MB | Processes: Py=10 Node=2
...
[145.0s] CPU: 34.5% | Mem: 3234MB/16384MB | Processes: Py=6 Node=2
[146.0s] CPU: 23.4% | Mem: 2987MB/16384MB | Processes: Py=4 Node=2
[147.0s] CPU: 15.6% | Mem: 2756MB/16384MB | Processes: Py=4 Node=2

Stopping monitor...

================================================================================
SYSTEM RESOURCE REPORT
================================================================================
Duration: 147.5s
Samples: 148

CPU Usage:
  Average: 54.32%
  Peak: 85.67%

Memory Usage:
  Average: 3124MB
  Peak: 3789MB
================================================================================

System monitor report saved to system-monitor-report.json
```

---

## 4. Race Condition Report

```
================================================================================
RACE CONDITION TEST REPORT
================================================================================
Total Operations: 45
Conflicts/Errors: 5
Conflict Rate: 11.11%

Operation Timings:

concurrent_edit:
  Successful: 15
  Avg Response: 234.56ms
  P95: 456.78ms

concurrent_slr:
  Successful: 18
  Avg Response: 312.45ms
  P95: 523.67ms

concurrent_generation:
  Successful: 7
  Avg Response: 478.90ms
  P95: 678.12ms

================================================================================
CONFLICTS DETECTED:
================================================================================
  concurrent_edit: 3 conflicts
  concurrent_generation: 2 conflicts

================================================================================
```

---

## 5. Queue Management Report

```
================================================================================
QUEUE MANAGEMENT TEST REPORT
================================================================================
Total Queue Operations: 156
Failed Operations: 2
Failure Rate: 1.28%

Queue Operation Performance:
--------------------------------------------------------------------------------

rapid_job_submission:
  Count: 25
  Avg: 267.34ms
  P95: 445.67ms
  P99: 512.34ms

status_poll:
  Count: 100
  Avg: 145.23ms
  P95: 234.56ms
  P99: 289.12ms

cancel_job:
  Count: 9
  Avg: 198.45ms
  P95: 312.67ms
  P99: 356.78ms

mixed_slr:
  Count: 8
  Avg: 289.56ms
  P95: 423.45ms
  P99: 478.90ms

capacity_submit:
  Count: 15
  Avg: 312.78ms
  P95: 489.12ms
  P99: 534.56ms

================================================================================
QUEUE ERRORS:
================================================================================
  rapid_job_submission: 1 errors
  capacity_submit: 1 errors

================================================================================
```

---

## 6. HTML Report Preview

The HTML report (`playwright-report-load/index.html`) contains:

- **Test Results**: Pass/fail status for each test
- **Timings**: Duration for each test and operation
- **Screenshots**: Captured on failures
- **Traces**: Full browser traces for debugging
- **Filters**: By status, browser, test file
- **Search**: Find specific tests
- **Trends**: Performance over time

**View with**: `npm run test:load:report`

---

## 7. JSON Results Structure

```json
{
  "config": {
    "workers": 10,
    "timeout": 300000
  },
  "suites": [
    {
      "title": "Concurrent Users Load Test",
      "specs": [
        {
          "title": "User 1: Create multiple papers",
          "tests": [
            {
              "status": "passed",
              "duration": 12345,
              "results": [...]
            }
          ]
        }
      ]
    }
  ],
  "stats": {
    "startTime": "2026-05-22T16:00:00.000Z",
    "duration": 150340,
    "expected": 28,
    "unexpected": 0,
    "passed": 28,
    "failed": 0
  }
}
```

---

## Interpreting Results

### ✅ Good Results
- Success rate > 95%
- P95 < 2000ms
- Error rate < 5%
- Grade B or better

### ⚠️ Warning Signs
- Success rate 90-95%
- P95 2000-5000ms
- Error rate 5-10%
- Grade C

### 🚨 Critical Issues
- Success rate < 90%
- P95 > 5000ms
- Error rate > 10%
- Grade D or F

---

## Next Steps Based on Results

### If Grade A/B
- ✅ System is ready for production
- Consider testing with more users
- Monitor in production

### If Grade C
- ⚠️ Optimize slow operations
- Add caching
- Review database queries

### If Grade D/F
- 🚨 Critical issues found
- Fix errors before production
- Review architecture
- Add database indexes
- Increase connection pool
