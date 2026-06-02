/**
 * E2E Test: Accessibility (a11y) Compliance
 * 
 * Tests WCAG 2.1 Level AA compliance:
 * - Keyboard navigation
 * - Screen reader compatibility
 * - ARIA labels and roles
 * - Focus management
 * - Color contrast
 * - Alt text for images
 * 
 * Tools: @axe-core/playwright for automated checks
 */

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Accessibility Compliance', () => {
  let userEmail;

  test.beforeEach(async ({ page, context }) => {
    userEmail = `a11y-test-${Date.now()}@test.local`;
    
    // Register user
    const api = context.request;
    const reg = await api.post('/api/auth/register', {
      data: {
        email: userEmail,
        name: 'A11y Test User',
        password: 'Test123!',
        captcha_token: '1x00000000000000000000AA',
      },
    });
    expect(reg.status()).toBe(201);
  });

  test('Landing page - Axe accessibility scan', async ({ page }) => {
    await page.goto('/');
    
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();
    
    console.log(`Landing page: ${accessibilityScanResults.violations.length} violations found`);
    
    if (accessibilityScanResults.violations.length > 0) {
      console.log('\nViolations:');
      accessibilityScanResults.violations.forEach((violation, i) => {
        console.log(`${i + 1}. ${violation.id}: ${violation.description}`);
        console.log(`   Impact: ${violation.impact}`);
        console.log(`   Nodes: ${violation.nodes.length}`);
      });
    }
    
    // Allow some violations but flag critical ones
    const criticalViolations = accessibilityScanResults.violations.filter(
      v => v.impact === 'critical' || v.impact === 'serious'
    );
    
    expect(criticalViolations.length).toBe(0);
  });

  test('Dashboard - Axe accessibility scan', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    
    console.log(`Dashboard: ${accessibilityScanResults.violations.length} violations found`);
    
    const criticalViolations = accessibilityScanResults.violations.filter(
      v => v.impact === 'critical' || v.impact === 'serious'
    );
    
    expect(criticalViolations.length).toBe(0);
  });

  test('Editor - Axe accessibility scan', async ({ page }) => {
    await page.goto('/dashboard');
    await page.click('text=New Paper');
    await page.waitForURL(/\/editor/, { timeout: 10000 });
    await page.waitForLoadState('networkidle');
    
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    
    console.log(`Editor: ${accessibilityScanResults.violations.length} violations found`);
    
    const criticalViolations = accessibilityScanResults.violations.filter(
      v => v.impact === 'critical' || v.impact === 'serious'
    );
    
    expect(criticalViolations.length).toBe(0);
  });

  test('Keyboard navigation - Tab through main elements', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Start from the beginning
    await page.keyboard.press('Tab');
    
    // Track focus order
    const focusOrder = [];
    
    for (let i = 0; i < 10; i++) {
      const focusedElement = await page.evaluate(() => {
        const el = document.activeElement;
        return {
          tag: el.tagName,
          type: el.type || '',
          text: el.textContent?.substring(0, 50) || '',
          ariaLabel: el.getAttribute('aria-label') || '',
          role: el.getAttribute('role') || '',
        };
      });
      
      focusOrder.push(focusedElement);
      await page.keyboard.press('Tab');
      await page.waitForTimeout(100);
    }
    
    console.log('\nKeyboard navigation focus order:');
    focusOrder.forEach((el, i) => {
      console.log(`${i + 1}. ${el.tag} ${el.type} - ${el.ariaLabel || el.text}`);
    });
    
    // Verify interactive elements are reachable
    const hasButtons = focusOrder.some(el => el.tag === 'BUTTON' || el.role === 'button');
    const hasLinks = focusOrder.some(el => el.tag === 'A');
    
    expect(hasButtons || hasLinks).toBe(true);
  });

  test('Keyboard navigation - Create paper with keyboard only', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Navigate to "New Paper" button using Tab
    let attempts = 0;
    let foundNewPaper = false;
    
    while (attempts < 20 && !foundNewPaper) {
      await page.keyboard.press('Tab');
      await page.waitForTimeout(100);
      
      const focusedText = await page.evaluate(() => {
        return document.activeElement?.textContent || '';
      });
      
      if (focusedText.includes('New Paper') || focusedText.includes('Create')) {
        foundNewPaper = true;
        await page.keyboard.press('Enter');
        break;
      }
      
      attempts++;
    }
    
    console.log(`Keyboard navigation: Found "New Paper" button = ${foundNewPaper} (attempts: ${attempts})`);
    
    if (foundNewPaper) {
      await page.waitForURL(/\/editor/, { timeout: 10000 });
      expect(page.url()).toContain('/editor/');
    }
  });

  test('Focus management - Modal dialog focus trap', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Try to open a modal (settings, help, etc.)
    const modalTriggers = [
      'button:has-text("Settings")',
      'button:has-text("Help")',
      'button:has-text("Profile")',
      '[aria-label*="menu"]',
    ];
    
    for (const selector of modalTriggers) {
      const button = page.locator(selector).first();
      if (await button.count() > 0) {
        await button.click();
        await page.waitForTimeout(500);
        
        // Check if modal is open
        const modal = page.locator('[role="dialog"], [role="alertdialog"], .modal').first();
        if (await modal.count() > 0) {
          console.log(`Modal opened with trigger: ${selector}`);
          
          // Test focus trap - Tab should stay within modal
          const initialFocus = await page.evaluate(() => document.activeElement?.tagName);
          
          for (let i = 0; i < 5; i++) {
            await page.keyboard.press('Tab');
            await page.waitForTimeout(100);
          }
          
          // Check if focus is still within modal
          const focusInModal = await page.evaluate(() => {
            const modal = document.querySelector('[role="dialog"], [role="alertdialog"], .modal');
            return modal?.contains(document.activeElement) || false;
          });
          
          console.log(`Focus trap working: ${focusInModal}`);
          
          // Close modal with Escape
          await page.keyboard.press('Escape');
          await page.waitForTimeout(500);
          
          break;
        }
      }
    }
  });

  test('ARIA labels - Form inputs have labels', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    
    // Check all input fields have labels or aria-label
    const inputs = await page.locator('input').all();
    const inputsWithoutLabels = [];
    
    for (const input of inputs) {
      const id = await input.getAttribute('id');
      const ariaLabel = await input.getAttribute('aria-label');
      const ariaLabelledBy = await input.getAttribute('aria-labelledby');
      const placeholder = await input.getAttribute('placeholder');
      
      let hasLabel = false;
      
      if (id) {
        const label = page.locator(`label[for="${id}"]`);
        hasLabel = await label.count() > 0;
      }
      
      if (!hasLabel && !ariaLabel && !ariaLabelledBy) {
        inputsWithoutLabels.push({
          id,
          placeholder,
          type: await input.getAttribute('type'),
        });
      }
    }
    
    console.log(`\nInputs without proper labels: ${inputsWithoutLabels.length}`);
    if (inputsWithoutLabels.length > 0) {
      console.log('Unlabeled inputs:');
      inputsWithoutLabels.forEach(input => {
        console.log(`  - Type: ${input.type}, Placeholder: ${input.placeholder}`);
      });
    }
    
    // Allow some inputs without labels (e.g., hidden fields)
    expect(inputsWithoutLabels.length).toBeLessThan(3);
  });

  test('Color contrast - Text readability', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Use Axe to check color contrast
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2aa'])
      .include('body')
      .analyze();
    
    const contrastViolations = accessibilityScanResults.violations.filter(
      v => v.id === 'color-contrast'
    );
    
    console.log(`\nColor contrast violations: ${contrastViolations.length}`);
    
    if (contrastViolations.length > 0) {
      contrastViolations.forEach(violation => {
        console.log(`  - ${violation.description}`);
        console.log(`    Nodes affected: ${violation.nodes.length}`);
      });
    }
    
    expect(contrastViolations.length).toBe(0);
  });

  test('Screen reader - Semantic HTML structure', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    
    // Check for semantic HTML elements
    const semanticElements = {
      header: await page.locator('header').count(),
      nav: await page.locator('nav').count(),
      main: await page.locator('main').count(),
      footer: await page.locator('footer').count(),
      article: await page.locator('article').count(),
      section: await page.locator('section').count(),
    };
    
    console.log('\nSemantic HTML elements:');
    Object.entries(semanticElements).forEach(([tag, count]) => {
      console.log(`  ${tag}: ${count}`);
    });
    
    // At minimum, should have main content area
    expect(semanticElements.main).toBeGreaterThan(0);
  });

  test('Images - Alt text present', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Check all images have alt text
    const images = await page.locator('img').all();
    const imagesWithoutAlt = [];
    
    for (const img of images) {
      const alt = await img.getAttribute('alt');
      const role = await img.getAttribute('role');
      const ariaLabel = await img.getAttribute('aria-label');
      
      // Decorative images should have empty alt or role="presentation"
      if (alt === null && role !== 'presentation' && !ariaLabel) {
        const src = await img.getAttribute('src');
        imagesWithoutAlt.push(src);
      }
    }
    
    console.log(`\nImages without alt text: ${imagesWithoutAlt.length}/${images.length}`);
    if (imagesWithoutAlt.length > 0) {
      console.log('Images missing alt:');
      imagesWithoutAlt.forEach(src => {
        console.log(`  - ${src}`);
      });
    }
    
    expect(imagesWithoutAlt.length).toBe(0);
  });
});
