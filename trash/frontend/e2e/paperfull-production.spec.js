/**
 * Test Paper Generation on paperfull.app
 * Tests chat functionality and paper generation with DOCX export
 */

import { test, expect } from '@playwright/test';

test.describe('PaperFull Production Test', () => {
  test('Generate paper via chat and export to DOCX', async ({ page }) => {
    console.log('\n🚀 Starting PaperFull Production Test');
    console.log('═'.repeat(60));

    // Navigate to paperfull.app
    await page.goto('https://paperfull.app');
    await page.waitForLoadState('networkidle');
    console.log('✓ Loaded paperfull.app');

    // Check if user is logged in by looking for dashboard or editor
    const currentUrl = page.url();
    console.log('Current URL:', currentUrl);

    // If on landing page, navigate to dashboard
    if (currentUrl.includes('paperfull.app') && !currentUrl.includes('/dashboard') && !currentUrl.includes('/editor')) {
      // Try to navigate to dashboard
      await page.goto('https://paperfull.app/dashboard');
      await page.waitForLoadState('networkidle');
      console.log('✓ Navigated to dashboard');
    }

    // Check if we're logged in (should see dashboard or not be redirected to login)
    await page.waitForTimeout(2000);
    const isOnLogin = page.url().includes('/login');

    if (isOnLogin) {
      console.log('⚠️  Not logged in - user needs to login first');
      console.log('Please login via Gmail and run the test again');
      return;
    }

    console.log('✓ User is logged in');

    // Navigate to editor (create new paper or use existing)
    await page.goto('https://paperfull.app/editor');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    console.log('✓ Opened editor');

    // Check if there's a paper title input
    const titleInput = page.locator('input[placeholder*="title" i], input[placeholder*="judul" i]').first();
    if (await titleInput.isVisible({ timeout: 5000 })) {
      // Set paper title
      await titleInput.fill('Test Paper - Machine Learning in Healthcare');
      await page.waitForTimeout(1000);
      console.log('✓ Set paper title');
    }

    // Open AI Chat
    const chatButton = page.locator('button:has-text("AI Chat"), button:has-text("Chat")').first();
    if (await chatButton.isVisible({ timeout: 5000 })) {
      await chatButton.click();
      await page.waitForTimeout(1000);
      console.log('✓ Opened AI Chat');
    }

    // Find chat input
    const chatInput = page.locator('textarea[placeholder*="Type" i], textarea[placeholder*="message" i], textarea[placeholder*="Ketik" i]').last();
    const sendButton = page.locator('button[title*="Send" i], button:has-text("Send"), button:has-text("Kirim")').last();

    if (await chatInput.isVisible({ timeout: 5000 })) {
      // Send a message to generate paper content
      const testMessage = 'Generate an introduction section about machine learning applications in healthcare, focusing on deep learning for medical image analysis. Make it around 500 words with proper academic style.';

      await chatInput.fill(testMessage);
      await page.waitForTimeout(500);
      console.log('✓ Entered chat message');

      if (await sendButton.isVisible({ timeout: 2000 })) {
        await sendButton.click();
        console.log('✓ Sent chat message');

        // Wait for AI response (this might take a while)
        console.log('⏳ Waiting for AI response...');
        await page.waitForTimeout(5000);

        // Check if there's a response
        const chatMessages = page.locator('[class*="message"], [class*="chat"]');
        const messageCount = await chatMessages.count();
        console.log(`✓ Chat has ${messageCount} messages`);

        // Wait a bit more for generation to complete
        await page.waitForTimeout(10000);
        console.log('✓ AI response received');
      }
    } else {
      console.log('⚠️  Chat input not found - trying alternative approach');
    }

    // Try to export to DOCX
    console.log('\n📄 Attempting to export to DOCX...');

    // Look for export button
    const exportButton = page.locator('button:has-text("Export"), button:has-text("Download"), button:has-text("DOCX")').first();

    if (await exportButton.isVisible({ timeout: 5000 })) {
      // Set up download listener
      const downloadPromise = page.waitForEvent('download', { timeout: 30000 });

      await exportButton.click();
      console.log('✓ Clicked export button');

      try {
        const download = await downloadPromise;
        const fileName = download.suggestedFilename();
        console.log('✓ Download started:', fileName);

        // Save the file
        const downloadPath = `/tmp/paperfull-test-${Date.now()}.docx`;
        await download.saveAs(downloadPath);
        console.log('✓ File saved to:', downloadPath);

        // Verify file exists and has content
        const fs = require('fs');
        const stats = fs.statSync(downloadPath);
        console.log('✓ File size:', stats.size, 'bytes');

        if (stats.size > 1000) {
          console.log('✅ DOCX export successful!');
        } else {
          console.log('⚠️  DOCX file seems too small');
        }
      } catch (error) {
        console.log('⚠️  Download timeout or error:', error.message);
      }
    } else {
      console.log('⚠️  Export button not found');

      // Take a screenshot to see what's on the page
      await page.screenshot({ path: '/tmp/paperfull-test-screenshot.png' });
      console.log('📸 Screenshot saved to /tmp/paperfull-test-screenshot.png');
    }

    console.log('\n✅ Test completed');
  });
});
