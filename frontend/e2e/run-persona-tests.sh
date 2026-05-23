#!/bin/bash

# Run all E2E persona tests
# Usage: ./run-persona-tests.sh [options]
# Options:
#   --headed    Run in headed mode (show browser)
#   --ui        Run in UI mode (interactive)
#   --debug     Run in debug mode
#   --report    Show report after tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "E2E Persona Tests - PaperFull"
echo "=========================================="
echo ""

MODE=""
SHOW_REPORT=false

for arg in "$@"; do
  case $arg in
    --headed)
      MODE="--headed"
      ;;
    --ui)
      MODE="--ui"
      ;;
    --debug)
      MODE="--debug"
      ;;
    --report)
      SHOW_REPORT=true
      ;;
  esac
done

echo "Checking prerequisites..."

if ! command -v npx &> /dev/null; then
    echo "❌ npx not found. Please install Node.js"
    exit 1
fi

if ! curl -s http://localhost:8000 > /dev/null; then
    echo "❌ Frontend not running on http://localhost:8000"
    echo "   Start with: npm run dev"
    exit 1
fi

if ! curl -s http://localhost:8001/api/health > /dev/null; then
    echo "❌ Backend not running on http://localhost:8001"
    echo "   Start with: python app.py or pm2 start"
    exit 1
fi

echo "✓ Prerequisites OK"
echo ""

mkdir -p test-results/medical-student
mkdir -p test-results/engineering-student
mkdir -p test-results/business-student
mkdir -p test-results/concurrent-users

echo "=========================================="
echo "Test 1/4: Medical Student"
echo "=========================================="
npx playwright test test-medical-student.spec.js $MODE
echo ""

echo "=========================================="
echo "Test 2/4: Engineering Student"
echo "=========================================="
npx playwright test test-engineering-student.spec.js $MODE
echo ""

echo "=========================================="
echo "Test 3/4: Business Student"
echo "=========================================="
npx playwright test test-business-student.spec.js $MODE
echo ""

echo "=========================================="
echo "Test 4/4: Concurrent Users"
echo "=========================================="
npx playwright test test-concurrent-users.spec.js $MODE
echo ""

echo "=========================================="
echo "All Tests Complete!"
echo "=========================================="
echo ""
echo "Results:"
echo "  - Screenshots: test-results/*/*.png"
echo "  - Exported papers: test-results/*/*.docx"
echo "  - HTML report: playwright-report/index.html"
echo ""

if [ "$SHOW_REPORT" = true ]; then
    echo "Opening HTML report..."
    npx playwright show-report
fi

echo "To view report: npx playwright show-report"
echo ""
