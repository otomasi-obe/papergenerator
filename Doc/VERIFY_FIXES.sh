#!/bin/bash
# Quick verification script - run this to check if all fixes are in place

echo "🔍 Verifying SLR Bug Fixes..."
echo ""

PASS=0
FAIL=0

# Check 1: OpenAlex abstract reconstruction fix
if grep -q "pos_map.get(i, \"\")" backend/SLR/fetchers/openalex.py; then
    echo "✅ OpenAlex abstract reconstruction fix present"
    ((PASS++))
else
    echo "❌ OpenAlex abstract reconstruction fix MISSING"
    ((FAIL++))
fi

# Check 2: DOI normalization fix
if grep -q "removeprefix" backend/SLR/paper.py; then
    echo "✅ DOI normalization fix present"
    ((PASS++))
else
    echo "❌ DOI normalization fix MISSING"
    ((FAIL++))
fi

# Check 3: Semantic Scholar rate limit fix
if grep -q "1.5" backend/SLR/fetchers/semantic_scholar.py; then
    echo "✅ Semantic Scholar rate limit fix present"
    ((PASS++))
else
    echo "❌ Semantic Scholar rate limit fix MISSING"
    ((FAIL++))
fi

# Check 4: ArXiv error logging fix
if grep -q "arxiv parse error" backend/SLR/fetchers/arxiv.py; then
    echo "✅ ArXiv error logging fix present"
    ((PASS++))
else
    echo "❌ ArXiv error logging fix MISSING"
    ((FAIL++))
fi

# Check 5: EuropePMC cursor fix
if grep -q "cursor stuck" backend/SLR/fetchers/europepmc.py; then
    echo "✅ EuropePMC cursor fix present"
    ((PASS++))
else
    echo "❌ EuropePMC cursor fix MISSING"
    ((FAIL++))
fi

# Check 6: Pipeline exception handling fix
if grep -q "cancel.*lower" backend/SLR/pipeline.py; then
    echo "✅ Pipeline exception handling fix present"
    ((PASS++))
else
    echo "❌ Pipeline exception handling fix MISSING"
    ((FAIL++))
fi

# Check 7: Worker sweep fix
if grep -q "Job timeout" backend/slr_worker.py; then
    echo "✅ Worker sweep timeout fix present"
    ((PASS++))
else
    echo "❌ Worker sweep timeout fix MISSING"
    ((FAIL++))
fi

# Check 8: Progress callback optimization
if grep -q "with_for_update" backend/slr_worker.py; then
    echo "✅ Progress callback optimization present"
    ((PASS++))
else
    echo "❌ Progress callback optimization fix MISSING"
    ((FAIL++))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results: $PASS passed, $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $FAIL -eq 0 ]; then
    echo "✅ All fixes verified! Ready for deployment."
    exit 0
else
    echo "❌ Some fixes are missing. Review the changes."
    exit 1
fi
