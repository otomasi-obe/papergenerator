# Chaos Testing Quick Reference

## Quick Start

```bash
# Run all chaos tests
npm run test:chaos

# Run with visual UI (recommended for first time)
npm run test:chaos:ui

# Run with full report generation
npm run test:chaos:report
```

## Test Categories at a Glance

| Category | Weight | Focus Area |
|----------|--------|------------|
| 🌐 Network Failures | 25% | Offline, slow, intermittent connections |
| 🔒 Invalid Inputs | 20% | XSS, SQL injection, validation |
| 💾 Resource Exhaustion | 15% | Large files, rate limits, memory |
| ⏱️ Timeouts | 15% | Cancellation, refresh, long operations |
| 🔑 Authentication | 15% | Token expiry, CSRF, sessions |
| 🖥️ Compatibility | 5% | Browsers, viewports, features |
| 🔄 Data Integrity | 5% | Duplicates, consistency, recovery |

## Common Commands

```bash
# Run specific category
npm run test:chaos -- -g "Network Failure"
npm run test:chaos -- -g "Security"
npm run test:chaos -- -g "Authentication"

# Run single test
npm run test:chaos -- -g "handles offline"

# Debug mode with headed browser
npm run test:chaos -- --headed --debug

# Generate HTML report
npm run test:chaos -- --reporter=html

# Run in specific browser
npm run test:chaos -- --project=chromium
npm run test:chaos -- --project=firefox
npm run test:chaos -- --project=webkit
```

## Score Interpretation

### Robustness Score
- 🟢 **90-100**: Production ready
- 🟡 **70-89**: Minor fixes needed
- 🟠 **50-69**: Significant issues
- 🔴 **0-49**: Critical problems

### Security Risk
- ✅ **LOW**: Safe to deploy
- ⚠️ **MEDIUM**: Review before deploy
- 🚨 **HIGH**: Fix before deploy
- 🔥 **CRITICAL**: Do not deploy

## What Each Test Checks

### Network Failures
- ✓ Shows error when offline
- ✓ Loading indicators on slow network
- ✓ Retry mechanisms work
- ✓ Recovers when connection restored

### Invalid Inputs
- ✓ Blocks empty submissions
- ✓ Handles long text gracefully
- ✓ Sanitizes special characters
- ✓ Prevents SQL injection
- ✓ Prevents XSS attacks
- ✓ Validates email format

### Resource Exhaustion
- ✓ Rejects oversized files
- ✓ Rate limits API requests
- ✓ Limits dataset sizes
- ✓ Handles memory pressure

### Timeouts
- ✓ Shows timeout errors
- ✓ Allows operation cancellation
- ✓ Preserves data on refresh
- ✓ Warns about unsaved changes

### Authentication
- ✓ Handles expired tokens
- ✓ Rejects invalid tokens
- ✓ Manages logout properly
- ✓ Enforces CSRF protection

### Compatibility
- ✓ Works without JavaScript (graceful degradation)
- ✓ Works without cookies (shows message)
- ✓ Handles localStorage errors
- ✓ Responsive on mobile
- ✓ Works on extreme viewports

### Data Integrity
- ✓ Prevents duplicate submissions
- ✓ Maintains consistency after errors
- ✓ Recovers from corrupted data

## Troubleshooting

### "Tests are timing out"
```bash
# Increase timeout in playwright.config.js
timeout: 60_000  # 60 seconds
```

### "Cannot connect to backend"
```bash
# Check backend is running
curl http://localhost:8001/api/health

# Start backend if needed
cd backend && python -m uvicorn main:app --reload --port 8001
```

### "Database errors"
```bash
# Check database connection
psql -U postgres -d paperfull -c "SELECT 1"

# Reset test database if needed
npm run db:reset:test
```

### "Authentication tests failing"
```bash
# Check CSRF implementation
# Verify cookies are set with httpOnly
# Ensure session management is working
```

## CI/CD Integration

### Minimal (just run tests)
```yaml
- run: npm run test:chaos
```

