#!/bin/bash
# Chaos Testing Execution Script
# Quick launcher for chaos testing suite

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "🔥 Chaos Testing Suite"
echo "======================"
echo ""

# Check if services are running
check_services() {
    echo "🔍 Checking services..."
    
    # Check frontend
    if curl -s http://localhost:8000 > /dev/null 2>&1; then
        echo "✅ Frontend running on :8000"
    else
        echo "❌ Frontend not running on :8000"
        echo "   Start with: npm run dev"
        return 1
    fi
    
    # Check backend
    if curl -s http://localhost:8001/api/health > /dev/null 2>&1; then
        echo "✅ Backend running on :8001"
    else
        echo "⚠️  Backend not running on :8001"
        echo "   Start with: cd backend && python -m uvicorn main:app --reload --port 8001"
        return 1
    fi
    
    echo ""
}

# Show menu
show_menu() {
    echo "Select test mode:"
    echo "1) Run all chaos tests (headless)"
    echo "2) Run with UI mode (interactive)"
    echo "3) Run with full report generation"
    echo "4) Run specific category"
    echo "5) Check services only"
    echo "6) Exit"
    echo ""
    read -p "Enter choice [1-6]: " choice
    
    case $choice in
        1)
            run_headless
            ;;
        2)
            run_ui
            ;;
        3)
            run_with_report
            ;;
        4)
            run_category
            ;;
        5)
            check_services
            ;;
        6)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo "Invalid choice"
            exit 1
            ;;
    esac
}

run_headless() {
    echo "🚀 Running chaos tests (headless)..."
    npm run test:chaos
}

run_ui() {
    echo "🎨 Running chaos tests (UI mode)..."
    npm run test:chaos:ui
}

run_with_report() {
    echo "📊 Running chaos tests with full report..."
    npm run test:chaos:report
    
    echo ""
    echo "📄 Reports generated:"
    ls -lh CHAOS_TEST_REPORT_*.md 2>/dev/null || echo "No reports found"
    ls -lh chaos-results-*.json 2>/dev/null || echo "No JSON results found"
}

run_category() {
    echo ""
    echo "Available categories:"
    echo "1) Network Failure Scenarios"
    echo "2) Invalid Input Scenarios"
    echo "3) Resource Exhaustion Scenarios"
    echo "4) Timeout & Cancellation Scenarios"
    echo "5) Authentication Error Scenarios"
    echo "6) Browser Compatibility & Edge Cases"
    echo "7) Data Integrity & Recovery"
    echo ""
    read -p "Enter category number [1-7]: " cat_choice
    
    case $cat_choice in
        1) GREP="Network Failure" ;;
        2) GREP="Invalid Input" ;;
        3) GREP="Resource Exhaustion" ;;
        4) GREP="Timeout" ;;
        5) GREP="Authentication" ;;
        6) GREP="Browser Compatibility" ;;
        7) GREP="Data Integrity" ;;
        *)
            echo "Invalid category"
            exit 1
            ;;
    esac
    
    echo "🎯 Running: $GREP tests..."
    npm run test:chaos -- -g "$GREP"
}

# Main execution
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0 [option]"
    echo ""
    echo "Options:"
    echo "  --headless    Run all tests headless"
    echo "  --ui          Run with UI mode"
    echo "  --report      Run with full report"
    echo "  --check       Check services only"
    echo "  --help        Show this help"
    echo ""
    echo "Without options, shows interactive menu"
    exit 0
fi

if [ "$1" = "--headless" ]; then
    check_services && run_headless
elif [ "$1" = "--ui" ]; then
    check_services && run_ui
elif [ "$1" = "--report" ]; then
    check_services && run_with_report
elif [ "$1" = "--check" ]; then
    check_services
else
    check_services && show_menu
fi
