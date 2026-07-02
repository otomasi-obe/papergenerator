#!/bin/bash
# Cleanup nested directories created by old relative path bugs
# All fixed in commit 2026-06-30: absolute paths from __file__

set -e

BACKEND_DIR="/home/sirobo/papergenerator/backend"
cd "$BACKEND_DIR"

echo "🧹 Cleaning up nested directories from old relative path bugs..."
echo "=================================================="

# 1. backend/backend/log/generator/ → should be backend/log/generator/
if [ -d "backend/backend" ]; then
    echo "📁 Found: backend/backend/ (104K)"
    echo "   Created by: old code running from wrong CWD"
    echo "   Fixed in: slrFetch.py, slrSummarize.py (now use Path(__file__).resolve())"
    
    # Move logs to correct location if any
    if [ -d "backend/backend/log/generator" ]; then
        echo "   → Moving logs to backend/log/generator/"
        mkdir -p log/generator
        rsync -av backend/backend/log/generator/ log/generator/ || true
    fi
    
    echo "   → Removing backend/backend/"
    rm -rf backend/backend
    echo "   ✅ Cleaned"
else
    echo "✓ backend/backend/ not found (already clean)"
fi

echo ""

# 2. tools/data/data/charts/ → should be backend/data/charts/
if [ -d "tools/data/data" ]; then
    echo "📁 Found: tools/data/data/ (8K)"
    echo "   Created by: old chart_generator.py with os.path.join('../..')"
    echo "   Fixed in: chart_generator.py (now use Path(__file__).resolve())"
    
    # Move charts to correct location if any
    if [ -d "tools/data/data/charts" ]; then
        echo "   → Moving charts to backend/data/charts/"
        mkdir -p data/charts
        rsync -av tools/data/data/charts/ data/charts/ || true
    fi
    
    echo "   → Removing tools/data/data/"
    rm -rf tools/data/data
    echo "   ✅ Cleaned"
else
    echo "✓ tools/data/data/ not found (already clean)"
fi

echo ""
echo "=================================================="
echo "✅ Cleanup complete!"
echo ""
echo "📊 Remaining nested dirs (should be empty):"
find . -type d -name "backend" -o -type d -name "data" | grep -v ".venv" | grep -E "(backend/backend|tools/data/data)" || echo "   (none found)"
