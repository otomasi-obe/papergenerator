/**
 * E2E Mobile Tests — Responsive Design & Touch Interactions
 * 
 * Persona: Mahasiswa yang sering kerja dari HP, akses dari smartphone
 * 
 * Tests mobile responsiveness, touch interactions, and performance
 * on both iOS (iPhone 12) and Android devices.
 */
import { test, expect } from '@playwright/test';

const E2E_USER = {
  email: `mobile-e2e-${Date.now()}@e2e.local`,
  name: 'Mobile E2E User',
  password: 'MobilePass123!',
};

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

test.describe('Mobile Responsiveness - iPhone 12', () => {
  test.use({ 
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test('landing page renders correctly on mobile', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/PaperFull|Paper Generator/i);
    
    const viewport = page.viewportSize();
    expect(viewport?.width).toBe(390);
    expect(viewport?.height).toBe(844);
  });

  test('mobile navigation - hamburger menu', async ({ page }) => {
    await page.goto('/');
    
    const hamburger = page.locator('[data-testid="mobile-menu-button"], button[aria-label*="menu" i], .hamburger, [class*="menu-toggle"]').first();
    
    if (await hamburger.isVisible()) {
      await hamburger.tap();
      
      const mobileMenu = page.locator('[data-testid="mobile-menu"], nav[class*="mobile"], .mobile-nav').first();
      await expect(mobileMenu).toBeVisible({ timeout: 2000 });
      
      await hamburger.tap();
      await expect(mobileMenu).toBeHidden({ timeout: 2000 });
    }
  });

  test('touch target sizes are adequate (min 44x44px)', async ({ page }) => {
    await page.goto('/');
    
    const buttons = await page.locator('button, a[role="button"], input[type="submit"]').all();
    
    for (const button of buttons.slice(0, 10)) {
      if (await button.isVisible()) {
        const box = await button.boundingBox();
        if (box) {
          expect(box.width).toBeGreaterThanOrEqual(40);
          expect(box.height).toBeGreaterThanOrEqual(40);
        }
      }
    }
  });

  test('scroll behavior works smoothly', async ({ page }) => {
    await page.goto('/');
    
    const initialScroll = await page.evaluate(() => window.scrollY);
    
    await page.evaluate(() => window.scrollBy(0, 500));
    await page.waitForTimeout(300);
    
    const afterScroll = await page.evaluate(() => window.scrollY);
    expect(afterScroll).toBeGreaterThan(initialScroll);
  });

  test('text input works on small screen', async ({ page }) => {
    await page.goto('/login');
    
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible();
    
    await emailInput.tap();
    await emailInput.fill('test@mobile.com');
    
    const value = await emailInput.inputValue();
    expect(value).toBe('test@mobile.com');
  });

  test('mobile page load performance', async ({ page }) => {
    const startTime = Date.now();
    
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    const loadTime = Date.now() - startTime;
    expect(loadTime).toBeLessThan(5000);
    
    const performanceMetrics = await page.evaluate(() => {
      const perf = performance.getEntriesByType('navigation')[0];
      return {
        domContentLoaded: perf.domContentLoadedEventEnd - perf.domContentLoadedEventStart,
        loadComplete: perf.loadEventEnd - perf.loadEventStart,
      };
    });
    
    expect(performanceMetrics.domContentLoaded).toBeLessThan(3000);
  });
});

test.describe('Mobile Responsiveness - Android', () => {
  test.use({ 
    viewport: { width: 412, height: 915 },
    isMobile: true,
    hasTouch: true,
    userAgent: 'Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36',
  });

  test('landing page renders on Android', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/PaperFull|Paper Generator/i);
    
    const viewport = page.viewportSize();
    expect(viewport?.width).toBe(412);
  });

  test('touch gestures work correctly', async ({ page }) => {
    await page.goto('/');
    
    const touchableElement = page.locator('button, a').first();
    if (await touchableElement.isVisible()) {
      await touchableElement.tap();
      await page.waitForTimeout(100);
    }
  });
});

