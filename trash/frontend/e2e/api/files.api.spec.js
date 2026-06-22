/**
 * API Test Suite: File Upload & Management
 *
 * Tests file upload, validation, security, and serving endpoints.
 * Validates file type checking, size limits, and access control.
 */
import { test, expect } from '@playwright/test';
import { Buffer } from 'buffer';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8000';

function generateTestUser() {
  const timestamp = Date.now();
  return {
    email: `file-api-${timestamp}@test.local`,
    name: 'File API Test User',
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

test.describe('Files API - Upload', () => {
  test('POST /api/papers/:id/files - uploads PDF successfully', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Create a minimal valid PDF
    const pdfContent = Buffer.from('%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n190\n%%EOF');

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'test.pdf',
          mimeType: 'application/pdf',
          buffer: pdfContent,
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toHaveProperty('id');
    expect(body.filename).toBe('test.pdf');
    expect(body.mime_type).toBe('application/pdf');
    expect(body).toHaveProperty('size');
    expect(body.paper_id).toBe(paper.id);
  });

  test('POST /api/papers/:id/files - uploads DOCX successfully', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Create a minimal valid DOCX (ZIP format)
    const docxContent = Buffer.from('PK\x03\x04' + '\x00'.repeat(100));

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'test.docx',
          mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          buffer: docxContent,
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.filename).toBe('test.docx');
  });

  test('POST /api/papers/:id/files - uploads text file successfully', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    const textContent = Buffer.from('This is a test text file with some content.\nLine 2\nLine 3');

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'test.txt',
          mimeType: 'text/plain',
          buffer: textContent,
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.filename).toBe('test.txt');
  });

  test('POST /api/papers/:id/files - rejects oversized files', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Create a 35MB file (exceeds 30MB limit)
    const largeContent = Buffer.alloc(35 * 1024 * 1024, 'a');

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'large.txt',
          mimeType: 'text/plain',
          buffer: largeContent,
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    expect([400, 413]).toContain(response.status());
    const body = await response.json();
    expect(body.error).toMatch(/size|limit|large|exceed/i);
  });

  test('POST /api/papers/:id/files - rejects invalid file types', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    const invalidFiles = [
      { name: 'test.exe', mimeType: 'application/x-msdownload', content: 'MZ\x90\x00' },
      { name: 'test.sh', mimeType: 'application/x-sh', content: '#!/bin/bash\necho "test"' },
      { name: 'test.php', mimeType: 'application/x-php', content: '<?php echo "test"; ?>' },
      { name: 'test.js', mimeType: 'application/javascript', content: 'console.log("test");' },
    ];

    for (const file of invalidFiles) {
      const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
        multipart: {
          file: {
            name: file.name,
            mimeType: file.mimeType,
            buffer: Buffer.from(file.content),
          },
        },
        headers: { 'X-CSRF-TOKEN': csrf },
        failOnStatusCode: false,
      });

      expect([400, 415]).toContain(response.status());
    }
  });

  test('POST /api/papers/:id/files - validates file magic bytes', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Upload file with .pdf extension but wrong content
    const fakeContent = Buffer.from('This is not a PDF file');

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'fake.pdf',
          mimeType: 'application/pdf',
          buffer: fakeContent,
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    expect([400, 415]).toContain(response.status());
    const body = await response.json();
    expect(body.error).toMatch(/invalid|type|format/i);
  });

  test('POST /api/papers/:id/files - sanitizes filenames', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    const maliciousFilenames = [
      '../../../etc/passwd.txt',
      '..\\..\\windows\\system32\\config.txt',
      'test<script>alert(1)</script>.txt',
      'test; rm -rf /.txt',
    ];

    for (const filename of maliciousFilenames) {
      const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
        multipart: {
          file: {
            name: filename,
            mimeType: 'text/plain',
            buffer: Buffer.from('test content'),
          },
        },
        headers: { 'X-CSRF-TOKEN': csrf },
      });

      if (response.status() === 200) {
        const body = await response.json();
        // Filename should be sanitized
        expect(body.filename).not.toContain('..');
        expect(body.filename).not.toContain('<script>');
        expect(body.filename).not.toContain(';');
      }
    }
  });

  test('POST /api/papers/:id/files - prevents upload to other user papers', async ({ request, context }) => {
    // User 1 creates paper
    const { csrf: csrf1 } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf1);

    // User 2 tries to upload
    await context.clearCookies();
    const { csrf: csrf2 } = await registerAndLogin(request, context);

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'unauthorized.txt',
          mimeType: 'text/plain',
          buffer: Buffer.from('test'),
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf2 },
      failOnStatusCode: false,
    });

    expect([403, 404]).toContain(response.status());
  });

  test('POST /api/papers/:id/files - handles multiple concurrent uploads', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    const uploads = [];
    for (let i = 1; i <= 5; i++) {
      uploads.push(
        request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
          multipart: {
            file: {
              name: `file${i}.txt`,
              mimeType: 'text/plain',
              buffer: Buffer.from(`Content ${i}`),
            },
          },
          headers: { 'X-CSRF-TOKEN': csrf },
        })
      );
    }

    const responses = await Promise.all(uploads);

    // All should succeed
    responses.forEach(res => {
      expect(res.status()).toBe(200);
    });

    // Verify all files are listed
    const listRes = await request.get(`${BASE_URL}/api/papers/${paper.id}/files`);
    const files = await listRes.json();
    expect(files.length).toBeGreaterThanOrEqual(5);
  });
});

