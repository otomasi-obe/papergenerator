# Load Testing Quick Reference

## Run Tests

```bash
# Interactive runner (easiest)
cd frontend && ./run-load-tests.sh

# All tests
npm run test:load

# Specific tests
npm run test:load:concurrent    # 10 concurrent users
npm run test:load:race          # Race conditions
npm run test:load:queue         # Queue management
```

## View Results

```bash
# HTML report (interactive)
npm run test:load:report

# Analysis report (console)
npm run test:load:analyze

# System monitor log
cat system-monitor.log
```

## Files

```
frontend/
├── playwright.config.load.js          # Config (10 workers)
├── run-load-tests.sh                  # Main runner
├── e2e/load/
│   ├── README.md                      # Full documentation
│   ├── concurrent-users.spec.js       # 10 user test
│   ├── race-conditions.spec.js        # Race condition test
│   ├── queue-management.spec.js       # Queue test
│   ├── helpers.js                     # Utilities
│   ├── system-monitor.js              # Resource monitor
│   └── analyzer.js                    # Results analyzer
```

## Test Scenarios

**Concurrent Users (10 users)**
- Users 1-3: Create 5 papers each
- Users 4-6: Run 3 SLR jobs each
- Users 7-8: Generate papers
- Users 9-10: Edit papers 10 times

**Race Conditions**
- 5 users edit same paper
- 3 concurrent SLR jobs
- 3 simultaneous generations

**Queue Management**
- Rapid job submission
- Status polling
- Job cancellation
- Capacity stress test

## Metrics

**Performance**
- Response times (avg, P50, P95, P99)
- Error rates
- Success rates

**System**
- CPU usage
- Memory usage
- Process counts

**Scalability**
- Score: 0-100
- Grade: A-F
- Recommendations

## Grading

| Grade | Score | Status |
|-------|-------|--------|
| A | 90-100 | Excellent |
| B | 80-89 | Good |
| C | 70-79 | Fair |
| D | 60-69 | Poor |
| F | 0-59 | Critical |

## Troubleshooting

**Tests timeout**: Increase timeout in config  
**High errors**: Check backend logs  
**Connection errors**: Verify services running  
**Slow tests**: Check database performance

## Configuration

**Change concurrency**: Edit `playwright.config.load.js` → `workers: 10`  
**Change timeout**: Edit config → `timeout: 300_000`  
**Change URL**: `E2E_BASE_URL=http://... npm run test:load`

## Prerequisites

- Backend on port 8000
- PostgreSQL running
- Redis running
- `npm install` + `npx playwright install chromium`
