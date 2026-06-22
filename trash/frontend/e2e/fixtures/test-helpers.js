/**
 * Shared Test Fixtures & Utilities
 *
 * Reusable functions, data generators, and helpers for all test suites.
 * Reduces code duplication and ensures consistency across tests.
 */

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8000';

// ============================================================================
// User Management
// ============================================================================

/**
 * Generate unique test user credentials
 */
export function generateTestUser(prefix = 'test') {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(7);
  return {
    email: `${prefix}-${timestamp}-${random}@test.local`,
    name: `Test User ${timestamp}`,
    password: 'SecurePass123!',
  };
}

/**
 * Register a new user and return credentials + cookies
 */
export async function registerUser(request, context, userPrefix = 'test') {
  const user = generateTestUser(userPrefix);

  const response = await request.post(`${BASE_URL}/api/auth/register`, {
    data: {
      ...user,
      captcha_token: '1x00000000000000000000AA', // Test bypass token
    },
  });

  if (response.status() !== 201) {
    throw new Error(`Registration failed: ${response.status()}`);
  }

  const cookies = await context.cookies();
  const csrf = csrfFromCookies(cookies);

  return { user, cookies, csrf, response };
}

/**
 * Login with existing credentials
 */
export async function loginUser(request, context, email, password) {
  const response = await request.post(`${BASE_URL}/api/auth/login`, {
    data: { email, password },
  });

  if (response.status() !== 200) {
    throw new Error(`Login failed: ${response.status()}`);
  }

  const cookies = await context.cookies();
  const csrf = csrfFromCookies(cookies);

  return { cookies, csrf, response };
}

/**
 * Register and login in one step (most common test setup)
 */
export async function registerAndLogin(request, context, userPrefix = 'test') {
  return await registerUser(request, context, userPrefix);
}

// ============================================================================
// CSRF Token Management
// ============================================================================

/**
 * Extract CSRF token from cookies
 */
export function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const cookie = cookies.find((x) => x.name === name);
  return cookie ? decodeURIComponent(cookie.value) : '';
}

/**
 * Get CSRF token from current context
 */
export async function getCsrfToken(context) {
  const cookies = await context.cookies();
  return csrfFromCookies(cookies);
}

// ============================================================================
// Paper Management
// ============================================================================

/**
 * Create a paper with default or custom data
 */
export async function createPaper(request, csrf, options = {}) {
  const {
    title = 'Test Paper',
    abstract = 'Test abstract',
    sections = [],
    metadata = {},
  } = options;

  const response = await request.post(`${BASE_URL}/api/papers`, {
    data: {
      title,
      data: { abstract, sections, metadata },
    },
    headers: { 'X-CSRF-TOKEN': csrf },
  });

  if (response.status() !== 200) {
    throw new Error(`Paper creation failed: ${response.status()}`);
  }

  return await response.json();
}

/**
 * Create multiple papers
 */
export async function createPapers(request, csrf, count = 3, titlePrefix = 'Paper') {
  const papers = [];

  for (let i = 1; i <= count; i++) {
    const paper = await createPaper(request, csrf, {
      title: `${titlePrefix} ${i}`,
    });
    papers.push(paper);
  }

  return papers;
}

/**
 * Update paper using JSON Patch
 */
export async function updatePaper(request, csrf, paperId, operation) {
  const response = await request.patch(`${BASE_URL}/api/papers/${paperId}`, {
    data: operation,
    headers: { 'X-CSRF-TOKEN': csrf },
  });

  if (response.status() !== 200) {
    throw new Error(`Paper update failed: ${response.status()}`);
  }

  return await response.json();
}

/**
 * Delete paper
 */
export async function deletePaper(request, csrf, paperId) {
  const response = await request.delete(`${BASE_URL}/api/papers/${paperId}`, {
    headers: { 'X-CSRF-TOKEN': csrf },
  });

  return response.status() === 200;
}

// ============================================================================
// File Management
// ============================================================================

/**
 * Create a minimal valid PDF buffer
 */
export function createPdfBuffer(content = 'Test PDF content') {
  return Buffer.from(
    '%PDF-1.4\n' +
    '1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n' +
    '2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n' +
    '3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\n' +
    'xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n' +
    '0000000058 00000 n\n0000000115 00000 n\ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\n' +
    'startxref\n190\n%%EOF'
  );
}

/**
 * Create a minimal valid DOCX buffer (ZIP format)
 */
export function createDocxBuffer() {
  return Buffer.from('PK\x03\x04' + '\x00'.repeat(100));
}

/**
 * Upload file to paper
 */
