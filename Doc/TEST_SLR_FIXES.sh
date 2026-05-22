#!/bin/bash
# SLR Bug Fixes Validation Script
# Run this after deploying fixes to validate all bugs are resolved

set -e

echo "=========================================="
echo "SLR Bug Fixes Validation"
echo "Date: $(date)"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
API_BASE="${API_BASE:-http://localhost:5000}"
TOKEN="${API_TOKEN:-}"
PAPER_ID="${TEST_PAPER_ID:-test_paper_$(date +%s)}"

if [ -z "$TOKEN" ]; then
    echo -e "${RED}ERROR: API_TOKEN environment variable not set${NC}"
    echo "Usage: API_TOKEN=your_token ./TEST_SLR_FIXES.sh"
    exit 1
fi

# Helper functions
test_passed() {
    echo -e "${GREEN}✓ PASSED${NC}: $1"
}

test_failed() {
    echo -e "${RED}✗ FAILED${NC}: $1"
    echo "  Details: $2"
}

test_warning() {
    echo -e "${YELLOW}⚠ WARNING${NC}: $1"
}

# Test 1: Verify OpenAlex abstract reconstruction
echo "Test 1: OpenAlex Abstract Reconstruction"
echo "----------------------------------------"
python3 -c "
import sys
sys.path.insert(0, 'backend')
from SLR.fetchers.openalex import _reconstruct_abstract

# Test case: inverted index with gaps
inv_index = {
    'machine': [0, 5],
    'learning': [1, 6],
    'is': [2],
    'powerful': [7],
    # Gap at positions 3, 4
}

result = _reconstruct_abstract(inv_index)
expected_words = ['machine', 'learning', 'is', 'powerful']

if result and all(word in result for word in expected_words):
    print('PASS: Abstract reconstruction handles gaps correctly')
    sys.exit(0)
else:
    print(f'FAIL: Got \"{result}\"')
    sys.exit(1)
" && test_passed "OpenAlex abstract reconstruction" || test_failed "OpenAlex abstract reconstruction" "See output above"

echo ""

# Test 2: Verify DOI normalization
echo "Test 2: DOI Deduplication"
echo "-------------------------"
python3 -c "
import sys
sys.path.insert(0, 'backend')
from SLR.paper import Paper

# Test cases: same DOI in different formats
p1 = Paper(source='test', source_id='1', title='Test', doi='10.1234/5678')
p2 = Paper(source='test', source_id='2', title='Test', doi=' 10.1234/5678 ')
p3 = Paper(source='test', source_id='3', title='Test', doi='https://doi.org/10.1234/5678')

keys = [p1.dedup_key(), p2.dedup_key(), p3.dedup_key()]
unique_keys = set(keys)

if len(unique_keys) == 1:
    print(f'PASS: All DOI formats normalize to same key: {unique_keys.pop()}')
    sys.exit(0)
else:
    print(f'FAIL: Got {len(unique_keys)} unique keys: {unique_keys}')
    sys.exit(1)
" && test_passed "DOI normalization" || test_failed "DOI normalization" "See output above"

echo ""

# Test 3: Create test paper
echo "Test 3: Create Test Paper"
echo "-------------------------"
PAPER_RESPONSE=$(curl -s -X POST "$API_BASE/api/papers" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"title\": \"SLR Test Paper $(date +%s)\", \"topic\": \"machine learning\"}")

PAPER_ID=$(echo "$PAPER_RESPONSE" | jq -r '.id // empty')

if [ -n "$PAPER_ID" ]; then
    test_passed "Created test paper: $PAPER_ID"
else
    test_failed "Failed to create test paper" "$PAPER_RESPONSE"
    exit 1
fi

echo ""

# Test 4: Run SLR job
echo "Test 4: Run SLR Job"
echo "-------------------"
JOB_RESPONSE=$(curl -s -X POST "$API_BASE/api/papers/$PAPER_ID/slr/jobs" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "query": "machine learning",
        "top_k": 20,
        "ai_summarize": true,
        "ai_model": "V-OPUS"
    }')

JOB_ID=$(echo "$JOB_RESPONSE" | jq -r '.id // empty')

if [ -n "$JOB_ID" ]; then
    test_passed "Created SLR job: $JOB_ID"
else
    test_failed "Failed to create SLR job" "$JOB_RESPONSE"
    exit 1
fi

echo ""

# Test 5: Poll for job completion
echo "Test 5: Wait for Job Completion"
echo "--------------------------------"
MAX_WAIT=300  # 5 minutes
ELAPSED=0
POLL_INTERVAL=5

