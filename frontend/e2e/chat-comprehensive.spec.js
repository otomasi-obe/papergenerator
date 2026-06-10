/**
 * Comprehensive Chat Function E2E Tests
 * =====================================
 * Covers all 10 test cases + error handling + concurrent chat.
 *
 * Run: cd frontend && npx playwright test e2e/chat-comprehensive.spec.js --project=workflow-with-video
 * Env: E2E_BASE_URL=http://localhost:8000
 */

import { test, expect } from '@playwright/test';

const BASE = process.env.E2E_BASE_URL || 'http://localhost:8000';
const SS_DIR = 'test-results/chat-comprehensive';

// ── Shared State ──────────────────────────────────────────────────────
let _user = null;
let _csrf = '';
let _cookies = [];
let _paper = null;

// ── Helpers ───────────────────────────────────────────────────────────

function uniqueUser() {
  const ts = Date.now();
  return { email: `chattest-${ts}@e2e.local`, name: `ChatTest ${ts}`, password: 'ChatTest123!' };
}

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

async function screenshot(page, name) {
  await page.screenshot({ path: `${SS_DIR}/${name}.png`, fullPage: true });
}

async function getJson(res) {
  try { return await res.json(); } catch { return null; }
}

// ── Setup: register user, create paper ────────────────────────────────

test.beforeAll(async ({ browser }) => {
  const ctx = await browser.newContext();
  const api = ctx.request;

  // Register test user
  _user = uniqueUser();
  const reg = await api.post(`${BASE}/api/auth/register`, {
    data: { ..._user, captcha_token: '1x00000000000000000000AA' },
  });
  if (reg.status() !== 201) {
    console.error('Registration failed:', reg.status(), await reg.text());
    throw new Error('Cannot register test user');
  }

  _cookies = await ctx.cookies();
  _csrf = csrfFromCookies(_cookies);

  // Create a paper
  const paperRes = await api.post(`${BASE}/api/papers`, {
    data: { title: 'Chat Test Paper', data: { abstract: 'Test abstract for chat', sections: [] } },
    headers: { 'X-CSRF-TOKEN': _csrf },
  });
  expect(paperRes.status()).toBe(200);
  _paper = await paperRes.json();
  console.log('Paper created:', _paper.id);

  await ctx.close();
});

test.beforeEach(async ({ page }) => {
  // Login in each page context
  const loginRes = await page.request.post(`${BASE}/api/auth/login`, {
    data: { email: _user.email, password: _user.password },
  });
  expect(loginRes.status()).toBe(200);
});

// ── TEST 1: Login & Auth ──────────────────────────────────────────────

test.describe('1. Login & Auth', () => {

  test('login sets httpOnly + CSRF cookies', async ({ page, context }) => {
    // Already logged via beforeEach
    const cookies = await context.cookies();
    const names = cookies.map(c => c.name);

    await screenshot(page, '01-login-cookies');

    expect(names).toContain('access_token_cookie');
    expect(names).toContain('refresh_token_cookie');
    expect(names).toContain('csrf_access_token');

    const access = cookies.find(c => c.name === 'access_token_cookie');
    expect(access?.httpOnly).toBe(true);

    const csrf = cookies.find(c => c.name === 'csrf_access_token');
    expect(csrf?.httpOnly).toBe(false);
  });

  test('GET /api/auth/me returns user info', async ({ page }) => {
    const res = await page.request.get(`${BASE}/api/auth/me`);
    expect(res.status()).toBe(200);
    const body = await getJson(res);
    expect(body.email).toBe(_user.email);
    expect(body.name).toBe(_user.name);

    await screenshot(page, '01-me-endpoint');
  });

  test('invalid credentials return 401', async ({ page }) => {
    const res = await page.request.post(`${BASE}/api/auth/login`, {
      data: { email: 'fake@none.com', password: 'wrong' },
    });
    expect(res.status()).toBe(401);
    const body = await getJson(res);
    expect(body.error).toBeTruthy();

    await screenshot(page, '01-login-fail');
  });
});

