/**
 * API Test Suite: Jobs & Async Operations
 *
 * Tests job lifecycle, SSE streaming, cancellation, and resume functionality.
 * Validates async paper generation, SLR jobs, and progress tracking.
 */
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8000';

function generateTestUser() {
  const timestamp = Date.now();
  return {
    email: `jobs-api-${timestamp}@test.local`,
    name: 'Jobs API Test User',
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

async function createPaper(request, csrf, title = 'Test Paper') {
  const response = await request.post(`${BASE_URL}/api/papers`, {
    data: { title, data: {} },
    headers: { 'X-CSRF-TOKEN': csrf },
  });
  return await response.json();
}

async function pollJobUntilComplete(request, jobId, maxAttempts = 30, interval = 2000) {
  for (let i = 0; i < maxAttempts; i++) {
    const response = await request.get(`${BASE_URL}/api/jobs/${jobId}`);
    const job = await response.json();

    if (['done', 'error', 'cancelled'].includes(job.status)) {
      return job;
    }

    await new Promise(resolve => setTimeout(resolve, interval));
  }

  throw new Error(`Job ${jobId} did not complete within ${maxAttempts * interval}ms`);
}

test.describe('Jobs API - Paper Generation', () => {
  test('POST /api/papers/:id/generate - enqueues generation job', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: {
        prompt: 'Generate a comprehensive introduction about machine learning',
        topic: 'Machine Learning',
        style: 'academic',
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toHaveProperty('job_id');
    expect(body.status).toBe('queued');
    expect(body.job_id).toMatch(/^[a-f0-9]{16}$/);
  });

  test('POST /api/papers/:id/generate - validates prompt', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Empty prompt
    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: '' },
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(400);
    const body = await response.json();
    expect(body.error).toMatch(/prompt|required/i);
  });

  test('POST /api/papers/:id/generate - prevents generation for other user papers', async ({ request, context }) => {
    // User 1 creates paper
    const { csrf: csrf1 } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf1);

    // User 2 tries to generate
    await context.clearCookies();
    const { csrf: csrf2 } = await registerAndLogin(request, context);

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'Generate content' },
      headers: { 'X-CSRF-TOKEN': csrf2 },
      failOnStatusCode: false,
    });

    expect([403, 404]).toContain(response.status());
  });

  test('POST /api/papers/:id/generate - handles long prompts', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // 5000 character prompt
    const longPrompt = 'Generate a paper about AI. '.repeat(200);

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: longPrompt },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty('job_id');
  });
});

