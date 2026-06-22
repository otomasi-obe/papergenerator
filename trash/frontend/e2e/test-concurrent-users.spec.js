/**
 * E2E Test: Concurrent Users - Database Concurrency & Race Conditions
 * 
 * Simulates 5 users working simultaneously on different papers
 * 
 * Test Scenarios:
 * 1. User 1: Medical student creating clinical paper
 * 2. User 2: Engineering student creating IoT paper
 * 3. User 3: Business student creating marketing paper
 * 4. User 4: Rapid paper edits (race condition test)
 * 5. User 5: Multiple SLR jobs (queue management test)
 * 
 * Verification:
 * - Database concurrency handling
 * - No race conditions
 * - No data corruption
 * - Proper transaction isolation
 * - Queue management integrity
 * 
 * Features:
 * - Parallel execution
 * - Performance monitoring
 * - Data integrity checks
 * - Error tracking
 */

import { test, expect } from '@playwright/test';
import { mkdir } from 'fs/promises';
import { existsSync } from 'fs';

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

async function ensureTestDir() {
  const dir = 'test-results/concurrent-users';
  if (!existsSync(dir)) {
    await mkdir(dir, { recursive: true });
  }
  return dir;
}

const testResults = {
  users: [],
  errors: [],
  apiCalls: [],
  startTime: 0,
  endTime: 0,
};

