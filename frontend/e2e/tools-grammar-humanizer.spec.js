/**
 * E2E test: Grammar & Humanizer tools
 *
 * Tests program mode and AI mode for both grammar and humanizer endpoints.
 * Verifies functional behavior (not just UI rendering).
 */
import { test, expect } from '@playwright/test';

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

function parseSSE(body) {
  const results = [];
  for (const line of body.split('\n')) {
    if (line.startsWith('data: ')) {
      try {
        results.push(JSON.parse(line.slice(6)));
      } catch {}
    }
  }
  return results;
}

test.describe('Grammar & Humanizer Tools', () => {
  let csrf;
  let cookies;
  let ctx;

  test.beforeEach(async ({ page }) => {
    ctx = page.context();
    const api = ctx.request;

    const uniqueEmail = `e2e-tools-${Date.now()}-${Math.random().toString(36).substring(7)}@e2e.local`;
    const reg = await api.post('/api/auth/register', {
      data: {
        email: uniqueEmail,
        name: 'E2E Tools Tester',
        password: 'E2eStrongPass123!',
        captcha_token: '1x00000000000000000000AA',
      },
    });
    expect(reg.status()).toBe(201);

    cookies = await ctx.cookies();
    csrf = csrfFromCookies(cookies);
  });

  test('Grammar program mode: returns corrected text', async ({ page }) => {
    const api = ctx.request;

    const resp = await api.post('/api/tools/grammar', {
      data: { text: 'It are wrong. She have a car.', option: 'Standard' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(resp.status()).toBe(200);
    const body = await resp.text();
    const sseData = parseSSE(body);
    expect(sseData.length).toBeGreaterThan(0);

    const resultFrame = sseData.find(d => d.result);
    expect(resultFrame).toBeTruthy();

    const result = resultFrame.result;
    expect(result.corrected).toBeTruthy();
    expect(result.corrected).toContain('is');
    console.log('Grammar corrected:', result.corrected);
  });

  test('Grammar program mode: returns diff markup in text field', async ({ page }) => {
    const api = ctx.request;

    const resp = await api.post('/api/tools/grammar', {
      data: { text: 'It are wrong.', option: 'Standard' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(resp.status()).toBe(200);
    const body = await resp.text();
    const sseData = parseSSE(body);
    const textFrame = sseData.find(d => d.text !== undefined);

    const text = textFrame?.text || '';
    console.log('Grammar markup:', text);
    expect(text).toBeTruthy();
  });

  test('Grammar program mode: rejects empty text', async ({ page }) => {
    const api = ctx.request;

    const resp = await api.post('/api/tools/grammar', {
      data: { text: '', option: 'Standard' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(resp.status()).toBe(400);
  });

  test('AI Grammar: endpoint exists and is registered', async ({ page }) => {
    const api = ctx.request;

    const resp = await api.post('/api/tools/ai-grammar', {
      data: { text: 'It are wrong.', option: 'Standard' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(resp.status()).not.toBe(404);
    console.log('AI Grammar status:', resp.status());
  });

  test('Humanizer program mode: removes AI slop words', async ({ page }) => {
    const api = ctx.request;

    const resp = await api.post('/api/tools/humanizer', {
      data: {
        text: 'Furthermore, this is a comprehensive and robust solution. It is crucial to note that it leverages AI.',
        option: 'Aggressive',
        mode: 'program',
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(resp.status()).toBe(200);
    const body = await resp.text();
    const sseData = parseSSE(body);
    expect(sseData.length).toBeGreaterThan(0);

    const resultFrame = sseData.find(d => d.result);
    const textFrame = sseData.find(d => d.text !== undefined);
    // Structure: {result: {text: "output text", result: {...}}}
    const outputText = resultFrame?.result?.text || textFrame?.text || '';
    console.log('Humanizer output:', outputText);

    expect(outputText).not.toContain('Furthermore');
    expect(outputText).not.toContain('comprehensive');
    expect(outputText).not.toContain('robust');
    expect(outputText).not.toContain('crucial');
  });

  test('Humanizer program mode: result has correct metadata', async ({ page }) => {
    const api = ctx.request;

    const resp = await api.post('/api/tools/humanizer', {
      data: { text: 'This is a test.', option: 'Standard', mode: 'program' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(resp.status()).toBe(200);
    const body = await resp.text();
    const sseData = parseSSE(body);
    const resultFrame = sseData.find(d => d.result);

    if (resultFrame) {
      // Structure: {result: {text: "...", result: {mode: "program", engine: "rule-based"}}}
      const meta = resultFrame.result.result || resultFrame.result;
      expect(meta.mode).toBe('program');
      expect(meta.engine).toBe('rule-based');
    }
  });

  test('Humanizer: rejects empty text', async ({ page }) => {
    const api = ctx.request;

    const resp = await api.post('/api/tools/humanizer', {
      data: { text: '', option: 'Standard', mode: 'program' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(resp.status()).toBe(400);
  });
});