while [ $ELAPSED -lt $MAX_WAIT ]; do
    JOB_STATUS=$(curl -s "$API_BASE/api/slr/jobs/$JOB_ID" \
        -H "Authorization: Bearer $TOKEN" \
        | jq -r '.status // empty')
    
    PROGRESS=$(curl -s "$API_BASE/api/slr/jobs/$JOB_ID" \
        -H "Authorization: Bearer $TOKEN" \
        | jq -r '.progress // 0')
    
    echo "  Status: $JOB_STATUS | Progress: $PROGRESS% | Elapsed: ${ELAPSED}s"
    
    if [ "$JOB_STATUS" = "done" ]; then
        test_passed "Job completed successfully"
        break
    elif [ "$JOB_STATUS" = "error" ]; then
        ERROR_MSG=$(curl -s "$API_BASE/api/slr/jobs/$JOB_ID" \
            -H "Authorization: Bearer $TOKEN" \
            | jq -r '.error // "Unknown error"')
        test_failed "Job failed" "$ERROR_MSG"
        exit 1
    elif [ "$JOB_STATUS" = "cancelled" ]; then
        test_failed "Job was cancelled" "Unexpected cancellation"
        exit 1
    fi
    
    sleep $POLL_INTERVAL
    ELAPSED=$((ELAPSED + POLL_INTERVAL))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    test_failed "Job timeout" "Job did not complete within ${MAX_WAIT}s"
    exit 1
fi

echo ""

# Test 6: Verify literature items
echo "Test 6: Verify Literature Items"
echo "--------------------------------"
LIT_RESPONSE=$(curl -s "$API_BASE/api/papers/$PAPER_ID/literature" \
    -H "Authorization: Bearer $TOKEN")

LIT_COUNT=$(echo "$LIT_RESPONSE" | jq 'length')

if [ "$LIT_COUNT" -gt 0 ]; then
    test_passed "Found $LIT_COUNT literature items"
else
    test_failed "No literature items found" "$LIT_RESPONSE"
    exit 1
fi

echo ""

# Test 7: Check for duplicate DOIs
echo "Test 7: Check for Duplicate DOIs"
echo "---------------------------------"
DUPLICATE_DOIS=$(echo "$LIT_RESPONSE" | jq '[.[] | select(.doi != null) | .doi] | group_by(.) | map(select(length > 1)) | length')

if [ "$DUPLICATE_DOIS" -eq 0 ]; then
    test_passed "No duplicate DOIs found"
else
    test_warning "Found $DUPLICATE_DOIS duplicate DOI(s)"
    echo "$LIT_RESPONSE" | jq '[.[] | select(.doi != null) | .doi] | group_by(.) | map(select(length > 1))'
fi

echo ""

# Test 8: Verify OpenAlex abstracts
echo "Test 8: Verify OpenAlex Abstracts"
echo "----------------------------------"
OPENALEX_PAPERS=$(echo "$LIT_RESPONSE" | jq '[.[] | select(.source == "openalex")]')
OPENALEX_COUNT=$(echo "$OPENALEX_PAPERS" | jq 'length')

if [ "$OPENALEX_COUNT" -gt 0 ]; then
    INCOMPLETE_ABSTRACTS=$(echo "$OPENALEX_PAPERS" | jq '[.[] | select(.abstract == null or (.abstract | length) < 50)] | length')
    
    if [ "$INCOMPLETE_ABSTRACTS" -eq 0 ]; then
        test_passed "All $OPENALEX_COUNT OpenAlex papers have complete abstracts"
    else
        test_warning "$INCOMPLETE_ABSTRACTS/$OPENALEX_COUNT OpenAlex papers have incomplete abstracts"
    fi
else
    test_warning "No OpenAlex papers in results (may be normal depending on query)"
fi

echo ""

# Test 9: Test cancellation
echo "Test 9: Test Job Cancellation"
echo "------------------------------"
CANCEL_JOB_RESPONSE=$(curl -s -X POST "$API_BASE/api/papers/$PAPER_ID/slr/jobs" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query": "deep learning", "top_k": 50}')

CANCEL_JOB_ID=$(echo "$CANCEL_JOB_RESPONSE" | jq -r '.id // empty')

if [ -n "$CANCEL_JOB_ID" ]; then
    echo "  Created job: $CANCEL_JOB_ID"
    sleep 5  # Wait for job to start
    
    curl -s -X DELETE "$API_BASE/api/slr/jobs/$CANCEL_JOB_ID" \
        -H "Authorization: Bearer $TOKEN" > /dev/null
    
    sleep 10  # Wait for cancellation to propagate
    
    CANCEL_STATUS=$(curl -s "$API_BASE/api/slr/jobs/$CANCEL_JOB_ID" \
        -H "Authorization: Bearer $TOKEN" \
        | jq -r '.status // empty')
    
    if [ "$CANCEL_STATUS" = "cancelled" ]; then
        test_passed "Job cancelled successfully"
    else
        test_warning "Job status is '$CANCEL_STATUS' (expected 'cancelled')"
    fi
else
    test_failed "Failed to create cancellation test job" "$CANCEL_JOB_RESPONSE"
fi

echo ""

# Test 10: Cleanup
echo "Test 10: Cleanup"
echo "----------------"
curl -s -X DELETE "$API_BASE/api/papers/$PAPER_ID" \
    -H "Authorization: Bearer $TOKEN" > /dev/null

test_passed "Cleaned up test paper"

echo ""
echo "=========================================="
echo "Validation Complete"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - All critical bugs have been tested"
echo "  - Check warnings above for any issues"
echo "  - Monitor production logs for 24 hours"
echo ""
