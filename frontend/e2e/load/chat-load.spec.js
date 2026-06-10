/**
 * Chat System Load Test
 *
 * Tests concurrent chat operations:
 * - Multiple users creating conversations simultaneously
 * - Concurrent message sends (semaphore stress)
 * - Memory operations under load
 * - Active job polling under concurrent access
 *
 * Uses API-level requests (not UI) for higher throughput.
 */

import { test, expect } from '@playwright/test';
import { PerformanceMonitor, sleep } from './helpers.js';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8000';
const monitor = new PerformanceMonitor();

// Helper: register user, return { user, cookies, csrf }
async function registerUser(api, index) {
  const ts = Date.now();
  const email = `chatload-${index}-${ts}@test.local`;
  const password = 'SecurePass123!';
  const res = await api.post(`${BASE_URL}/api/auth/register`, {
    data: { email, name: `Load User ${index}`, password, captcha_token: '1x00000000000000000000AA' }
  });
  if (res.status() !== 201) throw new Error(`Register failed: ${res.status()}`);
  return { email, password };
}

async function loginUser(api, email, password) {
  const res = await api.post(`${BASE_URL}/api/auth/login`, {
    data: { email, password }
  });
  return res;
}

async function getCsrfFromApiResponse(api) {
  const res = await api.get(`${BASE_URL}/api/auth/csrf-token`).catch(() => null);
  if (res && res.ok) {
    const data = await res.json();
    return data.csrf_token || '';
  }
  return '';
}

