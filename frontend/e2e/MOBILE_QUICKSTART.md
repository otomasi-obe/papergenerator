# Mobile Testing Quick Start Guide

## Prerequisites

```bash
cd frontend
npm install
```

Ensure backend is running on port 8001 and frontend on port 8000.

## Run Mobile Tests

### Option 1: Run All Mobile Tests (Recommended First Time)

```bash
npm run test:e2e -- mobile.spec.js
```

This runs all 40+ mobile test scenarios on both iPhone 12 and Android Pixel 5.

### Option 2: Run Specific Device

```bash
# iPhone 12 only
npm run test:e2e -- mobile.spec.js --project=mobile-iphone

# Android Pixel 5 only
npm run test:e2e -- mobile.spec.js --project=mobile-android
```

### Option 3: Run Specific Test Suite

```bash
# Responsiveness tests
npm run test:e2e -- mobile.spec.js -g "Mobile Responsiveness"

# Performance tests
npm run test:e2e -- mobile.spec.js -g "Mobile Performance"

# UX assessment
npm run test:e2e -- mobile.spec.js -g "Mobile UX Assessment"

# Paper creation flow
npm run test:e2e -- mobile.spec.js -g "Mobile Paper Creation"

# Editor functionality
npm run test:e2e -- mobile.spec.js -g "Mobile Editor"

# Chat interface
npm run test:e2e -- mobile.spec.js -g "Mobile Chat"

# Offline behavior
npm run test:e2e -- mobile.spec.js -g "Mobile Offline"
```

### Option 4: Debug Mode (Visual UI)

```bash
npm run test:e2e:ui -- mobile.spec.js
```

Opens Playwright UI where you can:
- See test execution in real-time
- Step through tests
- Inspect mobile viewport
- View network requests
- Check console logs

### Option 5: Headed Mode (See Browser)

```bash
npm run test:e2e -- mobile.spec.js --headed
```

Shows the actual mobile viewport in a browser window.

## Understanding Test Results

### ✅ All Tests Pass

```
Running 42 tests using 1 worker

  ✓ [mobile-iphone] › mobile.spec.js:15:3 › Mobile Responsiveness - iPhone 12 › landing page renders correctly on mobile (1.2s)
  ✓ [mobile-iphone] › mobile.spec.js:25:3 › Mobile Responsiveness - iPhone 12 › mobile navigation - hamburger menu (0.8s)
  ...
  
42 passed (5.2m)
```

**Action**: Great! Your mobile UX is solid. Review the MOBILE_ASSESSMENT_REPORT.md for optimization recommendations.

### ❌ Some Tests Fail

```
Running 42 tests using 1 worker

  ✓ [mobile-iphone] › mobile.spec.js:15:3 › landing page renders correctly on mobile (1.2s)
  ✗ [mobile-iphone] › mobile.spec.js:35:3 › touch target sizes are adequate (0.5s)
  
    Error: expect(received).toBeGreaterThanOrEqual(expected)
    Expected: >= 40
    Received: 32
```

**Action**: 
1. Check which element failed: Look at the test output
2. Fix the issue: Increase button size in CSS
3. Re-run: `npm run test:e2e -- mobile.spec.js -g "touch target"`

### ⚠️ Performance Tests Fail

```
  ✗ [mobile-iphone] › mobile.spec.js:89:3 › mobile page load performance (6.2s)
  
    Error: expect(received).toBeLessThan(expected)
    Expected: < 5000
    Received: 6200
```

**Action**:
1. Check what's slow: Review network tab in test trace
2. Optimize: Reduce bundle size, lazy load, compress images
3. Consider: Adjust threshold if 5s is too aggressive for your setup

## Common Issues & Solutions

### Issue: Tests timeout

```
Error: Test timeout of 30000ms exceeded
```

**Solution**:
```bash
# Increase timeout
npm run test:e2e -- mobile.spec.js --timeout=60000
```

Or check if backend is running:
```bash
curl http://localhost:8000/api/health
```

### Issue: Element not found

```
Error: locator.tap: Target closed
```

**Solution**: Add `data-testid` attributes to your components:

```html
<!-- Before -->
<button class="menu-btn">Menu</button>

<!-- After -->
<button class="menu-btn" data-testid="mobile-menu-button">Menu</button>
```

### Issue: CSRF token errors

```
Error: 401 Unauthorized
```

