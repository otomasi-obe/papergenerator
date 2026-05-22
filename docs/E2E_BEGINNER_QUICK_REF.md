# Beginner User E2E Test - Quick Reference

## 🚀 Quick Start

```bash
# 1. Ensure services are running
pm2 list  # or ./server.sh

# 2. Run the test
cd frontend
npm run test:e2e -- beginner-first-time.spec.js

# 3. View results
npx playwright show-report
```

## 📋 Test Checklist

### Pre-Test
- [ ] Backend running on http://localhost:8001
- [ ] Frontend running on http://localhost:8000
- [ ] Database initialized and healthy
- [ ] No other tests running (sequential execution)

### What Gets Tested
- [ ] Landing page loads with clear CTA
- [ ] Registration flow works smoothly
- [ ] Onboarding guides new users
- [ ] AI provides helpful suggestions
- [ ] Error messages are clear and actionable
- [ ] Help/documentation is accessible
- [ ] User can create first paper successfully
- [ ] Time to first paper < 2 minutes

### Post-Test
- [ ] Review console output for UX issues
- [ ] Check timing metrics
- [ ] View screenshots/videos if test failed
- [ ] Update baseline metrics if needed

## 🎯 Success Criteria

| Metric | Target | Status |
|--------|--------|--------|
| Time to first paper | < 120s | ⏱️ |
| UX issues | < 5 | 🔍 |
| Landing page load | < 3s | ⚡ |
| All flows complete | 100% | ✅ |

## 🔧 Common Commands

```bash
# Run with UI (interactive debugging)
npm run test:e2e:ui -- beginner-first-time.spec.js

# Run in headed mode (see browser)
npx playwright test beginner-first-time.spec.js --headed

# Run specific test case
npm run test:e2e -- beginner-first-time.spec.js -g "complete first-time"

# Debug mode
npx playwright test beginner-first-time.spec.js --debug

# Generate report
npx playwright show-report
```

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection refused | Start services: `pm2 start ecosystem.config.cjs` |
| Timeout exceeded | Check backend logs: `pm2 logs backend` |
| Test fails randomly | Run with `--headed` to see what's happening |
| UX issues found | Review console output, fix issues, re-run |

## 📊 Interpreting Results

### ✅ Excellent (0-2 issues)
- Smooth onboarding
- Clear guidance
- Fast completion
- **Action:** Maintain quality

### ⚠️ Needs Work (3-5 issues)
- Some friction points
- Missing guidance
- Unclear errors
- **Action:** Prioritize top 3 issues

### ❌ Critical (6+ issues)
- Major UX problems
- Broken flows
- Poor guidance
- **Action:** Immediate fixes needed

## 📁 Files Created

```
frontend/e2e/
├── beginner-first-time.spec.js    # Main test file
├── run-beginner-test.sh           # Helper script
└── README.md                      # E2E tests documentation

docs/
└── E2E_BEGINNER_TEST.md          # Detailed documentation
```

## 🔄 Workflow

```
1. Make UI changes
   ↓
2. Run beginner test
   ↓
3. Review UX issues
   ↓
4. Fix issues
   ↓
5. Re-run test
   ↓
6. Commit when passing
```

## 📈 Tracking Improvements

Create a baseline:
```bash
# First run - establish baseline
npm run test:e2e -- beginner-first-time.spec.js > baseline.txt

# After improvements
npm run test:e2e -- beginner-first-time.spec.js > improved.txt

# Compare
diff baseline.txt improved.txt
```

## 🎓 Test Scenarios Covered

1. **Happy Path:** Landing → Register → Create Paper → Success
2. **Error Recovery:** Invalid input → Error → Correction → Success  
3. **Cancel Flow:** Start creation → Cancel → Return to dashboard
4. **Guidance Test:** Vague input → AI suggestions → Clarification
5. **Help Access:** Find help → Access documentation → Continue

## 💡 Tips

- Run in UI mode first to understand the flow
- Use headed mode to debug visual issues
- Check screenshots in `test-results/` on failure
- Review timing metrics to identify bottlenecks
- Compare results over time to track improvements

## 📞 Support

- Full documentation: `docs/E2E_BEGINNER_TEST.md`
- E2E README: `frontend/e2e/README.md`
- Playwright docs: https://playwright.dev