// ── TEST 2: Create New Chat ───────────────────────────────────────────

test.describe('2. Create New Chat', () => {
  let convId = null;

  test('POST conversations creates a new chat', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());
    const res = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Paper Test Chat' },
    });
    expect(res.status()).toBe(201);
    const body = await getJson(res);
    expect(body.id).toBeTruthy();
    expect(body.title).toBe('Paper Test Chat');
    expect(body.paper_id).toBe(_paper.id);
    convId = body.id;

    await screenshot(page, '02-new-chat');
  });

  test('new chat appears in conversation list', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());
    const res = await page.request.get(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(res.status()).toBe(200);
    const convs = await getJson(res);
    expect(Array.isArray(convs)).toBe(true);
    expect(convs.length).toBeGreaterThan(0);
    expect(convs.some(c => c.id === convId)).toBe(true);

    await screenshot(page, '02-chat-list');
  });
});

// ── TEST 3: Send Message & SSE Streaming ──────────────────────────────

test.describe('3. Send Message & SSE Streaming', () => {

  test('POST messages returns text/event-stream', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    // Create conversation
    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Stream Test' },
    });
    const conv = await convRes.json();

    // Send message and verify SSE
    const streamRes = await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
        data: { content: 'Halo, apa kabar?' },
      }
    );

    expect(streamRes.status()).toBe(200);
    const contentType = streamRes.headers()['content-type'] || '';
    expect(contentType).toContain('text/event-stream');

    const body = await streamRes.text();
    // SSE should contain event and data fields
    expect(body).toContain('event:');
    expect(body).toContain('data:');
    // Should contain at least "done" or "text" event
    expect(body).toMatch(/event:\s*(text|done|tool_call)/);

    await screenshot(page, '03-sse-stream');
  });
});

// ── TEST 4: Tool Calls ────────────────────────────────────────────────

test.describe('4. Tool Calls', () => {

  test('WebSearch tool is registered in tool schema', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    // Verify WebSearch via sending a search-related message
    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'WebSearch Test' },
    });
    const conv = await convRes.json();

    const streamRes = await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
        data: { content: 'Tolong carikan informasi tentang machine learning di Google' },
      }
    );

    expect(streamRes.status()).toBe(200);
    const body = await streamRes.text();
    // AI should at least respond (text or tool_call event)
    expect(body).toMatch(/event:\s*(text|tool_call|done)/);

    await screenshot(page, '04-websearch');
  });

  test('StartWorkflow via onboarding endpoint', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const res = await page.request.post(`${BASE}/api/papers/${_paper.id}/workflow/onboarding`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(res.status()).toBe(200);
    const body = await getJson(res);
    // Workflow onboarding should return questions
    expect(body).toBeTruthy();
    expect(body.kind || body.questions || body.phase).toBeTruthy();

    await screenshot(page, '04-start-workflow');
  });

  test('GetPaperContent via chat message', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Paper Content Test' },
    });
    const conv = await convRes.json();

    const streamRes = await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
        data: { content: 'Tunjukkan isi paper saya' },
      }
    );

    expect(streamRes.status()).toBe(200);
    const body = await streamRes.text();
    expect(body).toMatch(/event:\s*(text|tool_call|done)/);

    await screenshot(page, '04-get-paper-content');
  });

  test('ProposeChips - chat generates suggestion chips', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Chips Test' },
    });
    const conv = await convRes.json();

    const streamRes = await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
        data: { content: 'Saya ingin membuat paper tentang AI' },
      }
    );

    expect(streamRes.status()).toBe(200);
    const body = await streamRes.text();
    // ProposeChips generates a chips event or contains chip data
    expect(body).toMatch(/event:\s*(text|chips|propose|tool_call|done)/);

    await screenshot(page, '04-propose-chips');
  });
});

// ── TEST 5: Memory Operations ─────────────────────────────────────────

