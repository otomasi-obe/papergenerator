#!/bin/bash
# Quick Reference: CS Student IoT E2E Test

cat << 'EOF'

╔═══════════════════════════════════════════════════════════════════╗
║          CS STUDENT IOT E2E TEST - QUICK REFERENCE                ║
╚═══════════════════════════════════════════════════════════════════╝

📍 LOCATION:
   frontend/e2e/cs-student-iot.spec.js

🎯 PURPOSE:
   Test complete paper generation flow for CS student thesis on IoT

⏱️  DURATION:
   5-10 minutes (max 10 minutes timeout)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 RUN COMMANDS:

   # Recommended (with checks)
   cd frontend && ./run-cs-iot-test.sh

   # Direct Playwright
   cd frontend && npx playwright test --project=cs-student-iot

   # With UI (debugging)
   cd frontend && npx playwright test cs-student-iot.spec.js --ui

   # Headed mode (see browser)
   cd frontend && npx playwright test cs-student-iot.spec.js --headed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ PRE-FLIGHT CHECKLIST:

   [ ] Backend running on :8001
   [ ] Frontend running on :8000
   [ ] Database accessible
   [ ] Playwright installed (npx playwright install chromium)
   [ ] Disk space >500MB (for videos/traces)

   Quick check:
   curl http://localhost:8000/api/health

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 EXPECTED OUTPUT:

   test-results/cs-student/
   ├── 18 screenshots (.png)
   └── 1 exported paper (.docx)

   playwright-report/
   ├── index.html (interactive report)
   ├── results.json (machine-readable)
   └── trace.zip (execution trace)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 VIEW RESULTS:

   # HTML report
   npx playwright show-report

   # Trace viewer
   npx playwright show-trace playwright-report/trace.zip

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 TROUBLESHOOTING:

   Test timeout?
   → Check backend/AI service response times
   → Increase timeout in playwright.config.js

   SLR not completing?
   → Check backend logs: pm2 logs backend
   → Verify API keys for Semantic Scholar

   Paper generation fails?
   → Check AI service API keys
   → Verify rate limits

   Screenshots missing?
   → mkdir -p frontend/test-results/cs-student
   → Check disk space

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📚 DOCUMENTATION:

   Detailed:  frontend/e2e/README-CS-IOT-TEST.md
   Summary:   CS_STUDENT_IOT_TEST_SUMMARY.md
   Config:    frontend/playwright.config.js

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EOF
