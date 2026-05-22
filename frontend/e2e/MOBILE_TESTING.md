# Mobile E2E Testing Documentation

## Overview

Comprehensive mobile testing suite for PaperFull app covering responsive design, touch interactions, and mobile-specific user experience.

**Persona**: Mahasiswa yang sering kerja dari HP, akses dari smartphone

## Test Coverage

### 1. Mobile Responsiveness Tests

#### iPhone 12 (390x844)
- ✅ Landing page rendering
- ✅ Mobile navigation (hamburger menu)
- ✅ Touch target sizes (min 44x44px WCAG compliance)
- ✅ Smooth scroll behavior
- ✅ Text input on small screens
- ✅ Page load performance (<5s)

#### Android (Pixel 5, 412x915)
- ✅ Landing page rendering
- ✅ Touch gesture support
- ✅ Android-specific user agent

### 2. Paper Creation Flow on Mobile
- ✅ Create paper button accessibility
- ✅ Question answering with touch input
- ✅ File upload from mobile device
- ✅ Form field interactions

### 3. Mobile Editor Functionality
- ✅ Editor accessibility on mobile
- ✅ Scrolling long content
- ✅ Toolbar accessibility and responsiveness
- ✅ Content editing with touch

### 4. Chat Interface on Mobile
- ✅ Chat input usability
- ✅ Scroll to bottom functionality
- ✅ Tool result display fitting mobile screen
- ✅ Message display and interaction

### 5. Performance Metrics
- ✅ Page load time measurement (<5s target)
- ✅ Memory usage monitoring (<100MB JS heap)
- ✅ Cumulative Layout Shift (CLS <0.25)
- ✅ Resource loading performance (<3s per resource)

### 6. Offline Behavior
- ✅ Offline indicator display
- ✅ Service worker caching
- ✅ Network failure handling

### 7. Mobile UX Assessment
- ✅ Font size readability (min 14px)
- ✅ No horizontal scrolling
- ✅ Responsive images
- ✅ Tap target spacing (min 8px)
- ✅ Viewport meta tag presence

## Running the Tests

### Run all mobile tests
```bash
cd frontend
npm run test:e2e -- mobile.spec.js
```

### Run specific mobile device
```bash
# iPhone 12 only
npm run test:e2e -- mobile.spec.js --project=mobile-iphone

# Android only
npm run test:e2e -- mobile.spec.js --project=mobile-android
```

### Run specific test suite
```bash
# Responsiveness tests only
npm run test:e2e -- mobile.spec.js -g "Mobile Responsiveness"

# Performance tests only
npm run test:e2e -- mobile.spec.js -g "Mobile Performance"

# UX assessment only
npm run test:e2e -- mobile.spec.js -g "Mobile UX Assessment"
```

### Run with UI mode (recommended for debugging)
```bash
npm run test:e2e:ui -- mobile.spec.js
```

### Run with headed browser (see actual mobile viewport)
```bash
npm run test:e2e -- mobile.spec.js --headed
```

## Test Results Interpretation

### Performance Benchmarks

| Metric | Target | Critical Threshold |
|--------|--------|-------------------|
| Page Load Time | <3s | <5s |
| DOM Content Loaded | <2s | <3s |
| Memory Usage (JS Heap) | <50MB | <100MB |
| Cumulative Layout Shift | <0.1 | <0.25 |
| Resource Load Time | <1s | <3s |

### Touch Target Guidelines

- **Minimum size**: 44x44px (WCAG 2.1 Level AAA)
- **Acceptable size**: 40x40px (tested threshold)
- **Minimum spacing**: 8px between interactive elements

### Viewport Sizes Tested

| Device | Width | Height | Notes |
|--------|-------|--------|-------|
| iPhone 12 | 390px | 844px | iOS Safari |
| Pixel 5 | 412px | 915px | Android Chrome |

## Mobile-Specific Issues to Watch

### Common Mobile UX Problems
1. **Horizontal scrolling** - Content wider than viewport
2. **Small touch targets** - Buttons/links <40px
3. **Unreadable text** - Font size <14px
4. **Layout shifts** - CLS >0.25
5. **Slow loading** - >5s on mobile network
6. **Memory leaks** - Growing heap size
7. **Fixed positioning issues** - Elements covering content
8. **Keyboard overlap** - Input fields hidden by virtual keyboard

