/**
 * Load Test: 10 Concurrent Users
 * 
 * Simulates a classroom scenario with 10 students using the system simultaneously.
 * 
 * User Distribution:
 * - Users 1-3: Creating new papers
 * - Users 4-6: Running SLR jobs
 * - Users 7-8: Generating papers
 * - Users 9-10: Editing existing papers
 * 
 * Monitors:
 * - Response times
 * - Error rates
 * - Race conditions
 * - Queue management
 */

import { test, expect } from '@playwright/test';
import {
  PerformanceMonitor,
  registerUser,
  csrfFromCookies,
  createPaper,
  updatePaper,
  enqueueSLR,
  enqueueGeneration,
  pollJobStatus,
  sleep,
} from './helpers.js';

const monitor = new PerformanceMonitor();

test.describe('Concurrent Users Load Test', () => {
  test.describe.configure({ mode: 'parallel' });

  // Users 1-3: Creating new papers
  for (let i = 1; i <= 3; i++) {
    test(`User ${i}: Create multiple papers`, async ({ page }) => {
      const ctx = page.context();
      const api = ctx.request;
      const userIndex = i;

      // Register user
      let start = Date.now();
      const user = await registerUser(api, userIndex);
      monitor.recordRequest('register', start, Date.now(), 201);

      const cookies = await ctx.cookies();

      // Create 5 papers sequentially
      for (let paperNum = 1; paperNum <= 5; paperNum++) {
        start = Date.now();
        try {
          const paperId = await createPaper(
            api,
            cookies,
            `User ${userIndex} Paper ${paperNum}`,
            {
              title: `User ${userIndex} Paper ${paperNum}`,
              abstract: `This is paper ${paperNum} created by user ${userIndex} during load testing`,
              sections: [],
            }
          );
          monitor.recordRequest('create_paper', start, Date.now(), 200);
          
          // Verify paper was created
          start = Date.now();
          const getRes = await api.get(`/api/papers/${paperId}`);
          monitor.recordRequest('get_paper', start, Date.now(), getRes.status());
          expect(getRes.status()).toBe(200);

          // Small delay between papers
          await sleep(500);
        } catch (error) {
          monitor.recordRequest('create_paper', start, Date.now(), 500, error.message);
          throw error;
        }
      }

      // List all papers
      start = Date.now();
      const listRes = await api.get('/api/papers');
      monitor.recordRequest('list_papers', start, Date.now(), listRes.status());
      expect(listRes.status()).toBe(200);
      const listBody = await listRes.json();
      expect(listBody.papers.length).toBeGreaterThanOrEqual(5);
    });
  }

  // Users 4-6: Running SLR jobs
  for (let i = 4; i <= 6; i++) {
    test(`User ${i}: Run SLR jobs`, async ({ page }) => {
      const ctx = page.context();
      const api = ctx.request;
      const userIndex = i;

      // Register user
      let start = Date.now();
      const user = await registerUser(api, userIndex);
      monitor.recordRequest('register', start, Date.now(), 201);

      const cookies = await ctx.cookies();

      // Create a paper for SLR
      start = Date.now();
      const paperId = await createPaper(
        api,
        cookies,
        `User ${userIndex} SLR Paper`,
        { title: `User ${userIndex} SLR Paper` }
      );
      monitor.recordRequest('create_paper', start, Date.now(), 200);

      // Enqueue 3 SLR jobs
      const jobIds = [];
      const queries = [
        'machine learning',
        'artificial intelligence',
        'deep learning',
      ];

      for (let jobNum = 0; jobNum < 3; jobNum++) {
        start = Date.now();
        try {
          const jobId = await enqueueSLR(api, cookies, paperId, queries[jobNum]);
          monitor.recordRequest('enqueue_slr', start, Date.now(), 202);
          jobIds.push(jobId);
          
          // Small delay between job submissions
          await sleep(1000);
        } catch (error) {
          monitor.recordRequest('enqueue_slr', start, Date.now(), 500, error.message);
          // Continue with other jobs even if one fails
        }
      }

      // Poll first job status (don't wait for completion, just check it's queued/running)
      if (jobIds.length > 0) {
        start = Date.now();
        const statusRes = await api.get(`/api/slr/jobs/${jobIds[0]}`);
        monitor.recordRequest('poll_slr_status', start, Date.now(), statusRes.status());
        expect(statusRes.status()).toBe(200);
        const statusBody = await statusRes.json();
        expect(['queued', 'running', 'done', 'error']).toContain(statusBody.status);
      }
    });
  }

  // Users 7-8: Generating papers
  for (let i = 7; i <= 8; i++) {
    test(`User ${i}: Generate papers`, async ({ page }) => {
      const ctx = page.context();
      const api = ctx.request;
      const userIndex = i;

      // Register user
      let start = Date.now();
      const user = await registerUser(api, userIndex);
      monitor.recordRequest('register', start, Date.now(), 201);

      const cookies = await ctx.cookies();

      // Create a paper
      start = Date.now();
      const paperId = await createPaper(
        api,
        cookies,
        `User ${userIndex} Generation Paper`,
        {
          title: `User ${userIndex} Generation Paper`,
          abstract: 'Paper for generation testing',
          sections: [],
        }
      );
      monitor.recordRequest('create_paper', start, Date.now(), 200);

      // Enqueue generation job
      start = Date.now();
      try {
        const jobId = await enqueueGeneration(
          api,
          cookies,
          paperId,
          'Generate a comprehensive introduction section about machine learning'
        );
        monitor.recordRequest('enqueue_generation', start, Date.now(), 202);

        // Poll job status (don't wait for full completion, just verify it's processing)
        await sleep(2000);
        start = Date.now();
        const statusRes = await api.get(`/api/jobs/${jobId}`);
        monitor.recordRequest('poll_generation_status', start, Date.now(), statusRes.status());
        expect(statusRes.status()).toBe(200);
        const statusBody = await statusRes.json();
        expect(['queued', 'running', 'done', 'error', 'paused']).toContain(statusBody.status);
      } catch (error) {
        monitor.recordRequest('enqueue_generation', start, Date.now(), 500, error.message);
        throw error;
      }
    });
  }

  // Users 9-10: Editing existing papers
  for (let i = 9; i <= 10; i++) {
    test(`User ${i}: Edit papers repeatedly`, async ({ page }) => {
      const ctx = page.context();
      const api = ctx.request;
      const userIndex = i;

      // Register user
      let start = Date.now();
      const user = await registerUser(api, userIndex);
      monitor.recordRequest('register', start, Date.now(), 201);

      const cookies = await ctx.cookies();

      // Create a paper
      start = Date.now();
      const paperId = await createPaper(
        api,
        cookies,
        `User ${userIndex} Edit Paper`,
        {
          title: `User ${userIndex} Edit Paper`,
          abstract: 'Initial abstract',
          sections: [],
        }
      );
      monitor.recordRequest('create_paper', start, Date.now(), 200);

      // Perform 10 rapid edits
      for (let editNum = 1; editNum <= 10; editNum++) {
        start = Date.now();
        try {
          await updatePaper(api, cookies, paperId, {
            op: 'replace',
            path: '/abstract',
            value: `Updated abstract version ${editNum} by user ${userIndex}`,
          });
          monitor.recordRequest('update_paper', start, Date.now(), 200);
          
          // Very short delay to simulate rapid editing
          await sleep(200);
        } catch (error) {
          monitor.recordRequest('update_paper', start, Date.now(), 500, error.message);
          throw error;
        }
      }

      // Verify final state
      start = Date.now();
      const getRes = await api.get(`/api/papers/${paperId}`);
      monitor.recordRequest('get_paper', start, Date.now(), getRes.status());
      expect(getRes.status()).toBe(200);
      const paper = await getRes.json();
      expect(paper.abstract).toContain('Updated abstract version 10');
    });
  }
});

