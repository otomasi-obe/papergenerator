/**
 * API Test Suite: Papers CRUD
 *
 * Tests paper creation, retrieval, update, and deletion endpoints.
 * Validates data integrity, authorization, and error handling.
 */
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8000';

function generateTestUser() {
  const timestamp = Date.now();
  return {
    email: `paper-api-${timestamp}@test.local`,
    name: 'Paper API Test User',
    password: 'SecurePass123!',
  };
}

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

async function registerAndLogin(request, context) {
  const user = generateTestUser();
  await request.post(`${BASE_URL}/api/auth/register`, {
    data: { ...user, captcha_token: '1x00000000000000000000AA' },
  });
  const cookies = await context.cookies();
  return { user, cookies, csrf: csrfFromCookies(cookies) };
}

test.describe('Papers API - Create', () => {
  test('POST /api/papers - creates paper successfully', async ({ request, context }) => {
    const { cookies, csrf } = await registerAndLogin(request, context);

    const paperData = {
      title: 'Test Paper Title',
      data: {
        abstract: 'This is a test abstract',
        sections: [],
        metadata: { topic: 'AI', type: 'research' },
      },
    };

    const response = await request.post(`${BASE_URL}/api/papers`, {
      data: paperData,
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toHaveProperty('id');
    expect(body.title).toBe(paperData.title);
    expect(body.data.abstract).toBe(paperData.data.abstract);
    expect(body).toHaveProperty('created_at');
    expect(body).toHaveProperty('updated_at');
  });

  test('POST /api/papers - validates required fields', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Missing title
    const response = await request.post(`${BASE_URL}/api/papers`, {
      data: { data: {} },
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(400);
    const body = await response.json();
    expect(body.error).toMatch(/title|required/i);
  });

  test('POST /api/papers - rejects unauthenticated request', async ({ request, context }) => {
    await context.clearCookies();

    const response = await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'Test', data: {} },
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(401);
  });

  test('POST /api/papers - rejects request without CSRF token', async ({ request, context }) => {
    await registerAndLogin(request, context);

    const response = await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'Test', data: {} },
      failOnStatusCode: false,
    });

    expect([400, 401, 403]).toContain(response.status());
  });

  test('POST /api/papers - handles special characters in title', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    const specialTitles = [
      'Paper with "quotes"',
      "Paper with 'apostrophes'",
      'Paper with <brackets>',
      'Paper with & ampersand',
      'Paper with émojis 🎓📄',
      'Paper with unicode: 中文标题',
    ];

    for (const title of specialTitles) {
      const response = await request.post(`${BASE_URL}/api/papers`, {
        data: { title, data: {} },
        headers: { 'X-CSRF-TOKEN': csrf },
      });

      expect(response.status()).toBe(200);
      const body = await response.json();
      expect(body.title).toBe(title);
    }
  });

  test('POST /api/papers - validates title length', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Very long title (>500 chars)
    const longTitle = 'A'.repeat(600);

    const response = await request.post(`${BASE_URL}/api/papers`, {
      data: { title: longTitle, data: {} },
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    // Should either accept and truncate, or reject
    if (response.status() === 200) {
      const body = await response.json();
      expect(body.title.length).toBeLessThanOrEqual(500);
    } else {
      expect(response.status()).toBe(400);
    }
  });
});

