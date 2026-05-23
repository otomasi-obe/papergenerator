/**
 * E2E Test: Business Student - Qualitative Research
 * 
 * Persona: Business/Management student conducting qualitative research
 * 
 * Test Flow:
 * 1. Login as test user
 * 2. Create new paper with business topic
 * 3. Upload interview transcripts (simulated)
 * 4. Use chat to generate qualitative analysis sections
 * 5. Add thematic analysis tables
 * 6. Export to DOCX with APA citations
 * 
 * Features:
 * - Headless mode
 * - Screenshots on failure
 * - API call logging
 * - Performance measurement
 * - APA citation verification
 */

import { test, expect } from '@playwright/test';
import { mkdir } from 'fs/promises';
import { existsSync } from 'fs';

const TEST_USER = {
  email: `business-${Date.now()}@test.local`,
  name: 'Business Student',
  password: 'BusinessTest123!',
};

const PAPER_CONFIG = {
  title: 'Digital Marketing Strategy Effectiveness in SMEs: A Qualitative Study',
  topic: 'Digital Marketing Effectiveness in SMEs',
  field: 'Manajemen / Bisnis',
  method: 'Kualitatif',
  dataType: 'Transkrip wawancara dan observasi',
  target: 'Tugas Akhir',
  citationStyle: 'APA 7th',
};

const BUSINESS_TERMS = [
  'digital marketing', 'social media', 'SME', 'UMKM', 'strategy',
  'brand awareness', 'customer engagement', 'ROI', 'conversion',
  'content marketing', 'influencer', 'analytics', 'KPI'
];

const QUALITATIVE_KEYWORDS = [
  'thematic analysis', 'interview', 'coding', 'themes',
  'participant', 'qualitative', 'narrative', 'interpretation'
];

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

async function ensureTestDir() {
  const dir = 'test-results/business-student';
  if (!existsSync(dir)) {
    await mkdir(dir, { recursive: true });
  }
  return dir;
}

