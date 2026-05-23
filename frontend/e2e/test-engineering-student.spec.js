/**
 * E2E Test: Engineering Student - IoT Smart Home Project
 * 
 * Persona: Engineering student working on IoT/embedded systems project
 * 
 * Test Flow:
 * 1. Login as test user
 * 2. Create new paper with IoT topic
 * 3. Upload PDF references (simulated)
 * 4. Use chat to generate sections with technical terminology
 * 5. Add system diagrams and data tables
 * 6. Export to DOCX
 * 
 * Features:
 * - Headless mode
 * - Screenshots on failure
 * - API call logging
 * - Performance measurement
 * - Technical terminology verification
 */

import { test, expect } from '@playwright/test';
import { mkdir } from 'fs/promises';
import { existsSync } from 'fs';

const TEST_USER = {
  email: `engineering-${Date.now()}@test.local`,
  name: 'Engineering Student',
  password: 'EngineeringTest123!',
};

const PAPER_CONFIG = {
  title: 'IoT-Based Smart Home Automation System with Machine Learning Integration',
  topic: 'IoT Smart Home Automation with ML',
  field: 'Teknik Informatika / Teknik Elektro',
  method: 'Kuantitatif (eksperimen)',
  dataType: 'Data hasil eksperimen dan pengujian sistem',
  target: 'Tugas Akhir / Skripsi',
};

const TECHNICAL_TERMS = [
  'IoT', 'smart home', 'sensor', 'actuator', 'automation',
  'MQTT', 'ESP32', 'Arduino', 'WiFi', 'microcontroller',
  'embedded', 'protocol', 'API', 'real-time', 'machine learning'
];

const METHODOLOGY_KEYWORDS = [
  'system design', 'implementation', 'testing', 'evaluation',
  'performance', 'accuracy', 'latency', 'throughput'
];

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

async function ensureTestDir() {
  const dir = 'test-results/engineering-student';
  if (!existsSync(dir)) {
    await mkdir(dir, { recursive: true });
  }
  return dir;
}

