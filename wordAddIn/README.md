# PaperFull Word

Add-in Microsoft Word bertenaga AI: **baca** seleksi/paragraf/seluruh dokumen, lalu **edit langsung** di dokumen — terjemah, ringkas, poles, perbaiki tata bahasa, kembangkan, perpendek, jadikan formal/poin, lanjutkan menulis, dan chat bebas.

Menggabungkan fitur dari 10 repo add-in AI Word open-source (lihat `referensi/`): pola baca/replace dari **word-GPT-Plus**, track-changes dari **word-ai-redliner**, alur locate→read→edit dari **WordAgent**, scope picker + word count dari **ollama-word-addin**, apply-to-document dari **ai-office-addin**, dan preview/insert dari **WordCopilotChat**.

## Fitur

- **Sumber konteks** (scope): Teks terpilih · Paragraf saat ini · Seluruh dokumen · Tanpa konteks (chat)
- **11 aksi cepat**: terjemah ID/EN, poles, perbaiki tata bahasa, ringkas, kembangkan, perpendek, formal, poin-poin, lanjutkan menulis, jelaskan
- **Terapkan hasil ke dokumen**: Ganti seleksi · Sisip setelah/sebelum · **Track changes (redline)** · Salin
- **Chat streaming** real-time (SSE)
- **API default**: `https://ai.otomasi.app/v1`, model `VIOLA-CHAT`
- **Custom API**: ganti Base URL / API Key / Model lewat tombol ⚙ (tombol "Muat" mengambil daftar model dari endpoint `/models`)

## Arsitektur

```
src/taskpane.html   — UI panel
src/taskpane.css    — gaya
src/taskpane.js     — logika UI (scope, aksi, apply, settings)
src/wordApi.js      — lapisan Office.js (baca/edit dokumen)
src/aiClient.js     — klien OpenAI-compatible (streaming) via proxy
src/prompts.js      — preset prompt aksi cepat
src/commands.html   — FunctionFile (wajib manifest)
server.js           — server HTTPS statis + PROXY AI (atasi CORS)
manifest.xml        — manifest add-in (port 3443)
assets/             — ikon
referensi/          — 10 repo sumber (git clone)
```

**Catatan CORS**: endpoint `https://ai.otomasi.app/v1` tidak mengirim header CORS, sehingga `fetch` langsung dari taskpane diblokir browser/webview Word. `server.js` menyediakan route `/proxy` (same-origin) yang meneruskan request + streaming SSE ke API. `aiClient.js` otomatis lewat proxy ini. Untuk endpoint custom yang sudah ber-CORS, set `window.VIOLA_DIRECT = true`.

## Cara pakai (sideload di Word Desktop)

1. **Install sertifikat dev** (sekali saja):
   ```bash
   cd wordAddIn
   npx office-addin-dev-certs install
   ```

2. **Jalankan server HTTPS** (port 3443):
   ```bash
   PORT=3443 node server.js
   # -> HTTPS add-in server: https://localhost:3443/src/taskpane.html
   ```

3. **Sideload manifest** ke Word:
   - **Otomatis**: `npx office-addin-debugging start manifest.xml desktop`
   - **Manual (Word di Windows/Mac)**: salin `manifest.xml` ke folder Trusted Catalog / Shared Folder, lalu di Word: **Insert → Add-ins → My Add-ins → Upload My Add-in** → pilih `manifest.xml`.

4. Di Word, tab **Home** → klik **PaperFull Word** → panel terbuka di samping.

5. Seleksi teks di dokumen → pilih scope → klik aksi (mis. "Poles tulisan") → klik **Ganti seleksi** untuk menerapkan.

## Ganti API (custom)

Klik ⚙ di panel:
- **Base URL**: mis. `https://api.openai.com/v1` atau endpoint lokal `http://localhost:11434/v1` (Ollama)
- **API Key**: token Anda
- **Model**: klik **↻ Muat** untuk ambil daftar, atau ketik manual
- **Temperature**: 0–1

Pengaturan tersimpan di `localStorage`. Tombol **Reset default** mengembalikan ke PaperFull API.

## Port

- **3443** — HTTPS, dipakai Word (default manifest).
- Ganti port: edit `manifest.xml` (ganti semua `localhost:3443`) + jalankan `PORT=xxxx node server.js`.
- `FORCE_HTTP=1 PORT=3100 node server.js` — mode HTTP untuk QA di browser biasa (Word tetap butuh HTTPS).

## Verifikasi yang sudah dilakukan

- XML manifest well-formed ✓
- Semua modul JS lolos `node --check` ✓
- 8 endpoint statik HTTPS → 200 ✓
- Proxy `/models` → daftar model nyata ✓
- Proxy chat streaming (SSE) → respons AI terkumpul benar ✓
- UI render penuh + chat end-to-end di browser, 0 JS error ✓

> Catatan: aksi baca/edit dokumen memakai API Office.js standar (`getSelection`, `insertText`, `body.search`, `changeTrackingMode`) yang hanya aktif di dalam Word — tidak bisa diuji di browser biasa.
