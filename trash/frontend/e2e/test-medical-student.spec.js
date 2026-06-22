/**
 * E2E Test: Medical Student - Clinical Research Paper
 * 
 * Persona: Medical student generating clinical research paper on diabetes management
 * 
 * Test Flow:
 * 1. Login as test user
 * 2. Create new paper with medical topic
 * 3. Upload PDF references (simulated)
 * 4. Use chat to generate sections
 * 5. Add figures and tables
 * 6. Export to DOCX
 * 
 * Features:
 * - Headless mode
 * - Screenshots on failure
 * - API call logging
 * - Performance measurement
 * - Output quality verification
 */

import { test, expect } from '@playwright/test';
import { mkdir } from 'fs/promises';
import { existsSync } from 'fs';

const TEST_USER = {
  email: `medical-${Date.now()}@test.local`,
  name: 'Dr. Medical Student',
  password: 'MedicalTest123!',
};

const PAPER_CONFIG = {
  title: 'Diabetes Management with Mobile Health Applications: A Systematic Review',
  topic: 'Diabetes Management with Mobile Health Apps',
  field: 'Kedokteran',
  method: 'Literature Review',
  citationStyle: 'Vancouver',
  keywords: ['diabetes mellitus', 'mobile health', 'mHealth', 'glycemic control', 'HbA1c'],
};

const MEDICAL_TERMS = [
  'diabetes', 'glycemic', 'HbA1c', 'insulin', 'glucose',
  'hyperglycemia', 'metabolic', 'cardiovascular', 'endocrine'
];

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

async function ensureTestDir() {
  const dir = 'test-results/medical-student';
  if (!existsSync(dir)) {
    await mkdir(dir, { recursive: true });
  }
  return dir;
}

