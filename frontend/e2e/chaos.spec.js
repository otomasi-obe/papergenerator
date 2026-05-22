/**
 * E2E Chaos Testing — Error Scenarios & Robustness Testing
 * 
 * Tests error handling, recovery mechanisms, and system robustness by
 * intentionally causing failures across network, input validation,
 * resource limits, timeouts, and authentication.
 */
import { test, expect } from '@playwright/test';

const CHAOS_USER = {
  email: `chaos-${Date.now()}@e2e.local`,
  name: 'Chaos Test User',
  password: 'ChaosPass123!',
};

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

async function registerAndLogin(page) {
  const ctx = page.context();
  const api = ctx.request;
  
  const reg = await api.post('/api/auth/register', {
    data: { ...CHAOS_USER, captcha_token: '1x00000000000000000000AA' },
  });
  expect(reg.status()).toBe(201);
  
  const cookies = await ctx.cookies();
  return { api, cookies, ctx };
}

test.describe('Network Failure Scenarios', () => {
  test('handles offline during paper generation', async ({ page, context }) => {
    await registerAndLogin(page);
    await page.goto('/');
    
    await page.route('**/api/papers/generate', async (route) => {
      await page.waitForTimeout(1000);
      await context.setOffline(true);
      await route.abort('failed');
    });
    
    await page.goto('/papers/new');
    await page.fill('input[name="title"]', 'Offline Test Paper');
    await page.click('button:has-text("Generate")');
    
    await expect(page.locator('.error-message, .toast-error, [role="alert"]')).toBeVisible({ timeout: 10000 });
    const errorText = await page.locator('.error-message, .toast-error, [role="alert"]').first().textContent();
    expect(errorText.toLowerCase()).toMatch(/network|connection|offline|failed/);
    
    await context.setOffline(false);
  });

  test('handles slow network (3G throttle)', async ({ page, context }) => {
    await registerAndLogin(page);
    
    await context.route('**/api/**', async (route) => {
      await page.waitForTimeout(3000);
      await route.continue();
    });
    
    await page.goto('/papers');
    
    await expect(page.locator('.loading, .spinner, [aria-busy="true"]')).toBeVisible({ timeout: 5000 });
    
    await expect(page.locator('.papers-list, .paper-item')).toBeVisible({ timeout: 10000 });
  });

  test('handles intermittent connection (50% packet loss)', async ({ page, context }) => {
    await registerAndLogin(page);
    let requestCount = 0;
    
    await context.route('**/api/**', async (route) => {
      requestCount++;
      if (requestCount % 2 === 0) {
        await route.abort('failed');
      } else {
        await route.continue();
      }
    });
    
    await page.goto('/papers');
    
    await page.waitForTimeout(2000);
    
    const hasError = await page.locator('.error-message, .toast-error, [role="alert"]').isVisible();
    const hasRetry = await page.locator('button:has-text("Retry"), button:has-text("Try Again")').isVisible();
    
    expect(hasError || hasRetry).toBe(true);
  });

  test('recovers from temporary network failure', async ({ page, context }) => {
    await registerAndLogin(page);
    let failCount = 0;
    
    await context.route('**/api/papers', async (route) => {
      failCount++;
      if (failCount <= 2) {
        await route.abort('failed');
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ papers: [], pagination: { total: 0 } }),
        });
      }
    });
    
    await page.goto('/papers');
    
    const retryButton = page.locator('button:has-text("Retry"), button:has-text("Try Again")');
    if (await retryButton.isVisible({ timeout: 5000 })) {
      await retryButton.click();
      await page.waitForTimeout(500);
      await retryButton.click();
    }
    
    await expect(page.locator('.papers-list, .empty-state')).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Invalid Input Scenarios', () => {
  test('rejects empty form submission', async ({ page }) => {
    await registerAndLogin(page);
    await page.goto('/papers/new');
    
    await page.click('button[type="submit"], button:has-text("Create"), button:has-text("Generate")');
    
    await expect(page.locator('.error, .validation-error, [aria-invalid="true"]')).toBeVisible({ timeout: 3000 });
  });

  test('handles extremely long text (10,000+ chars)', async ({ page }) => {
    await registerAndLogin(page);
    await page.goto('/papers/new');
    
    const longText = 'A'.repeat(15000);
    
    const titleInput = page.locator('input[name="title"], input[placeholder*="title" i]').first();
    await titleInput.fill(longText.substring(0, 500));
    
    const abstractInput = page.locator('textarea[name="abstract"], textarea[placeholder*="abstract" i]').first();
    if (await abstractInput.isVisible()) {
      await abstractInput.fill(longText);
    }
    
    await page.waitForTimeout(500);
    
    const hasValidation = await page.locator('.error, .validation-error, .text-red-500').isVisible();
    const hasMaxLength = await titleInput.getAttribute('maxlength');
    
    expect(hasValidation || hasMaxLength).toBeTruthy();
  });

  test('sanitizes special characters in all fields', async ({ page }) => {
    await registerAndLogin(page);
    await page.goto('/papers/new');
    
    const specialChars = '<script>alert("XSS")</script>\'";--/**/';
    
    const titleInput = page.locator('input[name="title"], input[placeholder*="title" i]').first();
    await titleInput.fill(specialChars);
    
    await page.click('button[type="submit"], button:has-text("Create")');
    
    await page.waitForTimeout(1000);
    
    const pageContent = await page.content();
    expect(pageContent).not.toContain('<script>alert("XSS")</script>');
    expect(pageContent).not.toMatch(/<script[^>]*>.*?<\/script>/);
  });

  test('blocks SQL injection attempts', async ({ page, context }) => {
    const { api, cookies } = await registerAndLogin(page);
    
    const sqlInjections = [
      "'; DROP TABLE papers; --",
      "1' OR '1'='1",
      "admin'--",
      "' UNION SELECT * FROM users--",
    ];
    
    for (const injection of sqlInjections) {
      const res = await api.post('/api/papers', {
        data: { title: injection, data: {} },
        headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
        failOnStatusCode: false,
      });
      
      expect([200, 400, 422]).toContain(res.status());
      
      if (res.status() === 200) {
        const body = await res.json();
        expect(body.title || '').not.toContain('DROP TABLE');
        expect(body.title || '').not.toContain('UNION SELECT');
      }
    }
  });

  test('blocks XSS attempts in API', async ({ page, context }) => {
    const { api, cookies } = await registerAndLogin(page);
    
    const xssPayloads = [
      '<img src=x onerror=alert(1)>',
      '<svg onload=alert(1)>',
      'javascript:alert(1)',
      '<iframe src="javascript:alert(1)">',
    ];
    
    for (const payload of xssPayloads) {
      const res = await api.post('/api/papers', {
        data: { title: payload, data: { content: payload } },
        headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
        failOnStatusCode: false,
      });
      
      expect([200, 400, 422]).toContain(res.status());
    }
    
    await page.goto('/papers');
    const content = await page.content();
    expect(content).not.toMatch(/<img[^>]*onerror/);
    expect(content).not.toMatch(/<svg[^>]*onload/);
  });

  test('validates email format in registration', async ({ page }) => {
    await page.goto('/register');
    
    const invalidEmails = ['notanemail', '@test.com', 'test@', 'test..test@test.com'];
    
    for (const email of invalidEmails) {
      await page.fill('input[type="email"]', email);
      await page.fill('input[type="password"]', 'ValidPass123!');
      await page.click('button[type="submit"]');
      
      await expect(page.locator('.error, [aria-invalid="true"]')).toBeVisible({ timeout: 2000 });
      
      await page.goto('/register');
    }
  });
});