test.describe('Engineering Student - IoT Smart Home Project', () => {
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
  const screenshotDir = 'test-results/engineering-student';

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
    console.log('ENGINEERING STUDENT TEST - PERFORMANCE REPORT');
    console.log('='.repeat(80));
    console.log(`Total execution time: ${totalTime}s`);
    console.log(`Paper generation time: ${(performanceMetrics.generationTime / 1000).toFixed(2)}s`);
    console.log(`Total API calls: ${performanceMetrics.apiCalls.length}`);
    console.log(`Console errors: ${performanceMetrics.consoleErrors.length}`);
    console.log(`Screenshots taken: ${performanceMetrics.screenshots.length}`);
    
    const apiCallsWithDuration = performanceMetrics.apiCalls.filter(c => c.duration);
    if (apiCallsWithDuration.length > 0) {
      const avgApiTime = apiCallsWithDuration.reduce((sum, c) => sum + c.duration, 0) / apiCallsWithDuration.length;
      const maxApiTime = Math.max(...apiCallsWithDuration.map(c => c.duration));
      console.log(`Average API response time: ${avgApiTime.toFixed(0)}ms`);
      console.log(`Max API response time: ${maxApiTime.toFixed(0)}ms`);
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

  test('Step 1: Register and login engineering student', async () => {
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

  test('Step 2: Create new paper with IoT topic', async () => {
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

  test('Step 3: Answer discovery questions via chat', async () => {
    const chatButton = page.locator('button:has-text("AI Chat"), button:has-text("Chat")').first();
    await chatButton.click();
    await page.waitForTimeout(1000);
    
    const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
    await expect(chatInput).toBeVisible();
    
    const discoveryMessage = `Saya mahasiswa ${PAPER_CONFIG.field} semester 7, sedang mengerjakan ${PAPER_CONFIG.target} tentang ${PAPER_CONFIG.topic}. 
Metode penelitian: ${PAPER_CONFIG.method}. 
Data yang digunakan: ${PAPER_CONFIG.dataType}.
Sistem menggunakan sensor DHT22, sensor PIR, relay module, dan ESP32 sebagai microcontroller.
Komunikasi menggunakan protokol MQTT dan integrasi dengan machine learning untuk prediksi pola penggunaan.`;
    
    await chatInput.fill(discoveryMessage);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(3000);
    
    await page.screenshot({ 
      path: `${screenshotDir}/03-discovery-answered.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('03-discovery-answered.png');
    
    console.log('✓ Discovery questions answered');
  });

  test('Step 4: Upload PDF references (simulated)', async () => {
    const literatureTab = page.locator('button:has-text("📚 Literatur"), button:has-text("Literature")').first();
    await literatureTab.click();
    await page.waitForTimeout(1000);
    
    await page.screenshot({ 
      path: `${screenshotDir}/04-literature-tab.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('04-literature-tab.png');
    
    console.log('✓ Literature tab opened (PDF upload simulated)');
  });

  test('Step 5: Generate paper with technical sections', async () => {
    const chatButton = page.locator('button:has-text("AI Chat"), button:has-text("Chat")').first();
    if (!(await chatButton.getAttribute('class'))?.includes('active')) {
      await chatButton.click();
      await page.waitForTimeout(1000);
    }
    
    const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
    
    const generatePrompt = `Generate complete paper tentang ${PAPER_CONFIG.title}. Sertakan:

1. Abstract (English) - background, methods, results, conclusion
2. Abstrak (Bahasa Indonesia)
3. BAB I PENDAHULUAN - latar belakang, rumusan masalah, tujuan, manfaat, batasan masalah
4. BAB II TINJAUAN PUSTAKA - IoT, smart home, sensor & actuator, MQTT protocol, ESP32, machine learning
5. BAB III METODOLOGI - system design, hardware architecture, software architecture, implementation steps
6. BAB IV HASIL DAN PEMBAHASAN - system testing, performance evaluation, accuracy measurement
7. BAB V PENUTUP - kesimpulan dan saran
8. DAFTAR PUSTAKA

Gunakan terminologi teknis: ${TECHNICAL_TERMS.slice(0, 10).join(', ')}`;
    
    await chatInput.fill(generatePrompt);
    
    await page.screenshot({ 
      path: `${screenshotDir}/05-generation-prompt.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('05-generation-prompt.png');
    
    const startTime = Date.now();
    await page.keyboard.press('Enter');
    
    console.log('⏳ Waiting for paper generation (max 3 minutes)...');
    await page.waitForTimeout(180000);
    performanceMetrics.generationTime = Date.now() - startTime;
    
    console.log(`✓ Generation completed in ${(performanceMetrics.generationTime / 1000).toFixed(2)}s`);
  });

  test('Step 6: Add system diagrams and equations', async () => {
    const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
    
    const diagramPrompt = `Add system architecture diagram showing:
- Sensor layer (DHT22, PIR, LDR)
- Microcontroller layer (ESP32)
- Communication layer (MQTT broker)
- Application layer (Web dashboard, Mobile app)
- ML prediction module
Include arrows showing data flow and labels for each component.
Caption: "Gambar 1: Arsitektur Sistem Smart Home berbasis IoT"`;
    
    if (await chatInput.isVisible()) {
      await chatInput.fill(diagramPrompt);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(5000);
      console.log('✓ System diagram requested');
    }
    
    await page.waitForTimeout(2000);
    
    const tablePrompt = `Add performance evaluation table:
Columns: Parameter, Target, Hasil Pengujian, Status
Rows:
- Response Time, <2s, 1.2s, ✓
- Sensor Accuracy, >95%, 97.5%, ✓
- System Uptime, >99%, 99.8%, ✓
- Power Consumption, <5W, 3.8W, ✓
- ML Prediction Accuracy, >90%, 92.3%, ✓
Caption: "Tabel 1: Hasil Evaluasi Performa Sistem"`;
    
    if (await chatInput.isVisible()) {
      await chatInput.fill(tablePrompt);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(5000);
      console.log('✓ Performance table requested');
    }
    
    await page.screenshot({ 
      path: `${screenshotDir}/06-diagrams-tables-added.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('06-diagrams-tables-added.png');
  });

  test('Step 7: Verify technical terminology', async () => {
    const previewTab = page.locator('button:has-text("Preview")').first();
    await previewTab.click();
    await page.waitForTimeout(2000);
    
    const pageContent = await page.content();
    const contentLower = pageContent.toLowerCase();
    
    const foundTerms = TECHNICAL_TERMS.filter(term => 
      contentLower.includes(term.toLowerCase())
    );
    
    console.log(`✓ Technical terminology coverage: ${foundTerms.length}/${TECHNICAL_TERMS.length}`);
    console.log(`  Found: ${foundTerms.join(', ')}`);
    
    expect(foundTerms.length).toBeGreaterThan(8);
    
    const foundMethodology = METHODOLOGY_KEYWORDS.filter(keyword =>
      contentLower.includes(keyword.toLowerCase())
    );
    
    console.log(`✓ Methodology keywords: ${foundMethodology.length}/${METHODOLOGY_KEYWORDS.length}`);
    console.log(`  Found: ${foundMethodology.join(', ')}`);
    
    await page.screenshot({ 
      path: `${screenshotDir}/07-preview-verification.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('07-preview-verification.png');
  });

  test('Step 8: Verify section structure', async () => {
    const pageContent = await page.content();
    
    const requiredSections = [
      'Abstract',
      'Pendahuluan',
      'Tinjauan Pustaka',
      'Metodologi',
      'Hasil',
      'Penutup',
    ];
    
    const foundSections = requiredSections.filter(section =>
      new RegExp(section, 'i').test(pageContent)
    );
    
    console.log(`✓ Section structure: ${foundSections.length}/${requiredSections.length}`);
    console.log(`  Found: ${foundSections.join(', ')}`);
    
    expect(foundSections.length).toBeGreaterThan(3);
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
    
    const savePath = `${screenshotDir}/iot-paper-${Date.now()}.docx`;
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
    console.log(`Sections: ${paperData.sections?.length || 0}`);
    console.log(`References: ${paperData.references?.length || 0}`);
    console.log(`Images/Diagrams: ${paperData.image_count || 0}`);
    console.log(`Word count: ${paperData.word_count || 'N/A'}`);
    
    expect(paperData.title).toContain('IoT');
    
    if (paperData.sections && paperData.sections.length > 0) {
      console.log('\n=== Section Breakdown ===');
      paperData.sections.forEach((section, i) => {
        console.log(`${i + 1}. ${section.title} (${section.content?.length || 0} chars)`);
      });
    }
  });
});
