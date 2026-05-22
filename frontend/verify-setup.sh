#!/bin/bash
# Verify E2E Test Setup
# Checks all prerequisites and dependencies for running the EE persona test

echo "🔍 Verifying E2E Test Setup for Electrical Engineering Persona"
echo "=============================================================="
echo ""

ERRORS=0
WARNINGS=0

# Check if we're in the right directory
if [ ! -f "playwright.config.js" ]; then
    echo "❌ Error: Not in frontend directory"
    echo "   Please run: cd /home/sirobo/papergenerator/frontend"
    exit 1
fi

echo "✅ In correct directory (frontend/)"
echo ""

# Check Node.js
echo "📦 Checking Node.js..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo "   ✅ Node.js installed: $NODE_VERSION"
else
    echo "   ❌ Node.js not found"
    ERRORS=$((ERRORS + 1))
fi

# Check npm
if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm --version)
    echo "   ✅ npm installed: $NPM_VERSION"
else
    echo "   ❌ npm not found"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check Playwright
echo "🎭 Checking Playwright..."
if [ -d "node_modules/@playwright" ]; then
    echo "   ✅ Playwright installed"
    PW_VERSION=$(npx playwright --version 2>/dev/null || echo "unknown")
    echo "   ✅ Version: $PW_VERSION"
else
    echo "   ❌ Playwright not installed"
    echo "   Run: npm install"
    ERRORS=$((ERRORS + 1))
fi

# Check if Chromium is installed
if npx playwright list-files chromium &> /dev/null; then
    echo "   ✅ Chromium browser installed"
else
    echo "   ⚠️  Chromium browser not installed"
    echo "   Run: npx playwright install chromium"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# Check test file exists
echo "📄 Checking test files..."
if [ -f "e2e/electrical-engineering-persona.spec.js" ]; then
    LINES=$(wc -l < e2e/electrical-engineering-persona.spec.js)
    echo "   ✅ Test file exists: electrical-engineering-persona.spec.js ($LINES lines)"
else
    echo "   ❌ Test file not found: e2e/electrical-engineering-persona.spec.js"
    ERRORS=$((ERRORS + 1))
fi

if [ -f "e2e/TEST_PLAN.md" ]; then
    echo "   ✅ Test plan exists: TEST_PLAN.md"
else
    echo "   ⚠️  Test plan not found: TEST_PLAN.md"
    WARNINGS=$((WARNINGS + 1))
fi

if [ -f "run-ee-test.sh" ]; then
    echo "   ✅ Helper script exists: run-ee-test.sh"
    if [ -x "run-ee-test.sh" ]; then
        echo "   ✅ Script is executable"
    else
        echo "   ⚠️  Script not executable (run: chmod +x run-ee-test.sh)"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo "   ⚠️  Helper script not found: run-ee-test.sh"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# Check backend
echo "🔌 Checking backend..."
if curl -s http://localhost:8001/api/health > /dev/null 2>&1; then
    echo "   ✅ Backend is running on http://localhost:8001"
    HEALTH=$(curl -s http://localhost:8001/api/health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    echo "   ✅ Health status: $HEALTH"
else
    echo "   ❌ Backend is NOT running on http://localhost:8001"
    echo "   Start with: pm2 start ecosystem.config.cjs"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check frontend
echo "🌐 Checking frontend..."
if curl -s http://localhost:8000 > /dev/null 2>&1; then
    echo "   ✅ Frontend is running on http://localhost:8000"
else
    echo "   ❌ Frontend is NOT running on http://localhost:8000"
    echo "   Start with: npm run dev"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check directories
echo "📁 Checking directories..."
if [ -d "test-results" ]; then
    echo "   ✅ test-results/ directory exists"
else
    echo "   ⚠️  test-results/ directory not found (will be created automatically)"
    WARNINGS=$((WARNINGS + 1))
fi

if [ -d "playwright-report" ]; then
    echo "   ✅ playwright-report/ directory exists"
else
    echo "   ⚠️  playwright-report/ directory not found (will be created automatically)"
    WARNINGS=$((WARNINGS + 1))
fi
echo ""

# Summary
echo "=============================================================="
echo "📊 Verification Summary"
echo "=============================================================="

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "✅ All checks passed! Ready to run tests."
    echo ""
    echo "🚀 Run the test with:"
    echo "   ./run-ee-test.sh"
    echo ""
    echo "Or with options:"
    echo "   ./run-ee-test.sh --ui       # Interactive mode"
    echo "   ./run-ee-test.sh --headed   # See browser"
    echo "   ./run-ee-test.sh --debug    # Step-by-step"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo "⚠️  Setup complete with $WARNINGS warning(s)"
    echo "   Tests should run, but some features may not work optimally"
    echo ""
    echo "🚀 You can still run the test with:"
    echo "   ./run-ee-test.sh"
    exit 0
else
    echo "❌ Setup incomplete: $ERRORS error(s), $WARNINGS warning(s)"
    echo ""
    echo "🔧 Fix the errors above before running tests"
    echo ""
    echo "Common fixes:"
    echo "   - Install dependencies: npm install"
    echo "   - Install browsers: npx playwright install chromium"
    echo "   - Start backend: pm2 start ecosystem.config.cjs"
    echo "   - Start frontend: npm run dev"
    exit 1
fi
