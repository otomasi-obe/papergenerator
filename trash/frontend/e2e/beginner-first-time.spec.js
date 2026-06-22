/**
 * E2E Test: Beginner User - First Time Experience
 * 
 * Persona: Mahasiswa semester 3, pertama kali bikin paper ilmiah, bingung mulai dari mana
 * 
 * Test Scenario: Complete onboarding and guidance flow for new users
 * 
 * Focus areas:
 * - Onboarding clarity
 * - AI guidance quality
 * - Error handling
 * - Time to first success
 */
import { test, expect } from '@playwright/test';

const BEGINNER_USER = {
  email: `beginner-${Date.now()}@student.local`,
  name: 'Mahasiswa Baru',
  password: 'BeginnerPass123!',
};

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

test.describe('Beginner User - First Time Experience', () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
    await context.clearPermissions();
  });

  test('complete first-time user journey: landing → register → onboarding → first paper', async ({ page }) => {
    const startTime = Date.now();
    const ctx = page.context();
    const api = ctx.request;
    
    const uxIssues = [];
    const timings = {};

    // ===== 1. LANDING PAGE CLARITY =====
    console.log('\n[TEST] Step 1: Landing page clarity');
    await page.goto('/');
    timings.landingPageLoad = Date.now() - startTime;
    
    await expect(page).toHaveTitle(/PaperFull|Paper Generator/i);
    
    const hasHero = await page.locator('h1, [class*="hero"], [class*="headline"]').count() > 0;
    if (!hasHero) {
      uxIssues.push('Landing page missing clear hero/headline');
    }
    
    const ctaButtons = page.locator('button, a').filter({ 
      hasText: /mulai|daftar|gratis|start|sign up|get started/i 
    });
    const ctaCount = await ctaButtons.count();
    
    if (ctaCount === 0) {
      uxIssues.push('No clear CTA button found on landing page');
    }
    
    const hasValueProposition = await page.locator('text=/generator|otomatis|AI|mudah|cepat/i').count() > 0;
    if (!hasValueProposition) {
      uxIssues.push('Value proposition not clearly communicated');
    }

    // ===== 2. CLICK CTA AND NAVIGATE TO REGISTRATION =====
    console.log('\n[TEST] Step 2: CTA click and registration flow');
    
    const primaryCta = ctaButtons.first();
    if (ctaCount > 0) {
      await primaryCta.click();
      await page.waitForLoadState('networkidle');
      timings.ctaToRegistration = Date.now() - startTime;
    } else {
      await page.goto('/register');
    }
    
    const currentUrl = page.url();
    const isOnAuthPage = currentUrl.includes('/register') || currentUrl.includes('/login') || currentUrl.includes('/auth');
    
    if (!isOnAuthPage) {
      uxIssues.push(`CTA did not lead to registration/auth page. Current URL: ${currentUrl}`);
    }

    // ===== 3. COMPLETE REGISTRATION =====
    console.log('\n[TEST] Step 3: Complete registration');
    
    if (!currentUrl.includes('/register')) {
      const registerLink = page.locator('a, button').filter({ hasText: /daftar|register|sign up/i });
      if (await registerLink.count() > 0) {
        await registerLink.first().click();
        await page.waitForLoadState('networkidle');
      } else {
        await page.goto('/register');
      }
    }
    
    const emailInput = page.locator('input[type="email"], input[name="email"]');
    const passwordInput = page.locator('input[type="password"], input[name="password"]');
    const nameInput = page.locator('input[name="name"], input[placeholder*="nama"]');
    
    await expect(emailInput).toBeVisible({ timeout: 5000 });
    
    await emailInput.fill(BEGINNER_USER.email);
    await passwordInput.fill(BEGINNER_USER.password);
    
    if (await nameInput.count() > 0) {
      await nameInput.fill(BEGINNER_USER.name);
    }
    
    const submitButton = page.locator('button[type="submit"], button').filter({ 
      hasText: /daftar|register|sign up|submit/i 
    });
    
    await submitButton.click();
    await page.waitForLoadState('networkidle');
    timings.registrationComplete = Date.now() - startTime;
    
    const cookies = await ctx.cookies();
    const hasAuthCookie = cookies.some(c => c.name === 'access_token_cookie');
    
    if (!hasAuthCookie) {
      uxIssues.push('Registration did not set authentication cookies');
    }

    // ===== 4. ONBOARDING FLOW OBSERVATION =====
    console.log('\n[TEST] Step 4: Onboarding flow');
    
    await page.waitForTimeout(1000);
    
    const hasOnboardingModal = await page.locator('[class*="modal"], [class*="onboard"], [class*="welcome"]').count() > 0;
    const hasOnboardingTour = await page.locator('[class*="tour"], [class*="guide"], [class*="tutorial"]').count() > 0;
    const hasWelcomeMessage = await page.locator('text=/selamat datang|welcome|mulai|get started/i').count() > 0;
    
    if (!hasOnboardingModal && !hasOnboardingTour && !hasWelcomeMessage) {
      uxIssues.push('No onboarding flow detected for new user');
    }
    
    if (hasOnboardingModal || hasOnboardingTour) {
      const skipButton = page.locator('button').filter({ hasText: /skip|lewati|close/i });
      const nextButton = page.locator('button').filter({ hasText: /next|lanjut|mulai/i });
      
      if (await nextButton.count() > 0) {
        await nextButton.first().click();
        await page.waitForTimeout(500);
      }
    }

    // ===== 5. NAVIGATE TO PAPER CREATION =====
    console.log('\n[TEST] Step 5: Navigate to paper creation');
    
    const createButton = page.locator('button, a').filter({ 
      hasText: /buat|create|new|paper|mulai/i 
    });
    
    if (await createButton.count() === 0) {
      uxIssues.push('No clear "Create Paper" button found on dashboard');
      await page.goto('/papers/new');
    } else {
      await createButton.first().click();
      await page.waitForLoadState('networkidle');
    }
    
    timings.toPaperCreation = Date.now() - startTime;

    // ===== 6. TEST AI GUIDANCE WITHOUT CLEAR TOPIC =====
    console.log('\n[TEST] Step 6: Test AI guidance quality');
    
    const titleInput = page.locator('input[name="title"], input[placeholder*="judul"], textarea[placeholder*="judul"]');
    const topicInput = page.locator('input[name="topic"], textarea[name="topic"], input[placeholder*="topik"]');
    
    if (await titleInput.count() > 0) {
      await titleInput.fill('');
    }
    
    if (await topicInput.count() > 0) {
      await topicInput.fill('saya bingung mau nulis apa');
    }
    
    const hasAiSuggestion = await page.locator('text=/saran|suggestion|rekomendasi|bantuan|help/i').count() > 0;
    const hasGuidanceText = await page.locator('text=/pilih topik|tentukan tema|mulai dengan/i').count() > 0;
    
    if (!hasAiSuggestion && !hasGuidanceText) {
      uxIssues.push('No AI guidance or suggestions visible when user is confused');
    }
    
    const aiAssistButton = page.locator('button').filter({ 
      hasText: /AI|bantuan|help|saran|suggestion/i 
    });
    
    if (await aiAssistButton.count() > 0) {
      await aiAssistButton.first().click();
      await page.waitForTimeout(1000);
      
      const aiResponse = await page.locator('[class*="ai"], [class*="assistant"], [class*="suggestion"]').count() > 0;
      if (!aiResponse) {
        uxIssues.push('AI assistance button clicked but no response visible');
      }
    }

    // ===== 7. TEST ERROR HANDLING - SKIP REQUIRED FIELDS =====
    console.log('\n[TEST] Step 7: Test error handling');
    
    const submitPaperButton = page.locator('button[type="submit"], button').filter({ 
      hasText: /buat|create|submit|simpan|save/i 
    });
    
    if (await submitPaperButton.count() > 0) {
      await submitPaperButton.first().click();
      await page.waitForTimeout(500);
      
      const errorMessage = await page.locator('[class*="error"], [class*="alert"], [role="alert"]').count() > 0;
      const validationMessage = await page.locator('text=/required|wajib|harus|diisi/i').count() > 0;
      
      if (!errorMessage && !validationMessage) {
        uxIssues.push('No error message shown when submitting incomplete form');
      }
      
      const errorText = await page.locator('[class*="error"], [role="alert"]').first().textContent().catch(() => '');
      if (errorText && !errorText.match(/judul|title|topik|topic|field|wajib|required/i)) {
        uxIssues.push(`Error message not helpful: "${errorText}"`);
      }
    }

    // ===== 8. TEST HELP/DOCUMENTATION ACCESS =====
    console.log('\n[TEST] Step 8: Test help/documentation access');
    
    const helpButton = page.locator('button, a').filter({ 
      hasText: /help|bantuan|panduan|guide|\?/i 
    });
    
    if (await helpButton.count() === 0) {
      uxIssues.push('No help/documentation button found');
    } else {
      const helpButtonVisible = await helpButton.first().isVisible();
      if (!helpButtonVisible) {
        uxIssues.push('Help button exists but not visible');
      }
    }
    
    const hasTooltips = await page.locator('[title], [data-tooltip], [aria-label]').count() > 0;
    if (!hasTooltips) {
      uxIssues.push('No tooltips or aria-labels found for guidance');
    }

    // ===== 9. COMPLETE PAPER CREATION WITH VALID DATA =====
    console.log('\n[TEST] Step 9: Complete paper creation with valid data');
    
    if (await titleInput.count() > 0) {
      await titleInput.fill('Pengaruh Teknologi AI terhadap Pendidikan');
    }
    
    if (await topicInput.count() > 0) {
      await topicInput.fill('Artificial Intelligence dalam pendidikan tinggi');
    }
    
    const typeSelect = page.locator('select[name="type"], select[name="paper_type"]');
    if (await typeSelect.count() > 0) {
      await typeSelect.selectOption({ index: 1 });
    }
    
    if (await submitPaperButton.count() > 0) {
      await submitPaperButton.first().click();
      await page.waitForLoadState('networkidle');
      timings.firstPaperCreated = Date.now() - startTime;
      
      const successMessage = await page.locator('text=/berhasil|success|created/i').count() > 0;
      const isPaperPage = page.url().includes('/paper') || page.url().includes('/edit');
      
      if (!successMessage && !isPaperPage) {
        uxIssues.push('Paper creation unclear - no success message or redirect');
      }
    }

    // ===== 10. MEASURE TIME TO FIRST PAPER =====
    const timeToFirstPaper = (timings.firstPaperCreated || Date.now() - startTime) / 1000;
    
    console.log('\n========================================');
    console.log('BEGINNER USER EXPERIENCE TEST RESULTS');
    console.log('========================================\n');
    
    console.log('TIMINGS:');
    console.log(`  Landing page load: ${timings.landingPageLoad}ms`);
    console.log(`  CTA to registration: ${timings.ctaToRegistration}ms`);
    console.log(`  Registration complete: ${timings.registrationComplete}ms`);
    console.log(`  To paper creation: ${timings.toPaperCreation}ms`);
    console.log(`  First paper created: ${timings.firstPaperCreated}ms`);
    console.log(`  Total time to first paper: ${timeToFirstPaper.toFixed(2)}s\n`);
    
    console.log('UX ASSESSMENT:');
    if (uxIssues.length === 0) {
      console.log('  ✓ No major UX issues detected');
    } else {
      console.log(`  ✗ ${uxIssues.length} UX issues found:`);
      uxIssues.forEach((issue, i) => {
        console.log(`    ${i + 1}. ${issue}`);
      });
    }
    
    console.log('\n========================================\n');
    
    expect(timeToFirstPaper).toBeLessThan(120);
    expect(uxIssues.length).toBeLessThan(5);
  });

  test('test error recovery: invalid data → correction → success', async ({ page }) => {
    const ctx = page.context();
    
    await page.goto('/register');
    
    const emailInput = page.locator('input[type="email"]');
    const passwordInput = page.locator('input[type="password"]');
    
    await emailInput.fill('invalid-email');
    await passwordInput.fill('weak');
    
    const submitButton = page.locator('button[type="submit"]');
    await submitButton.click();
    await page.waitForTimeout(500);
    
    const hasError = await page.locator('[class*="error"], [role="alert"]').count() > 0;
    expect(hasError).toBe(true);
    
    await emailInput.fill(`recovery-${Date.now()}@test.local`);
    await passwordInput.fill('StrongPass123!');
    
    await submitButton.click();
    await page.waitForLoadState('networkidle');
    
    const cookies = await ctx.cookies();
    const hasAuthCookie = cookies.some(c => c.name === 'access_token_cookie');
    expect(hasAuthCookie).toBe(true);
  });

  test('test cancel operations and navigation', async ({ page }) => {
    await page.goto('/');
    
    const createButton = page.locator('button, a').filter({ 
      hasText: /buat|create|new/i 
    }).first();
    
    if (await createButton.count() > 0) {
      await createButton.click();
      await page.waitForTimeout(500);
      
      const cancelButton = page.locator('button').filter({ 
        hasText: /cancel|batal|kembali|back/i 
      });
      
      if (await cancelButton.count() > 0) {
        await cancelButton.first().click();
        await page.waitForTimeout(500);
        
        const isBackToDashboard = !page.url().includes('/new') && !page.url().includes('/create');
        expect(isBackToDashboard).toBe(true);
      }
    }
  });
});
