# Medical Student E2E Test - Clinical Research

## Overview

Comprehensive Playwright E2E test for the Medical Student persona conducting clinical research on diabetes management using mobile health applications.

## Test Scenario

**Persona**: Mahasiswa Kedokteran (Medical Student)  
**Research Topic**: Diabetes Management with Mobile Health Apps  
**Paper Type**: Literature Review / Systematic Review  
**Target**: International Journal  
**Citation Style**: Vancouver

## Test Coverage

### 1. Authentication & Setup
- ✅ Login/Register medical student user
- ✅ Handle rate limiting gracefully
- ✅ Verify JWT cookies and CSRF tokens

### 2. Paper Creation
- ✅ Create paper with medical research metadata
- ✅ Set discovery parameters (Kedokteran, Literature Review)
- ✅ Configure research question and keywords

### 3. SLR Execution
- ✅ Trigger SLR job with medical query
- ✅ Include medical databases (PubMed, Google Scholar, Semantic Scholar)
- ✅ Apply filters (year range, study types: RCT, systematic review, meta-analysis)
- ✅ Poll for job completion

### 4. Medical Terminology Validation
- ✅ Verify presence of key medical terms:
  - diabetes mellitus
  - glycemic control
  - HbA1c
  - insulin, glucose
  - hyperglycemia, hypoglycemia
  - endocrine, metabolic, cardiovascular

### 5. Citation Format Validation
- ✅ Verify Vancouver citation style:
  - Numbered references
  - "et al" usage
  - Year format (YYYY;)
  - Volume/issue format (XX(YY):)
  - Page range format (:XX-YY.)

### 6. Medical Abbreviations Check
- ✅ Verify standard medical abbreviations:
  - HbA1c, BMI, WHO
  - RCT, CI, OR, RR, SD
  - PRISMA

### 7. Ethical Considerations
- ✅ Check for ethical keywords:
  - ethical/ethics
  - informed consent
  - IRB, ethical approval
  - patient privacy, confidentiality

### 8. Clinical Trial References
- ✅ Verify clinical trial patterns:
  - randomized controlled trial
  - RCT, clinical trial
  - double-blind, placebo-controlled
  - intervention study

### 9. Validation Report
- ✅ Generate comprehensive validation report
- ✅ Count found terms, abbreviations, ethical keywords
- ✅ Timestamp and metadata

## Test Execution

### Prerequisites
```bash
# Ensure backend is running
pm2 status

# Ensure frontend dependencies are installed
cd frontend
npm install
```

### Run Test
```bash
# Run medical student test only
npm run test:e2e -- medical-student.spec.js

# Run with UI mode for debugging
npm run test:e2e:ui -- medical-student.spec.js

# Run with extended timeout (for slow SLR jobs)
npx playwright test medical-student.spec.js --timeout=300000
```

### View Results
```bash
# Open HTML report
npx playwright show-report

# View screenshots/videos on failure
ls test-results/medical-student-*/
```

## Test Data

### Medical User
- Email: `medical-e2e@test.local`
- Password: `MedicalPass123!`
- Name: Dr. Medical Student

### Research Parameters
- **Field**: Medicine - Endocrinology
- **Topic**: Diabetes Management with Mobile Health Apps
- **Research Question**: How effective are mobile health applications in improving diabetes management outcomes?
- **Keywords**: diabetes mellitus, mobile health, mHealth, glycemic control, HbA1c, self-management
- **Study Types**: RCT, systematic review, meta-analysis, cohort study
- **Year Range**: 2018-2026

## Validation Criteria

### Medical Terminology (Pass: ≥3 terms found)
Checks for domain-specific medical vocabulary in literature results.

### Vancouver Citations (Pass: ≥2 format patterns matched)
Validates proper Vancouver citation style formatting.

### Medical Abbreviations (Pass: ≥2 abbreviations found)
Ensures standard medical abbreviations are present.

### Ethical Considerations (Pass: ≥1 keyword found)
Verifies ethical aspects are mentioned in research.

### Clinical Trial References (Pass: ≥1 pattern found)
Confirms clinical trial methodology is referenced.

## Known Issues & Limitations

### Rate Limiting
The backend enforces a rate limit of 10 registrations per minute per IP. The test handles this by:
1. Attempting login first (reuse existing user)
2. Only registering if user doesn't exist
3. Waiting 65 seconds and retrying if rate limit is hit

### SLR Job Timing
SLR jobs can take 30-180 seconds depending on:
- Number of databases queried
- API rate limits
- Network conditions
- Result count (top_k parameter)

The test includes a 180-second timeout with 3-second polling intervals.

### Test Isolation
The test reuses the same user account (`medical-e2e@test.local`) across runs. This means:
- Papers from previous runs may exist
- Literature results may be cached
- Test is idempotent but not fully isolated

For true isolation, use unique email addresses with timestamps (but be aware of rate limits).

## Troubleshooting

### Test Fails at Registration (429 Error)
**Cause**: Rate limit exceeded  
**Solution**: Wait 60 seconds or use existing user (test already handles this)

### Test Fails at SLR Job Creation (401 Error)
**Cause**: Authentication expired  
**Solution**: Check JWT token validity, ensure cookies are preserved

### Test Fails at Literature Validation (0 items)
**Cause**: SLR job failed or returned no results  
**Solution**: Check backend logs, verify API keys for external databases

### Test Times Out at Job Completion
**Cause**: SLR job taking too long or stuck  
**Solution**: Increase timeout, check backend worker status, review job logs

## Integration with CI/CD

### GitHub Actions Example
```yaml
- name: Run Medical Student E2E Test
  run: |
    cd frontend
    npx playwright test medical-student.spec.js --reporter=json > test-results.json
  timeout-minutes: 10

- name: Upload Test Results
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: medical-student-test-results
    path: |
      frontend/test-results/
      frontend/playwright-report/
```

## Future Enhancements

- [ ] Add more medical specialties (Cardiology, Oncology, Neurology)
- [ ] Test different citation styles (APA, Harvard, IEEE)
- [ ] Validate PRISMA checklist compliance
- [ ] Check for systematic review quality metrics
- [ ] Test multi-language medical terminology
- [ ] Validate medical image/figure references
- [ ] Check for conflict of interest statements
- [ ] Verify funding acknowledgments

## Related Tests

- `auth.spec.js` - Authentication flow tests
- `smoke.spec.js` - Basic health checks
- `literature-tab.*.spec.js` - Literature component tests

## Contact

For issues or questions about this test:
- Check backend logs: `/home/sirobo/papergenerator/backend/app.log`
- Review Playwright traces: `npx playwright show-trace trace.zip`
- Open issue in project repository

---

**Last Updated**: 2026-05-22  
**Test Status**: ✅ All 9 tests passing  
**Execution Time**: ~3-5 seconds (with cached data)
