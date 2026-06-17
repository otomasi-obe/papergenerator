const http = require('http');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

const PORT = parseInt(process.env.FRONTEND_PORT) || 8000;
const BACKEND_HOST = 'localhost';
const BACKEND_PORT = parseInt(process.env.BACKEND_PORT) || 8001;
const DIST_DIR = path.join(__dirname, 'dist');

const mimeTypes = {
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.xml': 'application/xml',
  '.webmanifest': 'application/manifest+json',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.eot': 'application/vnd.ms-fontobject',
};

// Crash-safe: never let a bad client/proxy hop kill the worker.
process.on('uncaughtException', (err) => {
  console.error('[uncaughtException]', err && err.stack ? err.stack : err);
});
process.on('unhandledRejection', (reason) => {
  console.error('[unhandledRejection]', reason);
});

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  // Proxy API requests to backend
  if (url.pathname.startsWith('/api/')) {
    // SSE streaming endpoints (paper generation) need unbounded duration:
    // long silent LLM "thinking" must not trip Node's default request/socket
    // timeouts, or the client sees a spurious "network error".
    const isStream = url.pathname.includes('/generate-stream');
    if (isStream) {
      try { req.setTimeout(0); } catch (_) { /* noop */ }
      try { res.setTimeout(0); } catch (_) { /* noop */ }
    }
    const originalHost = req.headers['x-forwarded-host'] || req.headers.host;
    const forwardedProto = req.headers['x-forwarded-proto'] || 'https';
    const proxyOptions = {
      hostname: BACKEND_HOST,
      port: BACKEND_PORT,
      path: url.pathname + url.search,
      method: req.method,
      headers: {
        ...req.headers,
        host: `${BACKEND_HOST}:${BACKEND_PORT}`,
        'x-forwarded-host': originalHost,
        'x-forwarded-proto': forwardedProto,
      },
    };

    const proxyReq = http.request(proxyOptions, (proxyRes) => {
      const isSSE = (proxyRes.headers['content-type'] || '').includes('text/event-stream');
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      if (isSSE) {
        // Flush headers and disable Nagle so heartbeat/token chunks reach the
        // client immediately instead of being buffered/coalesced.
        try { res.socket && res.socket.setNoDelay(true); } catch (_) { /* noop */ }
        try { res.flushHeaders(); } catch (_) { /* noop */ }
      }
      proxyRes.pipe(res);
      proxyRes.on('error', (err) => {
        console.error('[proxy-res] stream error:', err.code || err.message);
        try { res.destroy(); } catch (_) { /* already closed */ }
      });
    });

    // Never let the upstream socket time out on a long SSE generation.
    if (isStream) {
      try { proxyReq.setTimeout(0); } catch (_) { /* noop */ }
    }

    proxyReq.on('error', (err) => {
      const status = err.code === 'ECONNREFUSED' ? 503 : 502;
      const msg = err.code === 'ECONNREFUSED'
        ? 'Backend temporarily unavailable'
        : 'Proxy error';
      console.error(`[proxy-req] ${err.code || ''} ${url.pathname} -> ${status}`);
      if (!res.headersSent) {
        res.writeHead(status, {
          'Content-Type': 'application/json',
          'Retry-After': '5',
        });
        res.end(JSON.stringify({ error: msg, code: err.code || 'PROXY_ERR' }));
      } else {
        try { res.destroy(); } catch (_) { /* already closed */ }
      }
    });

    // Client may abort mid-request — kill upstream cleanly.
    req.on('error', (err) => {
      console.error('[client-req] error:', err.code || err.message);
      try { proxyReq.destroy(); } catch (_) { /* already destroyed */ }
    });
    req.on('aborted', () => {
      try { proxyReq.destroy(); } catch (_) { /* already destroyed */ }
    });

    req.pipe(proxyReq);
    return;
  }

  // Serve static files from dist/
  let pathname;
  try {
    pathname = decodeURIComponent(url.pathname);
  } catch {
    pathname = url.pathname;
  }
  // Block path-traversal escape attempts before joining onto DIST_DIR
  if (pathname.includes('\0') || pathname.split('/').some(p => p === '..')) {
    res.writeHead(400, { 'Content-Type': 'text/plain' });
    res.end('Bad Request');
    return;
  }
  let filePath = path.join(DIST_DIR, pathname);
  if (pathname === '/') {
    filePath = path.join(DIST_DIR, 'index.html');
  } else if (pathname.endsWith('/')) {
    // Directory request → serve its index.html (fixes EISDIR → 500)
    filePath = path.join(DIST_DIR, pathname, 'index.html');
  }

  const extname = path.extname(filePath);
  const contentType = mimeTypes[extname] || 'application/octet-stream';

  // Force-download for the Word add-in manifest so the browser saves the file
  // instead of rendering it (Word sideload needs the raw manifest.xml on disk).
  const extraHeaders = {};
  if (pathname === '/word-addin/manifest.xml') {
    extraHeaders['Content-Disposition'] = 'attachment; filename="manifest.xml"';
    extraHeaders['Access-Control-Allow-Origin'] = '*';
  }

  fs.readFile(filePath, (err, content) => {
    if (err) {
      if (err.code === 'ENOENT' || err.code === 'EISDIR') {
        // Serve index.html for SPA routing
        fs.readFile(path.join(DIST_DIR, 'index.html'), (err, content) => {
          if (err) {
            res.writeHead(404, { 'Content-Type': 'text/html' });
            res.end('404 Not Found');
          } else {
            res.writeHead(200, { 'Content-Type': 'text/html' });
            res.end(content);
          }
        });
      } else {
        res.writeHead(500, { 'Content-Type': 'text/html' });
        res.end('Server Error');
      }
    } else {
      res.writeHead(200, { 'Content-Type': contentType, ...extraHeaders });
      res.end(content);
    }
  });
});

server.listen(PORT, () => {
  console.log(`Proxy server running on port ${PORT}`);
  console.log(`Frontend: http://localhost:${PORT}`);
  console.log(`API proxy: http://localhost:${PORT}/api/* -> http://${BACKEND_HOST}:${BACKEND_PORT}`);
});

// Disable Node's built-in timeouts that would otherwise kill long SSE
// generations (paper generation can run many minutes with silent gaps).
// Node 18+ defaults: requestTimeout=300s, headersTimeout=60s, timeout=0.
// requestTimeout/headersTimeout are hard server-level limits NOT overridden
// by per-request setTimeout(0), so they must be cleared here.
server.requestTimeout = 0;     // no cap on full request duration
server.headersTimeout = 0;     // no cap on header receipt
server.timeout = 0;            // no socket inactivity timeout
server.keepAliveTimeout = 75000; // 75s keep-alive for idle connections