### Mobile Performance Considerations
- **Network**: Tests assume good WiFi; real users may have 3G/4G
- **CPU**: Mobile devices have less processing power
- **Memory**: Mobile browsers have stricter memory limits
- **Battery**: Heavy JS/animations drain battery faster

## Test Architecture

### Test Structure
```
mobile.spec.js
├── Mobile Responsiveness - iPhone 12
│   ├── Landing page rendering
│   ├── Navigation (hamburger menu)
│   ├── Touch target sizes
│   ├── Scroll behavior
│   ├── Text input
│   └── Performance
├── Mobile Responsiveness - Android
│   ├── Landing page rendering
│   └── Touch gestures
├── Mobile Paper Creation Flow
│   ├── Create paper
│   ├── Question answering
│   └── File upload
├── Mobile Editor Functionality
│   ├── Editor accessibility
│   ├── Scrolling
│   └── Toolbar
├── Mobile Chat Interface
│   ├── Chat input
│   ├── Scroll to bottom
│   └── Tool results
├── Mobile Performance Metrics
│   ├── Page load time
│   ├── Memory usage
│   ├── Layout shifts
│   └── Resource loading
├── Mobile Offline Behavior
│   ├── Offline indicator
│   └── Service worker
└── Mobile UX Assessment
    ├── Font sizes
    ├── Horizontal scrolling
    ├── Responsive images
    ├── Tap target spacing
    └── Viewport meta tag
```

### Helper Functions
- `csrfFromCookies()` - Extract CSRF token from cookies for authenticated requests

## Debugging Mobile Tests

### View test execution
```bash
npm run test:e2e -- mobile.spec.js --headed --project=mobile-iphone
```

### Generate trace for failed tests
```bash
npm run test:e2e -- mobile.spec.js
# Traces saved to: playwright-report/
npx playwright show-trace playwright-report/trace.zip
```

### Take screenshots during test
```javascript
await page.screenshot({ path: 'debug-mobile.png', fullPage: true });
```

### Check viewport size during test
```javascript
const viewport = page.viewportSize();
console.log('Viewport:', viewport);
```

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run Mobile E2E Tests
  run: |
    cd frontend
    npm run test:e2e -- mobile.spec.js --project=mobile-iphone
    npm run test:e2e -- mobile.spec.js --project=mobile-android
```

### Test Reports
- HTML report: `frontend/playwright-report/index.html`
- Screenshots: `frontend/test-results/`
- Videos: `frontend/test-results/` (on failure)
- Traces: `frontend/test-results/` (on failure)

## Known Limitations

1. **Real device testing**: Tests run in emulated mobile viewports, not real devices
2. **Network throttling**: Not implemented (can be added with `page.route()`)
3. **Battery impact**: Cannot be measured in Playwright
4. **Biometric auth**: Not testable in browser automation
5. **Native app features**: Push notifications, camera access limited
6. **Gesture complexity**: Advanced gestures (pinch-zoom) not fully tested

## Future Enhancements

- [ ] Add network throttling (3G/4G simulation)
- [ ] Test landscape orientation
- [ ] Add more device profiles (iPad, older Android)
- [ ] Test dark mode on mobile
- [ ] Add accessibility testing (screen reader simulation)
- [ ] Test PWA installation flow
- [ ] Add visual regression testing for mobile
- [ ] Test mobile-specific features (share API, etc.)

## Troubleshooting

### Tests failing on mobile but passing on desktop
1. Check viewport-specific CSS media queries
2. Verify touch event handlers vs click handlers
3. Check for fixed positioning issues
4. Verify mobile-specific JavaScript

### Performance tests failing
1. Check if backend is running locally
2. Verify no other heavy processes running
3. Consider adjusting thresholds for CI environment
4. Check network conditions

### Touch interactions not working
1. Verify `hasTouch: true` in test configuration
2. Use `.tap()` instead of `.click()` for mobile
3. Check element is visible and not covered

## Resources

- [Playwright Mobile Emulation](https://playwright.dev/docs/emulation)
- [WCAG Touch Target Guidelines](https://www.w3.org/WAI/WCAG21/Understanding/target-size.html)
- [Web Vitals](https://web.dev/vitals/)
- [Mobile UX Best Practices](https://developers.google.com/web/fundamentals/design-and-ux/principles)

## Contact

For issues or questions about mobile testing:
- Check existing test failures in CI
- Review Playwright documentation
- Consult with frontend team
