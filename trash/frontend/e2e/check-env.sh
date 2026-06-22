#!/bin/bash
# Quick verification that the E2E test is ready to run

echo "🔍 E2E Test Environment Check"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Check if we're in the right directory
if [ ! -f "playwright.config.js" ]; then
    echo "❌ Not in frontend directory"
    echo "   Run: cd /home/sirobo/papergenerator/frontend"
    exit 1
fi

echo "✓ In frontend directory"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "❌ node_modules not found"
    echo "   Run: npm install"
    exit 1
fi

echo "✓ node_modules exists"

# Check if Playwright is installed
if [ ! -d "node_modules/@playwright" ]; then
    echo "❌ Playwright not installed"
    echo "   Run: npm install"
    exit 1
fi

echo "✓ Playwright installed"

# Check if test files exist
if [ ! -f "e2e/complete-workflow.spec.js" ]; then
    echo "❌ complete-workflow.spec.js not found"
    exit 1
fi

echo "✓ Test file exists"

# Check if helpers exist
if [ ! -f "e2e/helpers.js" ]; then
    echo "❌ helpers.js not found"
    exit 1
fi

echo "✓ Helper utilities exist"

# Check if runner script exists
if [ ! -x "e2e/run-workflow-test.sh" ]; then
    echo "❌ run-workflow-test.sh not found or not executable"
    exit 1
fi

echo "✓ Runner script ready"

# Check if server is running
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "✓ Server is running"
else
    echo "⚠️  Server is NOT running"
    echo "   Start with: cd /home/sirobo/papergenerator && ./server.sh"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Environment check complete!"
echo ""
echo "To run the test:"
echo "   ./e2e/run-workflow-test.sh"
echo ""
echo "Or manually:"
echo "   npx playwright test complete-workflow.spec.js --project=workflow-with-video"
echo ""