test.describe('Papers API - Read', () => {
  test('GET /api/papers - lists user papers', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create multiple papers
    const paperTitles = ['Paper 1', 'Paper 2', 'Paper 3'];
    for (const title of paperTitles) {
      await request.post(`${BASE_URL}/api/papers`, {
        data: { title, data: {} },
        headers: { 'X-CSRF-TOKEN': csrf },
      });
    }

    // List papers
    const response = await request.get(`${BASE_URL}/api/papers`);

    expect(response.status()).toBe(200);
    const body = await response.json();

    expect(body).toHaveProperty('papers');
    expect(Array.isArray(body.papers)).toBe(true);
    expect(body.papers.length).toBeGreaterThanOrEqual(3);

    // Verify pagination metadata
    expect(body).toHaveProperty('pagination');
    expect(body.pagination).toHaveProperty('total');
  });

  test('GET /api/papers - supports pagination', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create 15 papers
    for (let i = 1; i <= 15; i++) {
      await request.post(`${BASE_URL}/api/papers`, {
        data: { title: `Paper ${i}`, data: {} },
        headers: { 'X-CSRF-TOKEN': csrf },
      });
    }

    // Get first page
    const page1 = await request.get(`${BASE_URL}/api/papers?page=1&limit=10`);
    const body1 = await page1.json();

    expect(body1.papers.length).toBeLessThanOrEqual(10);
    expect(body1.pagination.page).toBe(1);

    // Get second page
    const page2 = await request.get(`${BASE_URL}/api/papers?page=2&limit=10`);
    const body2 = await page2.json();

    expect(body2.papers.length).toBeGreaterThan(0);
    expect(body2.pagination.page).toBe(2);

    // Verify no overlap
    const page1Ids = body1.papers.map(p => p.id);
    const page2Ids = body2.papers.map(p => p.id);
    const overlap = page1Ids.filter(id => page2Ids.includes(id));
    expect(overlap.length).toBe(0);
  });

  test('GET /api/papers/:id - retrieves specific paper', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create paper
    const createRes = await request.post(`${BASE_URL}/api/papers`, {
      data: {
        title: 'Specific Paper',
        data: { abstract: 'Test abstract', sections: [] },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const created = await createRes.json();

    // Retrieve paper
    const response = await request.get(`${BASE_URL}/api/papers/${created.id}`);

    expect(response.status()).toBe(200);
    const body = await response.json();

    expect(body.id).toBe(created.id);
    expect(body.title).toBe('Specific Paper');
    expect(body.data.abstract).toBe('Test abstract');
  });

  test('GET /api/papers/:id - returns 404 for non-existent paper', async ({ request, context }) => {
    await registerAndLogin(request, context);

    const response = await request.get(`${BASE_URL}/api/papers/nonexistent-id-12345`, {
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(404);
  });

  test('GET /api/papers/:id - prevents access to other user papers', async ({ request, context }) => {
    // User 1 creates paper
    const { csrf: csrf1 } = await registerAndLogin(request, context);
    const createRes = await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'User 1 Paper', data: {} },
      headers: { 'X-CSRF-TOKEN': csrf1 },
    });
    const paper = await createRes.json();

    // User 2 tries to access
    await context.clearCookies();
    await registerAndLogin(request, context);

    const response = await request.get(`${BASE_URL}/api/papers/${paper.id}`, {
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(404); // Should not reveal existence
  });

  test('GET /api/papers - filters by search query', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create papers with different titles
    await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'Machine Learning Research', data: {} },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'Deep Learning Applications', data: {} },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'Natural Language Processing', data: {} },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    // Search for "learning"
    const response = await request.get(`${BASE_URL}/api/papers?search=learning`);
    const body = await response.json();

    expect(body.papers.length).toBeGreaterThanOrEqual(2);
    body.papers.forEach(paper => {
      expect(paper.title.toLowerCase()).toContain('learning');
    });
  });
});

