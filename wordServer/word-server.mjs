/**
 * Word GPT Plus Server — serves Vue frontend + proxies /v1/* to VIOLA backend.
 * Model hardcoded to VIOLA-CHAT, API key injected server-side from .env.
 */

import http from 'node:http'
import { createReadStream, existsSync, statSync } from 'node:fs'
import { extname, join, normalize } from 'node:path'
import { fileURLToPath } from 'node:url'
import { config } from 'dotenv'
import { resolve } from 'node:path'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
config({ path: resolve(__dirname, '../.env') }) // wordServer/ → papergenerator/.env

const DIST_DIR = join(__dirname, 'word-GPT-Plus', 'dist')
const PROXY_TARGET = process.env.AIOTOMASI_API || 'http://localhost:20128/v1'
const API_KEY = process.env.AIOTOMASI_APIKEY || ''
const PORT = 8011

const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'GET,POST,OPTIONS',
  'access-control-allow-headers': 'Content-Type,Authorization',
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.eot': 'application/vnd.ms-fontobject',
}

function serveStatic(req, res) {
  let urlPath = decodeURIComponent((req.url || '/').split('?')[0])
  if (urlPath === '/') urlPath = '/index.html'

  const filePath = normalize(join(DIST_DIR, urlPath))
  if (!filePath.startsWith(DIST_DIR)) {
    res.writeHead(403, CORS); res.end('Forbidden'); return
  }

  if (!existsSync(filePath) || !statSync(filePath).isFile()) {
    const indexPath = join(DIST_DIR, 'index.html')
    if (existsSync(indexPath)) {
      res.writeHead(200, { 'Content-Type': MIME['.html'], ...CORS })
      createReadStream(indexPath).pipe(res)
    } else {
      res.writeHead(404, CORS); res.end('Not Found')
    }
    return
  }

  const ext = extname(filePath).toLowerCase()
  res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream', ...CORS })
  createReadStream(filePath).pipe(res)
}

async function proxyRequest(req, res) {
  // Strip /v1 prefix if PROXY_TARGET already ends with /v1
  let targetPath = req.url || '/'
  let targetBase = PROXY_TARGET
  if (PROXY_TARGET.endsWith('/v1') && targetPath.startsWith('/v1/')) {
    targetPath = targetPath.slice(3) // keep /chat/completions etc
  }
  const targetUrl = targetBase + targetPath

  try {
    const headers = { ...req.headers }
    delete headers.host
    delete headers['content-length']

    if (req.method === 'POST' && (req.url || '').startsWith('/v1/')) {
      const chunks = []
      for await (const chunk of req) chunks.push(chunk)
      const body = Buffer.concat(chunks).toString('utf8')

      let parsed
      try { parsed = JSON.parse(body) } catch { parsed = {} }

      parsed.model = 'VIOLA-CHAT'
      delete parsed.apiKey

      headers['authorization'] = `Bearer ${API_KEY}`
      delete headers['api-key']

      const newBody = JSON.stringify(parsed)
      headers['content-length'] = Buffer.byteLength(newBody)

      const proxyRes = await fetch(targetUrl, {
        method: req.method,
        headers,
        body: newBody,
      })

      const respHeaders = { ...Object.fromEntries(proxyRes.headers.entries()), ...CORS }
      res.writeHead(proxyRes.status, respHeaders)
      const resBody = Buffer.from(await proxyRes.arrayBuffer())
      res.end(resBody)
    } else {
      const proxyRes = await fetch(targetUrl, { method: req.method, headers })
      const respHeaders = { ...Object.fromEntries(proxyRes.headers.entries()), ...CORS }
      res.writeHead(proxyRes.status, respHeaders)
      const resBody = Buffer.from(await proxyRes.arrayBuffer())
      res.end(resBody)
    }
  } catch (err) {
    res.writeHead(502, { 'Content-Type': 'application/json', ...CORS })
    res.end(JSON.stringify({ error: 'Backend unavailable', detail: err.message }))
  }
}

const server = http.createServer((req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, { ...CORS, 'access-control-max-age': '86400' })
    res.end()
    return
  }

  const urlPath = (req.url || '/').split('?')[0]
  if (urlPath.startsWith('/v1/')) {
    proxyRequest(req, res)
  } else {
    serveStatic(req, res)
  }
})

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[word-server] http://localhost:${PORT} — static: ${DIST_DIR} — proxy /v1/* → ${PROXY_TARGET}`)
})