export async function uploadFile(request, csrf, paperId, options = {}) {
  const {
    filename = 'test.txt',
    mimeType = 'text/plain',
    content = 'Test file content',
  } = options;

  const buffer = Buffer.isBuffer(content) ? content : Buffer.from(content);

  const response = await request.post(`${BASE_URL}/api/papers/${paperId}/files`, {
    multipart: {
      file: {
        name: filename,
        mimeType,
        buffer,
      },
    },
    headers: { 'X-CSRF-TOKEN': csrf },
  });

  if (response.status() !== 200) {
    throw new Error(`File upload failed: ${response.status()}`);
  }

  return await response.json();
}

// ============================================================================
// Job Management
// ============================================================================

/**
 * Enqueue paper generation job
 */
export async function enqueueGeneration(request, csrf, paperId, prompt, options = {}) {
  const { topic, style } = options;

  const response = await request.post(`${BASE_URL}/api/papers/${paperId}/generate`, {
    data: { prompt, topic, style },
    headers: { 'X-CSRF-TOKEN': csrf },
  });

  if (response.status() !== 200) {
    throw new Error(`Job enqueue failed: ${response.status()}`);
  }

  const body = await response.json();
  return body.job_id;
}

/**
 * Enqueue SLR job
 */
export async function enqueueSLR(request, csrf, paperId, query, maxResults = 10) {
  const response = await request.post(`${BASE_URL}/api/papers/${paperId}/slr/jobs`, {
    data: { query, max_results: maxResults },
    headers: { 'X-CSRF-TOKEN': csrf },
  });

  if (response.status() !== 202) {
    throw new Error(`SLR job enqueue failed: ${response.status()}`);
  }

  const body = await response.json();
  return body.job_id;
}

/**
 * Get job status
 */
export async function getJobStatus(request, jobId) {
  const response = await request.get(`${BASE_URL}/api/jobs/${jobId}`);

  if (response.status() !== 200) {
    throw new Error(`Get job status failed: ${response.status()}`);
  }

  return await response.json();
}

/**
 * Poll job until completion or timeout
 */
export async function pollJobUntilComplete(request, jobId, options = {}) {
  const {
    maxAttempts = 30,
    interval = 2000,
    acceptedStatuses = ['done', 'error', 'cancelled'],
  } = options;

  for (let i = 0; i < maxAttempts; i++) {
    const job = await getJobStatus(request, jobId);

    if (acceptedStatuses.includes(job.status)) {
      return job;
    }

    await sleep(interval);
  }

  throw new Error(`Job ${jobId} did not complete within ${maxAttempts * interval}ms`);
}

/**
 * Cancel job
 */
export async function cancelJob(request, csrf, jobId) {
  const response = await request.post(`${BASE_URL}/api/jobs/${jobId}/cancel`, {
    headers: { 'X-CSRF-TOKEN': csrf },
  });

  return response.status() === 200;
}

// ============================================================================
// Utilities
// ============================================================================

/**
 * Sleep for specified milliseconds
 */
export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Retry function with exponential backoff
 */
export async function retry(fn, options = {}) {
  const {
    maxAttempts = 3,
    initialDelay = 1000,
    backoffMultiplier = 2,
    onRetry = null,
  } = options;

  let lastError;
  let delay = initialDelay;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      if (attempt < maxAttempts) {
        if (onRetry) {
          onRetry(attempt, error);
        }
        await sleep(delay);
        delay *= backoffMultiplier;
      }
    }
  }

  throw lastError;
}

/**
 * Wait for condition to be true
 */
export async function waitFor(condition, options = {}) {
  const {
    timeout = 10000,
    interval = 500,
    timeoutMessage = 'Condition not met within timeout',
  } = options;

  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    if (await condition()) {
      return true;
    }
    await sleep(interval);
  }

  throw new Error(timeoutMessage);
}

/**
 * Generate random string
 */
export function randomString(length = 10) {
  return Math.random().toString(36).substring(2, 2 + length);
}

/**
 * Generate random integer between min and max (inclusive)
 */
export function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// ============================================================================
// Test Data Generators
// ============================================================================

/**
 * Generate realistic paper title
 */
export function generatePaperTitle() {
  const topics = [
    'Machine Learning',
    'Artificial Intelligence',
    'Deep Learning',
    'Natural Language Processing',
    'Computer Vision',
    'Robotics',
    'Data Science',
    'Blockchain',
    'Quantum Computing',
    'Cybersecurity',
  ];

  const actions = [
    'Analysis of',
    'Study on',
    'Investigation into',
    'Review of',
    'Exploration of',
    'Survey of',
    'Comparative Study of',
    'Novel Approach to',
  ];

  const topic = topics[randomInt(0, topics.length - 1)];
  const action = actions[randomInt(0, actions.length - 1)];

  return `${action} ${topic} in Modern Applications`;
}