test.describe('Files API - List & Retrieve', () => {
  test('GET /api/papers/:id/files - lists paper files', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Upload multiple files
    for (let i = 1; i <= 3; i++) {
      await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
        multipart: {
          file: {
            name: `file${i}.txt`,
            mimeType: 'text/plain',
            buffer: Buffer.from(`Content ${i}`),
          },
        },
        headers: { 'X-CSRF-TOKEN': csrf },
      });
    }

    // List files
    const response = await request.get(`${BASE_URL}/api/papers/${paper.id}/files`);

    expect(response.status()).toBe(200);
    const files = await response.json();

    expect(Array.isArray(files)).toBe(true);
    expect(files.length).toBeGreaterThanOrEqual(3);

    files.forEach(file => {
      expect(file).toHaveProperty('id');
      expect(file).toHaveProperty('filename');
      expect(file).toHaveProperty('size');
      expect(file).toHaveProperty('created_at');
    });
  });

  test('GET /api/papers/:id/files/:fileId/raw - serves file content', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    const testContent = 'This is test file content';

    // Upload file
    const uploadRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'test.txt',
          mimeType: 'text/plain',
          buffer: Buffer.from(testContent),
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const file = await uploadRes.json();

    // Retrieve file
    const response = await request.get(`${BASE_URL}/api/papers/${paper.id}/files/${file.id}/raw`);

    expect(response.status()).toBe(200);
    const content = await response.text();
    expect(content).toBe(testContent);
  });

  test('GET /api/papers/:id/files/:fileId/preview - generates preview', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Upload text file
    const uploadRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'preview.txt',
          mimeType: 'text/plain',
          buffer: Buffer.from('Preview content\nLine 2\nLine 3'),
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const file = await uploadRes.json();

    // Get preview
    const response = await request.get(`${BASE_URL}/api/papers/${paper.id}/files/${file.id}/preview`);

    expect(response.status()).toBe(200);
    const preview = await response.json();

    expect(preview).toHaveProperty('text');
    expect(preview.text).toContain('Preview content');
  });

  test('GET /api/papers/:id/files - prevents access to other user files', async ({ request, context }) => {
    // User 1 uploads file
    const { csrf: csrf1 } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf1);

    await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'private.txt',
          mimeType: 'text/plain',
          buffer: Buffer.from('Private content'),
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf1 },
    });

    // User 2 tries to list files
    await context.clearCookies();
    await registerAndLogin(request, context);

    const response = await request.get(`${BASE_URL}/api/papers/${paper.id}/files`, {
      failOnStatusCode: false,
    });

    expect([403, 404]).toContain(response.status());
  });
});