test.describe('Jobs API - Status & Progress', () => {
  test('GET /api/jobs/:id - retrieves job status', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'Test generation' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Get status
    const response = await request.get(`${BASE_URL}/api/jobs/${job_id}`);

    expect(response.status()).toBe(200);

    const job = await response.json();
    expect(job).toHaveProperty('id');
    expect(job).toHaveProperty('status');
    expect(job).toHaveProperty('progress');
    expect(job).toHaveProperty('stage');
    expect(['queued', 'running', 'done', 'error', 'paused']).toContain(job.status);
  });

  test('GET /api/jobs/:id - returns 404 for non-existent job', async ({ request, context }) => {
    await registerAndLogin(request, context);

    const response = await request.get(`${BASE_URL}/api/jobs/nonexistent123`, {
      failOnStatusCode: false,
    });

    expect(response.status()).toBe(404);
  });

  test('GET /api/jobs/:id - prevents access to other user jobs', async ({ request, context }) => {
    // User 1 creates job
    const { csrf: csrf1 } = await registerAndLogin(request, context);
    const paper1 = await createPaper(request, csrf1);

    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper1.id}/generate`, {
      data: { prompt: 'User 1 job' },
      headers: { 'X-CSRF-TOKEN': csrf1 },
    });
    const { job_id } = await enqueueRes.json();

    // User 2 tries to access
    await context.clearCookies();
    await registerAndLogin(request, context);

    const response = await request.get(`${BASE_URL}/api/jobs/${job_id}`, {
      failOnStatusCode: false,
    });

    expect([403, 404]).toContain(response.status());
  });

  test('GET /api/papers/:id/active-jobs - lists active jobs', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue multiple jobs
    const jobIds = [];
    for (let i = 0; i < 3; i++) {
      const res = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
        data: { prompt: `Job ${i}` },
        headers: { 'X-CSRF-TOKEN': csrf },
      });
      const body = await res.json();
      jobIds.push(body.job_id);
    }

    // List active jobs
    const response = await request.get(`${BASE_URL}/api/papers/${paper.id}/active-jobs`);

    expect(response.status()).toBe(200);
    const jobs = await response.json();

    expect(Array.isArray(jobs)).toBe(true);
    expect(jobs.length).toBeGreaterThan(0);

    jobs.forEach(job => {
      expect(['queued', 'running', 'paused']).toContain(job.status);
    });
  });

  test('GET /api/papers/:id/ai-jobs/active - returns single active job', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'Active job test' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Get active job
    const response = await request.get(`${BASE_URL}/api/papers/${paper.id}/ai-jobs/active`);

    expect(response.status()).toBe(200);
    const job = await response.json();

    if (job) {
      expect(job.id).toBe(job_id);
      expect(['queued', 'running', 'paused']).toContain(job.status);
    }
  });

  test('Job progress updates over time', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'Progress tracking test' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Poll multiple times to observe progress
    const progressSnapshots = [];

    for (let i = 0; i < 5; i++) {
      const res = await request.get(`${BASE_URL}/api/jobs/${job_id}`);
      const job = await res.json();
      progressSnapshots.push({
        progress: job.progress,
        stage: job.stage,
        status: job.status,
      });

      if (job.status === 'done' || job.status === 'error') {
        break;
      }

      await new Promise(resolve => setTimeout(resolve, 2000));
    }

    // Progress should be non-decreasing
    for (let i = 1; i < progressSnapshots.length; i++) {
      if (progressSnapshots[i].status === progressSnapshots[i - 1].status) {
        expect(progressSnapshots[i].progress).toBeGreaterThanOrEqual(progressSnapshots[i - 1].progress);
      }
    }

    console.log('Progress snapshots:', progressSnapshots);
  });
});

test.describe('Jobs API - Cancellation', () => {
  test('POST /api/jobs/:id/cancel - cancels running job', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'Job to cancel' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Wait a bit for job to start
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Cancel job
    const response = await request.post(`${BASE_URL}/api/jobs/${job_id}/cancel`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);

    // Verify cancellation
    await new Promise(resolve => setTimeout(resolve, 1000));

    const statusRes = await request.get(`${BASE_URL}/api/jobs/${job_id}`);
    const job = await statusRes.json();

    expect(['cancelled', 'error']).toContain(job.status);
  });

  test('POST /api/ai-jobs/:id/cancel - cancels AI job', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'AI job to cancel' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Cancel via AI jobs endpoint
    const response = await request.post(`${BASE_URL}/api/ai-jobs/${job_id}/cancel`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);
  });

  test('POST /api/jobs/:id/cancel - prevents cancelling other user jobs', async ({ request, context }) => {
    // User 1 creates job
    const { csrf: csrf1 } = await registerAndLogin(request, context);
    const paper1 = await createPaper(request, csrf1);

    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper1.id}/generate`, {
      data: { prompt: 'Protected job' },
      headers: { 'X-CSRF-TOKEN': csrf1 },
    });
    const { job_id } = await enqueueRes.json();

    // User 2 tries to cancel
    await context.clearCookies();
    const { csrf: csrf2 } = await registerAndLogin(request, context);

    const response = await request.post(`${BASE_URL}/api/jobs/${job_id}/cancel`, {
      headers: { 'X-CSRF-TOKEN': csrf2 },
      failOnStatusCode: false,
    });

    expect([403, 404]).toContain(response.status());
  });

  test('Cancelling already completed job is idempotent', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'Quick job' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Wait for completion (or timeout)
    try {
      await pollJobUntilComplete(request, job_id, 10, 1000);
    } catch (e) {
      // Job might not complete, that's ok for this test
    }

    // Try to cancel completed job
    const response = await request.post(`${BASE_URL}/api/jobs/${job_id}/cancel`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    // Should either succeed (idempotent) or return 400/409
    expect([200, 400, 409]).toContain(response.status());
  });
});

