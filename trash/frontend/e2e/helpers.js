/**
 * E2E Test Helpers
 * 
 * Shared utilities for Playwright tests
 */

/**
 * Extract CSRF token from cookies
 */
export function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

/**
 * Wait for element with custom timeout
 */
export async function waitForElement(page, selector, timeout = 10000) {
  return page.waitForSelector(selector, { timeout, state: 'visible' });
}

/**
 * Wait for AI generation to complete
 */
export async function waitForAiGeneration(page, maxWaitMs = 180000) {
  const statusBanner = page.locator('div:has-text("AI sedang generate"), div:has-text("generate paper")');
  
  let elapsed = 0;
  const interval = 5000;

  while (elapsed < maxWaitMs) {
    await page.waitForTimeout(interval);
    elapsed += interval;

    const isGenerating = await statusBanner.isVisible().catch(() => false);
    
    if (!isGenerating) {
      return { success: true, elapsed };
    }
  }

  return { success: false, elapsed };
}

/**
 * Create a test user with unique email
 */
export function createTestUser(prefix = 'test') {
  return {
    email: `${prefix}-${Date.now()}@e2e.local`,
    name: `${prefix.charAt(0).toUpperCase() + prefix.slice(1)} User`,
    password: 'TestPass123!',
  };
}

/**
 * Register and login a user
 */
export async function registerAndLogin(context, user) {
  const api = context.request;
  
  const reg = await api.post('/api/auth/register', {
    data: { ...user, captcha_token: '1x00000000000000000000AA' },
  });
  
  if (reg.status() !== 201) {
    throw new Error(`Registration failed: ${reg.status()}`);
  }
  
  return await reg.json();
}

/**
 * Create a new paper via API
 */
export async function createPaper(context, title = 'Test Paper') {
  const api = context.request;
  const cookies = await context.cookies();
  
  const res = await api.post('/api/papers', {
    data: { title, data: {} },
    headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
  });
  
  if (res.status() !== 200) {
    throw new Error(`Paper creation failed: ${res.status()}`);
  }
  
  return await res.json();
}

/**
 * Upload a file to a paper
 */
export async function uploadFile(page, filePath) {
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(filePath);
  
  // Wait for upload to complete
  await page.waitForTimeout(2000);
}

/**
 * Send a chat message and wait for response
 */
export async function sendChatMessage(page, message, waitForResponse = true) {
  const chatInput = page.locator('textarea[placeholder*="Type"], textarea[placeholder*="message"]').last();
  const sendBtn = page.locator('button[title*="Send"], button:has-text("Send")').last();
  
  await chatInput.fill(message);
  await sendBtn.click();
  
  if (waitForResponse) {
    // Wait for AI to respond (look for new message)
    await page.waitForTimeout(3000);
  }
}

/**
 * Switch to a specific tab in the editor
 */
export async function switchToTab(page, tabName) {
  const tab = page.locator(`button:has-text("${tabName}")`).first();
  await tab.click();
  await page.waitForTimeout(1000);
}

/**
 * Get paper metrics from the page
 */
export async function getPaperMetrics(page) {
  const metrics = {
    title: '',
    abstractLength: 0,
    keywordCount: 0,
    sectionCount: 0,
    referenceCount: 0,
  };
  
  // Title
  const titleInput = page.locator('input[placeholder*="Paper title"]').first();
  if (await titleInput.isVisible()) {
    metrics.title = await titleInput.inputValue();
  }
  
  // Abstract
  const abstractField = page.locator('textarea[placeholder*="abstract"]').first();
  if (await abstractField.isVisible()) {
    const abstract = await abstractField.inputValue();
    metrics.abstractLength = abstract.length;
  }
  
  // Keywords
  const keywords = page.locator('[class*="keyword"]');
  metrics.keywordCount = await keywords.count();
  
  // Sections
  const sections = page.locator('[class*="section"]');
  metrics.sectionCount = await sections.count();
  
  return metrics;
}

/**
 * Verify paper quality
 */