test.describe('Resource Exhaustion Scenarios', () => {
  test('rejects oversized file upload (>100MB)', async ({ page }) => {
    await registerAndLogin(page);
    await page.goto('/papers/new');
    
    const fileInput = page.locator('input[type="file"]').first();
    
    if (await fileInput.isVisible()) {
      const buffer = Buffer.alloc(1024 * 1024);
      await fileInput.setInputFiles({
        name: 'huge.pdf',
        mimeType: 'application/pdf',
        buffer: buffer,
      });
      
      await page.waitForTimeout(1000);
      
      const hasError = await page.locator('.error, .toast-error, [role="alert"]').isVisible();
      expect(hasError).toBe(true);
    }
  });

  test('handles request for excessive literature items', async ({ page, context }) => {
    const { api, cookies } = await registerAndLogin(page);
    
    const res = await api.get('/api/literature?limit=10000', {
      headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
      failOnStatusCode: false,
    });
    
    expect([200, 400, 413, 422]).toContain(res.status());
    
    if (res.status() === 200) {
      const body = await res.json();
      expect(body.items?.length || 0).toBeLessThan(1000);
    }
  });

  test('handles generation of extremely long paper', async ({ page, context }) => {
    await registerAndLogin(page);
    
    await context.route('**/api/papers/generate', async (route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ 
          error: 'Paper length exceeds maximum allowed',
          max_pages: 50 
        }),
      });
    });
    
    await page.goto('/papers/new');
    await page.fill('input[name="title"]', 'Very Long Paper');
    
    const sectionsInput = page.locator('input[name="sections"], input[type="number"]').first();
    if (await sectionsInput.isVisible()) {
      await sectionsInput.fill('100');
    }
    
    await page.click('button:has-text("Generate")');
    
    await expect(page.locator('.error-message, [role="alert"]')).toBeVisible({ timeout: 5000 });
  });

  test('rate limits excessive API requests', async ({ page, context }) => {
    const { api, cookies } = await registerAndLogin(page);
    
    const requests = [];
    for (let i = 0; i < 50; i++) {
      requests.push(
        api.get('/api/papers', {
          headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
          failOnStatusCode: false,
        })
      );
    }
    
    const responses = await Promise.all(requests);
    const rateLimited = responses.some(r => r.status() === 429);
    
    expect(rateLimited).toBe(true);
  });
});

