#!/bin/bash
# Apply Critical Bug Fixes
# Usage: ./apply_critical_fixes.sh [--dry-run]

set -e  # Exit on error

BACKEND_DIR="/home/sirobo/papergenerator/backend"
FIXES_DIR="$BACKEND_DIR/fixes"
BACKUP_DIR="$BACKEND_DIR/backup_$(date +%Y%m%d_%H%M%S)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DRY_RUN=false
if [ "$1" == "--dry-run" ]; then
    DRY_RUN=true
    echo -e "${YELLOW}DRY RUN MODE - No changes will be made${NC}"
fi

echo "=========================================="
echo "  Critical Bug Fixes Application Script"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "$BACKEND_DIR/app.py" ]; then
    echo -e "${RED}Error: Not in backend directory${NC}"
    echo "Please run from: $BACKEND_DIR"
    exit 1
fi

# Check if patch files exist
if [ ! -d "$FIXES_DIR" ]; then
    echo -e "${RED}Error: Fixes directory not found${NC}"
    echo "Expected: $FIXES_DIR"
    exit 1
fi

# Create backup directory
echo "Creating backup..."
if [ "$DRY_RUN" = false ]; then
    mkdir -p "$BACKUP_DIR"
    cp app.py "$BACKUP_DIR/"
    cp quota_bp.py "$BACKUP_DIR/"
    cp chat.py "$BACKUP_DIR/"
    cp slr_bp.py "$BACKUP_DIR/"
    echo -e "${GREEN}✓ Backup created: $BACKUP_DIR${NC}"
else
    echo -e "${YELLOW}[DRY RUN] Would create backup in: $BACKUP_DIR${NC}"
fi
echo ""

# Function to apply patch
apply_patch() {
    local patch_file=$1
    local description=$2
    
    echo "----------------------------------------"
    echo "Applying: $description"
    echo "Patch: $patch_file"
    
    if [ ! -f "$FIXES_DIR/$patch_file" ]; then
        echo -e "${RED}✗ Patch file not found: $patch_file${NC}"
        return 1
    fi
    
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY RUN] Would apply patch${NC}"
        patch --dry-run -p1 < "$FIXES_DIR/$patch_file"
        return $?
    else
        if patch -p1 < "$FIXES_DIR/$patch_file"; then
            echo -e "${GREEN}✓ Successfully applied${NC}"
            return 0
        else
            echo -e "${RED}✗ Failed to apply patch${NC}"
            return 1
        fi
    fi
}

# Apply patches
FAILED=0

apply_patch "fix_quota_race_condition.patch" "Fix #1: Race Condition in Token Quota" || FAILED=$((FAILED+1))
echo ""

apply_patch "fix_month_rollover_race.patch" "Fix #2: Race Condition in Month Rollover" || FAILED=$((FAILED+1))
echo ""

apply_patch "fix_semaphore_leak.patch" "Fix #3: Semaphore Leak in Upstream Calls" || FAILED=$((FAILED+1))
echo ""

apply_patch "fix_connection_pool_exhaustion.patch" "Fix #4: Connection Pool Exhaustion" || FAILED=$((FAILED+1))
echo ""

# Summary
echo "=========================================="
echo "  Summary"
echo "=========================================="

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All patches applied successfully!${NC}"
    echo ""
    
    if [ "$DRY_RUN" = false ]; then
        echo "Next steps:"
        echo "1. Run tests: pytest tests/test_critical_fixes.py -v"
        echo "2. Restart backend: systemctl restart paperfull-backend"
        echo "3. Monitor logs: tail -f data/logs/app.log"
        echo ""
        echo "Rollback command (if needed):"
        echo "  cp $BACKUP_DIR/* $BACKEND_DIR/"
        echo "  systemctl restart paperfull-backend"
    else
        echo -e "${YELLOW}Dry run completed. Run without --dry-run to apply changes.${NC}"
    fi
else
    echo -e "${RED}✗ $FAILED patch(es) failed to apply${NC}"
    echo ""
    echo "Possible causes:"
    echo "- Files have been modified since patches were created"
    echo "- Patches have already been applied"
    echo "- Merge conflicts"
    echo ""
    echo "To resolve:"
    echo "1. Check git status: git status"
    echo "2. Review patch files in: $FIXES_DIR"
    echo "3. Apply manually if needed"
    
    if [ "$DRY_RUN" = false ]; then
        echo ""
        echo "Backup preserved at: $BACKUP_DIR"
    fi
    
    exit 1
fi

echo ""
echo "=========================================="
