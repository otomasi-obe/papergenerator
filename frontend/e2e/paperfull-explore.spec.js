/**
 * Explore PaperFull page structure to find correct selectors
 */

import { test, expect, chromium } from '@playwright/test';

test.describe('PaperFull Page Explorer', () => {
  test('Explore editor page structure', async () => {
    console.log('\n🔍 Exploring PaperFull Editor Page');
    console.log('═'.repeat(60));

    const userDataDir = '/tmp/playwright-paperfull-session';
    const browser = await chromium.launchPersistentContext(userDataDir, {
      headless: false,
      viewport: { width: 1280, height: 720 },
    });

    const page = browser.pages()[0] || await browser.newPage();

    // Navigate to editor
    await page.goto('https://paperfull.app/editor');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    console.log('✓ Loaded editor page');

    // Take initial screenshot
    await page.screenshot({ path: '/tmp/paperfull-editor-initial.png', fullPage: true });
    console.log('📸 Screenshot: /tmp/paperfull-editor-initial.png');

    // Log all buttons on the page
    console.log('\n🔘 Buttons on page:');
    const buttons = await page.locator('button').all();
    for (let i = 0; i < Math.min(buttons.length, 20); i++) {
      const btn = buttons[i];
      const text = await btn.textContent().catch(() => '');
      const title = await btn.getAttribute('title').catch(() => '');
      const ariaLabel = await btn.getAttribute('aria-label').catch(() => '');
      if (text || title || ariaLabel) {
        console.log(`  ${i + 1}. "${text?.trim()}" | title="${title}" | aria-label="${ariaLabel}"`);
      }
    }

    // Log all textareas
    console.log('\n📝 Textareas on page:');
    const textareas = await page.locator('textarea').all();
    for (let i = 0; i < textareas.length; i++) {
      const ta = textareas[i];
      const placeholder = await ta.getAttribute('placeholder').catch(() => '');
      const ariaLabel = await ta.getAttribute('aria-label').catch(() => '');
      console.log(`  ${i + 1}. placeholder="${placeholder}" | aria-label="${ariaLabel}"`);
    }

    // Log all inputs
    console.log('\n📋 Inputs on page:');
    const inputs = await page.locator('input').all();
    for (let i = 0; i < Math.min(inputs.length, 15); i++) {
      const inp = inputs[i];
      const type = await inp.getAttribute('type').catch(() => '');
      const placeholder = await inp.getAttribute('placeholder').catch(() => '');
      const ariaLabel = await inp.getAttribute('aria-label').catch(() => '');
      if (placeholder || ariaLabel) {
        console.log(`  ${i + 1}. type="${type}" | placeholder="${placeholder}" | aria-label="${ariaLabel}"`);
      }
    }

    // Check for tabs or navigation
    console.log('\n📑 Looking for tabs/navigation:');
    const tabs = await page.locator('[role="tab"], button[class*="tab"]').all();
    for (let i = 0; i < tabs.length; i++) {
      const tab = tabs[i];
      const text = await tab.textContent().catch(() => '');
      console.log(`  ${i + 1}. "${text?.trim()}"`);
    }

    // Try to find and click chat/AI button
    console.log('\n💬 Looking for Chat/AI buttons:');
    const chatSelectors = [
      'button:has-text("Chat")',
      'button:has-text("AI")',
      'button[title*="chat" i]',
      'button[aria-label*="chat" i]',
      '[class*="chat"]',
    ];

    for (const selector of chatSelectors) {
      const elements = await page.locator(selector).all();
      if (elements.length > 0) {
        console.log(`  Found ${elements.length} elements matching: ${selector}`);
        for (let i = 0; i < Math.min(elements.length, 3); i++) {
          const text = await elements[i].textContent().catch(() => '');
          console.log(`    - "${text?.trim()}"`);
        }
      }
    }

    // Try clicking a chat button if found
    const chatBtn = page.locator('button:has-text("Chat"), button:has-text("AI Chat")').first();
    if (await chatBtn.isVisible({ timeout: 2000 })) {
      console.log('\n✓ Found chat button, clicking...');
      await chatBtn.click();
      await page.waitForTimeout(2000);

      // Take screenshot after clicking
      await page.screenshot({ path: '/tmp/paperfull-editor-chat-open.png', fullPage: true });
      console.log('📸 Screenshot after opening chat: /tmp/paperfull-editor-chat-open.png');

      // Log textareas again
      console.log('\n📝 Textareas after opening chat:');
      const textareasAfter = await page.locator('textarea').all();
      for (let i = 0; i < textareasAfter.length; i++) {
        const ta = textareasAfter[i];
        const placeholder = await ta.getAttribute('placeholder').catch(() => '');
        const visible = await ta.isVisible().catch(() => false);
        console.log(`  ${i + 1}. placeholder="${placeholder}" | visible=${visible}`);
      }
    }

    console.log('\n✅ Exploration complete');
    console.log('Check the screenshots to see the page structure');

    await page.waitForTimeout(2000);
    await browser.close();
  });
});
