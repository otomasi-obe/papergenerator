#!/bin/bash

# Load Test Runner Script
# Runs comprehensive load tests with system monitoring

set -e

echo "=========================================="
echo "PaperFull Load Testing Suite"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if services are running
echo "🔍 Checking if services are running..."

if ! curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo -e "${RED}❌ Backend is not running on port 8000${NC}"
    echo "Please start the backend first:"
    echo "  cd backend && source .venv/bin/activate && python app.py"
    exit 1
fi

if ! curl -s http://localhost:8000 > /dev/null 2>&1; then
    echo -e "${RED}❌ Frontend is not accessible on port 8000${NC}"
    echo "Please make sure the frontend is being served"
    exit 1
fi

echo -e "${GREEN}✓ Services are running${NC}"
echo ""

# Check if Playwright is installed
if ! npx playwright --version > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Playwright not found. Installing...${NC}"
    npm install
    npx playwright install chromium
fi

echo "=========================================="
echo "Test Configuration"
echo "=========================================="
echo "Workers: 10 concurrent users"
echo "Base URL: http://localhost:8000"
echo "Timeout: 300s per test"
echo ""

# Ask which tests to run
echo "Select test suite to run:"
echo "1) All tests (concurrent users + race conditions + queue management)"
echo "2) Concurrent users only"
echo "3) Race conditions only"
echo "4) Queue management only"
echo "5) Custom selection"
read -p "Enter choice [1-5]: " choice

TEST_PATTERN=""
case $choice in
    1)
        TEST_PATTERN="e2e/load/*.spec.js"
        ;;
    2)
        TEST_PATTERN="e2e/load/concurrent-users.spec.js"
        ;;
    3)
        TEST_PATTERN="e2e/load/race-conditions.spec.js"
        ;;
    4)
        TEST_PATTERN="e2e/load/queue-management.spec.js"
        ;;
    5)
        echo "Available test files:"
        echo "  - concurrent-users.spec.js"
        echo "  - race-conditions.spec.js"
        echo "  - queue-management.spec.js"
        read -p "Enter test file name: " custom_test
        TEST_PATTERN="e2e/load/${custom_test}"
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "Starting Load Tests"
echo "=========================================="
echo ""

# Start system monitor in background
echo "📊 Starting system resource monitor..."
node e2e/load/system-monitor.js > system-monitor.log 2>&1 &
MONITOR_PID=$!
echo "Monitor PID: $MONITOR_PID"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Stopping system monitor..."
    kill -INT $MONITOR_PID 2>/dev/null || true
    wait $MONITOR_PID 2>/dev/null || true
    echo ""
}

trap cleanup EXIT INT TERM

# Run the tests
echo "🚀 Running load tests..."
echo ""

if npx playwright test --config=playwright.config.load.js $TEST_PATTERN; then
    TEST_STATUS="PASSED"
    echo -e "${GREEN}✓ Tests completed successfully${NC}"
else
    TEST_STATUS="FAILED"
    echo -e "${RED}✗ Some tests failed${NC}"
fi

echo ""
echo "=========================================="
echo "Generating Reports"
echo "=========================================="
echo ""

# Stop monitor and generate report
kill -INT $MONITOR_PID 2>/dev/null || true
wait $MONITOR_PID 2>/dev/null || true

# Analyze results
if [ -f "load-test-results.json" ]; then
    echo "📈 Analyzing test results..."
    node e2e/load/analyzer.js
else
    echo -e "${YELLOW}⚠ No results file found${NC}"
fi

echo ""
echo "=========================================="
echo "Test Artifacts"
echo "=========================================="
echo "HTML Report: playwright-report-load/index.html"
echo "JSON Results: load-test-results.json"
echo "System Monitor: system-monitor-report.json"
echo "System Log: system-monitor.log"
echo ""
echo "To view HTML report:"
echo "  npx playwright show-report playwright-report-load"
echo ""

if [ "$TEST_STATUS" = "FAILED" ]; then
    exit 1
fi
