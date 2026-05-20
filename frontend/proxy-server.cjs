const http = require('http');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

const PORT = process.env.PORT || 8000;
const BACKEND_HOST = 'localhost';
const BACKEND_PORT = 8001;
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
    const proxyOptions = {
      hostname: BACKEND_HOST,
      port: BACKEND_PORT,
      path: url.pathname + url.search,
      method: req.method,
      headers: {
        ...req.headers,
        host: `${BACKEND_HOST}:${BACKEND_PORT}`,
      },
    };

    const proxyReq = http.request(proxyOptions, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res);
      proxyRes.on('error', (err) => {
        console.error('[proxy-res] stream error:', err.code || err.message);
        try { res.destroy(); } catch (_) { /* already closed */ }
      });
    });

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
  }

  const extname = path.extname(filePath);
  const contentType = mimeTypes[extname] || 'application/octet-stream';

  fs.readFile(filePath, (err, content) => {
    if (err) {
      if (err.code === 'ENOENT') {
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
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(content);
    }
  });
});

server.listen(PORT, () => {
  console.log(`Proxy server running on port ${PORT}`);
  console.log(`Frontend: http://localhost:${PORT}`);
  console.log(`API proxy: http://localhost:${PORT}/api/* -> http://${BACKEND_HOST}:${BACKEND_PORT}`);
});
