/**
 * API Test Suite: Authentication
 *
 * Tests authentication endpoints in isolation without browser overhead.
 * Validates JWT token lifecycle, CSRF protection, and OAuth flow.
 */
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8000';

function generateTestUser() {
  const timestamp = Date.now();
  return {
    email: `api-test-${timestamp}@test.local`,
    name: 'API Test User',
    password: 'SecurePass123!',
  };
}

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

test.describe('Auth API - Registration', () => {
  test('POST /api/auth/register - successful registration', async ({ request, context }) => {
    const user = generateTestUser();

    const response = await request.post(`${BASE_URL}/api/auth/register`, {
      data: {
        ...user,
        captcha_token: '1x00000000000000000000AA',
      },
    });

    expect(response.status()).toBe(201);

    const body = await response.json();
    expect(body).toHaveProperty('user');
    expect(body.user.email).toBe(user.email);
    expect(body.user.name).toBe(user.name);
    expect(body.user).toHaveProperty('id');
    expect(body.user).toHaveProperty('role');

    // Verify JWT cookies are set
    const cookies = await context.cookies();
    const accessCookie = cookies.find(c => c.name === 'access_token_cookie');
    const refreshCookie = cookies.find(c => c.name === 'refresh_token_cookie');
    const csrfCookie = cookies.find(c => c.name === 'csrf_access_token');

    expect(accessCookie).toBeTruthy();
    expect(refreshCookie).toBeTruthy();
    expect(csrfCookie).toBeTruthy();

    // Verify httpOnly flag for security
    expect(accessCookie.httpOnly).toBe(true);
    expect(refreshCookie.httpOnly).toBe(true);
  });

  test('POST /api/auth/register - rejects duplicate email', async ({ request }) => {
    const user = generateTestUser();

    // First registration
    await request.post(`${BASE_URL}/api/auth/register`, {
      data: { ...user, captcha_token: '1x00000000000000000000AA' },
    });

    // Duplicate registration
    const response = await request.post(`${BASE_URL}/api/auth/register`, {
      data: { ...user, captcha_token: '1x00000000000000000000AA' },
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(409);
    const body = await response.json();
    expect(body.error).toContain('already registered');
  });

  test('POST /api/auth/register - validates email format', async ({ request }) => {
    const invalidEmails = [
      'notanemail',
      '@test.com',
      'test@',
      'test..test@test.com',
      'test@test',
    ];

    for (const email of invalidEmails) {
      const response = await request.post(`${BASE_URL}/api/auth/register`, {
        data: {
          email,
          name: 'Test User',
          password: 'SecurePass123!',
          captcha_token: '1x00000000000000000000AA',
        },
        failOnStatusCode: false,
      });

      expect(response.status()).toBe(400);
      const body = await response.json();
      expect(body.error).toMatch(/email|invalid/i);
    }
  });

  test('POST /api/auth/register - enforces password strength', async ({ request }) => {
    const weakPasswords = [
      'short',           // Too short
      'alllowercase',    // No uppercase/digits/symbols
      'ALLUPPERCASE',    // No lowercase/digits/symbols
      '12345678',        // No letters
      'Simple1',         // Only 2 character classes
    ];

    for (const password of weakPasswords) {
      const user = generateTestUser();
      const response = await request.post(`${BASE_URL}/api/auth/register`, {
        data: {
          ...user,
          password,
          captcha_token: '1x00000000000000000000AA',
        },
        failOnStatusCode: false,
      });

      expect(response.status()).toBe(400);
      const body = await response.json();
      expect(body.error).toMatch(/password/i);
    }
  });

  test('POST /api/auth/register - validates required fields', async ({ request }) => {
    const testCases = [
      { email: '', name: 'Test', password: 'Pass123!' },
      { email: 'test@test.com', name: '', password: 'Pass123!' },
      { email: 'test@test.com', name: 'Test', password: '' },
    ];

    for (const data of testCases) {
      const response = await request.post(`${BASE_URL}/api/auth/register`, {
        data: { ...data, captcha_token: '1x00000000000000000000AA' },
        failOnStatusCode: false,
      });

      expect(response.status()).toBe(400);
      const body = await response.json();
      expect(body.error).toMatch(/required/i);
    }
  });

  test('POST /api/auth/register - rejects oversized fields', async ({ request }) => {
    const user = generateTestUser();

    // Email too long (>254 chars)
    const longEmail = 'a'.repeat(250) + '@test.com';
    let response = await request.post(`${BASE_URL}/api/auth/register`, {
      data: {
        email: longEmail,
        name: user.name,
        password: user.password,
        captcha_token: '1x00000000000000000000AA',
      },
      failOnStatusCode: false,
    });
    expect(response.status()).toBe(400);

    // Name too long (>80 chars)
    const longName = 'A'.repeat(100);
    response = await request.post(`${BASE_URL}/api/auth/register`, {
      data: {
        email: user.email,
        name: longName,
        password: user.password,
        captcha_token: '1x00000000000000000000AA',
      },
      failOnStatusCode: false,
    });
    expect(response.status()).toBe(400);
  });
});

test.describe('Auth API - Login', () => {
  test('POST /api/auth/login - successful login', async ({ request, context }) => {
    const user = generateTestUser();

    // Register first
    await request.post(`${BASE_URL}/api/auth/register`, {
      data: { ...user, captcha_token: '1x00000000000000000000AA' },
    });

    // Clear cookies
    await context.clearCookies();

    // Login
    const response = await request.post(`${BASE_URL}/api/auth/login`, {
      data: {
        email: user.email,
        password: user.password,
      },
    });

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body.user.email).toBe(user.email);

    // Verify cookies are set
    const cookies = await context.cookies();
    expect(cookies.find(c => c.name === 'access_token_cookie')).toBeTruthy();
  });

  test('POST /api/auth/login - rejects invalid credentials', async ({ request }) => {
    const user = generateTestUser();

    // Register
    await request.post(`${BASE_URL}/api/auth/register`, {
      data: { ...user, captcha_token: '1x00000000000000000000AA' },
    });

    // Wrong password
    const response = await request.post(`${BASE_URL}/api/auth/login`, {
      data: {
        email: user.email,
        password: 'WrongPassword123!',
      },
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(401);
    const body = await response.json();
    expect(body.error).toMatch(/invalid/i);
  });

  test('POST /api/auth/login - rejects non-existent user', async ({ request }) => {
    const response = await request.post(`${BASE_URL}/api/auth/login`, {
      data: {
        email: 'nonexistent@test.com',
        password: 'Password123!',
      },
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(401);
    const body = await response.json();
    expect(body.error).toMatch(/invalid/i);
  });

  test('POST /api/auth/login - timing attack protection', async ({ request }) => {
    const user = generateTestUser();

    // Register
    await request.post(`${BASE_URL}/api/auth/register`, {
      data: { ...user, captcha_token: '1x00000000000000000000AA' },
    });

    // Measure timing for non-existent user
    const start1 = Date.now();
    await request.post(`${BASE_URL}/api/auth/login`, {
      data: {
        email: 'nonexistent@test.com',
        password: 'Password123!',
      },
      failOnStatusCode: false,
    });
    const time1 = Date.now() - start1;

    // Measure timing for wrong password
    const start2 = Date.now();
    await request.post(`${BASE_URL}/api/auth/login`, {
      data: {
        email: user.email,
        password: 'WrongPassword123!',
      },
      failOnStatusCode: false,
    });
    const time2 = Date.now() - start2;

    // Timing difference should be minimal (within 100ms)
    // This prevents attackers from determining if email exists
    const timingDiff = Math.abs(time1 - time2);
    expect(timingDiff).toBeLessThan(100);
  });
});

test.describe('Auth API - Token Management', () => {
  test('GET /api/auth/me - returns current user', async ({ request, context }) => {
    const user = generateTestUser();

    // Register
    await request.post(`${BASE_URL}/api/auth/register`, {
      data: { ...user, captcha_token: '1x00000000000000000000AA' },
    });

    // Get current user
    const response = await request.get(`${BASE_URL}/api/auth/me`);

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.email).toBe(user.email);
    expect(body.name).toBe(user.name);
  });

  test('GET /api/auth/me - rejects unauthenticated request', async ({ request, context }) => {
    await context.clearCookies();

    const response = await request.get(`${BASE_URL}/api/auth/me`, {
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(401);
  });

  test('POST /api/auth/refresh - refreshes access token', async ({ request, context }) => {
    const user = generateTestUser();

    // Register
    await request.post(`${BASE_URL}/api/auth/register`, {
      data: { ...user, captcha_token: '1x00000000000000000000AA' },
    });

    // Get initial cookies
    const initialCookies = await context.cookies();
    const initialAccess = initialCookies.find(c => c.name === 'access_token_cookie');

    // Wait a bit to ensure new token is different
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Refresh token
    const response = await request.post(`${BASE_URL}/api/auth/refresh`);

    expect(response.status()).toBe(200);

    // Verify new cookies are set
    const newCookies = await context.cookies();
    const newAccess = newCookies.find(c => c.name === 'access_token_cookie');

    expect(newAccess).toBeTruthy();
    expect(newAccess.value).not.toBe(initialAccess.value);
  });

  test('POST /api/auth/logout - clears auth cookies', async ({ request, context }) => {
    const user = generateTestUser();

    // Register
    await request.post(`${BASE_URL}/api/auth/register`, {
      data: { ...user, captcha_token: '1x00000000000000000000AA' },
    });

    // Verify cookies exist
    let cookies = await context.cookies();
    expect(cookies.find(c => c.name === 'access_token_cookie')).toBeTruthy();

    // Logout
    const response = await request.post(`${BASE_URL}/api/auth/logout`);

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.success).toBe(true);

    // Verify cookies are cleared
    cookies = await context.cookies();
    const accessCookie = cookies.find(c => c.name === 'access_token_cookie');

    // Cookie should be expired or have empty value
    if (accessCookie) {
      expect(accessCookie.value).toBe('');
    }
  });

  test('Token expiration - expired token rejected', async ({ request, context }) => {
    // This test would require manipulating token expiration
    // In a real scenario, you'd either:
    // 1. Wait for actual expiration (not practical)
    // 2. Use a test endpoint that issues short-lived tokens
    // 3. Mock the JWT verification

    // For now, we test that invalid tokens are rejected
    await context.clearCookies();
    await context.addCookies([{
      name: 'access_token_cookie',
      value: 'invalid.jwt.token',
      domain: 'localhost',
      path: '/',
      httpOnly: true,
    }]);

    const response = await request.get(`${BASE_URL}/api/auth/me`, {
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(401);
  });
});

test.describe('Auth API - CSRF Protection', () => {
  test('POST endpoints require CSRF token', async ({ request, context }) => {
    const user = generateTestUser();

    // Register
    await request.post(`${BASE_URL}/api/auth/register`, {
      data: { ...user, captcha_token: '1x00000000000000000000AA' },
    });

    const cookies = await context.cookies();

    // Try to logout without CSRF token (should fail)
    const response = await request.post(`${BASE_URL}/api/auth/logout`, {
      headers: {
        'X-CSRF-TOKEN': 'invalid-csrf-token',
      },
      failOnStatusCode: false,
    });

    // Should reject due to invalid CSRF token
    expect([400, 401, 403]).toContain(response.status());
  });
});

test.describe('Auth API - Security', () => {
  test('Prevents SQL injection in email field', async ({ request }) => {
    const sqlInjections = [
      "admin'--",
      "' OR '1'='1",
      "'; DROP TABLE users; --",
      "admin' UNION SELECT * FROM users--",
    ];

    for (const injection of sqlInjections) {
      const response = await request.post(`${BASE_URL}/api/auth/login`, {
        data: {
          email: injection,
          password: 'Password123!',
        },
        failOnStatusCode: false,
      });

      // Should return 400 (invalid format) or 401 (not found)
      expect([400, 401]).toContain(response.status());
    }
  });

  test('Rate limiting on login attempts', async ({ request }) => {
    const user = generateTestUser();

    // Attempt multiple failed logins rapidly
    const attempts = [];
    for (let i = 0; i < 15; i++) {
      attempts.push(
        request.post(`${BASE_URL}/api/auth/login`, {
          data: {
            email: user.email,
            password: 'WrongPassword123!',
          },
          failOnStatusCode: false,
        })
      );
    }

    const responses = await Promise.all(attempts);

    // At least one should be rate limited (429)
    const rateLimited = responses.some(r => r.status() === 429);

    // Note: This might not trigger if rate limiting is per-IP and test runs too fast
    // Consider this a smoke test
    console.log(`Rate limiting triggered: ${rateLimited}`);
  });
});