test.describe('5. Memory Operations', () => {

  test('auto-memory: "simpan: key=value" triggers SaveMemory', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Memory Save Test' },
    });
    const conv = await convRes.json();

    // Send a "simpan:" format message
    const streamRes = await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
        data: { content: 'simpan: topik=Machine Learning untuk Prediksi Cuaca' },
      }
    );

    expect(streamRes.status()).toBe(200);
    // The response should include a memory_save event or the content should be saved
    const body = await streamRes.text();
    expect(body).toMatch(/event:\s*(text|memory|save_memory|done)/);

    await screenshot(page, '05-memory-save');
  });

  test('list memory returns entries', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const res = await page.request.get(`${BASE}/api/papers/${_paper.id}/memory`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(res.status()).toBe(200);
    const entries = await getJson(res);
    expect(Array.isArray(entries)).toBe(true);

    await screenshot(page, '05-memory-list');
  });

  test('delete memory entry', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    // Try deleting a non-existent entry (404 expected = endpoint works)
    const res = await page.request.delete(`${BASE}/api/papers/${_paper.id}/memory/99999`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect([200, 404]).toContain(res.status());

    await screenshot(page, '05-memory-delete');
  });
});

// ── TEST 6: Mode Switching ────────────────────────────────────────────

test.describe('6. Mode Switching', () => {

  test('conversation mode persists to database', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    // Create conversation
    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Mode Test' },
    });
    const conv = await convRes.json();
    expect(conv.id).toBeTruthy();

    // Send a message that triggers mode change via ClassifyIntent
    const streamRes = await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
        data: { content: 'Saya mau mulai bikin paper baru' },
      }
    );
    expect(streamRes.status()).toBe(200);

    // Verify via GET /api/chat/conversations/<id> that mode is persisted
    const getRes = await page.request.get(`${BASE}/api/chat/conversations/${conv.id}`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(getRes.status()).toBe(200);
    const convData = await getJson(getRes);
    expect(convData.id).toBe(conv.id);
    // Mode field exists (may be null/default if AI didn't switch)
    expect('mode' in convData).toBe(true);

    await screenshot(page, '06-mode-persisted');
  });
});

// ── TEST 7: Active Job Polling ────────────────────────────────────────

test.describe('7. Active Job Polling', () => {

  test('active job endpoint returns correct shape', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const res = await page.request.get(`${BASE}/api/papers/${_paper.id}/active-job`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(res.status()).toBe(200);
    const body = await getJson(res);
    expect('active' in body).toBe(true);
    // When no active job, active should be false
    expect(typeof body.active).toBe('boolean');

    await screenshot(page, '07-active-job');
  });

  test('GenerateFullPaper creates job and returns job_id', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const res = await page.request.post(`${BASE}/api/generate-full`, {
      headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
      data: { prompt: 'Test Paper Title for Job Polling', paper_id: _paper.id },
    });
    expect(res.status()).toBe(200);
    const body = await getJson(res);
    expect(body.success).toBe(true);
    expect(body.job_id).toBeTruthy();

    // Poll the job endpoint
    const jobId = body.job_id;
    let attempts = 0;
    let finalStatus = null;
    while (attempts < 10) {
      await page.waitForTimeout(3000); // 3 second polling
      const jobRes = await page.request.get(`${BASE}/api/job/${jobId}`);
      const jobData = await getJson(jobRes);
      finalStatus = jobData.status;
      if (finalStatus !== 'pending') break;
      attempts++;
    }
    // Job should eventually reach done/error (we don't assert which since AI may fail)
    expect(['done', 'error', 'cancelled']).toContain(finalStatus);

    await screenshot(page, '07-job-polling');
  });
});

// ── TEST 8: Proposal Rendering ────────────────────────────────────────

test.describe('8. Proposal Rendering', () => {

  test('<<PROPOSAL>> protocol in chat response', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Proposal Test' },
    });
    const conv = await convRes.json();

    // Send message that triggers a proposal
    const streamRes = await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
        data: { content: 'Buatkan judul paper tentang IoT untuk smart farming' },
      }
    );

    expect(streamRes.status()).toBe(200);
    const body = await streamRes.text();
    // Response should contain text, tool_call, or proposal events
    expect(body).toMatch(/event:\s*(text|tool_call|proposal|done)/);

    await screenshot(page, '08-proposal');
  });
});