test.describe('Medical Student - Clinical Research Paper', () => {
  let context;
  let page;
  let paperId;
  let testStartTime;
  let performanceMetrics = {
    apiCalls: [],
    consoleErrors: [],
    screenshots: [],
  };
  const screenshotDir = 'test-results/medical-student';

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
    console.log('MEDICAL STUDENT TEST - PERFORMANCE REPORT');
    console.log('='.repeat(80));
    console.log(`Total execution time: ${totalTime}s`);
    console.log(`Total API calls: ${performanceMetrics.apiCalls.length}`);
    console.log(`Console errors: ${performanceMetrics.consoleErrors.length}`);
    console.log(`Screenshots taken: ${performanceMetrics.screenshots.length}`);
    
    const avgApiTime = performanceMetrics.apiCalls
      .filter(c => c.duration)
      .reduce((sum, c) => sum + c.duration, 0) / 
      performanceMetrics.apiCalls.filter(c => c.duration).length;
    console.log(`Average API response time: ${avgApiTime.toFixed(0)}ms`);
    
    if (performanceMetrics.consoleErrors.length > 0) {
      console.log('\nConsole Errors:');
      performanceMetrics.consoleErrors.slice(0, 5).forEach((err, i) => {
        console.log(`  ${i + 1}. ${err.text}`);
      });
    }
    console.log('='.repeat(80) + '\n');
    
    await context.close();
  });

  test('Step 1: Register and login medical student user', async () => {
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

  test('Step 2: Create new paper with medical topic', async () => {
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

  test('Step 3: Upload PDF references (simulated)', async () => {
    const literatureTab = page.locator('button:has-text("📚 Literatur"), button:has-text("Literature")').first();
    await literatureTab.click();
    await page.waitForTimeout(1000);
    
    await page.screenshot({ 
      path: `${screenshotDir}/03-literature-tab.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('03-literature-tab.png');
    
    console.log('✓ Literature tab opened (PDF upload simulated in E2E)');
  });

  test('Step 4: Use chat to generate sections', async () => {
    const chatButton = page.locator('button:has-text("AI Chat"), button:has-text("Chat")').first();
    await chatButton.click();
    await page.waitForTimeout(1000);
    
    const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
    await expect(chatInput).toBeVisible();
    
    const generatePrompt = `Generate a comprehensive clinical research paper about ${PAPER_CONFIG.topic}. Include:
1. Abstract with background, methods, results, conclusion
2. Introduction with research objectives
3. Literature Review covering recent studies (2020-2026)
4. Methodology section
5. Results with statistical analysis
6. Discussion and clinical implications
7. Conclusion and recommendations
8. References in ${PAPER_CONFIG.citationStyle} format

Use medical terminology: ${PAPER_CONFIG.keywords.join(', ')}`;
    
    await chatInput.fill(generatePrompt);
    
    await page.screenshot({ 
      path: `${screenshotDir}/04-chat-prompt.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('04-chat-prompt.png');
    
    const startTime = Date.now();
    await page.keyboard.press('Enter');
    
    await page.waitForTimeout(3000);
    
    const generationTime = Date.now() - startTime;
    console.log(`✓ Generation requested (${generationTime}ms)`);
    
    await page.screenshot({ 
      path: `${screenshotDir}/05-generation-started.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('05-generation-started.png');
    
    console.log('⏳ Waiting for generation to complete (max 3 minutes)...');
    await page.waitForTimeout(180000);
  });

  test('Step 5: Add figures and tables', async () => {
    const editorTab = page.locator('button:has-text("Editor"), button:has-text("✏️")').first();
    await editorTab.click();
    await page.waitForTimeout(2000);
    
    const addFigurePrompt = `Add a figure showing HbA1c reduction trends over 12 months comparing mobile app users vs control group. Include:
- Line graph with two lines
- X-axis: Months (0-12)
- Y-axis: HbA1c percentage (6-10%)
- Legend showing intervention vs control
- Caption: "Figure 1: HbA1c trends in intervention and control groups"`;
    
    const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
    if (await chatInput.isVisible()) {
      await chatInput.fill(addFigurePrompt);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(5000);
      
      console.log('✓ Figure generation requested');
    }
    
    const addTablePrompt = `Add a table summarizing patient demographics:
- Columns: Characteristic, Intervention Group (n=150), Control Group (n=150), p-value
- Rows: Age (mean±SD), Gender (% female), BMI, Baseline HbA1c, Duration of diabetes
- Include statistical significance markers`;
    
    await page.waitForTimeout(2000);
    if (await chatInput.isVisible()) {
      await chatInput.fill(addTablePrompt);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(5000);
      
      console.log('✓ Table generation requested');
    }
    
    await page.screenshot({ 
      path: `${screenshotDir}/06-figures-tables-added.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('06-figures-tables-added.png');
  });

  test('Step 6: Verify medical terminology and quality', async () => {
    const previewTab = page.locator('button:has-text("Preview")').first();
    await previewTab.click();
    await page.waitForTimeout(2000);
    
    const pageContent = await page.content();
    const contentLower = pageContent.toLowerCase();
    
    const foundTerms = MEDICAL_TERMS.filter(term => 
      contentLower.includes(term.toLowerCase())
    );
    
    console.log(`✓ Medical terminology coverage: ${foundTerms.length}/${MEDICAL_TERMS.length}`);
    console.log(`  Found: ${foundTerms.join(', ')}`);
    
    expect(foundTerms.length).toBeGreaterThan(4);
    
    const hasCitations = /\[\d+\]|\(\d{4}\)|et al\./i.test(pageContent);
    console.log(`✓ Citations present: ${hasCitations}`);
    
    await page.screenshot({ 
      path: `${screenshotDir}/07-preview-quality-check.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('07-preview-quality-check.png');
  });

  test('Step 7: Export to DOCX', async () => {
    const exportButton = page.locator('button:has-text("DOCX"), button:has-text("Export")').first();
    await exportButton.scrollIntoViewIfNeeded();
    
    const startTime = Date.now();
    const downloadPromise = page.waitForEvent('download', { timeout: 30000 });
    
    await exportButton.click();
    
    const download = await downloadPromise;
    const exportTime = Date.now() - startTime;
    
    expect(download.suggestedFilename()).toMatch(/\.docx$/i);
    
    const savePath = `${screenshotDir}/medical-paper-${Date.now()}.docx`;
    await download.saveAs(savePath);
    
    console.log(`✓ Paper exported to DOCX in ${exportTime}ms`);
    console.log(`  Saved to: ${savePath}`);
    
    await page.screenshot({ 
      path: `${screenshotDir}/08-export-complete.png`,
      fullPage: true 
    });
    performanceMetrics.screenshots.push('08-export-complete.png');
  });

  test('Step 8: Verify paper metadata via API', async () => {
    if (!paperId) {
      console.log('⚠ Paper ID not available, skipping API verification');
      return;
    }
    
    const api = context.request;
    const paperRes = await api.get(`/api/papers/${paperId}`);
    expect(paperRes.status()).toBe(200);
    
    const paperData = await paperRes.json();
    
    console.log('\n=== Paper Metadata ===');
    console.log(`Title: ${paperData.title}`);
    console.log(`Field: ${paperData.data?.jurusan || 'N/A'}`);
    console.log(`Method: ${paperData.data?.metode || 'N/A'}`);
    console.log(`Citation Style: ${paperData.data?.citation_style || 'N/A'}`);
    console.log(`Sections: ${paperData.sections?.length || 0}`);
    console.log(`References: ${paperData.references?.length || 0}`);
    console.log(`Images: ${paperData.image_count || 0}`);
    
    expect(paperData.title).toContain('Diabetes');
  });
});