test.describe('Chat System Load Tests', () => {
  test.describe.configure({ mode: 'serial' });

  test('TC-LOAD-01: Create conversations concurrently', async ({ request }) => {
    const USERS = 5;
    const CONVERSATIONS_PER_USER = 3;
    const users = [];

    // Register users and create papers
    for (let i = 0; i < USERS; i++) {
      const start = Date.now();
      try {
        const { email } = await registerUser(request, i);
        await loginUser(request, email, 'SecurePass123!');
        // Get CSRF via cookie sometimes doesn't work in isolated request context
        const csrf = await getCsrfFromApiResponse(request);

        const paperRes = await request.post(`${BASE_URL}/api/papers`, {
          headers: { 'X-CSRF-TOKEN': csrf },
          data: { title: `Load Paper ${i}` }
        });
        const paper = await paperRes.json();
        users.push({ email, paperId: paper.id, csrf });
      } catch (e) {
        monitor.recordRequest('setup_user', start, Date.now(), 500, e.message);
      }
    }

    expect(users.length).toBeGreaterThanOrEqual(3);

    // Create conversations concurrently
    const promises = [];
    for (const user of users) {
      for (let c = 0; c < CONVERSATIONS_PER_USER; c++) {
        const start = Date.now();
        promises.push(
          request.post(`${BASE_URL}/api/papers/${user.paperId}/conversations`, {
            headers: { 'X-CSRF-TOKEN': user.csrf },
            data: { title: `Load Chat ${c}` }
          }).then(res => {
            monitor.recordRequest('create_conversation', start, Date.now(), res.status());
            return res.ok ? res.json() : null;
          }).catch(e => {
            monitor.recordRequest('create_conversation', start, Date.now(), 500, e.message);
            return null;
          })
        );
      }
    }

    const results = await Promise.allSettled(promises);
    const successCount = results.filter(r => r.status === 'fulfilled' && r.value !== null).length;
    expect(successCount).toBeGreaterThanOrEqual(5);
  });

  test('TC-LOAD-02: Send messages under concurrency (semaphore stress)', async ({ request }) => {
    const USERS = 4;
    const MESSAGES_PER_USER = 2;
    const users = [];

    for (let i = 0; i < USERS; i++) {
      try {
        const { email } = await registerUser(request, 100 + i);
        await loginUser(request, email, 'SecurePass123!');
        const csrf = await getCsrfFromApiResponse(request);

        const paperRes = await request.post(`${BASE_URL}/api/papers`, {
          headers: { 'X-CSRF-TOKEN': csrf },
          data: { title: `Semaphore Paper ${i}` }
        });
        const paper = await paperRes.json();

        const convRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/conversations`, {
          headers: { 'X-CSRF-TOKEN': csrf },
          data: { title: 'Semaphore Chat' }
        });
        const conv = await convRes.json();
        users.push({ csrf, convId: conv.id });
      } catch (e) {
        // skip failed setup
      }
    }

    expect(users.length).toBeGreaterThanOrEqual(2);

    // Send messages concurrently — this tests the semaphore under load
    const promises = [];
    for (const user of users) {
      for (let m = 0; m < MESSAGES_PER_USER; m++) {
        const start = Date.now();
        promises.push(
          request.post(`${BASE_URL}/api/chat/conversations/${user.convId}/messages`, {
            headers: {
              'X-CSRF-TOKEN': user.csrf,
              'Content-Type': 'application/json',
            },
            data: { content: `Load test message ${m}` }
          }).then(res => {
            // The message was accepted (streaming or error response)
            monitor.recordRequest('send_message', start, Date.now(), res.status());
            return res.status();
          }).catch(e => {
            monitor.recordRequest('send_message', start, Date.now(), 500, e.message);
            return 500;
          })
        );
        await sleep(100); // small stagger
      }
    }

    const statuses = await Promise.all(promises);
    // At least some messages should be accepted (200 or error event)
    const accepted = statuses.filter(s => s === 200).length;
    expect(accepted).toBeGreaterThanOrEqual(1);
  });

  test('TC-LOAD-03: Memory operations under concurrent access', async ({ request }) => {
    const USERS = 3;
    const users = [];

    for (let i = 0; i < USERS; i++) {
      try {
        const { email } = await registerUser(request, 200 + i);
        await loginUser(request, email, 'SecurePass123!');
        const csrf = await getCsrfFromApiResponse(request);

        const paperRes = await request.post(`${BASE_URL}/api/papers`, {
          headers: { 'X-CSRF-TOKEN': csrf },
          data: { title: `Memory Load Paper ${i}` }
        });
        const paper = await paperRes.json();
        users.push({ csrf, paperId: paper.id });
      } catch (e) { /* skip */ }
    }

    // List memory concurrently for all users
    const listPromises = users.map(user => {
      const start = Date.now();
      return request.get(`${BASE_URL}/api/papers/${user.paperId}/memory`, {
        headers: { 'X-CSRF-TOKEN': user.csrf }
      }).then(res => {
        monitor.recordRequest('list_memory', start, Date.now(), res.status());
        return res.ok;
      }).catch(e => {
        monitor.recordRequest('list_memory', start, Date.now(), 500, e.message);
        return false;
      });
    });

    const results = await Promise.all(listPromises);
    const successCount = results.filter(Boolean).length;
    expect(successCount).toBeGreaterThanOrEqual(1);
  });

  test('TC-LOAD-04: Active job polling under concurrent access', async ({ request }) => {
    const USERS = 5;
    const users = [];

    for (let i = 0; i < USERS; i++) {
      try {
        const { email } = await registerUser(request, 300 + i);
        await loginUser(request, email, 'SecurePass123!');
        const csrf = await getCsrfFromApiResponse(request);

        const paperRes = await request.post(`${BASE_URL}/api/papers`, {
          headers: { 'X-CSRF-TOKEN': csrf },
          data: { title: `ActiveJob Paper ${i}` }
        });
        const paper = await paperRes.json();
        users.push({ csrf, paperId: paper.id });
      } catch (e) { /* skip */ }
    }

    // Poll active-job concurrently (simulates multiple browser tabs)
    const POLLS_PER_USER = 3;
    const pollPromises = [];

    for (const user of users) {
      for (let p = 0; p < POLLS_PER_USER; p++) {
        const start = Date.now();
        pollPromises.push(
          request.get(`${BASE_URL}/api/papers/${user.paperId}/active-job`, {
            headers: { 'X-CSRF-TOKEN': user.csrf }
          }).then(res => {
            monitor.recordRequest('active_job_poll', start, Date.now(), res.status());
            return res.ok;
          }).catch(e => {
            monitor.recordRequest('active_job_poll', start, Date.now(), 500, e.message);
            return false;
          })
        );
        await sleep(50); // stagger
      }
    }

    const results = await Promise.all(pollPromises);
    const successCount = results.filter(Boolean).length;
    expect(successCount).toBeGreaterThan(0);
  });
});
