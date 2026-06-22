#!/bin/bash
# Quick Start Script for Playwright MCP Tests
# This script starts the application and prepares for test execution

set -e

echo "=========================================="
echo "Playwright MCP Test Quick Start"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "backend/tests/test_playwright_paper_generation.py" ]; then
    echo -e "${RED}Error: Must run from project root directory${NC}"
    exit 1
fi

echo "Step 1: Checking prerequisites..."
echo "-----------------------------------"

# Check Python
if command -v python3 &> /dev/null; then
    echo -e "${GREEN}✓${NC} Python3 found: $(python3 --version)"
else
    echo -e "${RED}✗${NC} Python3 not found"
    exit 1
fi

# Check Node
if command -v node &> /dev/null; then
    echo -e "${GREEN}✓${NC} Node found: $(node --version)"
else
    echo -e "${RED}✗${NC} Node not found"
    exit 1
fi

# Check if backend dependencies are installed
if [ -d ".venv" ]; then
    echo -e "${GREEN}✓${NC} Python virtual environment found"
else
    echo -e "${YELLOW}!${NC} Virtual environment not found, creating..."
    python3 -m venv .venv
fi

# Check if frontend dependencies are installed
if [ -d "frontend/node_modules" ]; then
    echo -e "${GREEN}✓${NC} Frontend dependencies found"
else
    echo -e "${YELLOW}!${NC} Frontend dependencies not found"
    echo "Run: cd frontend && npm install"
fi

echo ""
echo "Step 2: Starting application..."
echo "-----------------------------------"

# Check if already running
if curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Frontend already running on http://localhost:5173"
else
    echo -e "${YELLOW}!${NC} Frontend not running"
    echo "To start frontend: cd frontend && npm run dev"
fi

if curl -s http://localhost:5000/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Backend already running on http://localhost:5000"
else
    echo -e "${YELLOW}!${NC} Backend not running"
    echo "To start backend: cd backend && python app.py"
fi

echo ""
echo "Step 3: Test execution options..."
echo "-----------------------------------"
echo ""
echo "Option A: Run all tests"
echo "  pytest backend/tests/test_playwright_paper_generation.py -v"
echo ""
echo "Option B: Run specific test"
echo "  pytest backend/tests/test_playwright_paper_generation.py::test_beginner_user_workflow -v"
echo ""
echo "Option C: Run with AI agent (recommended)"
echo "  The AI agent will read test scenarios and execute using Playwright MCP tools"
echo ""
echo "Option D: Export test scenarios"
echo "  python backend/tests/playwright_mcp_runner.py"
echo ""

echo "=========================================="
echo "Test Scenarios Available:"
echo "=========================================="
echo "1. Beginner User Workflow"
echo "   - Tests step-by-step guided interaction"
echo "   - User starts confused, AI guides through process"
echo ""
echo "2. Intermediate User Workflow"
echo "   - Tests partial information handling"
echo "   - User provides some details, AI fills gaps"
echo ""
echo "3. Advanced User Workflow"
echo "   - Tests comprehensive information fast-track"
echo "   - User provides all details, minimal interaction"
echo ""
echo "4. Hybrid Literature Workflow"
echo "   - Tests file upload + AI paper discovery"
echo "   - Combines user files with AI-found papers"
echo ""
echo "5. Error Handling"
echo "   - Tests edge cases and error recovery"
echo ""
echo "6. Concurrent Users"
echo "   - Tests multiple simultaneous generations"
echo ""

echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo "1. Ensure both frontend and backend are running"
echo "2. Create test user account if needed"
echo "3. Run tests using one of the options above"
echo "4. Check test results and logs"
echo ""
echo "For detailed documentation, see:"
echo "  backend/tests/README_PLAYWRIGHT_TESTS.md"
echo ""
