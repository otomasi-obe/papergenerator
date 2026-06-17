/*
 * server.js — HTTPS static server untuk add-in (port 3000)
 * Office.js WAJIB HTTPS. Sertifikat dari office-addin-dev-certs.
 */
const https = require("https");
const http = require("http");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { URL } = require("url");

const PORT = process.env.PORT || 3000;
const ROOT = __dirname;
const DEFAULT_API_KEY = process.env.VIOLA_API_KEY || "sk-ccfa926bc01cfa19-wruy62-243f58d1";

/*
 * Proxy: meneruskan permintaan dari taskpane (same-origin) ke API AI.
 * Mengatasi ketiadaan header CORS pada endpoint AI. Streaming SSE didukung.
 * Client kirim header:
 *   X-Target-Url: URL lengkap endpoint tujuan (mis. https://ai.otomasi.app/v1/chat/completions)
 *   Authorization: Bearer <key>
 */
function handleProxy(req, res) {
  const target = req.headers["x-target-url"];
  if (!target) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "X-Target-Url header wajib ada" }));
    return;
  }
  let targetUrl;
  try { targetUrl = new URL(target); }
  catch (e) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "X-Target-Url tidak valid" }));
    return;
  }

  let body = [];
  req.on("data", (c) => body.push(c));
  req.on("end", () => {
    const payload = Buffer.concat(body);
    const lib = targetUrl.protocol === "http:" ? http : https;
    const opts = {
      method: req.method,
      hostname: targetUrl.hostname,
      port: targetUrl.port || (targetUrl.protocol === "http:" ? 80 : 443),
      path: targetUrl.pathname + targetUrl.search,
      headers: {
        "Content-Type": "application/json",
        "Content-Length": payload.length,
      },
    };
    if (req.headers["authorization"]) opts.headers["Authorization"] = req.headers["authorization"];
    // Cloudflare kadang melucuti header Authorization. Terima key via header custom
    // X-Api-Key (lolos Cloudflare), lalu fallback ke key default server.
    if (!opts.headers["Authorization"]) {
      const k = req.headers["x-api-key"] || DEFAULT_API_KEY;
      if (k) opts.headers["Authorization"] = "Bearer " + k;
    }

    const up = lib.request(opts, (upRes) => {
      // teruskan status + content-type, tambahkan CORS untuk jaga-jaga
      res.writeHead(upRes.statusCode, {
        "Content-Type": upRes.headers["content-type"] || "application/json",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
      });
      upRes.pipe(res); // streaming SSE lolos apa adanya
    });
    up.on("error", (e) => {
      res.writeHead(502, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" });
      res.end(JSON.stringify({ error: "Proxy gagal: " + e.message }));
    });
    if (payload.length) up.write(payload);
    up.end();
  });
}

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".png": "image/png",
  ".xml": "text/xml",
  ".json": "application/json",
  ".ico": "image/x-icon",
};

function serve(req, res) {
  // CORS + no-cache (penting agar Word memuat versi terbaru)
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Cache-Control", "no-store");

  // Route proxy AI (same-origin -> hindari CORS endpoint AI)
  if (req.url.split("?")[0] === "/proxy") {
    return handleProxy(req, res);
  }

  let urlPath = decodeURIComponent(req.url.split("?")[0]);
  if (urlPath === "/") urlPath = "/src/taskpane.html";
  const filePath = path.join(ROOT, urlPath);

  // cegah path traversal
  if (!filePath.startsWith(ROOT)) {
    res.writeHead(403); res.end("Forbidden"); return;
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("404 Not Found: " + urlPath);
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
    res.end(data);
  });
}

// Lokasi sertifikat dev office-addin-dev-certs (cek beberapa lokasi umum)
const candidateDirs = [
  path.join(os.homedir(), ".office-addin-dev-certs"),
  process.env.HOME ? path.join(process.env.HOME, ".office-addin-dev-certs") : null,
  "/home/sirobo/.office-addin-dev-certs",
  "/home/sirobo/.hermes/profiles/otomasiapp/home/.office-addin-dev-certs",
].filter(Boolean);

let keyPath = null, certPath = null;
for (const d of candidateDirs) {
  const k = path.join(d, "localhost.key");
  const c = path.join(d, "localhost.crt");
  if (fs.existsSync(k) && fs.existsSync(c)) { keyPath = k; certPath = c; break; }
}

if (keyPath && certPath && !process.env.FORCE_HTTP) {
  const opts = { key: fs.readFileSync(keyPath), cert: fs.readFileSync(certPath) };
  https.createServer(opts, serve).listen(PORT, () => {
    console.log("HTTPS add-in server: https://localhost:" + PORT + "/src/taskpane.html");
  });
} else {
  if (process.env.FORCE_HTTP) {
    console.warn("FORCE_HTTP aktif — server HTTP untuk QA browser (Word butuh HTTPS).");
  } else {
    console.warn("Sertifikat dev tidak ditemukan. Jalankan: npx office-addin-dev-certs install");
  }
  console.warn("Fallback HTTP (Word TIDAK menerima HTTP, hanya untuk QA lokal).");
  http.createServer(serve).listen(PORT, () => {
    console.log("HTTP server (dev only): http://localhost:" + PORT + "/src/taskpane.html");
  });
}
