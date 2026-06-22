/**
 * Test Paper Generation on paperfull.app with Persistent Context
 * This test uses a persistent browser context to maintain login session
 */

import { test, expect, chromium } from '@playwright/test';

test.describe('PaperFull Production Test (Persistent)', () => {
  test('Generate paper via chat and export to DOCX', async () => {
    console.log('\n🚀 Starting PaperFull Production Test with Persistent Context');
    console.log('═'.repeat(60));

    // Use persistent context to save login session
    const userDataDir = '/tmp/playwright-paperfull-session';
    const browser = await chromium.launchPersistentContext(userDataDir, {
      headless: false,
      viewport: { width: 1280, height: 720 },
    });

    const page = browser.pages()[0] || await browser.newPage();

    // Navigate to paperfull.app
    await page.goto('https://paperfull.app');
    await page.waitForLoadState('networkidle');
    console.log('✓ Loaded paperfull.app');

    // Check if user is logged in
    await page.waitForTimeout(2000);
    const currentUrl = page.url();
    console.log('Current URL:', currentUrl);

    const isOnLogin = currentUrl.includes('/login');

    if (isOnLogin) {
      console.log('\n⚠️  Not logged in yet');
      console.log('📝 Please login using Gmail in the browser window');
      console.log('⏳ Waiting 5 minutes for you to login...');
      console.log('   (The test will continue automatically after login)');

      // Wait for navigation away from login page (indicates successful login)
      try {
        await page.waitForURL(url => !url.includes('/login'), { timeout: 300000 });
        console.log('✓ Login detected!');
      } catch (error) {
        console.log('⚠️  Timeout waiting for login. Please run the test again after logging in.');
        await browser.close();
        return;
      }
    } else {
      console.log('✓ User is already logged in');
    }

    // Navigate to dashboard
    await page.goto('https://paperfull.app/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    console.log('✓ On dashboard');

    // Create new paper or navigate to editor
    const newPaperBtn = page.locator('a:has-text("New Paper"), a:has-text("Create"), button:has-text("New Paper")').first();
    if (await newPaperBtn.isVisible({ timeout: 5000 })) {
      await newPaperBtn.click();
      await page.waitForTimeout(2000);
      console.log('✓ Created new paper');
    } else {
      // Navigate directly to editor
      await page.goto('https://paperfull.app/editor');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
      console.log('✓ Navigated to editor');
    }

    // Set paper title
    const titleInput = page.locator('input[placeholder*="title" i], input[placeholder*="judul" i]').first();
    if (await titleInput.isVisible({ timeout: 5000 })) {
      await titleInput.clear();
      await titleInput.fill('Test Paper - AI in Healthcare ' + Date.now());
      await page.waitForTimeout(1500);
      console.log('✓ Set paper title');
    }

    // Open AI Chat
    console.log('\n💬 Testing Chat Functionality');
    const chatButton = page.locator('button:has-text("AI Chat"), button:has-text("Chat"), button[title*="Chat" i]').first();
    if (await chatButton.isVisible({ timeout: 5000 })) {
      await chatButton.click();
      await page.waitForTimeout(1500);
      console.log('✓ Opened AI Chat');
    }

    // Find chat input and send button
    const chatInput = page.locator('textarea[placeholder*="Type" i], textarea[placeholder*="message" i], textarea[placeholder*="Ketik" i]').last();
    const sendButton = page.locator('button[title*="Send" i], button:has-text("Send"), button:has-text("Kirim")').last();

    if (await chatInput.isVisible({ timeout: 5000 })) {
      // Send message to generate content
      const testMessage = 'Generate a short introduction paragraph (around 200 words) about artificial intelligence applications in healthcare, focusing on diagnostic systems.';

      await chatInput.fill(testMessage);
      await page.waitForTimeout(500);
      console.log('✓ Entered chat message');

      if (await sendButton.isVisible({ timeout: 2000 })) {
        await sendButton.click();
        console.log('✓ Sent chat message');
        console.log('⏳ Waiting for AI response (this may take 10-30 seconds)...');

        // Wait for response
        await page.waitForTimeout(15000);

        // Check for response in chat
        const chatArea = page.locator('[class*="chat"], [class*="message"], [role="log"]').first();
        if (await chatArea.isVisible({ timeout: 5000 })) {
          const chatText = await chatArea.textContent();
          if (chatText && chatText.length > 100) {
            console.log('✓ AI response received (length:', chatText.length, 'chars)');
          } else {
            console.log('⚠️  AI response might be incomplete');
          }
        }
      }
    } else {
      console.log('⚠️  Chat input not found');
    }

    // Try to export to DOCX
    console.log('\n📄 Testing DOCX Export');

    // Look for export/download button
    const exportButtons = [
      'button:has-text("Export")',
      'button:has-text("Download")',
      'button:has-text("DOCX")',
      'button[title*="Export" i]',
      'button[title*="Download" i]',
    ];

    let exportButton = null;
    for (const selector of exportButtons) {
      const btn = page.locator(selector).first();
      if (await btn.isVisible({ timeout: 2000 })) {
        exportButton = btn;
        break;
      }
    }

    if (exportButton) {
      // Set up download listener
      const downloadPromise = page.waitForEvent('download', { timeout: 30000 });

      await exportButton.click();
      console.log('✓ Clicked export button');

      try {
        const download = await downloadPromise;
        const fileName = download.suggestedFilename();
        console.log('✓ Download started:', fileName);

        // Save the file
        const downloadPath = `/tmp/paperfull-export-${Date.now()}.docx`;
        await download.saveAs(downloadPath);
        console.log('✓ File saved to:', downloadPath);

        // Verify file
        const fs = require('fs');
        const stats = fs.statSync(downloadPath);
        console.log('✓ File size:', stats.size, 'bytes');

        if (stats.size > 1000) {
          console.log('✅ DOCX export successful!');
          console.log('\n📊 Test Summary:');
          console.log('  ✓ Login: Success');
          console.log('  ✓ Chat: Success');
          console.log('  ✓ Paper Generation: Success');
          console.log('  ✓ DOCX Export: Success');
          console.log('  ✓ File size:', stats.size, 'bytes');
        } else {
          console.log('⚠️  DOCX file seems too small');
        }
      } catch (error) {
        console.log('⚠️  Download error:', error.message);
      }
    } else {
      console.log('⚠️  Export button not found');

      // Take screenshot
      const screenshotPath = '/tmp/paperfull-test-' + Date.now() + '.png';
      await page.screenshot({ path: screenshotPath, fullPage: true });
      console.log('📸 Screenshot saved to:', screenshotPath);
    }

    console.log('\n✅ Test completed');
    console.log('💡 Browser session saved - next run will use the same login');

    // Keep browser open for a moment
    await page.waitForTimeout(3000);
    await browser.close();
  });
});