/**
 * Generate realistic abstract
 */
export function generateAbstract() {
  return `This paper presents a comprehensive study on the application of advanced techniques
in solving complex problems. We propose a novel methodology that combines theoretical
foundations with practical implementations. Our experimental results demonstrate
significant improvements over existing approaches, with performance gains of up to 25%.
The findings have important implications for future research and practical applications
in the field.`;
}

/**
 * Generate paper section
 */
export function generateSection(title, paragraphs = 3) {
  const content = [];

  for (let i = 0; i < paragraphs; i++) {
    content.push(
      'Lorem ipsum dolor sit amet, consectetur adipiscing elit. ' +
      'Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. ' +
      'Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.'
    );
  }

  return {
    title,
    content: content.join('\n\n'),
  };
}

// ============================================================================
// Performance Monitoring
// ============================================================================

/**
 * Performance monitor for tracking request metrics
 */
export class PerformanceMonitor {
  constructor() {
    this.metrics = {
      requests: [],
      errors: [],
      timings: {},
    };
  }

  recordRequest(operation, startTime, endTime, status, error = null) {
    const duration = endTime - startTime;

    this.metrics.requests.push({
      operation,
      duration,
      status,
      timestamp: startTime,
      error,
    });

    if (error || status >= 400) {
      this.metrics.errors.push({
        operation,
        status,
        error,
        timestamp: startTime,
      });
    }

    if (!this.metrics.timings[operation]) {
      this.metrics.timings[operation] = [];
    }
    this.metrics.timings[operation].push(duration);
  }

  getStats() {
    const stats = {
      totalRequests: this.metrics.requests.length,
      totalErrors: this.metrics.errors.length,
      errorRate: this.metrics.requests.length > 0
        ? (this.metrics.errors.length / this.metrics.requests.length * 100).toFixed(2) + '%'
        : '0%',
      operations: {},
    };

    for (const [operation, timings] of Object.entries(this.metrics.timings)) {
      const sorted = [...timings].sort((a, b) => a - b);
      const sum = sorted.reduce((a, b) => a + b, 0);

      stats.operations[operation] = {
        count: timings.length,
        avg: (sum / timings.length).toFixed(2) + 'ms',
        min: sorted[0].toFixed(2) + 'ms',
        max: sorted[sorted.length - 1].toFixed(2) + 'ms',
        p50: sorted[Math.floor(sorted.length * 0.5)].toFixed(2) + 'ms',
        p95: sorted[Math.floor(sorted.length * 0.95)].toFixed(2) + 'ms',
        p99: sorted[Math.floor(sorted.length * 0.99)].toFixed(2) + 'ms',
      };
    }

    return stats;
  }

  getErrors() {
    return this.metrics.errors;
  }

  reset() {
    this.metrics = {
      requests: [],
      errors: [],
      timings: {},
    };
  }

  printReport() {
    const stats = this.getStats();
    const errors = this.getErrors();

    console.log('\n' + '='.repeat(80));
    console.log('PERFORMANCE REPORT');
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
  }
}

// ============================================================================
// Assertions & Validators
// ============================================================================

/**
 * Assert response has expected structure
 */
export function assertValidPaper(paper) {
  if (!paper.id) throw new Error('Paper missing id');
  if (!paper.title) throw new Error('Paper missing title');
  if (!paper.created_at) throw new Error('Paper missing created_at');
  if (!paper.updated_at) throw new Error('Paper missing updated_at');
  if (!paper.data) throw new Error('Paper missing data');
}

/**
 * Assert response has expected job structure
 */
export function assertValidJob(job) {
  if (!job.id) throw new Error('Job missing id');
  if (!job.status) throw new Error('Job missing status');
  if (job.progress === undefined) throw new Error('Job missing progress');
  if (!job.stage) throw new Error('Job missing stage');
}

/**
 * Assert response has expected file structure
 */
export function assertValidFile(file) {
  if (!file.id) throw new Error('File missing id');
  if (!file.filename) throw new Error('File missing filename');
  if (!file.mime_type) throw new Error('File missing mime_type');
  if (file.size === undefined) throw new Error('File missing size');
}

// ============================================================================
// Cleanup Utilities
// ============================================================================

/**
 * Clean up test data after test run
 */
export async function cleanupTestData(request, csrf, paperIds = []) {
  for (const paperId of paperIds) {
    try {
      await deletePaper(request, csrf, paperId);
    } catch (error) {
      console.warn(`Failed to cleanup paper ${paperId}:`, error.message);
    }
  }
}