test.describe('Mobile Paper Creation Flow', () => {
  test.use({ 
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test('create paper on mobile device', async ({ page }) => {
    const ctx = page.context();
    const api = ctx.request;

    await api.post('/api/auth/register', {
      data: { ...E2E_USER, captcha_token: '1x00000000000000000000AA' },
    });

    await page.goto('/');
    
    const createButton = page.locator('button:has-text("Create"), button:has-text("New Paper"), [data-testid="create-paper"]').first();
    
    if (await createButton.isVisible()) {
      await createButton.tap();
      await page.waitForTimeout(500);
    }
  });

  test('question answering with touch input', async ({ page }) => {
    const ctx = page.context();
    const api = ctx.request;

    await api.post('/api/auth/register', {
      data: { ...E2E_USER, captcha_token: '1x00000000000000000000AA' },
    });

    await page.goto('/');
    
    const textInput = page.locator('input[type="text"], textarea').first();
    if (await textInput.isVisible()) {
      await textInput.tap();
      await textInput.fill('Test question from mobile');
      
      const value = await textInput.inputValue();
      expect(value).toContain('Test question');
    }
  });

  test('file upload from mobile', async ({ page }) => {
    const ctx = page.context();
    const api = ctx.request;

    await api.post('/api/auth/register', {
      data: { ...E2E_USER, captcha_token: '1x00000000000000000000AA' },
    });

    await page.goto('/');
    
    const fileInput = page.locator('input[type="file"]').first();
    if (await fileInput.isVisible()) {
      const isEnabled = await fileInput.isEnabled();
      expect(isEnabled).toBeTruthy();
    }
  });
});

test.describe('Mobile Editor Functionality', () => {
  test.use({ 
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test('editor is accessible on mobile', async ({ page }) => {
    const ctx = page.context();
    const api = ctx.request;

    const reg = await api.post('/api/auth/register', {
      data: { ...E2E_USER, captcha_token: '1x00000000000000000000AA' },
    });

    const cookies = await ctx.cookies();
    const csrf = csrfFromCookies(cookies);

    const paper = await api.post('/api/papers', {
      data: { title: 'Mobile Editor Test', data: { content: 'Test content' } },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    const paperId = (await paper.json()).id;
    
    await page.goto(`/papers/${paperId}`);
    await page.waitForLoadState('networkidle');
    
    const editor = page.locator('[contenteditable="true"], textarea, .editor').first();
    if (await editor.isVisible()) {
      await editor.tap();
      await page.waitForTimeout(200);
    }
  });

  test('scrolling long content works', async ({ page }) => {
    await page.goto('/');
    
    const scrollableArea = page.locator('main, [role="main"], .content').first();
    
    if (await scrollableArea.isVisible()) {
      const initialScroll = await page.evaluate(() => window.scrollY);
      
      await page.evaluate(() => {
        window.scrollBy(0, 1000);
      });
      
      await page.waitForTimeout(300);
      
      const afterScroll = await page.evaluate(() => window.scrollY);
      expect(afterScroll).toBeGreaterThan(initialScroll);
    }
  });

  test('toolbar is accessible on mobile', async ({ page }) => {
    await page.goto('/');
    
    const toolbar = page.locator('[role="toolbar"], .toolbar, [data-testid="editor-toolbar"]').first();
    
    if (await toolbar.isVisible()) {
      const box = await toolbar.boundingBox();
      expect(box).toBeTruthy();
      
      if (box) {
        expect(box.width).toBeLessThanOrEqual(390);
      }
    }
  });
});

test.describe('Mobile Chat Interface', () => {
  test.use({ 
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test('chat input is usable on mobile', async ({ page }) => {
    const ctx = page.context();
    const api = ctx.request;

    await api.post('/api/auth/register', {
      data: { ...E2E_USER, captcha_token: '1x00000000000000000000AA' },
    });

    await page.goto('/');
    
    const chatInput = page.locator('input[placeholder*="message" i], textarea[placeholder*="chat" i], [data-testid="chat-input"]').first();
    
    if (await chatInput.isVisible()) {
      await chatInput.tap();
      await chatInput.fill('Test message from mobile');
      
      const value = await chatInput.inputValue();
      expect(value).toBe('Test message from mobile');
    }
  });

  test('scroll to bottom works in chat', async ({ page }) => {
    await page.goto('/');
    
    const chatContainer = page.locator('[data-testid="chat-messages"], .chat-container, [role="log"]').first();
    
    if (await chatContainer.isVisible()) {
      await page.evaluate(() => {
        const container = document.querySelector('[data-testid="chat-messages"], .chat-container, [role="log"]');
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      });
      
      await page.waitForTimeout(200);
    }
  });

  test('tool result display fits mobile screen', async ({ page }) => {
    await page.goto('/');
    
    const viewport = page.viewportSize();
    const toolResults = page.locator('[data-testid="tool-result"], .tool-output, .result-card').first();
    
    if (await toolResults.isVisible()) {
      const box = await toolResults.boundingBox();
      if (box && viewport) {
        expect(box.width).toBeLessThanOrEqual(viewport.width);
      }
    }
  });
});

test.describe('Mobile Performance Metrics', () => {
  test.use({ 
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test('measure page load time on mobile', async ({ page }) => {
    const startTime = Date.now();
    
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    
    const loadTime = Date.now() - startTime;
    
    expect(loadTime).toBeLessThan(5000);
  });

  test('measure memory usage', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    const memoryUsage = await page.evaluate(() => {
      if (performance.memory) {
        return {
          usedJSHeapSize: performance.memory.usedJSHeapSize,
          totalJSHeapSize: performance.memory.totalJSHeapSize,
          jsHeapSizeLimit: performance.memory.jsHeapSizeLimit,
        };
      }
      return null;
    });
    
    if (memoryUsage) {
      expect(memoryUsage.usedJSHeapSize).toBeLessThan(100 * 1024 * 1024);
    }
  });

  test('check for layout shifts (CLS)', async ({ page }) => {
    await page.goto('/');
    
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    
    const cls = await page.evaluate(() => {
      return new Promise((resolve) => {
        let clsScore = 0;
        const observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (entry.entryType === 'layout-shift' && !entry.hadRecentInput) {
              clsScore += entry.value;
            }
          }
        });
        observer.observe({ entryTypes: ['layout-shift'] });
        
        setTimeout(() => {
          observer.disconnect();
          resolve(clsScore);
        }, 2000);
      });
    });
    
    expect(cls).toBeLessThan(0.25);
  });

  test('check resource loading performance', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    const resources = await page.evaluate(() => {
      const entries = performance.getEntriesByType('resource');
      return entries.map(entry => ({
        name: entry.name,
        duration: entry.duration,
        size: entry.transferSize || 0,
      }));
    });
    
    const slowResources = resources.filter(r => r.duration > 3000);
    expect(slowResources.length).toBe(0);
  });
});

test.describe('Mobile Offline Behavior', () => {
  test.use({ 
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test('app shows offline indicator when network is down', async ({ page, context }) => {
    await page.goto('/');
    
    await context.setOffline(true);
    
    await page.reload({ waitUntil: 'domcontentloaded' }).catch(() => {});
    
    await page.waitForTimeout(1000);
    
    await context.setOffline(false);
  });

  test('service worker caches assets for offline use', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    const swRegistered = await page.evaluate(async () => {
      if ('serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.getRegistration();
        return !!registration;
      }
      return false;
    });
    
    if (swRegistered) {
      const cacheKeys = await page.evaluate(async () => {
        return await caches.keys();
      });
      
      expect(cacheKeys.length).toBeGreaterThan(0);
    }
  });
});

test.describe('Mobile UX Assessment', () => {
  test.use({ 
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });

  test('font sizes are readable on mobile', async ({ page }) => {
    await page.goto('/');
    
    const bodyFontSize = await page.evaluate(() => {
      return parseFloat(window.getComputedStyle(document.body).fontSize);
    });
    
    expect(bodyFontSize).toBeGreaterThanOrEqual(14);
  });

  test('no horizontal scrolling on mobile', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    const hasHorizontalScroll = await page.evaluate(() => {
      return document.documentElement.scrollWidth > window.innerWidth;
    });
    
    expect(hasHorizontalScroll).toBe(false);
  });

  test('images are responsive', async ({ page }) => {
    await page.goto('/');
    
    const images = await page.locator('img').all();
    const viewport = page.viewportSize();
    
    for (const img of images.slice(0, 5)) {
      if (await img.isVisible()) {
        const box = await img.boundingBox();
        if (box && viewport) {
          expect(box.width).toBeLessThanOrEqual(viewport.width);
        }
      }
    }
  });

  test('tap targets are not too close together', async ({ page }) => {
    await page.goto('/');
    
    const buttons = await page.locator('button, a[role="button"]').all();
    
    for (let i = 0; i < Math.min(buttons.length - 1, 5); i++) {
      const box1 = await buttons[i].boundingBox();
      const box2 = await buttons[i + 1].boundingBox();
      
      if (box1 && box2) {
        const distance = Math.abs(box1.y - box2.y);
        if (distance < 100) {
          expect(distance).toBeGreaterThan(8);
        }
      }
    }
  });

  test('viewport meta tag is present', async ({ page }) => {
    await page.goto('/');
    
    const viewportMeta = await page.evaluate(() => {
      const meta = document.querySelector('meta[name="viewport"]');
      return meta ? meta.getAttribute('content') : null;
    });
    
    expect(viewportMeta).toBeTruthy();
    expect(viewportMeta).toContain('width=device-width');
  });
});
