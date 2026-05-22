#!/bin/bash
# Run the complete workflow E2E test with video recording
# 
# Usage:
#   ./e2e/run-workflow-test.sh
#
# Prerequisites:
#   - PM2 server running (frontend on :8000, backend on :8001)
#   - Database initialized
#   - Playwright installed (npm install)

set -e

echo "🎬 Complete Workflow E2E Test Runner"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Check if server is running
if ! curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "❌ Server is not running on http://localhost:8000"
    echo "   Please start the server first:"
    echo "   cd /home/sirobo/papergenerator && ./server.sh"
    exit 1
fi

echo "✓ Server is running"
echo ""

# Create test data directory
TEST_DATA_DIR="/tmp/kilo/test-pdfs"
mkdir -p "$TEST_DATA_DIR"

# Create sample PDF files for testing
echo "📁 Creating sample PDF files..."
for i in 1 2 3; do
    cat > "$TEST_DATA_DIR/paper$i.pdf" << 'EOF'
%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 100 >>
stream
BT
/F1 12 Tf
100 700 Td
(Machine Learning in Healthcare - Test Paper) Tj
0 -20 Td
(This is a sample research paper for testing.) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
468
%%EOF
EOF
done

echo "✓ Created 3 sample PDF files in $TEST_DATA_DIR"
echo ""

# Run the test
echo "🧪 Running complete workflow test..."
echo "   This will take 3-10 minutes depending on AI generation speed"
echo ""

cd "$(dirname "$0")/.."

npx playwright test complete-workflow.spec.js --project=workflow-with-video

TEST_EXIT_CODE=$?

echo ""
echo "═══════════════════════════════════════════════════════════"

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ Test completed successfully!"
    echo ""
    echo "📊 Results:"
    echo "   - HTML Report: frontend/playwright-report/index.html"
    echo "   - Video: frontend/test-results/*/video.webm"
    echo "   - Trace: frontend/test-results/*/trace.zip"
    echo ""
    echo "To view the report:"
    echo "   cd frontend && npx playwright show-report"
else
    echo "❌ Test failed with exit code $TEST_EXIT_CODE"
    echo ""
    echo "📊 Debug artifacts:"
    echo "   - HTML Report: frontend/playwright-report/index.html"
    echo "   - Screenshots: frontend/test-results/*/test-failed-*.png"
    echo "   - Video: frontend/test-results/*/video.webm"
    echo "   - Trace: frontend/test-results/*/trace.zip"
    echo ""
    echo "To view the report:"
    echo "   cd frontend && npx playwright show-report"
fi

echo "═══════════════════════════════════════════════════════════"

exit $TEST_EXIT_CODE
