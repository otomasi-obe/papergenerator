/**
 * E2E smoke tests — exercise the public surface that's reachable without
 * a logged-in session. Auth-protected flows live in auth.spec.js.
 */
import { test, expect } from '@playwright/test';

test('landing page renders', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/PaperFull|Paper Generator/i);
});

test('login page is reachable and shows form', async ({ page }) => {
  await page.goto('/login');
  // Form fields are typed inputs; query by type rather than placeholder text.
  await expect(page.locator('input[type="email"]')).toBeVisible();
  await expect(page.locator('input[type="password"]')).toBeVisible();
});

test('health endpoint returns ok', async ({ request }) => {
  const res = await request.get('/api/health');
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.status).toBe('ok');
});

test('healthz reports DB + disk', async ({ request }) => {
  const res = await request.get('/api/healthz');
  // Either 200 (healthy) or 503 (degraded) — both are valid responses,
  // we only assert the schema.
  expect([200, 503]).toContain(res.status());
  const body = await res.json();
  expect(body).toHaveProperty('checks');
  expect(body.checks).toHaveProperty('db');
  expect(body.checks).toHaveProperty('disk');
});

test('metrics endpoint exposes Prometheus format', async ({ request }) => {
  const res = await request.get('/api/metrics').catch(() => null);
  // /metrics is mounted at root, not /api — try both.
  const r2 = res && res.ok() ? res : await request.get('/metrics');
  expect(r2.status()).toBe(200);
  const text = await r2.text();
  expect(text).toMatch(/^# HELP /m);
  expect(text).toMatch(/http_requests_total/);
});

test('papers endpoint requires auth', async ({ request }) => {
  const res = await request.get('/api/papers');
  expect(res.status()).toBe(401);
});

test('login with bad credentials returns 401', async ({ request }) => {
  const res = await request.post('/api/auth/login', {
    data: { email: 'nonexistent@e2e.invalid', password: 'wrong' },
  });
  expect(res.status()).toBe(401);
  const body = await res.json();
  expect(body).toHaveProperty('error');
});

test('openapi spec is served', async ({ request }) => {
  const res = await request.get('/api/openapi.yaml');
  expect(res.status()).toBe(200);
  const text = await res.text();
  expect(text).toContain('openapi: "3.1.0"');
  expect(text).toContain('PaperFull API');
});

test('swagger UI page renders', async ({ page }) => {
  const res = await page.goto('/api/docs');
  expect(res?.status()).toBe(200);
  // Wait for Swagger UI to mount.
  await expect(page.locator('#swagger')).toBeVisible();
});

test('security headers are present', async ({ request }) => {
  const res = await request.get('/api/health');
  expect(res.headers()['x-content-type-options']).toBe('nosniff');
  expect(res.headers()['x-frame-options']).toBe('DENY');
  expect(res.headers()['referrer-policy']).toBe('strict-origin-when-cross-origin');
  expect(res.headers()['x-request-id']).toMatch(/^[a-f0-9]+$/);
});