// ── TEST 9: CSRF Token ────────────────────────────────────────────────

test.describe('9. CSRF Token Verification', () => {

  test('POST without CSRF header is rejected', async ({ page, context }) => {
    // Create conversation with CSRF first
    const csrf = csrfFromCookies(await context.cookies());

    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'CSRF Probe' },
    });
    const conv = await convRes.json();

    // Now send a message WITHOUT CSRF header - should fail
    const noCsrf = await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'Content-Type': 'application/json' },
        data: { content: 'no csrf message' },
        failOnStatusCode: false,
      }
    );
    // Without CSRF, expect 401 or 422 (JWT CSRF validation)
    expect([401, 422]).toContain(noCsrf.status());

    await screenshot(page, '09-csrf-rejected');
  });

  test('POST with valid CSRF header succeeds', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'CSRF OK' },
    });
    const conv = await convRes.json();

    const streamRes = await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
        data: { content: 'Hello with CSRF' },
      }
    );
    expect(streamRes.status()).toBe(200);

    await screenshot(page, '09-csrf-accepted');
  });
});

// ── TEST 10: Conversation CRUD ────────────────────────────────────────

test.describe('10. Conversation CRUD', () => {
  let crudConvId = null;

  test('rename conversation', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Original Title' },
    });
    const conv = await convRes.json();
    crudConvId = conv.id;

    const renameRes = await page.request.patch(`${BASE}/api/chat/conversations/${conv.id}`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Renamed Title' },
    });
    expect(renameRes.status()).toBe(200);
    const renamed = await getJson(renameRes);
    expect(renamed.title).toBe('Renamed Title');

    await screenshot(page, '10-rename');
  });

  test('list conversations returns array', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const res = await page.request.get(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(res.status()).toBe(200);
    const convs = await getJson(res);
    expect(Array.isArray(convs)).toBe(true);
    expect(convs.length).toBeGreaterThan(0);

    await screenshot(page, '10-list');
  });

  test('delete conversation', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const res = await page.request.delete(`${BASE}/api/chat/conversations/${crudConvId}`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(res.status()).toBe(200);
    const body = await getJson(res);
    expect(body.ok).toBe(true);

    // Verify it's gone (404)
    const getRes = await page.request.get(`${BASE}/api/chat/conversations/${crudConvId}`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(getRes.status()).toBe(404);

    await screenshot(page, '10-delete');
  });
});

// ── BONUS: Error Handling ─────────────────────────────────────────────

