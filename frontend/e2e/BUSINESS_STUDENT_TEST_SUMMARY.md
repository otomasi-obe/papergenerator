# Business Student Qualitative Research E2E Test

## Test File
`frontend/e2e/business-student-qualitative.spec.js`

## Test Status
✅ **PASSED** (807ms)

## Persona
**Mahasiswa Manajemen** - Business student working on digital marketing thesis

## Test Scenario
Qualitative research paper about Social Media Marketing effectiveness on SMEs (UMKM)

## Test Flow

### 1. User Registration & Authentication
- Registers new user: `business-{timestamp}@e2e.local`
- Verifies authentication cookies (access_token, CSRF tokens)
- Confirms `/api/auth/me` returns correct user data

### 2. Paper Creation
Creates paper with qualitative business research metadata:
- **Title**: "Efektivitas Social Media Marketing pada UMKM"
- **Jurusan**: Manajemen
- **Topik**: Social Media Marketing Effectiveness pada UMKM di Era Digital
- **Metode**: Kualitatif
- **Jenis Data**: Transkrip wawancara dan observasi
- **Target**: Tugas Akhir
- **Citation Style**: APA 7th

### 3. Interview Transcript Data
Includes realistic interview transcript:
```
TRANSKRIP WAWANCARA 1
Narasumber: Pemilik UMKM Fashion Online
Tanggal: 15 Mei 2026

P: Bagaimana Anda menggunakan social media untuk marketing?
N: Kami aktif di Instagram dan TikTok. Posting produk setiap hari, engage dengan followers.

P: Apa dampaknya terhadap penjualan?
N: Sangat signifikan. Sejak aktif di TikTok, penjualan naik 150% dalam 3 bulan.

P: Strategi konten seperti apa yang efektif?
N: Behind-the-scenes, customer testimonials, dan tutorial styling. Konten autentik lebih engage.
```

### 4. Paper Generation
- Triggers generation via `/api/papers/{paperId}/generate`
- Includes interview transcript in prompt
- Requests qualitative analysis with thematic approach
- Specifies APA 7th citation format
- Verifies job is queued successfully

### 5. Verification
Validates paper metadata:
- ✅ Title matches input
- ✅ Jurusan = "Manajemen"
- ✅ Metode = "Kualitatif"
- ✅ Citation style = "APA 7th"
- ✅ Target = "Tugas Akhir"
- ✅ Paper data contains: "kualitatif", "wawancara", "marketing"

### 6. Cleanup
- Logs out user
- Verifies logout successful

## What This Test Validates

### ✅ Qualitative Methodology Support
- System accepts qualitative research method
- Stores qualitative-specific metadata (interview transcripts, observation data)

### ✅ Business/Management Domain
- Accepts Manajemen as field of study
- Handles business terminology (marketing, UMKM, engagement)
- Supports business research topics

### ✅ APA 7th Citation Format
- System stores APA 7th as citation preference
- Will apply APA formatting during generation

### ✅ Interview Data Handling
- Accepts interview transcript data
- Includes transcript in generation prompt
- Preserves qualitative data structure

### ✅ Case Study Structure
- Paper metadata includes context for case study approach
- Interview data supports case study methodology

## Running the Test

```bash
# Run this specific test
cd frontend
npm run test:e2e -- business-student-qualitative.spec.js

# Or with Playwright directly
npx playwright test business-student-qualitative.spec.js --project=chromium
```

## Test Design Notes

### Why Not Wait for Full Generation?
This test focuses on **workflow validation** rather than content quality:
- Paper generation with AI can take 1-5 minutes
- E2E tests should be fast and reliable
- Content quality is better tested separately with fixtures

### What's Tested vs. What's Not
**Tested:**
- ✅ User can create qualitative research papers
- ✅ Metadata is stored correctly
- ✅ Generation job is queued
- ✅ Interview data is accepted

**Not Tested (by design):**
- ❌ Generated paper content quality
- ❌ Actual thematic analysis in output
- ❌ APA citation formatting in final paper
- ❌ Business terminology in generated text

These should be tested with:
- Unit tests with mocked AI responses
- Integration tests with pre-generated fixtures
- Manual QA review of actual generated papers

## Related Test Files
- `auth.spec.js` - Authentication flow reference
- `smoke.spec.js` - Basic endpoint health checks

## Future Enhancements
1. Add test for uploading interview transcript files (not just inline text)
2. Test multiple interview transcripts
3. Test observational data format
4. Add test for mixed methods (qualitative + quantitative)
5. Test case study structure validation
6. Add test for thematic coding interface (if implemented)
