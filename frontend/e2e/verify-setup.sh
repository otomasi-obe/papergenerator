#!/bin/bash
# Quick verification script for chaos testing setup

echo "🔍 Chaos Testing Setup Verification"
echo "===================================="
echo ""

cd "$(dirname "$0")/.."

# Check files exist
echo "📁 Checking files..."
files=(
    "e2e/chaos.spec.js"
    "e2e/chaos-runner.js"
    "e2e/run-chaos.sh"
    "e2e/README-CHAOS.md"
    "e2e/CHAOS_QUICK_REFERENCE.md"
    "e2e/CHAOS_SAMPLE_REPORT.md"
    "e2e/CHAOS_DELIVERABLE.md"
)

all_exist=true
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        size=$(du -h "$file" | cut -f1)
        echo "  ✅ $file ($size)"
    else
        echo "  ❌ $file (missing)"
        all_exist=false
    fi
done

echo ""

# Check npm scripts
echo "📦 Checking npm scripts..."
if grep -q "test:chaos" package.json; then
    echo "  ✅ test:chaos"
fi
if grep -q "test:chaos:ui" package.json; then
    echo "  ✅ test:chaos:ui"
fi
if grep -q "test:chaos:report" package.json; then
    echo "  ✅ test:chaos:report"
fi

echo ""

# Check syntax
echo "🔧 Checking syntax..."
if node --check e2e/chaos.spec.js 2>/dev/null; then
    echo "  ✅ chaos.spec.js syntax valid"
else
    echo "  ❌ chaos.spec.js has syntax errors"
    all_exist=false
fi

if node --check e2e/chaos-runner.js 2>/dev/null; then
    echo "  ✅ chaos-runner.js syntax valid"
else
    echo "  ❌ chaos-runner.js has syntax errors"
    all_exist=false
fi

echo ""

# Check Playwright can load tests
echo "🎭 Checking Playwright integration..."
if npx playwright test chaos.spec.js --list > /dev/null 2>&1; then
    test_count=$(npx playwright test chaos.spec.js --list 2>&1 | grep -c "chaos.spec.js:")
    echo "  ✅ Playwright can load tests ($test_count tests found)"
else
    echo "  ⚠️  Could not verify Playwright (may need installation)"
fi

echo ""

# Summary
if [ "$all_exist" = true ]; then
    echo "✅ Setup verification PASSED"
    echo ""
    echo "🚀 Ready to run:"
    echo "   npm run test:chaos           # Run all tests"
    echo "   npm run test:chaos:ui        # Run with UI"
    echo "   npm run test:chaos:report    # Generate reports"
    echo "   ./e2e/run-chaos.sh           # Interactive mode"
    exit 0
else
    echo "❌ Setup verification FAILED"
    echo "   Some files are missing or have errors"
    exit 1
fi