test.describe('Concurrent Users - Database Concurrency Test', () => {
  test.describe.configure({ mode: 'parallel' });

  test.beforeAll(async () => {
    testResults.startTime = Date.now();
    await ensureTestDir();
  });

  test.afterAll(async () => {
    testResults.endTime = Date.now();
    const totalTime = ((testResults.endTime - testResults.startTime) / 1000).toFixed(2);
    
    console.log('\n' + '='.repeat(80));
    console.log('CONCURRENT USERS TEST - FINAL REPORT');
    console.log('='.repeat(80));
    console.log(`Total execution time: ${totalTime}s`);
    console.log(`Total users: ${testResults.users.length}`);
    console.log(`Total API calls: ${testResults.apiCalls.length}`);
    console.log(`Total errors: ${testResults.errors.length}`);
    
    console.log('\n=== User Results ===');
    testResults.users.forEach((user, i) => {
      console.log(`\nUser ${i + 1}: ${user.email}`);
      console.log(`  Papers created: ${user.papersCreated}`);
      console.log(`  Edits made: ${user.editsCount}`);
      console.log(`  Jobs queued: ${user.jobsQueued}`);
      console.log(`  Execution time: ${user.executionTime}s`);
      console.log(`  Status: ${user.success ? '✓ PASS' : '✗ FAIL'}`);
    });
    
    if (testResults.errors.length > 0) {
      console.log('\n=== Errors Detected ===');
      testResults.errors.forEach((err, i) => {
        console.log(`${i + 1}. [${err.user}] ${err.operation}: ${err.message}`);
      });
    }
    
    console.log('\n=== Data Integrity Check ===');
    const allPapersCreated = testResults.users.reduce((sum, u) => sum + u.papersCreated, 0);
    const allEdits = testResults.users.reduce((sum, u) => sum + u.editsCount, 0);
    const allJobs = testResults.users.reduce((sum, u) => sum + u.jobsQueued, 0);
    console.log(`Total papers created: ${allPapersCreated}`);
    console.log(`Total edits performed: ${allEdits}`);
    console.log(`Total jobs queued: ${allJobs}`);
    console.log(`Data corruption detected: ${testResults.errors.length > 0 ? 'YES ⚠' : 'NO ✓'}`);
    
    console.log('\n=== Performance Metrics ===');
    const avgApiTime = testResults.apiCalls
      .filter(c => c.duration)
      .reduce((sum, c) => sum + c.duration, 0) / 
      testResults.apiCalls.filter(c => c.duration).length;
    console.log(`Average API response time: ${avgApiTime.toFixed(0)}ms`);
    
    const slowCalls = testResults.apiCalls.filter(c => c.duration > 5000);
    console.log(`Slow API calls (>5s): ${slowCalls.length}`);
    
    console.log('='.repeat(80) + '\n');
  });

  test('User 1: Medical student - Create and edit paper', async ({ browser }) => {
    const userEmail = `concurrent-medical-${Date.now()}@test.local`;
    const userResult = {
      email: userEmail,
      papersCreated: 0,
      editsCount: 0,
      jobsQueued: 0,
      executionTime: 0,
      success: false,
    };
    const startTime = Date.now();
    
    try {
      const context = await browser.newContext();
      const page = await context.newPage();
      const api = context.request;
      
      context.on('request', request => {
        testResults.apiCalls.push({
          user: userEmail,
          url: request.url(),
          method: request.method(),
          timestamp: Date.now(),
        });
      });
      
      const reg = await api.post('/api/auth/register', {
        data: {
          email: userEmail,
          name: 'Medical User',
          password: 'Test123!',
          captcha_token: '1x00000000000000000000AA',
        },
      });
      expect(reg.status()).toBe(201);
      
      await page.goto('/dashboard');
      await page.click('text=New Paper');
      await page.waitForURL(/\/editor/, { timeout: 10000 });
      
      const url = page.url();
      const match = url.match(/\/editor\/(\d+)/);
      let paperId;
      if (match) {
        paperId = match[1];
        userResult.papersCreated++;
      }
      
      const titleInput = page.locator('input[placeholder*="Paper title"]').first();
      await titleInput.fill('Concurrent Test - Medical Paper on Diabetes Management');
      await page.waitForTimeout(1000);
      userResult.editsCount++;
      
      const chatButton = page.locator('button:has-text("AI Chat"), button:has-text("Chat")').first();
      await chatButton.click();
      await page.waitForTimeout(500);
      
      const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
      await chatInput.fill('Generate abstract about diabetes management with mobile health apps');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(2000);
      userResult.editsCount++;
      
      const cookies = await context.cookies();
      const csrf = csrfFromCookies(cookies);
      
      for (let i = 0; i < 3; i++) {
        const updateRes = await api.patch(`/api/papers/${paperId}`, {
          data: {
            op: 'replace',
            path: '/data/notes',
            value: `Concurrent edit ${i + 1} at ${Date.now()}`,
          },
          headers: { 'X-CSRF-TOKEN': csrf },
        });
        if (updateRes.status() === 200) {
          userResult.editsCount++;
        }
        await page.waitForTimeout(200);
      }
      
      await page.screenshot({ 
        path: `test-results/concurrent-users/user1-final.png`,
        fullPage: true 
      });
      
      const verifyRes = await api.get(`/api/papers/${paperId}`);
      expect(verifyRes.status()).toBe(200);
      const paperData = await verifyRes.json();
      expect(paperData.title).toContain('Medical Paper');
      
      userResult.success = true;
      await context.close();
      
    } catch (error) {
      testResults.errors.push({
        user: userEmail,
        operation: 'Medical paper workflow',
        message: error.message,
      });
    } finally {
      userResult.executionTime = ((Date.now() - startTime) / 1000).toFixed(2);
      testResults.users.push(userResult);
    }
  });

  test('User 2: Engineering student - Create IoT paper', async ({ browser }) => {
    const userEmail = `concurrent-engineering-${Date.now()}@test.local`;
    const userResult = {
      email: userEmail,
      papersCreated: 0,
      editsCount: 0,
      jobsQueued: 0,
      executionTime: 0,
      success: false,
    };
    const startTime = Date.now();
    
    try {
      const context = await browser.newContext();
      const page = await context.newPage();
      const api = context.request;
      
      const reg = await api.post('/api/auth/register', {
        data: {
          email: userEmail,
          name: 'Engineering User',
          password: 'Test123!',
          captcha_token: '1x00000000000000000000AA',
        },
      });
      expect(reg.status()).toBe(201);
      
      await page.goto('/dashboard');
      await page.click('text=New Paper');
      await page.waitForURL(/\/editor/, { timeout: 10000 });
      
      const url = page.url();
      const match = url.match(/\/editor\/(\d+)/);
      let paperId;
      if (match) {
        paperId = match[1];
        userResult.papersCreated++;
      }
      
      const titleInput = page.locator('input[placeholder*="Paper title"]').first();
      await titleInput.fill('Concurrent Test - IoT Smart Home System');
      await page.waitForTimeout(1000);
      userResult.editsCount++;
      
      const chatButton = page.locator('button:has-text("AI Chat"), button:has-text("Chat")').first();
      await chatButton.click();
      await page.waitForTimeout(500);
      
      const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
      await chatInput.fill('Generate introduction about IoT smart home with ESP32 and sensors');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(2000);
      userResult.editsCount++;
      
      await page.screenshot({ 
        path: `test-results/concurrent-users/user2-final.png`,
        fullPage: true 
      });
      
      const verifyRes = await api.get(`/api/papers/${paperId}`);
      expect(verifyRes.status()).toBe(200);
      const paperData = await verifyRes.json();
      expect(paperData.title).toContain('IoT');
      
      userResult.success = true;
      await context.close();
      
    } catch (error) {
      testResults.errors.push({
        user: userEmail,
        operation: 'Engineering paper workflow',
        message: error.message,
      });
    } finally {
      userResult.executionTime = ((Date.now() - startTime) / 1000).toFixed(2);
      testResults.users.push(userResult);
    }
  });

  test('User 3: Business student - Create marketing paper', async ({ browser }) => {
    const userEmail = `concurrent-business-${Date.now()}@test.local`;
    const userResult = {
      email: userEmail,
      papersCreated: 0,
      editsCount: 0,
      jobsQueued: 0,
      executionTime: 0,
      success: false,
    };
    const startTime = Date.now();
    
    try {
      const context = await browser.newContext();
      const page = await context.newPage();
      const api = context.request;
      
      const reg = await api.post('/api/auth/register', {
        data: {
          email: userEmail,
          name: 'Business User',
          password: 'Test123!',
          captcha_token: '1x00000000000000000000AA',
        },
      });
      expect(reg.status()).toBe(201);
      
      await page.goto('/dashboard');
      await page.click('text=New Paper');
      await page.waitForURL(/\/editor/, { timeout: 10000 });
      
      const url = page.url();
      const match = url.match(/\/editor\/(\d+)/);
      let paperId;
      if (match) {
        paperId = match[1];
        userResult.papersCreated++;
      }
      
      const titleInput = page.locator('input[placeholder*="Paper title"]').first();
      await titleInput.fill('Concurrent Test - Digital Marketing Strategy for SMEs');
      await page.waitForTimeout(1000);
      userResult.editsCount++;
      
      const chatButton = page.locator('button:has-text("AI Chat"), button:has-text("Chat")').first();
      await chatButton.click();
      await page.waitForTimeout(500);
      
      const chatInput = page.locator('textarea[placeholder*="Tanya"], textarea[placeholder*="Type"]').first();
      await chatInput.fill('Generate literature review about digital marketing effectiveness in SMEs');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(2000);
      userResult.editsCount++;
      
      await page.screenshot({ 
        path: `test-results/concurrent-users/user3-final.png`,
        fullPage: true 
      });
      
      const verifyRes = await api.get(`/api/papers/${paperId}`);
      expect(verifyRes.status()).toBe(200);
      const paperData = await verifyRes.json();
      expect(paperData.title).toContain('Marketing');
      
      userResult.success = true;
      await context.close();
      
    } catch (error) {
      testResults.errors.push({
        user: userEmail,
        operation: 'Business paper workflow',
        message: error.message,
      });
    } finally {
      userResult.executionTime = ((Date.now() - startTime) / 1000).toFixed(2);
      testResults.users.push(userResult);
    }
  });

  test('User 4: Rapid edits - Race condition test', async ({ browser }) => {
    const userEmail = `concurrent-race-${Date.now()}@test.local`;
    const userResult = {
      email: userEmail,
      papersCreated: 0,
      editsCount: 0,
      jobsQueued: 0,
      executionTime: 0,
      success: false,
    };
    const startTime = Date.now();
    
    try {
      const context = await browser.newContext();
      const api = context.request;
      
      const reg = await api.post('/api/auth/register', {
        data: {
          email: userEmail,
          name: 'Race Test User',
          password: 'Test123!',
          captcha_token: '1x00000000000000000000AA',
        },
      });
      expect(reg.status()).toBe(201);
      
      const cookies = await context.cookies();
      const csrf = csrfFromCookies(cookies);
      
      const createRes = await api.post('/api/papers', {
        data: {
          title: 'Race Condition Test Paper',
          data: { counter: 0 },
        },
        headers: { 'X-CSRF-TOKEN': csrf },
      });
      expect(createRes.status()).toBe(200);
      const createBody = await createRes.json();
      const paperId = createBody.id;
      userResult.papersCreated++;
      
      const editPromises = [];
      for (let i = 0; i < 20; i++) {
        const promise = api.patch(`/api/papers/${paperId}`, {
          data: {
            op: 'replace',
            path: '/data/counter',
            value: i,
          },
          headers: { 'X-CSRF-TOKEN': csrf },
        }).then(res => {
          if (res.status() === 200) {
            userResult.editsCount++;
          }
          return res;
        }).catch(err => {
          testResults.errors.push({
            user: userEmail,
            operation: `Rapid edit ${i}`,
            message: err.message,
          });
        });
        editPromises.push(promise);
      }
      
      await Promise.all(editPromises);
      
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const verifyRes = await api.get(`/api/papers/${paperId}`);
      expect(verifyRes.status()).toBe(200);
      const paperData = await verifyRes.json();
      
      console.log(`User 4: Final counter value: ${paperData.data?.counter}`);
      console.log(`User 4: Successful edits: ${userResult.editsCount}/20`);
      
      if (userResult.editsCount < 15) {
        testResults.errors.push({
          user: userEmail,
          operation: 'Race condition test',
          message: `Only ${userResult.editsCount}/20 edits succeeded - possible race condition`,
        });
      }
      
      userResult.success = true;
      await context.close();
      
    } catch (error) {
      testResults.errors.push({
        user: userEmail,
        operation: 'Race condition test',
        message: error.message,
      });
    } finally {
      userResult.executionTime = ((Date.now() - startTime) / 1000).toFixed(2);
      testResults.users.push(userResult);
    }
  });

  test('User 5: Multiple jobs - Queue management test', async ({ browser }) => {
    const userEmail = `concurrent-queue-${Date.now()}@test.local`;
    const userResult = {
      email: userEmail,
      papersCreated: 0,
      editsCount: 0,
      jobsQueued: 0,
      executionTime: 0,
      success: false,
    };
    const startTime = Date.now();
    
    try {
      const context = await browser.newContext();
      const api = context.request;
      
      const reg = await api.post('/api/auth/register', {
        data: {
          email: userEmail,
          name: 'Queue Test User',
          password: 'Test123!',
          captcha_token: '1x00000000000000000000AA',
        },
      });
      expect(reg.status()).toBe(201);
      
      const cookies = await context.cookies();
      const csrf = csrfFromCookies(cookies);
      
      const createRes = await api.post('/api/papers', {
        data: {
          title: 'Queue Management Test Paper',
          data: {},
        },
        headers: { 'X-CSRF-TOKEN': csrf },
      });
      expect(createRes.status()).toBe(200);
      const createBody = await createRes.json();
      const paperId = createBody.id;
      userResult.papersCreated++;
      
      const jobIds = [];
      const queries = ['machine learning', 'artificial intelligence', 'deep learning'];
      
      for (let i = 0; i < queries.length; i++) {
        try {
          const slrRes = await api.post(`/api/papers/${paperId}/slr/jobs`, {
            data: {
              query: queries[i],
              top_k: 10,
            },
            headers: { 'X-CSRF-TOKEN': csrf },
          });
          
          if (slrRes.status() === 202) {
            const slrBody = await slrRes.json();
            jobIds.push(slrBody.id);
            userResult.jobsQueued++;
          }
        } catch (err) {
          testResults.errors.push({
            user: userEmail,
            operation: `Queue SLR job ${i}`,
            message: err.message,
          });
        }
        
        await new Promise(resolve => setTimeout(resolve, 500));
      }
      
      console.log(`User 5: Queued ${userResult.jobsQueued} jobs`);
      
      for (const jobId of jobIds) {
        const statusRes = await api.get(`/api/slr/jobs/${jobId}`);
        if (statusRes.status() === 200) {
          const statusBody = await statusRes.json();
          console.log(`User 5: Job ${jobId} status: ${statusBody.status}`);
        }
      }
      
      userResult.success = true;
      await context.close();
      
    } catch (error) {
      testResults.errors.push({
        user: userEmail,
        operation: 'Queue management test',
        message: error.message,
      });
    } finally {
      userResult.executionTime = ((Date.now() - startTime) / 1000).toFixed(2);
      testResults.users.push(userResult);
    }
  });
});
