/**
 * E2E auth flow — register a fresh user, verify cookies are set
 * with httpOnly + CSRF, list empty papers, refresh, logout.
 *
 * Uses a single browser context throughout so cookies persist between requests.
 */
import { test, expect } from '@playwright/test';

const E2E_USER = {
  email: `e2e-${Date.now()}@e2e.local`,
  name: 'E2E Test User',
  password: 'E2eStrongPass123!',
};

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

test('full auth flow: register → me → CSRF → refresh → logout', async ({ page }) => {
  const ctx = page.context();
  const api = ctx.request;

  // 1. Register
  const reg = await api.post('/api/auth/register', { data: E2E_USER });
  expect(reg.status()).toBe(201);
  const regBody = await reg.json();
  expect(regBody.user.email).toBe(E2E_USER.email);

  // 2. Verify cookies are set with the right flags
  let cookies = await ctx.cookies();
  const names = cookies.map((c) => c.name);
  expect(names).toContain('access_token_cookie');
  expect(names).toContain('refresh_token_cookie');
  expect(names).toContain('csrf_access_token');
  expect(names).toContain('csrf_refresh_token');

  const access = cookies.find((c) => c.name === 'access_token_cookie');
  expect(access?.httpOnly).toBe(true);
  const csrf = cookies.find((c) => c.name === 'csrf_access_token');
  expect(csrf?.httpOnly).toBe(false); // CSRF cookie must be JS-readable

  // 3. /me works while authenticated
  const me = await api.get('/api/auth/me');
  expect(me.status()).toBe(200);
  expect((await me.json()).email).toBe(E2E_USER.email);

  // 4. List papers — empty for new user
  const papers = await api.get('/api/papers');
  expect(papers.status()).toBe(200);
  const papersBody = await papers.json();
  expect(papersBody.papers).toEqual([]);
  expect(papersBody.pagination.total).toBe(0);

  // 5. CSRF: POST without header is rejected
  const noCsrf = await api.post('/api/papers', {
    data: { title: 'CSRF probe', data: { foo: 'bar' } },
    failOnStatusCode: false,
  });
  expect([400, 401]).toContain(noCsrf.status());

  // 6. CSRF: POST with header succeeds
  const ok = await api.post('/api/papers', {
    data: { title: 'E2E paper', data: { test: true } },
    headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
  });
  expect(ok.status()).toBe(200);
  const okBody = await ok.json();
  expect(okBody.success).toBe(true);
  const createdId = okBody.id;
  expect(createdId).toBeTruthy();

  // 7. Refresh rotates tokens
  cookies = await ctx.cookies();
  const accessBefore = cookies.find((c) => c.name === 'access_token_cookie')?.value;
  const ref = await api.post('/api/auth/refresh', {
    headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies, 'csrf_refresh_token') },
  });
  expect(ref.status()).toBe(200);
  cookies = await ctx.cookies();
  const accessAfter = cookies.find((c) => c.name === 'access_token_cookie')?.value;
  expect(accessAfter).not.toBe(accessBefore);

  // 8. Logout clears cookies; subsequent /me should be 401
  const logout = await api.post('/api/auth/logout', {
    headers: { 'X-CSRF-TOKEN': csrfFromCookies(await ctx.cookies()) },
  });
  expect(logout.status()).toBe(200);

  const meAfter = await api.get('/api/auth/me', { failOnStatusCode: false });
  expect(meAfter.status()).toBe(401);

  // 9. Cleanup: delete the e2e user via DB? — skipped, leave for backend job.
});