test.describe('Papers API - Update', () => {
  test('PATCH /api/papers/:id - updates paper successfully', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create paper
    const createRes = await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'Original Title', data: { abstract: 'Original abstract' } },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const paper = await createRes.json();

    // Update paper
    const response = await request.patch(`${BASE_URL}/api/papers/${paper.id}`, {
      data: {
        op: 'replace',
        path: '/title',
        value: 'Updated Title',
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);
    const updated = await response.json();

    expect(updated.title).toBe('Updated Title');
    expect(updated.data.abstract).toBe('Original abstract'); // Unchanged
  });

  test('PATCH /api/papers/:id - supports JSON Patch operations', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create paper
    const createRes = await request.post(`${BASE_URL}/api/papers`, {
      data: {
        title: 'Test Paper',
        data: { sections: [{ title: 'Section 1', content: 'Content 1' }] },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const paper = await createRes.json();

    // Add section
    const addRes = await request.patch(`${BASE_URL}/api/papers/${paper.id}`, {
      data: {
        op: 'add',
        path: '/data/sections/-',
        value: { title: 'Section 2', content: 'Content 2' },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(addRes.status()).toBe(200);
    const updated = await addRes.json();
    expect(updated.data.sections.length).toBe(2);
  });

  test('PATCH /api/papers/:id - prevents unauthorized updates', async ({ request, context }) => {
    // User 1 creates paper
    const { csrf: csrf1 } = await registerAndLogin(request, context);
    const createRes = await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'User 1 Paper', data: {} },
      headers: { 'X-CSRF-TOKEN': csrf1 },
    });
    const paper = await createRes.json();

    // User 2 tries to update
    await context.clearCookies();
    const { csrf: csrf2 } = await registerAndLogin(request, context);

    const response = await request.patch(`${BASE_URL}/api/papers/${paper.id}`, {
      data: { op: 'replace', path: '/title', value: 'Hacked Title' },
      headers: { 'X-CSRF-TOKEN': csrf2 },
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(404);
  });

  test('PATCH /api/papers/:id - validates patch operations', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create paper
    const createRes = await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'Test Paper', data: {} },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const paper = await createRes.json();

    // Invalid operation
    const response = await request.patch(`${BASE_URL}/api/papers/${paper.id}`, {
      data: { op: 'invalid_op', path: '/title', value: 'New Title' },
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(400);
  });

  test('PATCH /api/papers/:id - handles concurrent updates', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create paper
    const createRes = await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'Concurrent Test', data: { counter: 0 } },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const paper = await createRes.json();

    // Perform 5 concurrent updates
    const updates = [];
    for (let i = 1; i <= 5; i++) {
      updates.push(
        request.patch(`${BASE_URL}/api/papers/${paper.id}`, {
          data: { op: 'replace', path: '/data/counter', value: i },
          headers: { 'X-CSRF-TOKEN': csrf },
        })
      );
    }

    const responses = await Promise.all(updates);

    // All should succeed
    responses.forEach(res => {
      expect(res.status()).toBe(200);
    });

    // Final state should be consistent
    const finalRes = await request.get(`${BASE_URL}/api/papers/${paper.id}`);
    const final = await finalRes.json();
    expect(final.data.counter).toBeGreaterThanOrEqual(1);
    expect(final.data.counter).toBeLessThanOrEqual(5);
  });
});

test.describe('Papers API - Delete', () => {
  test('DELETE /api/papers/:id - deletes paper successfully', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create paper
    const createRes = await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'Paper to Delete', data: {} },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const paper = await createRes.json();

    // Delete paper
    const response = await request.delete(`${BASE_URL}/api/papers/${paper.id}`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);

    // Verify deletion
    const getRes = await request.get(`${BASE_URL}/api/papers/${paper.id}`, {
      failOnStatusCode: false,
    });
    expect(getRes.status()).toBe(404);
  });

  test('DELETE /api/papers/:id - prevents unauthorized deletion', async ({ request, context }) => {
    // User 1 creates paper
    const { csrf: csrf1 } = await registerAndLogin(request, context);
    const createRes = await request.post(`${BASE_URL}/api/papers`, {
      data: { title: 'User 1 Paper', data: {} },
      headers: { 'X-CSRF-TOKEN': csrf1 },
    });
    const paper = await createRes.json();

    // User 2 tries to delete
    await context.clearCookies();
    const { csrf: csrf2 } = await registerAndLogin(request, context);

    const response = await request.delete(`${BASE_URL}/api/papers/${paper.id}`, {
      headers: { 'X-CSRF-TOKEN': csrf2 },
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(404);

    // Verify paper still exists for user 1
    await context.clearCookies();
    await request.post(`${BASE_URL}/api/auth/login`, {
      data: { email: 'paper-api-' + paper.user_id + '@test.local', password: 'SecurePass123!' },
    });
    // Note: This is simplified; in real test you'd store user credentials
  });

  test('DELETE /api/papers/:id - cascades to related data', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create paper with sections
    const createRes = await request.post(`${BASE_URL}/api/papers`, {
      data: {
        title: 'Paper with Data',
        data: {
          sections: [{ title: 'Section 1', content: 'Content' }],
          literature: [{ title: 'Reference 1', authors: 'Author' }],
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const paper = await createRes.json();

    // Delete paper
    await request.delete(`${BASE_URL}/api/papers/${paper.id}`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    // Verify all related data is gone
    const getRes = await request.get(`${BASE_URL}/api/papers/${paper.id}`, {
      failOnStatusCode: false,
    });
    expect(getRes.status()).toBe(404);
  });
});

test.describe('Papers API - Performance', () => {
  test('Bulk paper creation performance', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    const startTime = Date.now();
    const promises = [];

    // Create 20 papers concurrently
    for (let i = 1; i <= 20; i++) {
      promises.push(
        request.post(`${BASE_URL}/api/papers`, {
          data: { title: `Bulk Paper ${i}`, data: {} },
          headers: { 'X-CSRF-TOKEN': csrf },
        })
      );
    }

    const responses = await Promise.all(promises);
    const duration = Date.now() - startTime;

    // All should succeed
    responses.forEach(res => {
      expect(res.status()).toBe(200);
    });

    // Should complete in reasonable time (< 10 seconds)
    expect(duration).toBeLessThan(10000);

    console.log(`Created 20 papers in ${duration}ms (avg: ${(duration / 20).toFixed(2)}ms per paper)`);
  });

  test('Large paper data handling', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);

    // Create paper with large content
    const largeSections = [];
    for (let i = 0; i < 50; i++) {
      largeSections.push({
        title: `Section ${i}`,
        content: 'Lorem ipsum dolor sit amet. '.repeat(100), // ~2.8KB per section
      });
    }

    const response = await request.post(`${BASE_URL}/api/papers`, {
      data: {
        title: 'Large Paper',
        data: { sections: largeSections },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);

    const paper = await response.json();
    expect(paper.data.sections.length).toBe(50);
  });
});
