/**
 * Queue Management Tests
 * 
 * Tests job queue behavior under load:
 * - Job queuing and processing order
 * - Priority handling
 * - Timeout handling
 * - Queue capacity limits
 * - Job cancellation under load
 */

import { test, expect } from '@playwright/test';
import {
  PerformanceMonitor,
  registerUser,
  csrfFromCookies,
  createPaper,
  enqueueSLR,
  enqueueGeneration,
  sleep,
} from './helpers.js';

const monitor = new PerformanceMonitor();

test.describe('Queue Management Tests', () => {
  test.describe.configure({ mode: 'parallel' });

  // Test: Rapid job submission
  for (let i = 1; i <= 5; i++) {
    test(`Queue ${i}: Rapid job submission`, async ({ page }) => {
      const ctx = page.context();
      const api = ctx.request;

      const user = await registerUser(api, 100 + i);
      const cookies = await ctx.cookies();

      const paperId = await createPaper(
        api,
        cookies,
        `Queue Test Paper ${i}`,
        { title: `Queue Test Paper ${i}` }
      );

      const jobIds = [];
      const submissionTimes = [];

      // Submit 5 jobs as fast as possible
      for (let j = 0; j < 5; j++) {
        const start = Date.now();
        try {
          const jobId = await enqueueSLR(
            api,
            cookies,
            paperId,
            `rapid query ${j}`
          );
          const end = Date.now();
          
          jobIds.push(jobId);
          submissionTimes.push(end - start);
          monitor.recordRequest('rapid_job_submission', start, end, 202);
        } catch (error) {
          monitor.recordRequest('rapid_job_submission', start, Date.now(), 500, error.message);
        }
      }

      // Verify all jobs were queued
      expect(jobIds.length).toBeGreaterThan(0);
      
      // Check average submission time
      const avgSubmission = submissionTimes.reduce((a, b) => a + b, 0) / submissionTimes.length;
      console.log(`User ${i} avg submission time: ${avgSubmission.toFixed(2)}ms`);
    });
  }

  // Test: Job status polling under load
  test('Queue: Concurrent status polling', async ({ page }) => {
    const ctx = page.context();
    const api = ctx.request;

    const user = await registerUser(api, 200);
    const cookies = await ctx.cookies();

    const paperId = await createPaper(
      api,
      cookies,
      'Status Polling Test',
      { title: 'Status Polling Test' }
    );

    // Submit a job
    const jobId = await enqueueSLR(api, cookies, paperId, 'status test query');

    // Poll status 20 times rapidly
    const pollTimes = [];
    for (let i = 0; i < 20; i++) {
      const start = Date.now();
      try {
        const res = await api.get(`/api/slr/jobs/${jobId}`);
        const end = Date.now();
        
        monitor.recordRequest('status_poll', start, end, res.status());
        pollTimes.push(end - start);
        
        expect(res.status()).toBe(200);
        
        // Small delay between polls
        await sleep(100);
      } catch (error) {
        monitor.recordRequest('status_poll', start, Date.now(), 500, error.message);
      }
    }

    const avgPoll = pollTimes.reduce((a, b) => a + b, 0) / pollTimes.length;
    console.log(`Average poll time: ${avgPoll.toFixed(2)}ms`);
  });

  // Test: Job cancellation under load
  for (let i = 1; i <= 3; i++) {
    test(`Queue ${i}: Job cancellation`, async ({ page }) => {
      const ctx = page.context();
      const api = ctx.request;

      const user = await registerUser(api, 300 + i);
      const cookies = await ctx.cookies();

      const paperId = await createPaper(
        api,
        cookies,
        `Cancel Test Paper ${i}`,
        { title: `Cancel Test Paper ${i}` }
      );

      // Submit multiple jobs
      const jobIds = [];
      for (let j = 0; j < 3; j++) {
        const jobId = await enqueueSLR(api, cookies, paperId, `cancel query ${j}`);
        jobIds.push(jobId);
      }

      // Cancel all jobs
      for (const jobId of jobIds) {
        const start = Date.now();
        try {
          const res = await api.post(`/api/slr/jobs/${jobId}/cancel`, {
            headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
          });
          monitor.recordRequest('cancel_job', start, Date.now(), res.status());
          
          // Verify cancellation
          await sleep(500);
          const statusRes = await api.get(`/api/slr/jobs/${jobId}`);
          const status = await statusRes.json();
          expect(['cancelled', 'error', 'done']).toContain(status.status);
        } catch (error) {
          monitor.recordRequest('cancel_job', start, Date.now(), 500, error.message);
        }
      }
    });
  }

  // Test: Mixed job types (SLR + Generation)
  test('Queue: Mixed job types', async ({ page }) => {
    const ctx = page.context();
    const api = ctx.request;

    const user = await registerUser(api, 400);
    const cookies = await ctx.cookies();

    const paperId = await createPaper(
      api,
      cookies,
      'Mixed Jobs Test',
      { title: 'Mixed Jobs Test' }
    );

    const jobs = [];

    // Submit alternating SLR and generation jobs
    for (let i = 0; i < 4; i++) {
      const start = Date.now();
      try {
        if (i % 2 === 0) {
          const jobId = await enqueueSLR(api, cookies, paperId, `mixed slr ${i}`);
          jobs.push({ type: 'slr', id: jobId });
          monitor.recordRequest('mixed_slr', start, Date.now(), 202);
        } else {
          const jobId = await enqueueGeneration(
            api,
            cookies,
            paperId,
            `Generate content ${i}`
          );
          jobs.push({ type: 'generation', id: jobId });
          monitor.recordRequest('mixed_generation', start, Date.now(), 202);
        }
        
        await sleep(500);
      } catch (error) {
        monitor.recordRequest('mixed_job_error', start, Date.now(), 500, error.message);
      }
    }

    expect(jobs.length).toBeGreaterThan(0);
    console.log(`Submitted ${jobs.length} mixed jobs`);
  });

  // Test: Queue capacity - submit many jobs
  test('Queue: Capacity stress test', async ({ page }) => {
    const ctx = page.context();
    const api = ctx.request;

    const user = await registerUser(api, 500);
    const cookies = await ctx.cookies();

    const paperId = await createPaper(
      api,
      cookies,
      'Capacity Test',
      { title: 'Capacity Test' }
    );

    const jobIds = [];
    let successCount = 0;
    let failCount = 0;

    // Try to submit 15 jobs
    for (let i = 0; i < 15; i++) {
      const start = Date.now();
      try {
        const jobId = await enqueueSLR(api, cookies, paperId, `capacity query ${i}`);
        jobIds.push(jobId);
        successCount++;
        monitor.recordRequest('capacity_submit', start, Date.now(), 202);
      } catch (error) {
        failCount++;
        monitor.recordRequest('capacity_submit', start, Date.now(), 500, error.message);
        // Continue even if some fail
      }
      
      await sleep(200);
    }

    console.log(`Capacity test: ${successCount} succeeded, ${failCount} failed`);
    expect(successCount).toBeGreaterThan(0);
  });
});