export async function verifyPaperQuality(page) {
  const issues = [];
  
  // Check title
  const titleInput = page.locator('input[placeholder*="Paper title"]').first();
  if (await titleInput.isVisible()) {
    const title = await titleInput.inputValue();
    if (title.length < 10) {
      issues.push('Title too short');
    }
  } else {
    issues.push('Title field not found');
  }
  
  // Check abstract
  const abstractField = page.locator('textarea[placeholder*="abstract"]').first();
  if (await abstractField.isVisible()) {
    const abstract = await abstractField.inputValue();
    if (abstract.length < 50) {
      issues.push('Abstract too short');
    }
  }
  
  // Check for placeholder text
  const pageText = await page.textContent('body');
  if (/\[TODO\]|\[PLACEHOLDER\]|\[INSERT.*\]|Lorem ipsum/i.test(pageText)) {
    issues.push('Placeholder text detected');
  }
  
  return {
    isValid: issues.length === 0,
    issues,
  };
}

/**
 * Take a screenshot with timestamp
 */
export async function takeTimestampedScreenshot(page, name) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `${name}-${timestamp}.png`;
  await page.screenshot({ path: `/tmp/kilo/${filename}`, fullPage: true });
  return filename;
}

/**
 * Format duration in human-readable format
 */
export function formatDuration(ms) {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  
  if (minutes > 0) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  return `${seconds}s`;
}

/**
 * Create metrics tracker
 */
export function createMetricsTracker() {
  return {
    startTime: Date.now(),
    endTime: 0,
    clicks: 0,
    aiInteractions: 0,
    filesUploaded: 0,
    sectionsEdited: 0,
    referencesAdded: 0,
    chartsGenerated: 0,
    
    trackClick() {
      this.clicks++;
    },
    
    trackAiInteraction() {
      this.aiInteractions++;
    },
    
    trackFileUpload() {
      this.filesUploaded++;
    },
    
    trackSectionEdit() {
      this.sectionsEdited++;
    },
    
    trackReferenceAdd() {
      this.referencesAdded++;
    },
    
    trackChartGeneration() {
      this.chartsGenerated++;
    },
    
    finish() {
      this.endTime = Date.now();
    },
    
    getTotalTime() {
      return this.endTime - this.startTime;
    },
    
    getReport() {
      const totalTime = this.getTotalTime();
      return {
        totalTime,
        totalTimeFormatted: formatDuration(totalTime),
        clicks: this.clicks,
        aiInteractions: this.aiInteractions,
        filesUploaded: this.filesUploaded,
        sectionsEdited: this.sectionsEdited,
        referencesAdded: this.referencesAdded,
        chartsGenerated: this.chartsGenerated,
        clicksPerMinute: (this.clicks / (totalTime / 60000)).toFixed(1),
        avgTimePerPhase: Math.round(totalTime / 13),
      };
    },
    
    printReport() {
      const report = this.getReport();
      console.log('\n📊 METRICS REPORT');
      console.log('═'.repeat(60));
      console.log(`⏱️  Total Time: ${report.totalTimeFormatted}`);
      console.log(`🖱️  Total Clicks: ${report.clicks} (${report.clicksPerMinute}/min)`);
      console.log(`🤖 AI Interactions: ${report.aiInteractions}`);
      console.log(`📁 Files Uploaded: ${report.filesUploaded}`);
      console.log(`✏️  Sections Edited: ${report.sectionsEdited}`);
      console.log(`📚 References Added: ${report.referencesAdded}`);
      console.log(`📊 Charts Generated: ${report.chartsGenerated}`);
      console.log(`⚡ Avg Time/Phase: ${report.avgTimePerPhase}s`);
      console.log('═'.repeat(60));
    },
  };
}

/**
 * Wait for download and save it
 */
export async function waitForDownload(page, triggerFn, timeout = 30000) {
  const downloadPromise = page.waitForEvent('download', { timeout });
  await triggerFn();
  const download = await downloadPromise;
  return download;
}

/**
 * Check if server is healthy
 */
export async function checkServerHealth(baseURL) {
  try {
    const response = await fetch(`${baseURL}/api/health`);
    const data = await response.json();
    return data.status === 'ok';
  } catch (error) {
    return false;
  }
}