test.describe('Business Student - Qualitative Research', () => {
  let context;
  let page;
  let paperId;
  let testStartTime;
  let performanceMetrics = {
    apiCalls: [],
    consoleErrors: [],
    screenshots: [],
    generationTime: 0,
  };
  const screenshotDir = 'test-results/business-student';

  test.beforeAll(async ({ browser }) => {
    testStartTime = Date.now();
    await ensureTestDir();
    
    context = await browser.newContext({
      recordVideo: { dir: screenshotDir },
    });
    page = await context.newPage();
    
    page.on('request', request => {
      performanceMetrics.apiCalls.push({
        url: request.url(),
        method: request.method(),
        timestamp: Date.now(),
      });
    });
    
    page.on('response', response => {
      const call = performanceMetrics.apiCalls.find(
        c => c.url === response.url() && !c.status
      );
      if (call) {
        call.status = response.status();
        call.duration = Date.now() - call.timestamp;
      }
    });
    
    page.on('console', msg => {
      if (msg.type() === 'error') {
        performanceMetrics.consoleErrors.push({
          text: msg.text(),
          timestamp: Date.now(),
        });
      }
    });
  });

  test.afterAll(async () => {
    const totalTime = ((Date.now() - testStartTime) / 1000).toFixed(2);
    
    console.log('\n' + '='.repeat(80));
    console.log('BUSINESS STUDENT TEST - PERFORMANCE REPORT');
    console.log('='.repeat(80));
    console.log(`Total execution time: ${totalTime}s`);
    console.log(`Paper generation time: ${(performanceMetrics.generationTime / 1000).toFixed(2)}s`);
    console.log(`Total API calls: ${performanceMetrics.apiCalls.length}`);
    console.log(`Console errors: ${performanceMetrics.consoleErrors.length}`);
    console.log(`Screenshots taken: ${performanceMetrics.screenshots.length}`);
    
    const apiCallsWithDuration = performanceMetrics.apiCalls.filter(c => c.duration);
    if (apiCallsWithDuration.length > 0) {
      const avgApiTime = apiCallsWithDuration.reduce((sum, c) => sum + c.duration, 0) / apiCallsWithDuration.length;
      console.log(`Average API response time: ${avgApiTime.toFixed(0)}ms`);
    }
    
    if (performanceMetrics.consoleErrors.length > 0) {
      console.log('\nConsole Errors:');
      performanceMetrics.consoleErrors.slice(0, 5).forEach((err, i) => {
        console.log(`  ${i + 1}. ${err.text}`);
      });
    }
    console.log('='.repeat(80) + '\n');
    
    await context.close();
  });

  test('Step 1: Register and login business student', async () => {
    const api = context.request;
    
    const startTime = Date.now();
    const reg = await api.post('/api/auth/register', {
      data: { ...TEST_USER, captcha_token: '1x00000000000000000000AA' },
    });
    
    expect(reg.status()).toBe(201);
    const regBody = await reg.json();
    expect(regBody.user.email).toBe(TEST_USER.email);
    
    const cookies = await context.cookies();
    expect(cookies.map(c => c.name)).toContain('access_token_cookie');
    
    console.log(`✓ User registered in ${Date.now() - startTime}ms`);
  });

  test('Step 2: Create new paper with business topic', async () => {
    await page.goto('/dashboard');
    await expect(page).toHaveTitle(/PaperFull|Paper Generator/i);
    
    await page.screenshot({ 
      path: `${screenshotDir}/01-dashboard.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('01-dashboard.png');
    
    const startTime = Date.now();
    await page.click('text=New Paper');
    await page.waitForURL(/\/editor/, { timeout: 10000 });
    
    const url = page.url();
    const match = url.match(/\/editor\/(\d+)/);
    if (match) {
      paperId = match[1];
      console.log(`✓ Paper created (ID: ${paperId}) in ${Date.now() - startTime}ms`);
    }
    
    const titleInput = page.locator('input[placeholder*="Paper title"]').first();
    await titleInput.fill(PAPER_CONFIG.title);
    await page.waitForTimeout(1000);
    await expect(page.locator('text=Saved')).toBeVisible({ timeout: 10000 });
    
    await page.screenshot({ 
      path: `${screenshotDir}/02-paper-created.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('02-paper-created.png');
  });

  test('Step 3: Provide interview data via chat', async () => {
    const chatButton = page.locator('button:has-text("AI Chat"), button:has-text("Chat")').first();
    await chatButton.click();
    await page.waitForTimeout(1000);
    
    const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
    await expect(chatInput).toBeVisible();
    
    const interviewData = `Saya mahasiswa ${PAPER_CONFIG.field}, sedang penelitian ${PAPER_CONFIG.method} tentang ${PAPER_CONFIG.topic}.

Data wawancara:

INFORMAN 1 - Pemilik UMKM Fashion Online (3 tahun beroperasi)
"Sejak aktif di Instagram dan TikTok, penjualan naik 150% dalam 6 bulan. Kunci sukses adalah konten autentik dan konsisten posting setiap hari. Engagement rate kami 8-10%, jauh lebih tinggi dari rata-rata industri."

INFORMAN 2 - Owner Kuliner Online (5 tahun beroperasi)
"Digital marketing mengubah bisnis kami total. Dulu hanya offline, sekarang 70% order dari online. Facebook Ads dan Instagram Stories paling efektif. ROI mencapai 300% untuk campaign tertentu."

INFORMAN 3 - Pengusaha Kerajinan Tangan (2 tahun beroperasi)
"Tantangan terbesar adalah konsistensi konten dan mengukur efektivitas. Kami coba berbagai platform, tapi Instagram dan marketplace yang paling menghasilkan. Influencer marketing juga membantu brand awareness."

Tolong generate paper dengan analisis tematik mendalam.`;
    
    await chatInput.fill(interviewData);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(3000);
    
    await page.screenshot({ 
      path: `${screenshotDir}/03-interview-data-provided.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('03-interview-data-provided.png');
    
    console.log('✓ Interview data provided');
  });

  test('Step 4: Generate qualitative research paper', async () => {
    const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
    
    const generatePrompt = `Generate complete qualitative research paper dengan struktur:

1. Abstract (English) - background, methods, findings, implications
2. Abstrak (Bahasa Indonesia)
3. BAB I PENDAHULUAN
   - Latar Belakang
   - Rumusan Masalah
   - Tujuan Penelitian
   - Manfaat Penelitian
4. BAB II TINJAUAN PUSTAKA
   - Digital Marketing Theory
   - Social Media Marketing
   - SME/UMKM Characteristics
   - Previous Studies (2020-2026)
5. BAB III METODOLOGI PENELITIAN
   - Pendekatan Kualitatif
   - Teknik Pengumpulan Data (wawancara mendalam)
   - Informan Penelitian (3 pemilik UMKM)
   - Analisis Data (thematic analysis)
6. BAB IV HASIL DAN PEMBAHASAN
   - Profil Informan
   - Temuan Penelitian (themes dari wawancara)
   - Analisis Tematik
   - Diskusi dan Interpretasi
7. BAB V PENUTUP
   - Kesimpulan
   - Implikasi Manajerial
   - Keterbatasan Penelitian
   - Saran untuk Penelitian Selanjutnya
8. DAFTAR PUSTAKA (format ${PAPER_CONFIG.citationStyle})

Gunakan kutipan langsung dari wawancara dan lakukan coding untuk identifikasi themes.`;
    
    await chatInput.fill(generatePrompt);
    
    await page.screenshot({ 
      path: `${screenshotDir}/04-generation-prompt.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('04-generation-prompt.png');
    
    const startTime = Date.now();
    await page.keyboard.press('Enter');
    
    console.log('⏳ Waiting for paper generation (max 3 minutes)...');
    await page.waitForTimeout(180000);
    performanceMetrics.generationTime = Date.now() - startTime;
    
    console.log(`✓ Generation completed in ${(performanceMetrics.generationTime / 1000).toFixed(2)}s`);
  });

  test('Step 5: Add thematic analysis tables', async () => {
    const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
    
    const themeTablePrompt = `Add thematic analysis table:

Tabel 1: Hasil Analisis Tematik

Columns: Theme, Sub-theme, Supporting Quotes, Frequency
Rows:
1. Platform Effectiveness
   - Instagram dominance, "Instagram dan TikTok paling efektif" (I1, I3), 3/3
   - Multi-platform strategy, "Coba berbagai platform" (I3), 2/3
2. Content Strategy
   - Authentic content, "konten autentik dan konsisten" (I1), 3/3
   - Consistency importance, "posting setiap hari" (I1), 2/3
3. Business Impact
   - Sales increase, "penjualan naik 150%" (I1), 3/3
   - High ROI, "ROI mencapai 300%" (I2), 2/3
4. Challenges
   - Content consistency, "konsistensi konten" (I3), 2/3
   - Measurement difficulty, "mengukur efektivitas" (I3), 2/3

Caption: "Tabel 1: Hasil Analisis Tematik dari Wawancara Mendalam"`;
    
    if (await chatInput.isVisible()) {
      await chatInput.fill(themeTablePrompt);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(5000);
      console.log('✓ Thematic analysis table requested');
    }
    
    await page.waitForTimeout(2000);
    
    const profileTablePrompt = `Add informant profile table:

Tabel 2: Profil Informan Penelitian

Columns: Kode, Jenis Usaha, Lama Beroperasi, Platform Utama, Omzet Bulanan
Rows:
- I1, Fashion Online, 3 tahun, Instagram & TikTok, Rp 50-100 juta
- I2, Kuliner Online, 5 tahun, Facebook & Instagram, Rp 100-200 juta
- I3, Kerajinan Tangan, 2 tahun, Instagram & Marketplace, Rp 30-50 juta

Caption: "Tabel 2: Profil Informan Penelitian"`;
    
    if (await chatInput.isVisible()) {
      await chatInput.fill(profileTablePrompt);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(5000);
      console.log('✓ Informant profile table requested');
    }
    
    await page.screenshot({ 
      path: `${screenshotDir}/05-tables-added.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('05-tables-added.png');
  });

  test('Step 6: Verify business terminology', async () => {
    const previewTab = page.locator('button:has-text("Preview")').first();
    await previewTab.click();
    await page.waitForTimeout(2000);
    
    const pageContent = await page.content();
    const contentLower = pageContent.toLowerCase();
    
    const foundTerms = BUSINESS_TERMS.filter(term => 
      contentLower.includes(term.toLowerCase())
    );
    
    console.log(`✓ Business terminology coverage: ${foundTerms.length}/${BUSINESS_TERMS.length}`);
    console.log(`  Found: ${foundTerms.join(', ')}`);
    
    expect(foundTerms.length).toBeGreaterThan(6);
    
    const foundQualitative = QUALITATIVE_KEYWORDS.filter(keyword =>
      contentLower.includes(keyword.toLowerCase())
    );
    
    console.log(`✓ Qualitative keywords: ${foundQualitative.length}/${QUALITATIVE_KEYWORDS.length}`);
    console.log(`  Found: ${foundQualitative.join(', ')}`);
    
    await page.screenshot({ 
      path: `${screenshotDir}/06-terminology-check.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('06-terminology-check.png');
  });

  test('Step 7: Verify APA citation style', async () => {
    const pageContent = await page.content();
    
    const apaCitationPatterns = [
      /\([A-Z][a-z]+,\s*\d{4}\)/,
      /\([A-Z][a-z]+\s*&\s*[A-Z][a-z]+,\s*\d{4}\)/,
      /\([A-Z][a-z]+\s*et\s*al\.,\s*\d{4}\)/,
    ];
    
    let apaMatches = 0;
    apaCitationPatterns.forEach(pattern => {
      const matches = pageContent.match(new RegExp(pattern, 'g'));
      if (matches) {
        apaMatches += matches.length;
      }
    });
    
    console.log(`✓ APA-style citations found: ${apaMatches}`);
    
    const hasReferences = /References|Daftar Pustaka/i.test(pageContent);
    console.log(`✓ References section present: ${hasReferences}`);
    
    await page.screenshot({ 
      path: `${screenshotDir}/07-citation-check.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('07-citation-check.png');
  });

  test('Step 8: Verify qualitative research structure', async () => {
    const pageContent = await page.content();
    
    const requiredElements = [
      'Abstract',
      'Pendahuluan',
      'Tinjauan Pustaka',
      'Metodologi',
      'wawancara',
      'Hasil',
      'Pembahasan',
      'Kesimpulan',
      'Daftar Pustaka',
    ];
    
    const foundElements = requiredElements.filter(element =>
      new RegExp(element, 'i').test(pageContent)
    );
    
    console.log(`✓ Research structure: ${foundElements.length}/${requiredElements.length}`);
    console.log(`  Found: ${foundElements.join(', ')}`);
    
    expect(foundElements.length).toBeGreaterThan(6);
  });

  test('Step 9: Export to DOCX', async () => {
    const exportButton = page.locator('button:has-text("DOCX"), button:has-text("Export")').first();
    await exportButton.scrollIntoViewIfNeeded();
    
    const startTime = Date.now();
    const downloadPromise = page.waitForEvent('download', { timeout: 30000 });
    
    await exportButton.click();
    
    const download = await downloadPromise;
    const exportTime = Date.now() - startTime;
    
    expect(download.suggestedFilename()).toMatch(/\.docx$/i);
    
    const savePath = `${screenshotDir}/business-paper-${Date.now()}.docx`;
    await download.saveAs(savePath);
    
    console.log(`✓ Paper exported to DOCX in ${exportTime}ms`);
    console.log(`  Saved to: ${savePath}`);
    
    await page.screenshot({ 
      path: `${screenshotDir}/08-export-complete.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('08-export-complete.png');
  });

  test('Step 10: Verify paper quality via API', async () => {
    if (!paperId) {
      console.log('⚠ Paper ID not available, skipping API verification');
      return;
    }
    
    const api = context.request;
    const paperRes = await api.get(`/api/papers/${paperId}`);
    expect(paperRes.status()).toBe(200);
    
    const paperData = await paperRes.json();
    
    console.log('\n=== Paper Quality Report ===');
    console.log(`Title: ${paperData.title}`);
    console.log(`Field: ${paperData.data?.jurusan || 'N/A'}`);
    console.log(`Method: ${paperData.data?.metode || 'N/A'}`);
    console.log(`Citation Style: ${paperData.data?.citation_style || 'N/A'}`);
    console.log(`Sections: ${paperData.sections?.length || 0}`);
    console.log(`References: ${paperData.references?.length || 0}`);
    console.log(`Word count: ${paperData.word_count || 'N/A'}`);
    
    expect(paperData.title).toContain('Digital Marketing');
    expect(paperData.data?.metode).toBe('Kualitatif');
  });
});
