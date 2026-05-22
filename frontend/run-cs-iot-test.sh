#!/bin/bash
# Run CS Student IoT Paper E2E Test
# This script runs the comprehensive E2E test for the CS student IoT smart home paper scenario

set -e

echo "=========================================="
echo "CS Student IoT Paper E2E Test"
echo "=========================================="
echo ""
echo "Test scenario: Complete paper generation flow"
echo "Persona: Mahasiswa Teknik Informatika semester 7"
echo "Topic: IoT Smart Home Automation"
echo "Timeout: 10 minutes max"
echo ""
echo "Prerequisites:"
echo "  - Backend server running on :8001"
echo "  - Frontend server running on :8000"
echo "  - Database accessible"
echo ""

# Check if servers are running
echo "Checking if servers are running..."
if ! curl -s http://localhost:8000 > /dev/null 2>&1; then
    echo "❌ Frontend server not running on :8000"
    echo "   Start with: npm run dev (in frontend/)"
    exit 1
fi

if ! curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "❌ Backend API not accessible via :8000/api"
    echo "   Make sure backend is running and proxied correctly"
    exit 1
fi

echo "✓ Servers are running"
echo ""

# Clean previous test results
echo "Cleaning previous test results..."
rm -rf test-results/cs-student/*.png
rm -rf test-results/cs-student/*.docx
rm -rf playwright-report/
echo "✓ Cleaned"
echo ""

# Run the test
echo "Starting test execution..."
echo "This will take up to 10 minutes..."
echo ""

START_TIME=$(date +%s)

# Run with the specific project configuration
npx playwright test --project=cs-student-iot --reporter=list,html,json

EXIT_CODE=$?
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "=========================================="
echo "Test Execution Complete"
echo "=========================================="
echo "Duration: ${DURATION}s"
echo "Exit code: ${EXIT_CODE}"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ TEST PASSED"
else
    echo "❌ TEST FAILED"
fi

echo ""
echo "Test artifacts:"
echo "  - Screenshots: test-results/cs-student/*.png"
echo "  - Exported paper: test-results/cs-student/*.docx"
echo "  - HTML report: playwright-report/index.html"
echo "  - JSON results: playwright-report/results.json"
echo ""

if [ -f playwright-report/index.html ]; then
    echo "To view the HTML report:"
    echo "  npx playwright show-report"
fi

echo ""

exit $EXIT_CODE