test.describe('Files API - Delete', () => {
  test('DELETE /api/papers/:id/files/:fileId - deletes file', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Upload file
    const uploadRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'delete-me.txt',
          mimeType: 'text/plain',
          buffer: Buffer.from('Delete this'),
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });
    const file = await uploadRes.json();

    // Delete file
    const response = await request.delete(`${BASE_URL}/api/papers/${paper.id}/files/${file.id}`, {
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    expect(response.status()).toBe(200);

    // Verify deletion
    const listRes = await request.get(`${BASE_URL}/api/papers/${paper.id}/files`);
    const files = await listRes.json();
    expect(files.find(f => f.id === file.id)).toBeUndefined();
  });

  test('DELETE /api/papers/:id/files/:fileId - prevents unauthorized deletion', async ({ request, context }) => {
    // User 1 uploads file
    const { csrf: csrf1 } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf1);

    const uploadRes = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'protected.txt',
          mimeType: 'text/plain',
          buffer: Buffer.from('Protected'),
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf1 },
    });
    const file = await uploadRes.json();

    // User 2 tries to delete
    await context.clearCookies();
    const { csrf: csrf2 } = await registerAndLogin(request, context);

    const response = await request.delete(`${BASE_URL}/api/papers/${paper.id}/files/${file.id}`, {
      headers: { 'X-CSRF-TOKEN': csrf2 },
      failOnStatusCode: false,
    });

    expect([403, 404]).toContain(response.status());
  });
});

test.describe('Files API - Security', () => {
  test('Prevents path traversal in file storage', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    const pathTraversalNames = [
      '../../../etc/passwd',
      '..\\..\\..\\windows\\system32\\config',
      'test/../../sensitive.txt',
    ];

    for (const filename of pathTraversalNames) {
      const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
        multipart: {
          file: {
            name: filename,
            mimeType: 'text/plain',
            buffer: Buffer.from('test'),
          },
        },
        headers: { 'X-CSRF-TOKEN': csrf },
      });

      if (response.status() === 200) {
        const file = await response.json();
        // Stored filename should not contain path traversal
        expect(file.filename).not.toContain('..');
        expect(file.filename).not.toMatch(/[\/\\]/);
      }
    }
  });

  test('Prevents zip bomb attacks', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Create a small zip that would expand to huge size
    // This is a simplified test; real zip bombs are more sophisticated
    const zipBomb = Buffer.from('PK\x03\x04' + '\x00'.repeat(1000));

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'bomb.zip',
          mimeType: 'application/zip',
          buffer: zipBomb,
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
      failOnStatusCode: false,
    });

    // Should reject zip files or handle safely
    expect([400, 415]).toContain(response.status());
  });

  test('Validates content-type matches file extension', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Upload PDF with wrong mime type
    const pdfContent = Buffer.from('%PDF-1.4\ntest');

    const response = await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
      multipart: {
        file: {
          name: 'test.pdf',
          mimeType: 'text/plain', // Wrong mime type
          buffer: pdfContent,
        },
      },
      headers: { 'X-CSRF-TOKEN': csrf },
    });

    // Should either accept (and correct) or reject
    if (response.status() === 200) {
      const file = await response.json();
      // Should detect actual type
      expect(file.mime_type).toMatch(/pdf/i);
    }
  });
});

test.describe('Files API - Performance', () => {
  test('Handles multiple file uploads efficiently', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    const startTime = Date.now();

    // Upload 10 files sequentially
    for (let i = 1; i <= 10; i++) {
      await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
        multipart: {
          file: {
            name: `perf-test-${i}.txt`,
            mimeType: 'text/plain',
            buffer: Buffer.from(`Content ${i}`),
          },
        },
        headers: { 'X-CSRF-TOKEN': csrf },
      });
    }

    const duration = Date.now() - startTime;

    // Should complete in reasonable time (< 5 seconds)
    expect(duration).toBeLessThan(5000);

    console.log(`Uploaded 10 files in ${duration}ms (avg: ${(duration / 10).toFixed(2)}ms per file)`);
  });

  test('File listing performance with many files', async ({ request, context }) => {
    const { csrf } = await registerAndLogin(request, context);
    const paper = await createPaper(request, csrf);

    // Upload 20 files
    for (let i = 1; i <= 20; i++) {
      await request.post(`${BASE_URL}/api/papers/${paper.id}/files`, {
        multipart: {
          file: {
            name: `file-${i}.txt`,
            mimeType: 'text/plain',
            buffer: Buffer.from(`Content ${i}`),
          },
        },
        headers: { 'X-CSRF-TOKEN': csrf },
      });
    }

    // Measure list performance
    const startTime = Date.now();
    const response = await request.get(`${BASE_URL}/api/papers/${paper.id}/files`);
    const duration = Date.now() - startTime;

    expect(response.status()).toBe(200);
    const files = await response.json();
    expect(files.length).toBeGreaterThanOrEqual(20);

    // Should be fast (< 500ms)
    expect(duration).toBeLessThan(500);

    console.log(`Listed ${files.length} files in ${duration}ms`);
  });
});
