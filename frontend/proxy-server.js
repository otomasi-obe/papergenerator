import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 8000;

// Serve static files from dist FIRST
app.use(express.static(path.join(__dirname, 'dist')));

// API proxy to backend - only for /api/* requests
app.use('/api', createProxyMiddleware({
  target: 'http://localhost:8001',
  changeOrigin: true,
  ws: true,
  timeout: 1800000,
  proxyTimeout: 1800000,
  onError: (err, req, res) => {
    console.error('Proxy error:', err.message);
    res.status(502).json({ error: 'Bad Gateway', message: err.message });
  }
}));

// SPA fallback - serve index.html for all other routes
app.use((req, res) => {
  res.sendFile(path.join(__dirname, 'dist', 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Frontend proxy server running on http://0.0.0.0:${PORT}`);
  console.log(`Proxying /api/* to http://localhost:8001`);
});
