#!/bin/bash
# Run Electrical Engineering Persona E2E Test
# Usage: ./run-ee-test.sh [options]
#
# Options:
#   --headed    Run in headed mode (show browser)
#   --debug     Run in debug mode (step-by-step)
#   --ui        Run in UI mode (interactive)
#   --report    Show HTML report after test

set -e

cd "$(dirname "$0")"

echo "🧪 Running Electrical Engineering Persona E2E Test"
echo "=================================================="
echo ""

# Check if backend is running
if ! curl -s http://localhost:8001/api/health > /dev/null 2>&1; then
    echo "❌ Backend is not running on http://localhost:8001"
    echo "   Please start the backend first:"
    echo "   cd .. && pm2 start ecosystem.config.cjs"
    exit 1
fi

# Check if frontend is running
if ! curl -s http://localhost:8000 > /dev/null 2>&1; then
    echo "❌ Frontend is not running on http://localhost:8000"
    echo "   Please start the frontend first:"
    echo "   cd frontend && npm run dev"
    exit 1
fi

echo "✅ Backend is running"
echo "✅ Frontend is running"
echo ""

# Parse arguments
MODE=""
SHOW_REPORT=false

for arg in "$@"; do
    case $arg in
        --headed)
            MODE="--headed"
            ;;
        --debug)
            MODE="--debug"
            ;;
        --ui)
            MODE="--ui"
            ;;
        --report)
            SHOW_REPORT=true
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Usage: $0 [--headed|--debug|--ui] [--report]"
            exit 1
            ;;
    esac
done

# Create test-results directory if it doesn't exist
mkdir -p test-results

echo "🚀 Starting test..."
echo ""

# Run the test
if [ -n "$MODE" ]; then
    npx playwright test e2e/electrical-engineering-persona.spec.js $MODE
else
    npx playwright test e2e/electrical-engineering-persona.spec.js
fi

TEST_EXIT_CODE=$?

echo ""
echo "=================================================="

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ Test completed successfully!"
    echo ""
    echo "📊 Test Artifacts:"
    echo "   - Screenshots: test-results/ee-*.png"
    echo "   - Exported paper: test-results/ee-paper-*.docx"
    echo "   - HTML report: playwright-report/index.html"
    echo ""
    
    # List generated artifacts
    if ls test-results/ee-*.png 1> /dev/null 2>&1; then
        echo "   Generated screenshots:"
        ls -lh test-results/ee-*.png | awk '{print "     - " $9 " (" $5 ")"}'
    fi
    
    if ls test-results/ee-paper-*.docx 1> /dev/null 2>&1; then
        echo "   Generated papers:"
        ls -lh test-results/ee-paper-*.docx | awk '{print "     - " $9 " (" $5 ")"}'
    fi
    
    if [ "$SHOW_REPORT" = true ]; then
        echo ""
        echo "📖 Opening HTML report..."
        npx playwright show-report
    else
        echo ""
        echo "💡 To view detailed HTML report, run:"
        echo "   npx playwright show-report"
    fi
else
    echo "❌ Test failed with exit code $TEST_EXIT_CODE"
    echo ""
    echo "🔍 Debugging tips:"
    echo "   1. Check screenshots in test-results/"
    echo "   2. View HTML report: npx playwright show-report"
    echo "   3. Run in headed mode: $0 --headed"
    echo "   4. Run in debug mode: $0 --debug"
    echo "   5. Check backend logs: pm2 logs backend"
fi

echo ""

exit $TEST_EXIT_CODE
