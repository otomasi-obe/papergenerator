#!/bin/bash
# Run comprehensive chat E2E tests
# Usage: bash run-chat-tests.sh

set -e

cd "$(dirname "$0")"

echo "╔══════════════════════════════════════════════╗"
echo "║  Chat Comprehensive E2E Test Runner          ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Ensure test results dir
mkdir -p test-results/chat-comprehensive

# Check server
echo "Checking server health..."
HEALTH=$(curl -s http://localhost:8000/api/health 2>/dev/null || echo '{"status":"unreachable"}')
echo "  $HEALTH"
echo ""

# Run tests
echo "Running tests..."
npx playwright test e2e/chat-comprehensive.spec.js \
  --project=workflow-with-video \
  --reporter=list,html \
  --output=test-results/chat-comprehensive \
  2>&1

echo ""
echo "Screenshots saved to: test-results/chat-comprehensive/"
echo "HTML report: playwright-report/"
