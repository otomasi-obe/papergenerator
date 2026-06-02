# PERINTAH.md — Fix Auth Error & Penerapan Claude Design

## Ringkasan Masalah

1. **Google OAuth `auth_failed`** — Frontend `.env` menggunakan `VITE_API_URL=http://localhost:8001` 
   yang di-embed saat build. Di production (paperfull.app), browser redirect ke `localhost:8001` 
   untuk OAuth → gagal → `auth_failed`.
2. **Session state overwrite** — `google_callback()` menimpa session OAuth state dengan dict kosong,
   menghapus PKCE `code_verifier` yang dibutuhkan authlib.
3. **Error messages tidak informatif** — User hanya melihat "auth_failed" tanpa tahu penyebabnya.
4. **Asset path salah** — LandingPage dan LoginPage menggunakan import image yang tidak ada di produksi.

---

## Perubahan yang Dilakukan

### 1. Frontend `.env` (`frontend/.env`)

```
VITE_API_URL=              ← kosong = relative URL (same-origin)
VITE_API_BASE_URL=/api     ← relative path
VITE_WS_URL=              ← kosong = same-origin WS
```

**Kenapa**: Di production, frontend dan backend di-serve dari domain yang sama (`paperfull.app`) 
melalui nginx. API calls ke `/api/...` di-proxy oleh nginx ke backend port 8001.

### 2. Backend `api/auth_bp.py`

**Fix 1 — `google_login()`**: Tambahkan `session.modified = True` setelah `authorize_redirect()` 
untuk memastikan session cookie dikirim ke browser sebelum redirect ke Google.

**Fix 2 — `google_callback()`**: 
- Hapus baris `session[f"_state_google_{signed_state}"] = {}` yang menimpa PKCE verifier
- Ganti dengan pengecekan: baca existing state data, jika tidak ada → `session_expired`
- Parse `error` dari Google (user bisa deny permission)
- Redirect dengan error code yang spesifik (`google_denied`, `csrf_detected`, `session_expired`)

### 3. Frontend `views/AuthCallbackPage.vue`
- Tambah mapping error code → message yang user-friendly
- Tambah retry mechanism (1 detik delay) untuk `fetchMe()` jika cookie belum siap
- Handle direct access tanpa `code` parameter

### 4. Frontend `views/LoginPage.vue`
- Tambah `errorMessages` map untuk semua error codes baru:
  - `auth_failed` → "Google sign-in failed. Please try again."
  - `google_denied` → "You denied access..."
  - `invalid_state` → "Sign-in session invalid..."
  - `csrf_detected` → "Security check failed..."
  - `session_expired` → "Sign-in session expired..."

### 5. Design Assets

Copy dari `PaperRiset/claudedesign/PaperFull Design System (1)/assets/` ke `frontend/public/assets/`:
- `logo.png` → brand logo kecil
- `logo-with-text.png` → logo dengan teks "PaperFull"
- `landing-page.jpg` → hero image
- `feature-illustration.jpg` → feature section image
- `trust-strip-bg.jpg` → trust strip background
- `favicon-32x32.png` → favicon

### 6. Asset Paths

| Komponen | Lama | Baru |
|----------|------|------|
| `LoginPage.vue` | `../image/logo-with-text.png` | `/assets/logo-with-text.png` |
| `LandingPage.vue` | `../image/landing-page.jpg` | `/assets/landing-page.jpg` |
| `LandingPage.vue` | (trust strip sama) | `/assets/trust-strip-bg.jpg` |
| `LandingPage.vue` | (feature sama) | `/assets/feature-illustration.jpg` |
| `AppHeader.vue` | `/logo.png` | `/assets/logo.png` |

### 7. `style.css` — Token tambahan

Ditambahkan:
- `.bg-sunken`, `.bg-panel`, `.text-on-navy`
- `.btn-primary` dengan dark mode support
- `.card` utility class

---

## Cara Deploy

### Build Frontend Ulang (WAJIB — karena .env berubah)

```bash
cd /home/sirobo/papergenerator/frontend
npm run build
```

### Restart Semua Service

```bash
cd /home/sirobo/papergenerator
pm2 delete paper-frontend paper-backend-flask 2>/dev/null
```

Option A — via server.sh:
```bash
bash server.sh start
```

Option B — manual:
```bash
# Backend
cd /home/sirobo/papergenerator/backend
pm2 start python3 --name "paper-backend-flask" --interpreter none -- app.py

# Frontend
cd /home/sirobo/papergenerator/frontend
npm run build
pm2 start npm --name "paper-frontend" -- run preview -- --port 8000 --host 0.0.0.0
```

### Verifikasi

1. Buka `https://paperfull.app/login`
2. Klik "Continue with Google"
3. OAuth flow harus redirect ke Google, lalu kembali ke `/auth/catch`
4. Jika sukses → redirect ke `/dashboard`
5. Jika gagal → tampil error message yang spesifik

### Debug OAuth

Jika masih error, cek PM2 logs:
```bash
pm2 logs paper-backend-flask --lines 50
```

Cari log entries:
- `OAuth login - Generated signed state` → login dimulai
- `OAuth callback - State signature verified OK` → CSRF valid
- `OAuth callback - No state data in session` → session cookie tidak tersimpan
- `OAuth success - redirecting to` → berhasil

---

## nginx Config (pastikan sudah benar)

```nginx
server {
    listen 443 ssl;
    server_name paperfull.app;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }
}
```

---

## Session Cookie Requirements (untuk OAuth bekerja)

Cookie settings di `backend/app.py`:
- `SESSION_COOKIE_SECURE=true` → cookie hanya via HTTPS
- `SESSION_COOKIE_HTTPONLY=true` → tidak bisa dibaca JS (XSS-safe)
- `SESSION_COOKIE_SAMESite=None` → cookie bisa dikirim cross-site (Google redirect)
- `SESSION_COOKIE_DOMAIN=.paperfull.app` → cookie tersedia di subdomain

**Browser requirement**: Modern browser harus mendukung SameSite=None + Secure. 
Browser lama mungkin blok cookie ini.
