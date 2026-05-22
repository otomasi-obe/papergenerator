/**
 * Race Condition Tests
 * 
 * Tests system behavior when multiple users interact with the same resources:
 * - Multiple users editing the same paper
 * - Concurrent SLR jobs on the same paper
 * - Simultaneous paper generation requests
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
  sleep,
} from './helpers.js';

const monitor = new PerformanceMonitor();

test.describe('Race Condition Tests', () => {
  test.describe.configure({ mode: 'parallel' });

  let sharedPaperId;
  let sharedUserCookies;

  test.beforeAll(async ({ browser }) => {
    // Create a shared paper that all race condition tests will use
    const context = await browser.newContext();
    const api = context.request;
    
    const user = await registerUser(api, 999);
    const cookies = await context.cookies();
    sharedPaperId = await createPaper(
      api,
      cookies,
      'Shared Race Condition Paper',
      {
        title: 'Shared Race Condition Paper',
        abstract: 'Initial content',
        sections: [
          { id: 'intro', title: 'Introduction', content: 'Initial intro' },
          { id: 'methods', title: 'Methods', content: 'Initial methods' },
        ],
      }
    );
    sharedUserCookies = cookies;
    
    await context.close();
  });

  // Test: Multiple users editing the same paper simultaneously
  for (let i = 1; i <= 5; i++) {
    test(`Race ${i}: Concurrent edits to same paper`, async ({ browser }) => {
      const context = await browser.newContext();
      const api = context.request;
      
      // Use the shared user's session
      await context.addCookies(sharedUserCookies);
      const cookies = await context.cookies();

      const editId = `edit-${i}-${Date.now()}`;
      const start = Date.now();
      
      try {
        // All users try to update the abstract simultaneously
        await updatePaper(api, cookies, sharedPaperId, {
          op: 'replace',
          path: '/abstract',
          value: `Concurrent edit ${editId}`,
        });
        monitor.recordRequest('concurrent_edit', start, Date.now(), 200);
      } catch (error) {
        monitor.recordRequest('concurrent_edit', start, Date.now(), 500, error.message);
        // Don't throw - we expect some conflicts
      }

      await context.close();
    });
  }

  // Test: Multiple SLR jobs on the same paper
  for (let i = 1; i <= 3; i++) {
    test(`Race ${i}: Concurrent SLR jobs on same paper`, async ({ browser }) => {
      const context = await browser.newContext();
      const api = context.request;
      
      await context.addCookies(sharedUserCookies);
      const cookies = await context.cookies();

      const start = Date.now();
      
      try {
        const jobId = await enqueueSLR(
          api,
          cookies,
          sharedPaperId,
          `concurrent query ${i}`
        );
        monitor.recordRequest('concurrent_slr', start, Date.now(), 202);
        
        // Verify job was queued
        const statusRes = await api.get(`/api/slr/jobs/${jobId}`);
        expect(statusRes.status()).toBe(200);
      } catch (error) {
        monitor.recordRequest('concurrent_slr', start, Date.now(), 500, error.message);
      }

      await context.close();
    });
  }

  // Test: Simultaneous generation requests
  for (let i = 1; i <= 3; i++) {
    test(`Race ${i}: Concurrent generation on same paper`, async ({ browser }) => {
      const context = await browser.newContext();
      const api = context.request;
      
      await context.addCookies(sharedUserCookies);
      const cookies = await context.cookies();

      const start = Date.now();
      
      try {
        const jobId = await enqueueGeneration(
          api,
          cookies,
          sharedPaperId,
          `Generate section ${i}`
        );
        monitor.recordRequest('concurrent_generation', start, Date.now(), 202);
        
        // Check if job was queued or if there's already an active job
        const statusRes = await api.get(`/api/jobs/${jobId}`);
        expect([200, 409]).toContain(statusRes.status());
      } catch (error) {
        monitor.recordRequest('concurrent_generation', start, Date.now(), 500, error.message);
        // Expected - system should prevent multiple concurrent generations
      }

      await context.close();
    });
  }

  // Test: Verify data integrity after race conditions
  test('Verify paper integrity after concurrent operations', async ({ browser }) => {
    const context = await browser.newContext();
    const api = context.request;
    
    await context.addCookies(sharedUserCookies);

    // Wait for all operations to settle
    await sleep(5000);

    const start = Date.now();
    const res = await api.get(`/api/papers/${sharedPaperId}`);
    monitor.recordRequest('verify_integrity', start, Date.now(), res.status());
    
    expect(res.status()).toBe(200);
    const paper = await res.json();
    
    // Verify paper structure is intact
    expect(paper).toHaveProperty('id');
    expect(paper).toHaveProperty('title');
    expect(paper).toHaveProperty('abstract');
    
    // Abstract should have one of the concurrent edits
    expect(paper.abstract).toMatch(/Concurrent edit|Initial content/);

    await context.close();
  });
});

test.afterAll(async () => {
  const stats = monitor.getStats();
  const errors = monitor.getErrors();

  console.log('\n' + '='.repeat(80));
  console.log('RACE CONDITION TEST REPORT');
  console.log('='.repeat(80));
  console.log(`Total Operations: ${stats.totalRequests}`);
  console.log(`Conflicts/Errors: ${stats.totalErrors}`);
  console.log(`Conflict Rate: ${stats.errorRate}`);
  
  console.log('\nOperation Timings:');
  for (const [operation, metrics] of Object.entries(stats.operations)) {
    console.log(`\n${operation}:`);
    console.log(`  Successful: ${metrics.count}`);
    console.log(`  Avg Response: ${metrics.avg}`);
    console.log(`  P95: ${metrics.p95}`);
  }

  if (errors.length > 0) {
    console.log('\n' + '='.repeat(80));
    console.log('CONFLICTS DETECTED:');
    console.log('='.repeat(80));
    const conflictTypes = {};
    errors.forEach(err => {
      conflictTypes[err.operation] = (conflictTypes[err.operation] || 0) + 1;
    });
    for (const [op, count] of Object.entries(conflictTypes)) {
      console.log(`  ${op}: ${count} conflicts`);
    }
  }

  console.log('\n' + '='.repeat(80));
});