**Solution**: Tests handle CSRF automatically. If failing, check:
1. Backend CSRF middleware is enabled
2. Cookies are being set correctly
3. CSRF token is in response cookies

### Issue: Database conflicts

```
Error: User already exists
```

**Solution**: Tests create unique users with timestamps. If still failing:
```bash
# Reset test database
npm run db:reset:test
```

## View Test Reports

### HTML Report (After Test Run)

```bash
npx playwright show-report
```

Opens interactive HTML report with:
- Test results summary
- Screenshots of failures
- Video recordings
- Network logs
- Console output

### Trace Viewer (For Failed Tests)

```bash
npx playwright show-trace test-results/mobile-spec-js-mobile-iphone-landing-page/trace.zip
```

Shows detailed timeline of:
- Every action taken
- Screenshots at each step
- Network requests
- Console logs
- DOM snapshots

## Test Coverage Checklist

After running tests, verify these areas are covered:

- [ ] Landing page loads on mobile
- [ ] Navigation menu works (hamburger)
- [ ] Touch targets are adequate size (≥40px)
- [ ] No horizontal scrolling
- [ ] Text is readable (≥14px)
- [ ] Forms work with touch input
- [ ] Editor is usable on mobile
- [ ] Chat interface fits screen
- [ ] Page loads in <5 seconds
- [ ] Memory usage is reasonable
- [ ] Layout doesn't shift (CLS <0.25)
- [ ] Offline behavior is handled

## Next Steps After First Run

### 1. Review Results
```bash
npx playwright show-report
```

### 2. Fix Critical Issues
- Touch targets too small
- Horizontal scrolling
- Performance problems
- Layout shifts

### 3. Add Test Identifiers
Add `data-testid` attributes to make tests more reliable:

```html
<button data-testid="mobile-menu-button">Menu</button>
<input data-testid="chat-input" />
<div data-testid="editor-toolbar">...</div>
```

### 4. Optimize Performance
- Lazy load images
- Code split bundles
- Compress assets
- Implement caching

### 5. Run in CI
Add to your CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run Mobile E2E Tests
  run: |
    cd frontend
    npm run test:e2e -- mobile.spec.js
```

## Advanced Usage

### Run with Network Throttling (Future Enhancement)

```javascript
// Add to test
await page.route('**/*', route => {
  setTimeout(() => route.continue(), 100); // Simulate slow network
});
```

### Test Landscape Orientation

```javascript
test.use({ 
  viewport: { width: 844, height: 390 }, // Rotated
});
```

### Test on Tablet

```javascript
test.use({ 
  ...devices['iPad Pro'],
});
```

### Capture Performance Metrics

```javascript
const metrics = await page.evaluate(() => JSON.stringify(performance.timing));
console.log('Performance:', metrics);
```

## Getting Help

### Test Failing?
1. Run with `--headed` to see what's happening
2. Use `--debug` to step through test
3. Check test trace: `npx playwright show-trace`
4. Review MOBILE_TESTING.md for troubleshooting

### Need to Modify Tests?
1. Read existing test structure in `mobile.spec.js`
2. Follow same patterns for consistency
3. Add `data-testid` attributes for reliability
4. Test your changes: `npm run test:e2e -- mobile.spec.js -g "your test"`

### Performance Issues?
1. Check MOBILE_ASSESSMENT_REPORT.md for benchmarks
2. Review which resources are slow
3. Optimize critical path
4. Consider adjusting thresholds

## Resources

- **Full Documentation**: `MOBILE_TESTING.md`
- **Assessment Report**: `MOBILE_ASSESSMENT_REPORT.md`
- **Test File**: `mobile.spec.js`
- **Playwright Docs**: https://playwright.dev/docs/emulation

## Quick Command Reference

```bash
# Run all mobile tests
npm run test:e2e -- mobile.spec.js

# Run specific device
npm run test:e2e -- mobile.spec.js --project=mobile-iphone

# Debug mode
npm run test:e2e:ui -- mobile.spec.js

# Headed mode
npm run test:e2e -- mobile.spec.js --headed

# Specific test
npm run test:e2e -- mobile.spec.js -g "performance"

# View report
npx playwright show-report

# View trace
npx playwright show-trace test-results/.../trace.zip
```

---

**Ready to start?** Run: `npm run test:e2e -- mobile.spec.js`
