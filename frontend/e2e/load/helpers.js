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
}

export async function registerUser(api, userIndex) {
  const timestamp = Date.now();
  const user = {
    email: `load-test-${timestamp}-user${userIndex}@e2e.local`,
    name: `Load Test User ${userIndex}`,
    password: 'LoadTest123!',
  };

  const res = await api.post('/api/auth/register', {
    data: { ...user, captcha_token: '1x00000000000000000000AA' },
  });

  if (res.status() !== 201) {
    throw new Error(`Registration failed: ${res.status()}`);
  }

  return user;
}

export function csrfFromCookies(cookies, name = 'csrf_access_token') {
  const c = cookies.find((x) => x.name === name);
  return c ? decodeURIComponent(c.value) : '';
}

export async function createPaper(api, cookies, title, data = {}) {
  const res = await api.post('/api/papers', {
    data: { title, data },
    headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
  });

  if (res.status() !== 200) {
    throw new Error(`Create paper failed: ${res.status()}`);
  }

  const body = await res.json();
  return body.id;
}

export async function updatePaper(api, cookies, paperId, updates) {
  const res = await api.patch(`/api/papers/${paperId}`, {
    data: updates,
    headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
  });

  if (res.status() !== 200) {
    throw new Error(`Update paper failed: ${res.status()}`);
  }

  return await res.json();
}

export async function enqueueSLR(api, cookies, paperId, query) {
  const res = await api.post(`/api/papers/${paperId}/slr/jobs`, {
    data: { query, max_results: 10 },
    headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
  });

  if (res.status() !== 202) {
    throw new Error(`Enqueue SLR failed: ${res.status()}`);
  }

  const body = await res.json();
  return body.job_id;
}

export async function enqueueGeneration(api, cookies, paperId, prompt) {
  const res = await api.post(`/api/papers/${paperId}/generate`, {
    data: { prompt },
    headers: { 'X-CSRF-TOKEN': csrfFromCookies(cookies) },
  });

  if (res.status() !== 200 && res.status() !== 202) {
    throw new Error(`Enqueue generation failed: ${res.status()}`);
  }

  const body = await res.json();
  return body.job_id;
}

export async function pollJobStatus(api, jobId, endpoint = '/api/jobs', maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    const res = await api.get(`${endpoint}/${jobId}`);
    if (res.status() !== 200) {
      throw new Error(`Poll job failed: ${res.status()}`);
    }

    const body = await res.json();
    if (body.status === 'done' || body.status === 'error' || body.status === 'cancelled') {
      return body;
    }

    await new Promise(resolve => setTimeout(resolve, 2000));
  }

  throw new Error(`Job ${jobId} did not complete in time`);
}

export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
