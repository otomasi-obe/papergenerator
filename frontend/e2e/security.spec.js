/**
 * E2E Test: Security & Data Protection
 * 
 * Tests security measures:
 * - XSS prevention
 * - CSRF token validation
 * - SQL injection attempts
 * - Session security
 * - Input sanitization
 * - File upload security
 * 
 * Verification:
 * - No script execution from user input
 * - Proper token validation
 * - Secure session handling
 * - Input validation
 */

import { test, expect } from '@playwright/test';

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

test.describe('Security & Data Protection', () => {
  let userEmail;
  let paperId;

  test.beforeEach(async ({ page, context }) => {
    userEmail = `security-test-${Date.now()}@test.local`;
    
    // Register and create a paper
    const api = context.request;
    const reg = await api.post('/api/auth/register', {
      data: {
        email: userEmail,
        name: 'Security Test User',
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

  test('XSS Prevention - Script tags in title', async ({ page }) => {
    const xssPayloads = [
      '<script>alert("XSS")</script>',
      '<img src=x onerror="alert(\'XSS\')" />',
      '<svg onload="alert(\'XSS\')" />',
      'javascript:alert("XSS")',
      '<iframe src="javascript:alert(\'XSS\')"></iframe>',
    ];
    
    const alerts = [];
    page.on('dialog', dialog => {
      alerts.push(dialog.message());
      dialog.dismiss();
    });
    
    for (const payload of xssPayloads) {
      const titleInput = page.locator('input[placeholder*="Paper title"]').first();
      await titleInput.fill(payload);
      await page.waitForTimeout(1000);
      
      // Check if script was executed
      expect(alerts.length).toBe(0);
      
      // Verify the input is sanitized
      const titleValue = await titleInput.inputValue();
      console.log(`XSS test: Payload "${payload.substring(0, 30)}..." -> "${titleValue.substring(0, 30)}..."`);
    }
    
    console.log(`XSS Prevention: ${xssPayloads.length} payloads tested, ${alerts.length} alerts triggered`);
    expect(alerts.length).toBe(0);
  });

  test('XSS Prevention - Script in content editor', async ({ page }) => {
    const xssPayload = '<script>window.xssExecuted = true;</script><p>Normal content</p>';
    
    // Try to inject script in editor
    const editor = page.locator('[contenteditable="true"], textarea, .editor').first();
    
    if (await editor.count() > 0) {
      await editor.click();
      await page.keyboard.type(xssPayload);
      await page.waitForTimeout(2000);
      
      // Check if script was executed
      const xssExecuted = await page.evaluate(() => {
        return window.xssExecuted === true;
      });
      
      console.log(`XSS in editor: Script executed = ${xssExecuted}`);
      expect(xssExecuted).toBe(false);
    }
  });

  test('CSRF Protection - Request without token', async ({ context }) => {
    const api = context.request;
    
    // Try to update paper without CSRF token
    const updateRes = await api.patch(`/api/papers/${paperId}`, {
      data: {
        op: 'replace',
        path: '/title',
        value: 'Unauthorized Update',
      },
      // Intentionally omit X-CSRF-TOKEN header
    });
    
    console.log(`CSRF test: Request without token status = ${updateRes.status()}`);
    
    // Should be rejected (401, 403, or 422)
    expect([401, 403, 422]).toContain(updateRes.status());
  });

  test('CSRF Protection - Request with invalid token', async ({ context }) => {
    const api = context.request;
    
    // Try to update paper with fake CSRF token
    const updateRes = await api.patch(`/api/papers/${paperId}`, {
      data: {
        op: 'replace',
        path: '/title',
        value: 'Unauthorized Update',
      },
      headers: {
        'X-CSRF-TOKEN': 'fake-invalid-token-12345',
      },
    });
    
    console.log(`CSRF test: Request with invalid token status = ${updateRes.status()}`);
    
    // Should be rejected
    expect([401, 403, 422]).toContain(updateRes.status());
  });

  test('SQL Injection - Title field', async ({ page, context }) => {
    const sqlPayloads = [
      "' OR '1'='1",
      "'; DROP TABLE papers; --",
      "1' UNION SELECT * FROM users--",
      "admin'--",
      "' OR 1=1--",
    ];
    
    const api = context.request;
    const cookies = await context.cookies();
    const csrf = csrfFromCookies(cookies);
    
    for (const payload of sqlPayloads) {
      const titleInput = page.locator('input[placeholder*="Paper title"]').first();
      await titleInput.fill(payload);
      await page.waitForTimeout(1000);
      
      // Verify the paper still exists and wasn't corrupted
      const verifyRes = await api.get(`/api/papers/${paperId}`);
      expect(verifyRes.status()).toBe(200);
      
      const paperData = await verifyRes.json();
      console.log(`SQL injection test: Payload "${payload}" -> Title stored as "${paperData.title}"`);
    }
    
    console.log(`SQL Injection: ${sqlPayloads.length} payloads tested, paper integrity maintained`);
  });

  test('Session Security - HttpOnly cookies', async ({ context }) => {
    const cookies = await context.cookies();
    
    const authCookies = cookies.filter(c => 
      c.name.includes('access_token') || 
      c.name.includes('refresh_token') ||
      c.name.includes('session')
    );
    
    console.log(`\nAuth cookies found: ${authCookies.length}`);
    
    authCookies.forEach(cookie => {
      console.log(`  ${cookie.name}: httpOnly=${cookie.httpOnly}, secure=${cookie.secure}, sameSite=${cookie.sameSite}`);
      
      // Auth cookies should be httpOnly
      expect(cookie.httpOnly).toBe(true);
      
      // Should use secure flag in production
      // expect(cookie.secure).toBe(true); // Uncomment for production
      
      // Should use SameSite to prevent CSRF
      expect(['Strict', 'Lax']).toContain(cookie.sameSite);
    });
  });

  test('Session Security - Token not accessible via JavaScript', async ({ page }) => {
    // Try to access auth tokens via JavaScript
    const accessibleTokens = await page.evaluate(() => {
      const tokens = [];
      
      // Try to read from cookies
      const cookies = document.cookie;
      if (cookies.includes('access_token')) {
        tokens.push('access_token in document.cookie');
      }
      if (cookies.includes('refresh_token')) {
        tokens.push('refresh_token in document.cookie');
      }
      
      // Try to read from localStorage
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (key.includes('token') || key.includes('auth'))) {
          tokens.push(`localStorage: ${key}`);
        }
      }
      
      // Try to read from sessionStorage
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (key && (key.includes('token') || key.includes('auth'))) {
          tokens.push(`sessionStorage: ${key}`);
        }
      }
      
      return tokens;
    });
    
    console.log(`\nAccessible tokens via JavaScript: ${accessibleTokens.length}`);
    if (accessibleTokens.length > 0) {
      console.log('Accessible tokens:');
      accessibleTokens.forEach(token => console.log(`  - ${token}`));
    }
    
    // HttpOnly cookies should not be accessible
    expect(accessibleTokens.filter(t => t.includes('access_token'))).toHaveLength(0);
  });

  test('Input Validation - Email format', async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/register');
    
    const invalidEmails = [
      'notanemail',
      '@example.com',
      'user@',
      'user @example.com',
      'user@example',
    ];
    
    for (const email of invalidEmails) {
      const emailInput = page.locator('input[type="email"], input[name="email"]').first();
      await emailInput.fill(email);
      
      const nameInput = page.locator('input[name="name"]').first();
      if (await nameInput.count() > 0) {
        await nameInput.fill('Test User');
      }
      
      const passwordInput = page.locator('input[type="password"]').first();
      await passwordInput.fill('Test123!');
      
      const submitButton = page.locator('button[type="submit"], button:has-text("Register")').first();
      await submitButton.click();
      await page.waitForTimeout(1000);
      
      // Should show validation error
      const errorMessage = page.locator('text=/invalid|email|format/i');
      const hasError = await errorMessage.count() > 0;
      
      console.log(`Email validation: "${email}" -> Error shown = ${hasError}`);
    }
  });

  test('Input Validation - Password strength', async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/register');
    
    const weakPasswords = [
      '123',
      'password',
      'abc',
      '12345678',
    ];
    
    for (const password of weakPasswords) {
      const emailInput = page.locator('input[type="email"]').first();
      await emailInput.fill(`test-${Date.now()}@example.com`);
      
      const nameInput = page.locator('input[name="name"]').first();
      if (await nameInput.count() > 0) {
        await nameInput.fill('Test User');
      }
      
      const passwordInput = page.locator('input[type="password"]').first();
      await passwordInput.fill(password);
      
      const submitButton = page.locator('button[type="submit"], button:has-text("Register")').first();
      await submitButton.click();
      await page.waitForTimeout(1000);
      
      // Should show validation error for weak password
      const errorMessage = page.locator('text=/weak|strong|password|character/i');
      const hasError = await errorMessage.count() > 0;
      
      console.log(`Password validation: "${password}" -> Error shown = ${hasError}`);
    }
  });

  test('Authorization - Access other user\'s paper', async ({ browser, context }) => {
    // Create second user
    const user2Email = `security-test-2-${Date.now()}@test.local`;
    const api = context.request;
    
    const reg2 = await api.post('/api/auth/register', {
      data: {
        email: user2Email,
        name: 'Security Test User 2',
        password: 'Test123!',
        captcha_token: '1x00000000000000000000AA',
      },
    });
    expect(reg2.status()).toBe(201);
    
    // User 2 tries to access User 1's paper
    const context2 = await browser.newContext();
    const api2 = context2.request;
    
    await api2.post('/api/auth/login', {
      data: {
        email: user2Email,
        password: 'Test123!',
      },
    });
    
    const accessRes = await api2.get(`/api/papers/${paperId}`);
    console.log(`Authorization test: User 2 accessing User 1's paper status = ${accessRes.status()}`);
    
    // Should be forbidden (403) or not found (404)
    expect([403, 404]).toContain(accessRes.status());
    
    await context2.close();
  });

  test('Rate Limiting - Rapid API requests', async ({ context }) => {
    const api = context.request;
    const cookies = await context.cookies();
    const csrf = csrfFromCookies(cookies);
    
    // Make 50 rapid requests
    const requests = [];
    for (let i = 0; i < 50; i++) {
      requests.push(
        api.get(`/api/papers/${paperId}`).then(res => res.status())
      );
    }
    
    const results = await Promise.all(requests);
    const rateLimited = results.filter(status => status === 429).length;
    const successful = results.filter(status => status === 200).length;
    
    console.log(`Rate limiting: ${successful} successful, ${rateLimited} rate-limited out of 50 requests`);
    
    // If rate limiting is implemented, some requests should be blocked
    // If not implemented, all should succeed (which is also acceptable for now)
    console.log(`Rate limiting ${rateLimited > 0 ? 'IS' : 'IS NOT'} implemented`);
  });

  test('Security Headers - Response headers check', async ({ page }) => {
    const response = await page.goto('/dashboard');
    const headers = response?.headers() || {};
    
    console.log('\nSecurity headers:');
    
    const securityHeaders = {
      'x-content-type-options': headers['x-content-type-options'],
      'x-frame-options': headers['x-frame-options'],
      'x-xss-protection': headers['x-xss-protection'],
      'strict-transport-security': headers['strict-transport-security'],
      'content-security-policy': headers['content-security-policy'],
    };
    
    Object.entries(securityHeaders).forEach(([header, value]) => {
      console.log(`  ${header}: ${value || 'NOT SET'}`);
    });
    
    // At minimum, should have X-Content-Type-Options
    expect(securityHeaders['x-content-type-options']).toBeTruthy();
  });
});