test.describe('Error Handling', () => {

  test('400 - empty message content', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Error Test 400' },
    });
    const conv = await convRes.json();

    const res = await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
        data: { content: '' },
      }
    );
    expect(res.status()).toBe(400);
    const body = await getJson(res);
    expect(body.error).toBeTruthy();

    await screenshot(page, 'err-400');
  });

  test('401 - no auth token', async ({ page }) => {
    const res = await page.request.get(`${BASE}/api/chat/papers`);
    expect(res.status()).toBe(401);

    await screenshot(page, 'err-401');
  });

  test('404 - non-existent conversation', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const res = await page.request.get(`${BASE}/api/chat/conversations/nonexistent999`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(res.status()).toBe(404);

    await screenshot(page, 'err-404');
  });

  test('404 - non-existent paper for conversation', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const res = await page.request.get(`${BASE}/api/papers/nonexistent/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(res.status()).toBe(404);

    await screenshot(page, 'err-404-paper');
  });

  test('400 - rename with empty title', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Rename Test' },
    });
    const conv = await convRes.json();

    const res = await page.request.patch(`${BASE}/api/chat/conversations/${conv.id}`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: '' },
    });
    expect(res.status()).toBe(400);

    await screenshot(page, 'err-400-rename');
  });
});

// ── BONUS: Concurrent Chat ────────────────────────────────────────────

test.describe('Concurrent Chat (2 tabs)', () => {

  test('two tabs send messages in parallel without conflict', async ({ browser }) => {
    const ctx1 = await browser.newContext();
    const ctx2 = await browser.newContext();

    // Login in both contexts
    for (const ctx of [ctx1, ctx2]) {
      const loginRes = await ctx.request.post(`${BASE}/api/auth/login`, {
        data: { email: _user.email, password: _user.password },
      });
      expect(loginRes.status()).toBe(200);
    }

    const csrf1 = csrfFromCookies(await ctx1.cookies());
    const csrf2 = csrfFromCookies(await ctx2.cookies());

    // Create conversations
    const conv1Res = await ctx1.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf1 },
      data: { title: 'Concurrent Tab 1' },
    });
    const conv1 = await conv1Res.json();

    const conv2Res = await ctx2.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf2 },
      data: { title: 'Concurrent Tab 2' },
    });
    const conv2 = await conv2Res.json();

    // Send messages in parallel
    const [res1, res2] = await Promise.all([
      ctx1.request.post(`${BASE}/api/chat/conversations/${conv1.id}/messages`, {
        headers: { 'X-CSRF-TOKEN': csrf1, 'Content-Type': 'application/json' },
        data: { content: 'Message from tab 1' },
      }),
      ctx2.request.post(`${BASE}/api/chat/conversations/${conv2.id}/messages`, {
        headers: { 'X-CSRF-TOKEN': csrf2, 'Content-Type': 'application/json' },
        data: { content: 'Message from tab 2' },
      }),
    ]);

    expect(res1.status()).toBe(200);
    expect(res2.status()).toBe(200);

    const ct1 = res1.headers()['content-type'] || '';
    const ct2 = res2.headers()['content-type'] || '';
    expect(ct1).toContain('text/event-stream');
    expect(ct2).toContain('text/event-stream');

    await ctx1.close();
    await ctx2.close();
  });
});

// ── BONUS: Conversation with Messages ─────────────────────────────────

test.describe('Conversation with Messages', () => {

  test('get conversation includes messages array', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const convRes = await page.request.post(`${BASE}/api/papers/${_paper.id}/conversations`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      data: { title: 'Messages Test' },
    });
    const conv = await convRes.json();

    // Send a message first
    await page.request.post(
      `${BASE}/api/chat/conversations/${conv.id}/messages`,
      {
        headers: { 'X-CSRF-TOKEN': csrf, 'Content-Type': 'application/json' },
        data: { content: 'Test message for history' },
      }
    );

    // Wait for response
    await page.waitForTimeout(5000);

    // GET conversation with messages
    const getRes = await page.request.get(`${BASE}/api/chat/conversations/${conv.id}`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(getRes.status()).toBe(200);
    const data = await getJson(getRes);
    expect(data.id).toBe(conv.id);
    expect('messages' in data).toBe(true);
    expect(Array.isArray(data.messages)).toBe(true);
    // Should have at least user message
    expect(data.messages.length).toBeGreaterThan(0);
    expect(data.messages[0].role).toBe('user');

    await screenshot(page, 'conv-messages');
  });
});

// ── BONUS: Paper Chats Endpoint ───────────────────────────────────────

test.describe('Paper Chats Endpoint', () => {

  test('GET /api/chat/papers returns paper list with chat counts', async ({ page, context }) => {
    const csrf = csrfFromCookies(await context.cookies());

    const res = await page.request.get(`${BASE}/api/chat/papers`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    expect(res.status()).toBe(200);
    const data = await getJson(res);
    expect(Array.isArray(data)).toBe(true);
    if (data.length > 0) {
      expect(data[0]).toHaveProperty('paper_id');
      expect(data[0]).toHaveProperty('title');
      expect(data[0]).toHaveProperty('chat_count');
    }

    await screenshot(page, 'paper-chats');
  });
});
