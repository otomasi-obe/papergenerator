#!/bin/bash
# Complete Workflow E2E Test - Quick Start Guide
# Run this to see all available commands and options

cat << 'EOF'

╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   📋 PLAYWRIGHT E2E TEST - COMPLETE WORKFLOW                  ║
║   End-to-End Test: Paper Generation Happy Path               ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

📁 PROJECT STRUCTURE
═══════════════════════════════════════════════════════════════

frontend/
├── e2e/
│   ├── complete-workflow.spec.js    ⭐ Main test (13 phases)
│   ├── helpers.js                   🛠️  Utility functions
│   ├── run-workflow-test.sh         🚀 Test runner script
│   ├── check-env.sh                 ✅ Environment checker
│   ├── README.md                    📖 Full documentation
│   ├── auth.spec.js                 🔐 Auth tests
│   └── smoke.spec.js                💨 Smoke tests
├── playwright.config.js             ⚙️  Playwright config
└── package.json                     📦 Dependencies

Root/
└── PLAYWRIGHT_E2E_DELIVERY.md       📊 Delivery summary


🎯 WHAT WAS DELIVERED
═══════════════════════════════════════════════════════════════

✅ Complete Workflow Test (23KB)
   - 13 workflow phases from registration to export
   - Metrics tracking (time, clicks, AI interactions)
   - Paper quality verification
   - Video recording (always on)
   - Detailed console logging

✅ Test Helpers (8.2KB)
   - Reusable utility functions
   - Metrics tracker
   - Quality verification
   - CSRF handling
   - Wait helpers

✅ Test Runner Script (3.3KB)
   - Server health check
   - Sample PDF creation
   - Test execution
   - Results summary

✅ Documentation (7.7KB)
   - Complete usage guide
   - Troubleshooting
   - Performance benchmarks
   - Best practices

✅ Updated Playwright Config
   - Extended timeout (10 minutes)
   - Dedicated workflow-with-video project
   - Always-on video recording


🚀 QUICK START
═══════════════════════════════════════════════════════════════

1️⃣  Check Environment
    cd /home/sirobo/papergenerator/frontend
    ./e2e/check-env.sh

2️⃣  Start Server (if not running)
    cd /home/sirobo/papergenerator
    ./server.sh

3️⃣  Run the Test
    cd /home/sirobo/papergenerator/frontend
    ./e2e/run-workflow-test.sh

4️⃣  View Results
    npx playwright show-report


📋 ALTERNATIVE RUN METHODS
═══════════════════════════════════════════════════════════════

# Method 1: Using the runner script (recommended)
./e2e/run-workflow-test.sh

# Method 2: Direct Playwright command
npx playwright test complete-workflow.spec.js --project=workflow-with-video

# Method 3: With UI mode (interactive)
npx playwright test complete-workflow.spec.js --ui

# Method 4: With debug mode
npx playwright test complete-workflow.spec.js --debug

# Method 5: Run all E2E tests
npm run test:e2e


📊 WHAT THE TEST DOES
═══════════════════════════════════════════════════════════════

Phase 1:  🔐 Registration & Login
Phase 2:  📝 Create New Paper
Phase 3:  💬 Discovery Questions (AI Chat)
Phase 4:  📁 File Upload (3 PDFs)
Phase 5:  🔬 Request SLR Execution
Phase 6:  📄 Request Paper Generation
Phase 7:  ⏳ Wait for Generation (monitor progress)
Phase 8:  👀 Review Generated Paper
Phase 9:  ✏️  Edit Sections (2-3 edits)
Phase 10: 📚 Add Custom References
Phase 11: 📊 Generate Charts/Figures
Phase 12: 👁️  Preview Paper
Phase 13: 💾 Export to DOCX & Download


📈 METRICS TRACKED
═══════════════════════════════════════════════════════════════

⏱️  Total Time          - From start to download
🖱️  Clicks              - Number of user interactions
🤖 AI Interactions     - Chat messages sent
📁 Files Uploaded      - PDF uploads
✏️  Sections Edited     - Manual edits made
📚 References Added    - Custom citations
📊 Charts Generated    - AI-generated figures


✅ QUALITY CHECKS
═══════════════════════════════════════════════════════════════

✓ Title present and meaningful (>10 chars)
✓ Abstract present and substantial (>50 chars)
✓ Keywords present
✓ Sections present
✓ No placeholder text
✓ Proper academic language


🎬 VIDEO RECORDING
═══════════════════════════════════════════════════════════════

The test ALWAYS records video for:
- User experience analysis
- Bug reproduction
- Workflow optimization
- Demo purposes

Video Location: frontend/test-results/*/video.webm
Video Format:   WebM
Duration:       3-10 minutes (depending on AI speed)


📊 EXPECTED RESULTS
═══════════════════════════════════════════════════════════════

Timing Benchmarks:
  ⚡ Fast:    < 3 minutes  (excellent)
  ✅ Normal:  3-5 minutes  (good)
  ⚠️  Slow:    5-10 minutes (acceptable)
  ❌ Timeout: > 10 minutes (investigate)

Typical Metrics:
  Clicks:            20-30
  AI Interactions:   5-8
  Files Uploaded:    3
  Sections Edited:   2-3
  References Added:  1-2
  Charts Generated:  1


🔍 VIEWING RESULTS
═══════════════════════════════════════════════════════════════

# Open HTML report (interactive)
npx playwright show-report

# View video
vlc test-results/*/video.webm
# or
open test-results/*/video.webm

# View trace (detailed timeline)
npx playwright show-trace test-results/*/trace.zip

# Check console output
cat test-results/*/stdout.txt


🛠️  TROUBLESHOOTING
═══════════════════════════════════════════════════════════════

Problem: Server not running
Solution: cd /home/sirobo/papergenerator && ./server.sh

Problem: Test timeout
Solution: Check AI generation, review backend logs

Problem: File upload fails
Solution: Run ./e2e/run-workflow-test.sh (creates sample PDFs)

Problem: Video not recording
Solution: Use --project=workflow-with-video flag


📚 DOCUMENTATION
═══════════════════════════════════════════════════════════════

Full Documentation:
  frontend/e2e/README.md

Delivery Summary:
  PLAYWRIGHT_E2E_DELIVERY.md

Test Code:
  frontend/e2e/complete-workflow.spec.js

Helpers:
  frontend/e2e/helpers.js


🎯 SUCCESS CRITERIA
═══════════════════════════════════════════════════════════════

✅ All 13 phases completed
✅ Paper generated with all sections
✅ DOCX file downloaded
✅ No placeholder text
✅ Quality checks passed
✅ Video recorded
✅ Metrics collected


📞 SUPPORT
═══════════════════════════════════════════════════════════════

Issues? Check:
1. Test output and console logs
2. Video recording
3. Trace files
4. Backend logs
5. Report with video evidence


═══════════════════════════════════════════════════════════════
✅ Ready to run! Execute: ./e2e/run-workflow-test.sh
═══════════════════════════════════════════════════════════════

EOF