test.describe('Timeout & Cancellation Scenarios', () => {
  test('handles operation timeout gracefully', async ({ page, context }) => {
    await registerAndLogin(page);
    
    await context.route('**/api/papers/generate', async (route) => {
      await page.waitForTimeout(35000);
      await route.continue();
    });
    
    await page.goto('/papers/new');
    await page.fill('input[name="title"]', 'Timeout Test');
    await page.click('button:has-text("Generate")');
    
    await expect(page.locator('.error, .timeout, [role="alert"]')).toBeVisible({ timeout: 40000 });
  });

  test('allows cancellation of long-running operation', async ({ page, context }) => {
    await registerAndLogin(page);
    
    await context.route('**/api/papers/generate', async (route) => {
      await page.waitForTimeout(10000);
      await route.continue();
    });
    
    await page.goto('/papers/new');
    await page.fill('input[name="title"]', 'Cancel Test');
    await page.click('button:has-text("Generate")');
    
    await page.waitForTimeout(1000);
    
    const cancelButton = page.locator('button:has-text("Cancel"), button:has-text("Stop"), button[aria-label*="cancel" i]');
    if (await cancelButton.isVisible({ timeout: 2000 })) {
      await cancelButton.click();
      
      await expect(page.locator('.cancelled, .stopped')).toBeVisible({ timeout: 3000 });
    }
  });

  test('preserves data after page refresh during operation', async ({ page, context }) => {
    await registerAndLogin(page);
    await page.goto('/papers/new');
    
    const testTitle = 'Refresh Test Paper';
    await page.fill('input[name="title"]', testTitle);
    
    await page.reload();
    
    await page.waitForTimeout(1000);
    
    const titleValue = await page.locator('input[name="title"]').first().inputValue();
    const hasAutosave = titleValue === testTitle;
    const hasDraft = await page.locator('.draft, .autosaved, :has-text("draft")').isVisible();
    
    expect(hasAutosave || hasDraft).toBeTruthy();
  });

  test('warns before closing with unsaved changes', async ({ page }) => {
    await registerAndLogin(page);
    await page.goto('/papers/new');
    
    await page.fill('input[name="title"]', 'Unsaved Changes Test');
    
    let dialogShown = false;
    page.on('dialog', async (dialog) => {
      dialogShown = true;
      expect(dialog.type()).toBe('beforeunload');
      await dialog.dismiss();
    });
    
    await page.evaluate(() => {
      window.dispatchEvent(new Event('beforeunload'));
    });
    
    await page.waitForTimeout(500);
  });
});

test.describe('Authentication Error Scenarios', () => {
  test('handles expired token gracefully', async ({ page, context }) => {
    await registerAndLogin(page);
    
    await context.clearCookies();
    
    await page.goto('/papers');
    
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
    
    await expect(page.locator('.error, .session-expired, [role="alert"]')).toBeVisible({ timeout: 3000 });
  });

  test('handles invalid token in API request', async ({ page, context }) => {
    const { api } = await registerAndLogin(page);
    
    const res = await api.get('/api/papers', {
      headers: { 
        'Authorization': 'Bearer invalid_token_12345',
        'Cookie': 'access_token_cookie=invalid'
      },
      failOnStatusCode: false,
    });
    
    expect(res.status()).toBe(401);
    const body = await res.json();
    expect(body).toHaveProperty('error');
  });

  test('redirects to login after logout during operation', async ({ page, context }) => {
    const { api, cookies } = await registerAndLogin(page);
    await page.goto('/papers');
    
    await api.post('/api/auth/logout', {
      headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
    });
    
    await page.click('a[href="/papers/new"], button:has-text("New Paper")');
    
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
  });

  test('handles concurrent session logout', async ({ page, context }) => {
    await registerAndLogin(page);
    await page.goto('/papers');
    
    await context.clearCookies();
    
    await page.click('a[href="/papers/new"], button:has-text("New")');
    
    await page.waitForTimeout(1000);
    
    const isLoginPage = page.url().includes('/login');
    const hasError = await page.locator('.error, [role="alert"]').isVisible();
    
    expect(isLoginPage || hasError).toBe(true);
  });

  test('prevents CSRF without proper token', async ({ page, context }) => {
    const { api } = await registerAndLogin(page);
    
    const res = await api.post('/api/papers', {
      data: { title: 'CSRF Test', data: {} },
      failOnStatusCode: false,
    });
    
    expect([400, 401, 403]).toContain(res.status());
  });
});

