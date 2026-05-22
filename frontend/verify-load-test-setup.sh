#!/bin/bash

# Verify Load Test Setup
# Checks that all files are in place and ready to run

echo "=========================================="
echo "Load Test Setup Verification"
echo "=========================================="
echo ""

ERRORS=0
WARNINGS=0

# Check files exist
echo "📁 Checking files..."

FILES=(
    "playwright.config.load.js"
    "run-load-tests.sh"
    "e2e/load/README.md"
    "e2e/load/concurrent-users.spec.js"
    "e2e/load/race-conditions.spec.js"
    "e2e/load/queue-management.spec.js"
    "e2e/load/helpers.js"
    "e2e/load/system-monitor.js"
    "e2e/load/analyzer.js"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ✗ $file (MISSING)"
        ((ERRORS++))
    fi
done

echo ""

# Check executables
echo "🔧 Checking executables..."

EXECUTABLES=(
    "run-load-tests.sh"
    "e2e/load/system-monitor.js"
    "e2e/load/analyzer.js"
)

for file in "${EXECUTABLES[@]}"; do
    if [ -x "$file" ]; then
        echo "  ✓ $file is executable"
    else
        echo "  ⚠ $file is not executable"
        ((WARNINGS++))
    fi
done

echo ""

# Check npm scripts
echo "📦 Checking npm scripts..."

if grep -q "test:load" package.json; then
    echo "  ✓ npm scripts configured"
else
    echo "  ✗ npm scripts missing"
    ((ERRORS++))
fi

echo ""

# Check dependencies
echo "📚 Checking dependencies..."

if [ -d "node_modules/@playwright/test" ]; then
    echo "  ✓ Playwright installed"
else
    echo "  ⚠ Playwright not installed (run: npm install)"
    ((WARNINGS++))
fi

if npx playwright --version > /dev/null 2>&1; then
    PLAYWRIGHT_VERSION=$(npx playwright --version)
    echo "  ✓ $PLAYWRIGHT_VERSION"
else
    echo "  ⚠ Playwright CLI not available"
    ((WARNINGS++))
fi

echo ""

# Check services
echo "🌐 Checking services..."

if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "  ✓ Backend is running (port 8000)"
else
    echo "  ⚠ Backend is not running (port 8000)"
    echo "    Start with: cd backend && python app.py"
    ((WARNINGS++))
fi

echo ""

# Summary
echo "=========================================="
echo "Summary"
echo "=========================================="

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "✅ All checks passed! Ready to run load tests."
    echo ""
    echo "Quick start:"
    echo "  ./run-load-tests.sh"
    echo ""
    echo "Or use npm:"
    echo "  npm run test:load"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo "⚠️  Setup complete with $WARNINGS warning(s)"
    echo "You can run tests, but some features may not work optimally."
    exit 0
else
    echo "❌ Setup incomplete: $ERRORS error(s), $WARNINGS warning(s)"
    echo "Please fix the errors before running tests."
    exit 1
fi
