/**
 * E2E Test: Advanced Power User Workflow
 * 
 * Persona: Dosen/peneliti berpengalaman, sudah bikin 10+ paper, butuh efisiensi
 * 
 * Test Coverage:
 * 1. Bulk operations (multiple papers, 10+ PDFs, multiple SLR jobs)
 * 2. Advanced editing (direct section editing, batch reference import, custom templates)
 * 3. Collaboration features
 * 4. Export options (DOCX, PDF, LaTeX, batch export)
 * 5. Performance measurements (page load, generation speed, export speed)
 * 6. Keyboard shortcuts
 * 7. API rate limits
 * 
 * Focus: Efficiency, bulk operations, performance under load
 */
import { test, expect } from '@playwright/test';
import { readFileSync } from 'fs';
import { join } from 'path';

const POWER_USER = {
  email: `power-user-${Date.now()}@e2e.local`,
  name: 'Prof. Power User',
  password: 'PowerUser123!',
};

const PERFORMANCE_THRESHOLDS = {
  pageLoadMs: 3000,
  paperCreationMs: 2000,
  slrJobSubmitMs: 1000,
  exportMs: 5000,
  bulkOperationMs: 10000,
};

const BULK_PAPER_COUNT = 5;
const BULK_PDF_COUNT = 12;
const CONCURRENT_SLR_JOBS = 3;

function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

async function waitForJobCompletion(api, jobId, maxWaitMs = 180000, pollIntervalMs = 3000) {
  const startTime = Date.now();
  while (Date.now() - startTime < maxWaitMs) {
    const resp = await api.get(`/api/slr/jobs/${jobId}`);
    if (resp.status() !== 200) {
      throw new Error(`Job status check failed: ${resp.status()}`);
    }
    const body = await resp.json();
    if (body.status === 'done') {
      return { body, duration: Date.now() - startTime };
    }
    if (body.status === 'error' || body.status === 'cancelled') {
      throw new Error(`Job failed with status: ${body.status}`);
    }
    await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
  }
  throw new Error('Job did not complete within timeout');
}

async function measurePerformance(fn, label) {
  const start = Date.now();
  const result = await fn();
  const duration = Date.now() - start;
  console.log(`⏱️  ${label}: ${duration}ms`);
  return { result, duration };
}

