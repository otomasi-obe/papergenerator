#!/bin/bash
# Quick script to run the beginner first-time experience test

set -e

echo "=========================================="
echo "Beginner User First-Time Experience Test"
echo "=========================================="
echo ""

# Check if services are running
echo "Checking if services are running..."
if ! curl -s http://localhost:8000 > /dev/null; then
    echo "❌ Frontend not running on http://localhost:8000"
    echo "   Start services with: ./server.sh or pm2 start ecosystem.config.cjs"
    exit 1
fi

if ! curl -s http://localhost:8001/api/health > /dev/null; then
    echo "❌ Backend not running on http://localhost:8001"
    echo "   Start services with: ./server.sh or pm2 start ecosystem.config.cjs"
    exit 1
fi

echo "✅ Services are running"
echo ""

# Navigate to frontend directory
cd "$(dirname "$0")/.."

# Run the test
echo "Running beginner first-time experience test..."
echo ""

if [ "$1" == "--ui" ]; then
    echo "Opening Playwright UI mode..."
    npm run test:e2e:ui -- beginner-first-time.spec.js
elif [ "$1" == "--headed" ]; then
    echo "Running in headed mode..."
    npx playwright test beginner-first-time.spec.js --headed
elif [ "$1" == "--debug" ]; then
    echo "Running in debug mode..."
    npx playwright test beginner-first-time.spec.js --debug
else
    npm run test:e2e -- beginner-first-time.spec.js
fi

echo ""
echo "=========================================="
echo "Test complete!"
echo ""
echo "View detailed report:"
echo "  npx playwright show-report"
echo ""
echo "Run with UI mode:"
echo "  $0 --ui"
echo "=========================================="