// Teardown: Print performance report
test.afterAll(async () => {
  const stats = monitor.getStats();
  const errors = monitor.getErrors();

  console.log('\n' + '='.repeat(80));
  console.log('LOAD TEST PERFORMANCE REPORT');
  console.log('='.repeat(80));
  console.log(`Total Requests: ${stats.totalRequests}`);
  console.log(`Total Errors: ${stats.totalErrors}`);
  console.log(`Error Rate: ${stats.errorRate}`);
  console.log('\nOperation Statistics:');
  console.log('-'.repeat(80));
  
  for (const [operation, metrics] of Object.entries(stats.operations)) {
    console.log(`\n${operation}:`);
    console.log(`  Count: ${metrics.count}`);
    console.log(`  Avg: ${metrics.avg}`);
    console.log(`  Min: ${metrics.min}`);
    console.log(`  Max: ${metrics.max}`);
    console.log(`  P50: ${metrics.p50}`);
    console.log(`  P95: ${metrics.p95}`);
    console.log(`  P99: ${metrics.p99}`);
  }

  if (errors.length > 0) {
    console.log('\n' + '='.repeat(80));
    console.log('ERRORS:');
    console.log('='.repeat(80));
    errors.forEach((err, idx) => {
      console.log(`\n${idx + 1}. ${err.operation} (Status: ${err.status})`);
      if (err.error) {
        console.log(`   ${err.error}`);
      }
    });
  }

  console.log('\n' + '='.repeat(80));
});