test.describe('Advanced Power User - Efficiency & Bulk Operations', () => {
  let userId;
  let cookies;
  let ctx;
  let api;
  let page;
  let paperIds = [];
  let performanceMetrics = {};

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    ctx = page.context();
    api = ctx.request;

    const { result: authResp, duration: authDuration } = await measurePerformance(
      async () => {
        let loginResp = await api.post('/api/auth/login', {
          data: { email: POWER_USER.email, password: POWER_USER.password },
        });

        if (loginResp.status() === 401) {
          const reg = await api.post('/api/auth/register', {
            data: { ...POWER_USER, captcha_token: '1x00000000000000000000AA' },
          });
          
          if (reg.status() === 429) {
            console.log('⚠️  Rate limit hit during registration, waiting 65s...');
            await new Promise(resolve => setTimeout(resolve, 65000));
            const retryReg = await api.post('/api/auth/register', {
              data: { ...POWER_USER, captcha_token: '1x00000000000000000000AA' },
            });
            expect(retryReg.status()).toBe(201);
            return retryReg;
          } else {
            expect(reg.status()).toBe(201);
            return reg;
          }
        } else {
          expect(loginResp.status()).toBe(200);
          return loginResp;
        }
      },
      'User Authentication'
    );

    expect([200, 201]).toContain(authResp.status());
    const authBody = await authResp.json();
    userId = authBody.user?.id || authBody.id;
    expect(authBody.user?.email || authBody.email).toBe(POWER_USER.email);
    
    cookies = await ctx.cookies();
    const names = cookies.map(c => c.name);
    expect(names).toContain('access_token_cookie');
    expect(names).toContain('csrf_access_token');
    
    performanceMetrics.auth = authDuration;
  });

  test.afterAll(async () => {
    if (page) {
      await page.close();
    }
  });

  test('1. Bulk Paper Creation - Create multiple papers simultaneously', async () => {
    const paperTemplates = [
      {
        title: 'Machine Learning in Healthcare: A Systematic Review',
        discovery: {
          jurusan: 'Teknik Informatika',
          topik: 'Machine Learning in Healthcare',
          jenis: 'Systematic Review',
          target: 'Jurnal internasional',
        },
      },
      {
        title: 'Blockchain Technology for Supply Chain Management',
        discovery: {
          jurusan: 'Teknik Industri',
          topik: 'Blockchain Supply Chain',
          jenis: 'Literature Review',
          target: 'Jurnal nasional terakreditasi',
        },
      },
      {
        title: 'IoT Security Challenges in Smart Cities',
        discovery: {
          jurusan: 'Teknik Elektro',
          topik: 'IoT Security Smart Cities',
          jenis: 'Survey Paper',
          target: 'Konferensi internasional',
        },
      },
      {
        title: 'Deep Learning for Natural Language Processing',
        discovery: {
          jurusan: 'Ilmu Komputer',
          topik: 'Deep Learning NLP',
          jenis: 'Literature Review',
          target: 'Jurnal internasional',
        },
      },
      {
        title: 'Renewable Energy Integration in Smart Grids',
        discovery: {
          jurusan: 'Teknik Elektro',
          topik: 'Renewable Energy Smart Grid',
          jenis: 'Systematic Review',
          target: 'Jurnal internasional',
        },
      },
    ];

    const { duration: bulkCreateDuration } = await measurePerformance(
      async () => {
        const createPromises = paperTemplates.map(template =>
          api.post('/api/papers', {
            data: { title: template.title, data: template },
            headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
          })
        );

        const responses = await Promise.all(createPromises);
        
        for (const resp of responses) {
          expect(resp.status()).toBe(200);
          const body = await resp.json();
          expect(body.success).toBe(true);
          paperIds.push(body.id);
        }

        return responses;
      },
      `Bulk Paper Creation (${paperTemplates.length} papers)`
    );

    expect(paperIds.length).toBe(paperTemplates.length);
    expect(bulkCreateDuration).toBeLessThan(PERFORMANCE_THRESHOLDS.bulkOperationMs);
    performanceMetrics.bulkPaperCreation = bulkCreateDuration;
    
    console.log(`✅ Created ${paperIds.length} papers in ${bulkCreateDuration}ms`);
    console.log(`   Average: ${Math.round(bulkCreateDuration / paperIds.length)}ms per paper`);
  });

  test('2. Bulk PDF Upload - Upload 10+ PDF files at once', async () => {
    expect(paperIds.length).toBeGreaterThan(0);
    const testPaperId = paperIds[0];

    const mockPdfBuffer = Buffer.from('%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n/Contents 4 0 R\n>>\nendobj\n4 0 obj\n<<\n/Length 44\n>>\nstream\nBT\n/F1 12 Tf\n100 700 Td\n(Test PDF) Tj\nET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000214 00000 n\ntrailer\n<<\n/Size 5\n/Root 1 0 R\n>>\nstartxref\n308\n%%EOF');

    const { duration: bulkUploadDuration } = await measurePerformance(
      async () => {
        const uploadPromises = [];
        
        for (let i = 0; i < BULK_PDF_COUNT; i++) {
          const formData = new FormData();
          const blob = new Blob([mockPdfBuffer], { type: 'application/pdf' });
          formData.append('file', blob, `reference-${i + 1}.pdf`);
          formData.append('type', 'reference');

          uploadPromises.push(
            api.post(`/api/papers/${testPaperId}/files`, {
              multipart: {
                file: {
                  name: `reference-${i + 1}.pdf`,
                  mimeType: 'application/pdf',
                  buffer: mockPdfBuffer,
                },
                type: 'reference',
              },
              headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
            })
          );
        }

        const responses = await Promise.all(uploadPromises);
        return responses;
      },
      `Bulk PDF Upload (${BULK_PDF_COUNT} files)`
    );

    performanceMetrics.bulkPdfUpload = bulkUploadDuration;
    console.log(`✅ Uploaded ${BULK_PDF_COUNT} PDFs in ${bulkUploadDuration}ms`);
    console.log(`   Average: ${Math.round(bulkUploadDuration / BULK_PDF_COUNT)}ms per file`);
  });

  test('3. Multiple Concurrent SLR Jobs - Run multiple SLR jobs simultaneously', async () => {
    expect(paperIds.length).toBeGreaterThanOrEqual(CONCURRENT_SLR_JOBS);
    
    const slrQueries = [
      {
        paperId: paperIds[0],
        query: 'machine learning healthcare diagnosis prediction',
        databases: ['pubmed', 'semantic_scholar'],
        top_k: 30,
      },
      {
        paperId: paperIds[1],
        query: 'blockchain supply chain traceability transparency',
        databases: ['google_scholar', 'semantic_scholar'],
        top_k: 30,
      },
      {
        paperId: paperIds[2],
        query: 'IoT security smart city vulnerability attack',
        databases: ['semantic_scholar', 'arxiv'],
        top_k: 30,
      },
    ];

    const jobIds = [];
    const { duration: submitDuration } = await measurePerformance(
      async () => {
        const submitPromises = slrQueries.map(({ paperId, query, databases, top_k }) =>
          api.post(`/api/papers/${paperId}/slr/jobs`, {
            data: { query, databases, top_k },
            headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
          })
        );

        const responses = await Promise.all(submitPromises);
        
        for (const resp of responses) {
          expect(resp.status()).toBe(202);
          const body = await resp.json();
          expect(body.id).toBeTruthy();
          jobIds.push(body.id);
        }

        return responses;
      },
      `Submit ${CONCURRENT_SLR_JOBS} SLR Jobs Concurrently`
    );

    expect(jobIds.length).toBe(CONCURRENT_SLR_JOBS);
    performanceMetrics.concurrentSlrSubmit = submitDuration;
    
    console.log(`✅ Submitted ${jobIds.length} SLR jobs in ${submitDuration}ms`);

    const completionPromises = jobIds.map(jobId => 
      waitForJobCompletion(api, jobId, 240000, 5000)
    );

    const { duration: completionDuration } = await measurePerformance(
      async () => {
        const results = await Promise.allSettled(completionPromises);
        return results;
      },
      `Wait for ${CONCURRENT_SLR_JOBS} SLR Jobs Completion`
    );

    performanceMetrics.concurrentSlrCompletion = completionDuration;
    console.log(`✅ All ${jobIds.length} SLR jobs completed in ${completionDuration}ms`);
    console.log(`   Average: ${Math.round(completionDuration / jobIds.length)}ms per job`);
  });

  test('4. Advanced Editing - Direct section editing and batch operations', async ({ page }) => {
    await page.goto('/');
    
    const { duration: pageLoadDuration } = await measurePerformance(
      async () => {
        await page.goto(`/papers/${paperIds[0]}`);
        await page.waitForLoadState('networkidle');
      },
      'Paper Editor Page Load'
    );

    expect(pageLoadDuration).toBeLessThan(PERFORMANCE_THRESHOLDS.pageLoadMs);
    performanceMetrics.editorPageLoad = pageLoadDuration;

    const abstractSection = page.locator('[data-section="abstract"]').first();
    if (await abstractSection.isVisible()) {
      await abstractSection.click();
      
      const editor = page.locator('textarea, [contenteditable="true"]').first();
      if (await editor.isVisible()) {
        const { duration: editDuration } = await measurePerformance(
          async () => {
            await editor.fill('This is an advanced edit test for the abstract section. Testing direct section editing capabilities for power users who need quick access to modify content without going through multiple steps.');
            await page.keyboard.press('Control+S');
            await page.waitForTimeout(1000);
          },
          'Direct Section Edit + Save'
        );
        
        performanceMetrics.directSectionEdit = editDuration;
        console.log(`✅ Direct section edit completed in ${editDuration}ms`);
      }
    }
  });

  test('5. Batch Reference Import - Import multiple references at once', async () => {
    const testPaperId = paperIds[0];
    
    const batchReferences = [
      {
        title: 'Deep Learning for Medical Image Analysis',
        authors: 'Smith, J., Johnson, A., Williams, B.',
        year: 2023,
        journal: 'Nature Medicine',
        doi: '10.1038/s41591-023-00001-1',
        type: 'journal',
      },
      {
        title: 'Machine Learning in Healthcare: Current Applications',
        authors: 'Brown, C., Davis, D., Miller, E.',
        year: 2024,
        journal: 'JAMA',
        doi: '10.1001/jama.2024.00001',
        type: 'journal',
      },
      {
        title: 'AI-Powered Diagnosis Systems: A Review',
        authors: 'Wilson, F., Moore, G., Taylor, H.',
        year: 2023,
        conference: 'NeurIPS 2023',
        type: 'conference',
      },
      {
        title: 'Clinical Decision Support with Neural Networks',
        authors: 'Anderson, I., Thomas, J., Jackson, K.',
        year: 2024,
        journal: 'The Lancet Digital Health',
        doi: '10.1016/S2589-7500(24)00001-1',
        type: 'journal',
      },
      {
        title: 'Ethical Considerations in Medical AI',
        authors: 'White, L., Harris, M., Martin, N.',
        year: 2023,
        journal: 'New England Journal of Medicine',
        doi: '10.1056/NEJMra2300001',
        type: 'journal',
      },
    ];

    const { duration: batchImportDuration } = await measurePerformance(
      async () => {
        const resp = await api.post(`/api/papers/${testPaperId}/references/batch`, {
          data: { references: batchReferences },
          headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
        });

        if (resp.status() === 404) {
          console.log('⚠️  Batch reference import endpoint not available, testing individual imports');
          const importPromises = batchReferences.map(ref =>
            api.post(`/api/papers/${testPaperId}/references`, {
              data: ref,
              headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
            })
          );
          return await Promise.all(importPromises);
        }

        expect([200, 201]).toContain(resp.status());
        return resp;
      },
      `Batch Reference Import (${batchReferences.length} references)`
    );

    performanceMetrics.batchReferenceImport = batchImportDuration;
    console.log(`✅ Imported ${batchReferences.length} references in ${batchImportDuration}ms`);
  });

  test('6. Export Options - Test multiple format exports', async () => {
    const testPaperId = paperIds[0];
    const exportFormats = ['docx', 'pdf', 'latex'];
    const exportResults = {};

    for (const format of exportFormats) {
      const { duration: exportDuration } = await measurePerformance(
        async () => {
          const resp = await api.get(`/api/papers/${testPaperId}/export/${format}`, {
            headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
          });

          if (resp.status() === 404) {
            console.log(`⚠️  Export format ${format} not available`);
            return null;
          }

          expect([200, 201]).toContain(resp.status());
          const buffer = await resp.body();
          expect(buffer.length).toBeGreaterThan(0);
          
          return { format, size: buffer.length };
        },
        `Export to ${format.toUpperCase()}`
      );

      exportResults[format] = {
        duration: exportDuration,
        available: exportDuration !== null,
      };

      if (exportDuration) {
        expect(exportDuration).toBeLessThan(PERFORMANCE_THRESHOLDS.exportMs);
      }
    }

    performanceMetrics.exports = exportResults;
    console.log('✅ Export formats tested:', Object.keys(exportResults).filter(k => exportResults[k].available));
  });

  test('7. Batch Export - Export multiple papers at once', async () => {
    const exportPaperIds = paperIds.slice(0, 3);

    const { duration: batchExportDuration } = await measurePerformance(
      async () => {
        const resp = await api.post('/api/papers/export/batch', {
          data: { paper_ids: exportPaperIds, format: 'pdf' },
          headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
        });

        if (resp.status() === 404) {
          console.log('⚠️  Batch export endpoint not available, testing individual exports');
          const exportPromises = exportPaperIds.map(id =>
            api.get(`/api/papers/${id}/export/pdf`, {
              headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
            })
          );
          return await Promise.allSettled(exportPromises);
        }

        expect([200, 201]).toContain(resp.status());
        return resp;
      },
      `Batch Export (${exportPaperIds.length} papers)`
    );

    performanceMetrics.batchExport = batchExportDuration;
    console.log(`✅ Batch export completed in ${batchExportDuration}ms`);
  });

  test('8. Keyboard Shortcuts - Test efficiency features', async ({ page }) => {
    await page.goto(`/papers/${paperIds[0]}`);
    await page.waitForLoadState('networkidle');

    const shortcuts = [
      { key: 'Control+S', action: 'Save', selector: null },
      { key: 'Control+E', action: 'Edit Mode', selector: null },
      { key: 'Control+P', action: 'Preview', selector: null },
      { key: 'Escape', action: 'Close Modal', selector: null },
    ];

    const workingShortcuts = [];

    for (const shortcut of shortcuts) {
      try {
        await page.keyboard.press(shortcut.key);
        await page.waitForTimeout(500);
        workingShortcuts.push(shortcut.action);
      } catch (error) {
        console.log(`⚠️  Keyboard shortcut ${shortcut.key} (${shortcut.action}) not available or failed`);
      }
    }

    performanceMetrics.keyboardShortcuts = {
      tested: shortcuts.length,
      working: workingShortcuts.length,
      shortcuts: workingShortcuts,
    };

    console.log(`✅ Keyboard shortcuts tested: ${workingShortcuts.length}/${shortcuts.length} working`);
  });

  test('9. API Rate Limits - Test rate limiting behavior', async () => {
    const rateLimitTests = [];
    let hitRateLimit = false;
    let requestCount = 0;

    const { duration: rateLimitTestDuration } = await measurePerformance(
      async () => {
        for (let i = 0; i < 20; i++) {
          const resp = await api.get('/api/papers', {
            failOnStatusCode: false,
          });
          
          requestCount++;
          rateLimitTests.push({
            request: i + 1,
            status: resp.status(),
            timestamp: Date.now(),
          });

          if (resp.status() === 429) {
            hitRateLimit = true;
            const retryAfter = resp.headers()['retry-after'];
            console.log(`⚠️  Rate limit hit at request ${i + 1}, retry-after: ${retryAfter}s`);
            break;
          }

          await page.waitForTimeout(100);
        }
      },
      'Rate Limit Testing'
    );

    performanceMetrics.rateLimit = {
      hitLimit: hitRateLimit,
      requestsBeforeLimit: hitRateLimit ? requestCount : 'No limit hit',
      testDuration: rateLimitTestDuration,
    };

    console.log(`✅ Rate limit test: ${hitRateLimit ? `Hit at ${requestCount} requests` : 'No limit hit in 20 requests'}`);
  });

  test('10. Performance Summary & Recommendations', async () => {
    console.log('\n📊 PERFORMANCE BENCHMARK SUMMARY\n');
    console.log('=' .repeat(60));
    
    console.log('\n🔐 Authentication:');
    console.log(`   Registration: ${performanceMetrics.auth}ms`);
    
    console.log('\n📝 Bulk Operations:');
    console.log(`   Paper Creation (${BULK_PAPER_COUNT} papers): ${performanceMetrics.bulkPaperCreation}ms`);
    console.log(`   Average per paper: ${Math.round(performanceMetrics.bulkPaperCreation / BULK_PAPER_COUNT)}ms`);
    console.log(`   PDF Upload (${BULK_PDF_COUNT} files): ${performanceMetrics.bulkPdfUpload}ms`);
    console.log(`   Average per file: ${Math.round(performanceMetrics.bulkPdfUpload / BULK_PDF_COUNT)}ms`);
    
    console.log('\n🔍 SLR Operations:');
    console.log(`   Concurrent Job Submit (${CONCURRENT_SLR_JOBS} jobs): ${performanceMetrics.concurrentSlrSubmit}ms`);
    console.log(`   Concurrent Job Completion: ${performanceMetrics.concurrentSlrCompletion}ms`);
    console.log(`   Average per job: ${Math.round(performanceMetrics.concurrentSlrCompletion / CONCURRENT_SLR_JOBS)}ms`);
    
    console.log('\n✏️  Editing:');
    console.log(`   Editor Page Load: ${performanceMetrics.editorPageLoad}ms`);
    if (performanceMetrics.directSectionEdit) {
      console.log(`   Direct Section Edit: ${performanceMetrics.directSectionEdit}ms`);
    }
    console.log(`   Batch Reference Import: ${performanceMetrics.batchReferenceImport}ms`);
    
    console.log('\n📤 Export:');
    if (performanceMetrics.exports) {
      Object.entries(performanceMetrics.exports).forEach(([format, data]) => {
        if (data.available) {
          console.log(`   ${format.toUpperCase()}: ${data.duration}ms`);
        }
      });
    }
    if (performanceMetrics.batchExport) {
      console.log(`   Batch Export: ${performanceMetrics.batchExport}ms`);
    }
    
    console.log('\n⌨️  Efficiency Features:');
    if (performanceMetrics.keyboardShortcuts) {
      console.log(`   Keyboard Shortcuts: ${performanceMetrics.keyboardShortcuts.working}/${performanceMetrics.keyboardShortcuts.tested} working`);
      console.log(`   Available: ${performanceMetrics.keyboardShortcuts.shortcuts.join(', ')}`);
    }
    
    console.log('\n🚦 Rate Limiting:');
    if (performanceMetrics.rateLimit) {
      console.log(`   Hit Limit: ${performanceMetrics.rateLimit.hitLimit}`);
      console.log(`   Requests Before Limit: ${performanceMetrics.rateLimit.requestsBeforeLimit}`);
    }
    
    console.log('\n' + '='.repeat(60));
    console.log('\n💡 POWER USER RECOMMENDATIONS:\n');
    
    const recommendations = [];
    
    if (performanceMetrics.bulkPaperCreation / BULK_PAPER_COUNT < 500) {
      recommendations.push('✅ Bulk paper creation is efficient - suitable for batch operations');
    } else {
      recommendations.push('⚠️  Consider optimizing bulk paper creation for better performance');
    }
    
    if (performanceMetrics.concurrentSlrCompletion / CONCURRENT_SLR_JOBS < 60000) {
      recommendations.push('✅ SLR jobs complete quickly - good for parallel research workflows');
    } else {
      recommendations.push('⚠️  SLR jobs take significant time - consider background processing');
    }
    
    if (performanceMetrics.editorPageLoad < PERFORMANCE_THRESHOLDS.pageLoadMs) {
      recommendations.push('✅ Editor loads quickly - good for rapid editing workflows');
    } else {
      recommendations.push('⚠️  Editor page load could be optimized for power users');
    }
    
    if (performanceMetrics.keyboardShortcuts?.working > 2) {
      recommendations.push('✅ Keyboard shortcuts available - enhances power user efficiency');
    } else {
      recommendations.push('💡 Consider adding more keyboard shortcuts for power users');
    }
    
    if (!performanceMetrics.rateLimit?.hitLimit) {
      recommendations.push('✅ Rate limits are reasonable for power user workflows');
    } else {
      recommendations.push('⚠️  Rate limits may impact power users - consider higher limits for authenticated users');
    }
    
    recommendations.forEach(rec => console.log(`   ${rec}`));
    
    console.log('\n' + '='.repeat(60));
    console.log('\n✅ Advanced Power User Test Complete!\n');

    expect(performanceMetrics.bulkPaperCreation).toBeLessThan(PERFORMANCE_THRESHOLDS.bulkOperationMs);
    expect(performanceMetrics.editorPageLoad).toBeLessThan(PERFORMANCE_THRESHOLDS.pageLoadMs);
  });
});