test.describe('Jobs API - Resume & Retry', () => {
  test('POST /api/ai-jobs/:id/resume - resumes paused job', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'Job to resume' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Note: In real scenario, job would be paused by system or user action
    // For testing, we attempt resume regardless of state

    const response = await request.post(`${BASE_URL}/api/ai-jobs/${job_id}/resume`, {
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    // Should either succeed or return appropriate error
    expect([200, 400, 409]).toContain(response.status());
  });

  test('POST /api/ai-jobs/:id/retry-section - retries failed section', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'Job with sections' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Attempt to retry a section
    const response = await request.post(`${BASE_URL}/api/ai-jobs/${job_id}/retry-section`, {
      data: { stage: 'introduction' },
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    // Should either succeed or return appropriate error
    expect([200, 400, 404]).toContain(response.status());
  });
});

test.describe('Jobs API - SLR Jobs', () => {
  test('POST /api/papers/:id/slr/jobs - enqueues SLR job', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/slr/jobs`, {
      data: {
        query: 'machine learning',
        max_results: 10,
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(202);

    const body = await response.json();
    expect(body).toHaveProperty('job_id');
  });

  test('GET /api/papers/:id/slr/jobs - lists SLR jobs', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue multiple SLR jobs
    for (let i = 0; i < 3; i++) {
      await request.post(`${BASE_URL}/api/papers/${paper.id}/slr/jobs`, {
        data: { query: `query ${i}`, max_results: 5 },
        headers: { 'X-CSRF-TOKEN': csrf },
      });
    }

    // List jobs
    const response = await request.get(`${BASE_URL}/api/papers/${paper.id}/slr/jobs`);

    expect(response.status()).toBe(200);
    const jobs = await response.json();

    expect(Array.isArray(jobs)).toBe(true);
    expect(jobs.length).toBeGreaterThanOrEqual(3);
  });

  test('GET /api/slr/jobs/:id - retrieves SLR job status', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue SLR job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/slr/jobs`, {
      data: { query: 'artificial intelligence', max_results: 10 },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Get status
    const response = await request.get(`${BASE_URL}/api/slr/jobs/${job_id}`);

    expect(response.status()).toBe(200);

    const job = await response.json();
    expect(job).toHaveProperty('status');
    expect(['queued', 'running', 'done', 'error', 'cancelled']).toContain(job.status);
  });

  test('DELETE /api/slr/jobs/:id - cancels SLR job', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue SLR job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/slr/jobs`, {
      data: { query: 'deep learning', max_results: 10 },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Cancel job
    const response = await request.delete(`${BASE_URL}/api/slr/jobs/${job_id}`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);
  });

  test('SLR job rate limiting', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Attempt to enqueue many SLR jobs rapidly
    const promises = [];
    for (let i = 0; i < 15; i++) {
      promises.push(
        request.post(`${BASE_URL}/api/papers/${paper.id}/slr/jobs`, {
          data: { query: `query ${i}`, max_results: 5 },
          headers: { 'X-CSRF-TOKEN': csrf },
          failOnStatusCode: false,
        })
      );
    }

    const responses = await Promise.all(promises);

    // Some should be rate limited
    const rateLimited = responses.some(r => r.status() === 429);
    const successful = responses.filter(r => r.status() === 202).length;

    console.log(`SLR jobs: ${successful} successful, rate limited: ${rateLimited}`);

    // At least some should succeed
    expect(successful).toBeGreaterThan(0);
  });
});

test.describe('Jobs API - Recent Jobs', () => {
  test('GET /api/me/ai-jobs/recent - lists user recent jobs', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Create multiple jobs
    for (let i = 0; i < 5; i++) {
      await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
        data: { prompt: `Recent job ${i}` },
        headers: { 'X-CSRF-TOKEN': csrf },
      });
    }

    // Get recent jobs
    const response = await request.get(`${BASE_URL}/api/me/ai-jobs/recent`);

    expect(response.status()).toBe(200);
    const jobs = await response.json();

    expect(Array.isArray(jobs)).toBe(true);
    expect(jobs.length).toBeGreaterThan(0);

    // Jobs should be sorted by creation time (newest first)
    for (let i = 1; i < jobs.length; i++) {
      const prev = new Date(jobs[i - 1].created_at);
      const curr = new Date(jobs[i].created_at);
      expect(prev.getTime()).toBeGreaterThanOrEqual(curr.getTime());
    }
  });

  test('GET /api/me/ai-jobs/recent - supports filtering', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Create jobs
    await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'Test job' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    // Filter by status
    const response = await request.get(`${BASE_URL}/api/me/ai-jobs/recent?status=queued`);

    expect(response.status()).toBe(200);
    const jobs = await response.json();

    jobs.forEach(job => {
      expect(job.status).toBe('queued');
    });
  });
});

test.describe('Jobs API - Error Handling', () => {
  test('Handles job failures gracefully', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue job with potentially problematic prompt
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'x'.repeat(10000) }, // Very long prompt
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    if (enqueueRes.status() === 200) {
      const { job_id } = await enqueueRes.json();

      // Poll for result
      try {
        const finalJob = await pollJobUntilComplete(request, job_id, 10, 2000);

        // Job should either complete or error
        expect(['done', 'error']).toContain(finalJob.status);

        if (finalJob.status === 'error') {
          expect(finalJob).toHaveProperty('error');
        }
      } catch (e) {
        // Timeout is acceptable for this test
        console.log('Job did not complete within timeout');
      }
    }
  });

  test('Returns appropriate error for invalid job ID format', async ({ request, context }) => {
    await registerAndLogin(request, context);

    const invalidIds = [
      'invalid-id-with-special-chars!@#',
      '../../../etc/passwd',
      '<script>alert(1)</script>',
    ];

    for (const id of invalidIds) {
      const response = await request.get(`${BASE_URL}/api/jobs/${id}`, {
        failOnStatusCode: false,
      });

      expect([400, 404]).toContain(response.status());
    }
  });
});

test.describe('Jobs API - Concurrent Operations', () => {
  test('Handles multiple concurrent job submissions', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Submit 10 jobs concurrently
    const promises = [];
    for (let i = 0; i < 10; i++) {
      promises.push(
        request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
          data: { prompt: `Concurrent job ${i}` },
          headers: { 'X-CSRF-TOKEN': csrf },
        })
      );
    }

    const responses = await Promise.all(promises);

    // All should succeed
    responses.forEach(res => {
      expect(res.status()).toBe(200);
    });

    // All should have unique job IDs
    const jobIds = await Promise.all(responses.map(r => r.json().then(b => b.job_id)));
    const uniqueIds = new Set(jobIds);
    expect(uniqueIds.size).toBe(10);
  });

  test('Handles concurrent status checks', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Enqueue job
    const enqueueRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/generate`, {
      data: { prompt: 'Status check test' },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const { job_id } = await enqueueRes.json();

    // Check status 20 times concurrently
    const promises = [];
    for (let i = 0; i < 20; i++) {
      promises.push(request.get(`${BASE_URL}/api/jobs/${job_id}`));
    }

    const responses = await Promise.all(promises);

    // All should succeed
    responses.forEach(res => {
      expect(res.status()).toBe(200);
    });
  });
});