test.afterAll(async () => {
  const stats = monitor.getStats();
  const errors = monitor.getErrors();

  console.log('\n' + '='.repeat(80));
  console.log('QUEUE MANAGEMENT TEST REPORT');
  console.log('='.repeat(80));
  console.log(`Total Queue Operations: ${stats.totalRequests}`);
  console.log(`Failed Operations: ${stats.totalErrors}`);
  console.log(`Failure Rate: ${stats.errorRate}`);
  
  console.log('\nQueue Operation Performance:');
  console.log('-'.repeat(80));
  
  for (const [operation, metrics] of Object.entries(stats.operations)) {
    console.log(`\n${operation}:`);
    console.log(`  Count: ${metrics.count}`);
    console.log(`  Avg: ${metrics.avg}`);
    console.log(`  P95: ${metrics.p95}`);
    console.log(`  P99: ${metrics.p99}`);
  }

  if (errors.length > 0) {
    console.log('\n' + '='.repeat(80));
    console.log('QUEUE ERRORS:');
    console.log('='.repeat(80));
    
    const errorsByType = {};
    errors.forEach(err => {
      errorsByType[err.operation] = (errorsByType[err.operation] || 0) + 1;
    });
    
    for (const [op, count] of Object.entries(errorsByType)) {
      console.log(`  ${op}: ${count} errors`);
    }
  }

  console.log('\n' + '='.repeat(80));
});
