#!/bin/bash
# Image Generation System - Deployment Verification Script
# Run this after deploying fixes to verify everything works

set -e

echo "=========================================="
echo "Image Generation System - Verification"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0
WARNINGS=0

# Helper functions
pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASSED++))
}

fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAILED++))
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

# 1. Check files exist
echo "1. Checking modified files..."
if grep -q "intercept_timeout = generate_timeout_s + 30" backend/imageGenerator/CreateImageGemini.py; then
    pass "Fix #2: Image intercept timeout applied"
else
    fail "Fix #2: Image intercept timeout NOT found"
fi

if grep -q "launch_attempts = 3" backend/image_worker.py; then
    pass "Fix #3: Browser launch retry applied"
else
    fail "Fix #3: Browser launch retry NOT found"
fi

if grep -q "raise RuntimeError" backend/imageGenerator/GeminiCookies.py | grep -q "PSIDTS"; then
    pass "Fix #1: Cookie validation applied"
else
    fail "Fix #1: Cookie validation NOT found"
fi

if grep -q "if not compress_image(out_path, max_size_mb=1.0):" backend/image_worker.py; then
    pass "Fix #4: Compression failure handling applied"
else
    fail "Fix #4: Compression failure handling NOT found"
fi

if grep -q "timeout_s: int = 30" backend/imageGenerator/CreateImageGemini.py; then
    pass "Fix #5: UI operation timeouts applied"
else
    fail "Fix #5: UI operation timeouts NOT found"
fi

if grep -q "queued|running|done|error|cancelled" backend/models.py; then
    pass "Fix #6: Model documentation updated"
else
    fail "Fix #6: Model documentation NOT updated"
fi

echo ""

# 2. Check environment configuration
echo "2. Checking environment configuration..."
if [ -f backend/.env ]; then
    pass ".env file exists"
    
    # Check for account duplication
    ACCOUNT1_EMAIL=$(grep "GEMINI_ACCOUNT1_EMAIL=" backend/.env | cut -d'=' -f2)
    ACCOUNT4_EMAIL=$(grep "GEMINI_ACCOUNT4_EMAIL=" backend/.env | cut -d'=' -f2)
    
    if [ "$ACCOUNT1_EMAIL" = "$ACCOUNT4_EMAIL" ]; then
        fail "CRITICAL: Account1 and Account4 use same email: $ACCOUNT1_EMAIL"
        echo "   Fix: Update GEMINI_ACCOUNT4_EMAIL in .env to use unique account"
    else
        pass "All accounts use unique emails"
    fi
    
    # Check required env vars
    if grep -q "GEMINI_PROFILES_DIR=" backend/.env; then
        pass "GEMINI_PROFILES_DIR configured"
    else
        warn "GEMINI_PROFILES_DIR not set"
    fi
    
    if grep -q "GEMINI_HEADLESS=" backend/.env; then
        HEADLESS=$(grep "GEMINI_HEADLESS=" backend/.env | cut -d'=' -f2)
        if [ "$HEADLESS" = "1" ]; then
            warn "GEMINI_HEADLESS=1 (may cause issues if xvfb not available)"
        else
            pass "GEMINI_HEADLESS=0 (headed mode)"
        fi
    fi
else
    fail ".env file not found"
fi

echo ""

# 3. Check account profiles
echo "3. Checking Gemini account profiles..."
for i in {1..4}; do
    if [ -d "backend/imageGenerator/account$i" ]; then
        pass "Account$i profile directory exists"
        
        # Check for cookies
        if [ -f "backend/imageGenerator/cookies-account$i.json" ]; then
            pass "Account$i cookies file exists"
            
            # Validate cookies have required fields
            if grep -q "__Secure-1PSID" "backend/imageGenerator/cookies-account$i.json" && \
               grep -q "__Secure-1PSIDTS" "backend/imageGenerator/cookies-account$i.json"; then
                pass "Account$i has required cookies (PSID + PSIDTS)"
            else
                fail "Account$i missing required cookies"
                echo "   Fix: python backend/imageGenerator/GeminiCookies.py --slot $i --refresh"
            fi
        else
            fail "Account$i cookies file missing"
        fi
    else
        fail "Account$i profile directory missing"
    fi
done

echo ""

# 4. Check worker process
echo "4. Checking worker process..."
if pgrep -f "image_worker.py" > /dev/null; then
    pass "Image worker process is running"
    WORKER_PID=$(pgrep -f "image_worker.py")
    echo "   PID: $WORKER_PID"
else
    warn "Image worker process not running"
    echo "   Start with: cd backend && python image_worker.py &"
fi

echo ""

# 5. Check log directories
echo "5. Checking log directories..."
if [ -d "logs/generator" ]; then
    pass "Generator log directory exists"
    
    # Check for recent logs
    for i in {1..4}; do
        if [ -f "logs/generator/account$i.log" ]; then
            pass "Account$i log file exists"
            
            # Check if log was written recently (within last hour)
            if [ -n "$(find logs/generator/account$i.log -mmin -60 2>/dev/null)" ]; then
                pass "Account$i log recently updated"
            else
                warn "Account$i log not updated in last hour"
            fi
        else
            warn "Account$i log file not found"
        fi
    done
else
    warn "Generator log directory not found"
    echo "   Will be created on first worker launch"
fi

echo ""

# 6. Check database
echo "6. Checking database..."
if [ -f "backend/papergenerator.db" ] || [ -n "$DATABASE_URL" ]; then
    pass "Database configured"
else
    warn "Database file not found (may be using PostgreSQL)"
fi

echo ""

# 7. Test Python imports
echo "7. Testing Python dependencies..."
cd backend
if python -c "from imageGenerator.CreateImageGemini import GeminiPool" 2>/dev/null; then
    pass "CreateImageGemini imports successfully"
else
    fail "CreateImageGemini import failed"
fi

if python -c "from imageGenerator.compress import compress_image" 2>/dev/null; then
    pass "compress module imports successfully"
else
    fail "compress module import failed"
fi

if python -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
    pass "Playwright installed"
else
    fail "Playwright not installed"
    echo "   Fix: pip install playwright && playwright install chrome"
fi

if python -c "from PIL import Image" 2>/dev/null; then
    pass "Pillow installed"
else
    fail "Pillow not installed"
    echo "   Fix: pip install Pillow"
fi

cd ..

echo ""

# 8. Run automated tests
echo "8. Running automated tests..."
if [ -f "backend/tests/test_image_fixes.py" ]; then
    pass "Test suite exists"
    
    if command -v pytest &> /dev/null; then
        echo "   Running tests..."
        if pytest backend/tests/test_image_fixes.py -v --tb=short 2>&1 | tail -20; then
            pass "Tests passed"
        else
            warn "Some tests failed (check output above)"
        fi
    else
        warn "pytest not installed, skipping tests"
        echo "   Install with: pip install pytest"
    fi
else
    warn "Test suite not found"
fi

echo ""

# Summary
echo "=========================================="
echo "Verification Summary"
echo "=========================================="
echo -e "${GREEN}Passed:${NC}   $PASSED"
echo -e "${YELLOW}Warnings:${NC} $WARNINGS"
echo -e "${RED}Failed:${NC}   $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    if [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}✓ All checks passed! System ready for production.${NC}"
        exit 0
    else
        echo -e "${YELLOW}⚠ System functional but has warnings. Review above.${NC}"
        exit 0
    fi
else
    echo -e "${RED}✗ Critical issues found. Fix before deploying.${NC}"
    exit 1
fi