### With reporting
```yaml
- run: npm run test:chaos:report
- uses: actions/upload-artifact@v3
  with:
    name: chaos-reports
    path: CHAOS_TEST_REPORT_*.md
```

### With score threshold
```yaml
- run: |
    npm run test:chaos:report
    SCORE=$(node -pe "require('./chaos-results-latest.json').robustnessScore")
    if [ $SCORE -lt 70 ]; then exit 1; fi
```

## Reading Reports

### Markdown Report Structure
```
1. Executive Summary - Overall stats
2. Robustness Score Breakdown - By category
3. Error Handling Assessment - What failed
4. Security Vulnerability Report - Security issues
5. Recovery Mechanism Evaluation - Recovery status
6. Recommendations - What to fix first
```

### JSON Report Structure
```json
{
  "analysis": {
    "total": 45,
    "passed": 38,
    "failed": 7,
    "categories": { /* by category */ }
  },
  "robustnessScore": 85.5,
  "errorReport": { /* error details */ },
  "securityReport": { 
    "risk_level": "LOW",
    "vulnerabilities": []
  },
  "recoveryReport": {
    "score": 90,
    "mechanisms": { /* by type */ }
  }
}
```

## Best Practices

1. **Run before every release**
   ```bash
   npm run test:chaos:report
   ```

2. **Track score over time**
   ```bash
   # Save to git
   git add CHAOS_TEST_REPORT_*.md
   git commit -m "chore: chaos test results"
   ```

3. **Fix security issues first**
   - Check `securityReport.vulnerabilities`
   - Address CRITICAL and HIGH severity
   - Re-run tests to verify

4. **Monitor trends**
   - Compare scores across releases
   - Watch for regressions
   - Set minimum score threshold

5. **Update tests as features grow**
   - Add new scenarios
   - Update expected behaviors
   - Adjust weights if needed

## Example Workflow

```bash
# 1. Start services
npm run dev          # Terminal 1
cd ../backend && python -m uvicorn main:app --reload  # Terminal 2

# 2. Run chaos tests with UI (first time)
npm run test:chaos:ui

# 3. Fix any failures

# 4. Run full report
npm run test:chaos:report

# 5. Review report
cat CHAOS_TEST_REPORT_*.md

# 6. If score > 70, proceed to deploy
# 7. If score < 70, fix issues and repeat
```

## Key Metrics to Watch

| Metric | Target | Action if Below |
|--------|--------|-----------------|
| Robustness Score | > 85 | Review failed categories |
| Security Risk | LOW | Fix vulnerabilities immediately |
| Recovery Score | > 80 | Improve error recovery |
| Network Tests | 100% | Add retry logic |
| Security Tests | 100% | Critical - must fix |
| Auth Tests | > 90% | Review token handling |

## Getting Help

1. **Check test output**: `playwright-report/index.html`
2. **Enable trace**: Set `trace: 'on'` in config
3. **Run with debug**: `npm run test:chaos -- --debug`
4. **Check logs**: Backend logs, browser console
5. **Review docs**: `README-CHAOS.md`

## Quick Fixes

### Low Network Score
```javascript
// Add retry logic
const fetchWithRetry = async (url, retries = 3) => {
  for (let i = 0; i < retries; i++) {
    try {
      return await fetch(url);
    } catch (err) {
      if (i === retries - 1) throw err;
      await new Promise(r => setTimeout(r, 1000 * (i + 1)));
    }
  }
};
```

### Low Security Score
```javascript
// Sanitize inputs
import DOMPurify from 'dompurify';
const clean = DOMPurify.sanitize(userInput);

// Use parameterized queries (backend)
cursor.execute("SELECT * FROM papers WHERE id = %s", (paper_id,))
```

### Low Recovery Score
```javascript
// Add error boundaries
<ErrorBoundary fallback={<ErrorPage />}>
  <App />
</ErrorBoundary>

// Implement autosave
useEffect(() => {
  const timer = setInterval(() => {
    localStorage.setItem('draft', JSON.stringify(formData));
  }, 5000);
  return () => clearInterval(timer);
}, [formData]);
```

---

**Last Updated**: 2026-05-22  
**Version**: 1.0.0
