# Chaos Testing Suite

Comprehensive error scenario and robustness testing for PaperFull application.

## Overview

This chaos testing suite intentionally causes failures to test the application's:
- **Error handling** - How gracefully errors are caught and displayed
- **Security** - Resistance to injection attacks and malicious input
- **Recovery** - Ability to recover from failures and maintain data integrity
- **Robustness** - Overall system stability under adverse conditions

## Test Categories

### 1. Network Failure Scenarios (25% weight)
- Offline during operations
- Slow network (3G throttle)
- Intermittent connection (packet loss)
- Recovery from temporary failures

### 2. Invalid Input Scenarios (20% weight)
- Empty form submissions
- Extremely long text (10,000+ chars)
- Special characters and encoding
- SQL injection attempts
- XSS (Cross-Site Scripting) attempts
- Email format validation

### 3. Resource Exhaustion Scenarios (15% weight)
- Oversized file uploads (>100MB)
- Excessive API requests (rate limiting)
- Large dataset requests
- Long-running operations

### 4. Timeout & Cancellation Scenarios (15% weight)
- Operation timeouts
- User cancellation
- Page refresh during operations
- Unsaved changes warnings

### 5. Authentication Error Scenarios (15% weight)
- Expired tokens
- Invalid tokens
- Logout during operations
- Concurrent session handling
- CSRF protection

### 6. Browser Compatibility & Edge Cases (5% weight)
- Disabled JavaScript
- Disabled cookies
- localStorage unavailable
- Mobile viewports
- Extreme viewport sizes (320px - 4K)

### 7. Data Integrity & Recovery (5% weight)
- Duplicate submission prevention
- Data consistency after errors
- Recovery from corrupted data

## Running Tests

### Run all chaos tests:
```bash
npm run test:e2e -- chaos.spec.js
```

### Run with UI mode (recommended for debugging):
```bash
npm run test:e2e:ui -- chaos.spec.js
```

### Run specific test category:
```bash
npm run test:e2e -- chaos.spec.js -g "Network Failure"
```

### Run with comprehensive reporting:
```bash
node e2e/chaos-runner.js
```

## Generated Reports

The chaos runner generates multiple reports:

### 1. Markdown Report (`CHAOS_TEST_REPORT_*.md`)
Human-readable report with:
- Executive summary
- Robustness score breakdown
- Error handling assessment
- Security vulnerability report
- Recovery mechanism evaluation
- Prioritized recommendations

### 2. JSON Report (`chaos-results-*.json`)
Machine-readable data for CI/CD integration:
```json
{
  "analysis": { /* test results by category */ },
  "robustnessScore": 85.5,
  "errorReport": { /* error handling details */ },
  "securityReport": { /* vulnerabilities found */ },
  "recoveryReport": { /* recovery mechanisms */ }
}
```

## Interpreting Results

### Robustness Score
- **90-100**: Excellent - System handles errors gracefully
- **70-89**: Good - Minor improvements needed
- **50-69**: Fair - Several issues need attention
- **0-49**: Poor - Critical issues detected

### Security Risk Levels
- **LOW**: No critical vulnerabilities
- **MEDIUM**: Minor security concerns
- **HIGH**: Significant vulnerabilities found
- **CRITICAL**: Immediate action required

### Recovery Status
- **EXCELLENT**: All recovery mechanisms working
- **GOOD**: Most mechanisms working (>70%)
- **FAIR**: Some mechanisms failing (50-70%)
- **POOR**: Critical recovery failures (<50%)

## Prerequisites

1. **Backend must be running:**
   ```bash
   cd backend
   python -m uvicorn main:app --reload --port 8001
   ```

2. **Frontend must be running:**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Database must be accessible:**
   - PostgreSQL running on configured port
   - Test database initialized

## Configuration

Edit `playwright.config.js` to adjust:
- `timeout`: Test timeout (default: 30s)
- `baseURL`: Application URL (default: http://localhost:8000)
- `workers`: Parallel execution (default: 1 for shared DB)

## Common Issues

### Tests timing out
- Increase timeout in `playwright.config.js`
- Check backend is responding
- Verify database connection

### Network tests failing
- Ensure proper route mocking
- Check Playwright version (requires 1.40+)
- Verify context isolation

### Authentication tests failing
- Check CSRF token implementation
- Verify cookie settings (httpOnly, secure)
- Ensure session management is working

## Best Practices

1. **Run before deployment** - Catch issues early
2. **Monitor trends** - Track robustness score over time
3. **Fix critical first** - Prioritize security vulnerabilities
4. **Test in CI/CD** - Automate chaos testing in pipeline
5. **Update regularly** - Add new scenarios as features grow

## CI/CD Integration

### GitHub Actions Example:
```yaml
- name: Run Chaos Tests
  run: |
    npm run test:e2e -- chaos.spec.js
    node e2e/chaos-runner.js
  
- name: Upload Reports
  uses: actions/upload-artifact@v3
  with:
    name: chaos-reports
    path: |
      CHAOS_TEST_REPORT_*.md
      chaos-results-*.json
```

### Fail Build on Low Score:
```bash
SCORE=$(node -e "console.log(require('./chaos-results-latest.json').robustnessScore)")
if [ "$SCORE" -lt 70 ]; then
  echo "Robustness score too low: $SCORE"
  exit 1
fi
```

## Extending Tests

### Add new test category:
```javascript
test.describe('New Category', () => {
  test('new scenario', async ({ page }) => {
    // Your test logic
  });
});
```

### Add to chaos-runner.js:
```javascript
const TEST_CATEGORIES = {
  // ... existing categories
  newCategory: {
    name: 'New Category',
    weight: 0.10,
    tests: ['scenario1', 'scenario2']
  }
};
```

## Support

For issues or questions:
1. Check Playwright docs: https://playwright.dev
2. Review existing test patterns in `smoke.spec.js` and `auth.spec.js`
3. Check application logs for backend errors
4. Enable Playwright trace: `trace: 'on'` in config

## License

Part of PaperFull project - Internal testing suite