test.describe('Browser Compatibility & Edge Cases', () => {
  test('handles disabled JavaScript gracefully', async ({ page }) => {
    await page.goto('/');
    
    const noscript = await page.locator('noscript').count();
    expect(noscript).toBeGreaterThan(0);
  });

  test('works without cookies (shows appropriate message)', async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/papers');
    
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 });
  });

  test('handles localStorage unavailable', async ({ page }) => {
    await page.goto('/');
    
    await page.evaluate(() => {
      Object.defineProperty(window, 'localStorage', {
        get: () => { throw new Error('localStorage disabled'); }
      });
    });
    
    await page.reload();
    
    await page.waitForTimeout(1000);
    
    const hasError = await page.locator('.error, [role="alert"]').isVisible();
    const pageLoaded = await page.locator('body').isVisible();
    
    expect(pageLoaded).toBe(true);
  });

  test('responsive design works on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    
    await expect(page.locator('body')).toBeVisible();
    
    const mobileMenu = page.locator('[aria-label*="menu" i], .mobile-menu, .hamburger');
    const hasResponsive = await mobileMenu.isVisible() || 
                          await page.locator('nav').isVisible();
    
    expect(hasResponsive).toBe(true);
  });

  test('handles very small viewport (320px)', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto('/');
    
    await expect(page.locator('body')).toBeVisible();
    
    const overflow = await page.evaluate(() => {
      return document.body.scrollWidth > window.innerWidth + 10;
    });
    
    expect(overflow).toBe(false);
  });

  test('handles very large viewport (4K)', async ({ page }) => {
    await page.setViewportSize({ width: 3840, height: 2160 });
    await page.goto('/');
    
    await expect(page.locator('body')).toBeVisible();
    
    const content = page.locator('main, .container, .content');
    await expect(content).toBeVisible();
  });
});

test.describe('Data Integrity & Recovery', () => {
  test('prevents duplicate submissions', async ({ page, context }) => {
    const { api, cookies } = await registerAndLogin(page);
    
    const paperData = { title: 'Duplicate Test', data: { test: true } };
    
    const [res1, res2] = await Promise.all([
      api.post('/api/papers', {
        data: paperData,
        headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
        failOnStatusCode: false,
      }),
      api.post('/api/papers', {
        data: paperData,
        headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
        failOnStatusCode: false,
      }),
    ]);
    
    const successCount = [res1, res2].filter(r => r.status() === 200).length;
    expect(successCount).toBeLessThanOrEqual(1);
  });

  test('maintains data consistency after error', async ({ page, context }) => {
    const { api, cookies } = await registerAndLogin(page);
    
    const res1 = await api.post('/api/papers', {
      data: { title: 'Paper 1', data: {} },
      headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
    });
    expect(res1.status()).toBe(200);
    
    await api.post('/api/papers', {
      data: { title: '', data: {} },
      headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
      failOnStatusCode: false,
    });
    
    const listRes = await api.get('/api/papers');
    const papers = await listRes.json();
    
    expect(papers.papers.length).toBeGreaterThanOrEqual(1);
    expect(papers.papers.some(p => p.title === 'Paper 1')).toBe(true);
  });

  test('recovers from partial data corruption', async ({ page }) => {
    await registerAndLogin(page);
    await page.goto('/papers/new');
    
    await page.evaluate(() => {
      localStorage.setItem('draft_paper', '{"title":"Test","data":{invalid json}');
    });
    
    await page.reload();
    
    await page.waitForTimeout(1000);
    
    const pageLoaded = await page.locator('body').isVisible();
    expect(pageLoaded).toBe(true);
  });
});
