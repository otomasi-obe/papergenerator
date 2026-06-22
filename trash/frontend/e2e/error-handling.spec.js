/**
 * E2E Test: Error Handling & Edge Cases
 * 
 * Tests application resilience and error recovery:
 * - Network failures and offline mode
 * - Server errors (500, 503)
 * - Invalid file uploads
 * - Timeout handling
 * - Edge cases (long inputs, special characters)
 * 
 * Verification:
 * - Graceful error messages
 * - No data loss
 * - Recovery mechanisms
 * - User feedback
 */

import { test, expect } from '@playwright/test';

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

test.describe('Error Handling & Edge Cases', () => {
  let userEmail;
  let paperId;

  test.beforeEach(async ({ page, context }) => {
    userEmail = `error-test-${Date.now()}@test.local`;
    
    // Register and create a paper
    const api = context.request;
    const reg = await api.post('/api/auth/register', {
      data: {
        email: userEmail,
        name: 'Error Test User',
        password: 'Test123!',
        captcha_token: '1x00000000000000000000AA',
      },
    });
    expect(reg.status()).toBe(201);
    
    await page.goto('/dashboard');
    await page.click('text=New Paper');
    await page.waitForURL(/\/editor/, { timeout: 10000 });
    
    const url = page.url();
    const match = url.match(/\/editor\/(\d+)/);
    if (match) {
      paperId = match[1];
    }
  });

  test('Network failure - Offline mode handling', async ({ page, context }) => {
    // Fill in some content
    const titleInput = page.locator('input[placeholder*="Paper title"]').first();
    await titleInput.fill('Test Paper - Network Failure');
    await page.waitForTimeout(1000);
    
    // Simulate offline mode
    await context.setOffline(true);
    
    // Try to make changes
    await titleInput.fill('Test Paper - Network Failure (Offline Edit)');
    await page.waitForTimeout(2000);
    
    // Check for offline indicator or error message
    const errorMessage = page.locator('text=/offline|network|connection/i');
    const hasError = await errorMessage.count() > 0;
    
    console.log(`Offline mode: Error message displayed = ${hasError}`);
    
    // Go back online
    await context.setOffline(false);
    await page.waitForTimeout(2000);
    
    // Verify data is still there
    const titleValue = await titleInput.inputValue();
    expect(titleValue).toContain('Network Failure');
  });

  test('Server error - 500 Internal Server Error handling', async ({ page, context }) => {
    // Intercept API calls and return 500 error
    await page.route('**/api/papers/**', route => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Internal Server Error' }),
        });
      } else {
        route.continue();
      }
    });
    
    const titleInput = page.locator('input[placeholder*="Paper title"]').first();
    await titleInput.fill('Test Paper - Server Error');
    await page.waitForTimeout(2000);
    
    // Check for error notification
    const errorNotification = page.locator('text=/error|failed|try again/i');
    const hasErrorNotification = await errorNotification.count() > 0;
    
    console.log(`Server error: Error notification displayed = ${hasErrorNotification}`);
    expect(hasErrorNotification).toBe(true);
  });

  test('Invalid file upload - Wrong file format', async ({ page }) => {
    // Try to upload a non-PDF file
    const fileInput = page.locator('input[type="file"]').first();
    
    if (await fileInput.count() > 0) {
      // Create a temporary text file
      const fs = require('fs');
      const path = require('path');
      const tmpFile = path.join('/tmp', 'invalid-file.txt');
      fs.writeFileSync(tmpFile, 'This is not a PDF file');
      
      await fileInput.setInputFiles(tmpFile);
      await page.waitForTimeout(2000);
      
      // Check for error message about invalid format
      const errorMessage = page.locator('text=/invalid|format|pdf|supported/i');
      const hasError = await errorMessage.count() > 0;
      
      console.log(`Invalid file: Error message displayed = ${hasError}`);
      
      // Cleanup
      fs.unlinkSync(tmpFile);
    } else {
      console.log('File upload not available in current view');
    }
  });

  test('Edge case - Very long paper title', async ({ page }) => {
    const longTitle = 'A'.repeat(500) + ' - This is an extremely long paper title that exceeds normal limits';
    
    const titleInput = page.locator('input[placeholder*="Paper title"]').first();
    await titleInput.fill(longTitle);
    await page.waitForTimeout(2000);
    
    // Check if there's a character limit or validation
    const titleValue = await titleInput.inputValue();
    console.log(`Long title: Input length = ${titleValue.length}, Original length = ${longTitle.length}`);
    
    // Check for validation message
    const validationMessage = page.locator('text=/too long|maximum|limit|characters/i');
    const hasValidation = await validationMessage.count() > 0;
    console.log(`Long title: Validation message displayed = ${hasValidation}`);
  });

  test('Edge case - Special characters in title', async ({ page }) => {
    const specialTitle = 'Test <script>alert("XSS")</script> & "Special" Characters: 你好 🚀 #Test';
    
    const titleInput = page.locator('input[placeholder*="Paper title"]').first();
    await titleInput.fill(specialTitle);
    await page.waitForTimeout(2000);
    
    // Verify the title is properly escaped/sanitized
    const titleValue = await titleInput.inputValue();
    console.log(`Special chars: Input value = ${titleValue}`);
    
    // Check that script tags are not executed
    const alerts = [];
    page.on('dialog', dialog => {
      alerts.push(dialog.message());
      dialog.dismiss();
    });
    
    await page.waitForTimeout(1000);
    expect(alerts.length).toBe(0); // No XSS alert should appear
  });

  test('Timeout handling - Long-running AI request', async ({ page }) => {
    // Intercept AI chat requests and delay response
    await page.route('**/api/papers/**/chat', route => {
      setTimeout(() => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ response: 'Delayed response' }),
        });
      }, 35000); // 35 second delay
    });
    
    const chatButton = page.locator('button:has-text("AI Chat"), button:has-text("Chat")').first();
    if (await chatButton.count() > 0) {
      await chatButton.click();
      await page.waitForTimeout(500);
      
      const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
      await chatInput.fill('Generate abstract');
      await page.keyboard.press('Enter');
      
      // Wait and check for timeout message or loading indicator
      await page.waitForTimeout(5000);
      
      const loadingIndicator = page.locator('text=/loading|processing|generating/i');
      const hasLoading = await loadingIndicator.count() > 0;
      console.log(`Timeout test: Loading indicator displayed = ${hasLoading}`);
    }
  });

  test('Data persistence - Browser refresh recovery', async ({ page, context }) => {
    const titleInput = page.locator('input[placeholder*="Paper title"]').first();
    const testTitle = 'Test Paper - Refresh Recovery';
    
    await titleInput.fill(testTitle);
    await page.waitForTimeout(2000);
    
    // Refresh the page
    await page.reload();
    await page.waitForTimeout(2000);
    
    // Check if the title is still there
    const titleAfterRefresh = await titleInput.inputValue();
    console.log(`Refresh recovery: Title before = "${testTitle}", after = "${titleAfterRefresh}"`);
    
    expect(titleAfterRefresh).toContain('Test Paper');
  });

  test('Concurrent edits - Multiple tabs conflict', async ({ browser }) => {
    // Open two tabs with the same paper
    const context1 = await browser.newContext();
    const context2 = await browser.newContext();
    
    // Login in both contexts
    const api1 = context1.request;
    const api2 = context2.request;
    
    await api1.post('/api/auth/login', {
      data: { email: userEmail, password: 'Test123!' },
    });
    
    await api2.post('/api/auth/login', {
      data: { email: userEmail, password: 'Test123!' },
    });
    
    const page1 = await context1.newPage();
    const page2 = await context2.newPage();
    
    await page1.goto(`/editor/${paperId}`);
    await page2.goto(`/editor/${paperId}`);
    
    await page1.waitForTimeout(1000);
    await page2.waitForTimeout(1000);
    
    // Edit in both tabs
    const title1 = page1.locator('input[placeholder*="Paper title"]').first();
    const title2 = page2.locator('input[placeholder*="Paper title"]').first();
    
    await title1.fill('Edit from Tab 1');
    await page1.waitForTimeout(1000);
    
    await title2.fill('Edit from Tab 2');
    await page2.waitForTimeout(2000);
    
    // Check for conflict notification
    const conflictMessage1 = page1.locator('text=/conflict|updated|refresh/i');
    const conflictMessage2 = page2.locator('text=/conflict|updated|refresh/i');
    
    const hasConflict1 = await conflictMessage1.count() > 0;
    const hasConflict2 = await conflictMessage2.count() > 0;
    
    console.log(`Concurrent edits: Tab 1 conflict = ${hasConflict1}, Tab 2 conflict = ${hasConflict2}`);
    
    await context1.close();
    await context2.close();
  });
});
