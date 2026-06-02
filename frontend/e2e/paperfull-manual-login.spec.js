/**
 * Test PaperFull with Manual Login
 * This test will wait for you to login manually, then test paper generation
 */

import { test, expect, chromium } from '@playwright/test';

test.describe('PaperFull Manual Login Test', () => {
  test('Login manually and test paper generation', async () => {
    console.log('\n🚀 PaperFull Test - Manual Login');
    console.log('═'.repeat(60));

    const browser = await chromium.launch({
      headless: false,
      slowMo: 500, // Slow down actions for visibility
    });

    const context = await browser.newContext({
      viewport: { width: 1400, height: 900 },
    });

    const page = await context.newPage();

    // Navigate to paperfull.app
    await page.goto('https://paperfull.app');
    await page.waitForLoadState('networkidle');
    console.log('✓ Loaded paperfull.app');

    // Check if on login page
    await page.waitForTimeout(2000);
    const isOnLogin = page.url().includes('/login') ||
                      await page.locator('button:has-text("Sign In")').isVisible().catch(() => false);

    if (isOnLogin) {
      console.log('\n📝 PLEASE LOGIN NOW');
      console.log('   1. Click "Continue with Google" or enter email/password');
      console.log('   2. Complete the login process');
      console.log('   3. Wait for dashboard to load');
      console.log('\n⏳ Waiting up to 2 minutes for login...\n');

      // Wait for navigation away from login (indicates successful login)
      try {
        await page.waitForFunction(
          () => !window.location.href.includes('/login') &&
                (window.location.href.includes('/dashboard') || window.location.href.includes('/editor')),
          { timeout: 120000 }
        );
        console.log('✅ Login successful!');
        await page.waitForTimeout(2000);
      } catch (error) {
        console.log('❌ Login timeout. Please try again.');
        await browser.close();
        return;
      }
    } else {
      console.log('✓ Already logged in');
    }

    // Navigate to dashboard
    console.log('\n📊 Navigating to dashboard...');
    await page.goto('https://paperfull.app/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Check if we have papers or need to create one
    const hasPapers = await page.locator('h1:has-text("My Papers")').isVisible().catch(() => false);
    console.log(hasPapers ? '✓ Dashboard loaded' : '⚠️  Dashboard layout different');

    // Navigate to editor (create new paper)
    console.log('\n📝 Opening editor...');
    const newPaperBtn = page.locator('a:has-text("New Paper"), a:has-text("Create")').first();
    if (await newPaperBtn.isVisible({ timeout: 5000 })) {
      await newPaperBtn.click();
      await page.waitForTimeout(2000);
    } else {
      await page.goto('https://paperfull.app/editor');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
    }
    console.log('✓ Editor opened');

    // Take screenshot of editor
    await page.screenshot({ path: '/tmp/paperfull-editor-view.png', fullPage: false });
    console.log('📸 Screenshot: /tmp/paperfull-editor-view.png');

    // Set paper title
    console.log('\n📋 Setting paper title...');
    const titleSelectors = [
      'input[placeholder*="title" i]',
      'input[placeholder*="judul" i]',
      'input[type="text"]',
    ];

    let titleSet = false;
    for (const selector of titleSelectors) {
      const titleInput = page.locator(selector).first();
      if (await titleInput.isVisible({ timeout: 2000 })) {
        await titleInput.click();
        await titleInput.fill('Test Paper - AI Healthcare ' + Date.now());
        await page.waitForTimeout(1000);
        console.log('✓ Paper title set');
        titleSet = true;
        break;
      }
    }

    if (!titleSet) {
      console.log('⚠️  Could not find title input');
    }

    // Look for Chat button
    console.log('\n💬 Looking for Chat functionality...');
    const chatSelectors = [
      'button:has-text("AI Chat")',
      'button:has-text("Chat")',
      'button[title*="chat" i]',
      '[aria-label*="chat" i]',
    ];

    let chatOpened = false;
    for (const selector of chatSelectors) {
      const chatBtn = page.locator(selector).first();
      if (await chatBtn.isVisible({ timeout: 2000 })) {
        console.log(`✓ Found chat button: ${selector}`);
        await chatBtn.click();
        await page.waitForTimeout(2000);
        chatOpened = true;

        // Take screenshot after opening chat
        await page.screenshot({ path: '/tmp/paperfull-chat-opened.png', fullPage: false });
        console.log('📸 Screenshot: /tmp/paperfull-chat-opened.png');
        break;
      }
    }

    if (!chatOpened) {
      console.log('⚠️  Chat button not found. Checking page structure...');

      // Log visible buttons
      const buttons = await page.locator('button:visible').all();
      console.log(`   Found ${buttons.length} visible buttons`);
      for (let i = 0; i < Math.min(buttons.length, 10); i++) {
        const text = await buttons[i].textContent();
        if (text && text.trim()) {
          console.log(`   - "${text.trim()}"`);
        }
      }
    }

    // Try to find chat input
    console.log('\n✍️  Looking for chat input...');
    const chatInputSelectors = [
      'textarea[placeholder*="type" i]',
      'textarea[placeholder*="message" i]',
      'textarea[placeholder*="ketik" i]',
      'textarea',
      'input[type="text"][placeholder*="message" i]',
    ];

    let messageSet = false;
    for (const selector of chatInputSelectors) {
      const chatInput = page.locator(selector).last();
      if (await chatInput.isVisible({ timeout: 2000 })) {
        console.log(`✓ Found chat input: ${selector}`);

        const testMessage = 'Generate a brief introduction paragraph about AI in healthcare (around 150 words).';
        await chatInput.fill(testMessage);
        await page.waitForTimeout(500);
        console.log('✓ Message entered');

        // Look for send button
        const sendBtn = page.locator('button[title*="send" i], button:has-text("Send"), button:has-text("Kirim")').last();
        if (await sendBtn.isVisible({ timeout: 2000 })) {
          await sendBtn.click();
          console.log('✓ Message sent');
          console.log('⏳ Waiting for AI response (20 seconds)...');
          await page.waitForTimeout(20000);
          console.log('✓ Response time elapsed');
          messageSet = true;
        }
        break;
      }
    }

    if (!messageSet) {
      console.log('⚠️  Could not find chat input');
    }

    // Look for export/download button
    console.log('\n📥 Looking for export functionality...');
    const exportSelectors = [
      'button:has-text("Export")',
      'button:has-text("Download")',
      'button:has-text("DOCX")',
      'button[title*="export" i]',
      'button[title*="download" i]',
    ];

    let exportFound = false;
    for (const selector of exportSelectors) {
      const exportBtn = page.locator(selector).first();
      if (await exportBtn.isVisible({ timeout: 2000 })) {
        console.log(`✓ Found export button: ${selector}`);

        // Set up download listener
        const downloadPromise = page.waitForEvent('download', { timeout: 30000 });

        await exportBtn.click();
        console.log('✓ Clicked export button');

        try {
          const download = await downloadPromise;
          const fileName = download.suggestedFilename();
          const downloadPath = `/tmp/paperfull-export-${Date.now()}.docx`;
          await download.saveAs(downloadPath);

          const fs = require('fs');
          const stats = fs.statSync(downloadPath);

          console.log('✅ DOCX EXPORT SUCCESS!');
          console.log(`   File: ${fileName}`);
          console.log(`   Size: ${stats.size} bytes`);
          console.log(`   Path: ${downloadPath}`);

          exportFound = true;
        } catch (error) {
          console.log('⚠️  Download timeout:', error.message);
        }
        break;
      }
    }

    if (!exportFound) {
      console.log('⚠️  Export button not found');
    }

    // Final screenshot
    await page.screenshot({ path: '/tmp/paperfull-final.png', fullPage: true });
    console.log('\n📸 Final screenshot: /tmp/paperfull-final.png');

    console.log('\n' + '═'.repeat(60));
    console.log('✅ TEST COMPLETED');
    console.log('═'.repeat(60));

    // Keep browser open for review
    console.log('\n💡 Browser will stay open for 10 seconds for review...');
    await page.waitForTimeout(10000);

    await browser.close();
  });
});
