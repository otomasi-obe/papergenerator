# Setup Email support@paperfull.app via Cloudflare Email Routing

## Langkah 1: Buka Cloudflare Dashboard
- Login ke https://dash.cloudflare.com
- Pilih domain **paperfull.app**

## Langkah 2: Buka Email Routing
- Di sidebar kiri, klik **Email** → **Email Routing**
- Jika pertama kali, klik **Get started** atau **Enable Email Routing**
- Cloudflare akan otomatis tambah MX record — klik **Enable** / **Add records**

## Langkah 3: Tambah Destination Email
- Buka tab **Destination addresses**
- Klik **Add destination address**
- Isi: `anabilhisyam23@gmail.com`
- Klik **Save**
- Buka Gmail → cari email verifikasi dari Cloudflare → klik link verifikasi
- ⚠️ Cek folder Spam jika tidak muncul di inbox

## Langkah 4: Buat Custom Address
- Kembali ke tab **Email Routing** → **Routes**  (atau **Routing rules**)
- Klik **Create address**
- Custom address: `support`
- Action: **Send to** → pilih `anabilhisyam23@gmail.com`
- Klik **Save**

## Selesai ✅
Email ke `support@paperfull.app` sekarang masuk ke Gmail.

---

## (Opsional) Reply dari Gmail sebagai support@paperfull.app

Supaya reply dari Gmail tampil sebagai `support@paperfull.app`, bukan `anabilhisyam23@gmail.com`:

1. Buka Gmail → **Settings** (⚙️) → **See all settings**
2. Tab **Accounts and Import**
3. Di bagian **Send mail as**, klik **Add another email address**
4. Isi:
   - Name: `Paperfull Support`
   - Email: `support@paperfull.app`
   - ❌ Uncheck "Treat as an alias" (opsional, terserah)
5. Klik **Next Step**
6. SMTP Server: `smtp.gmail.com`
   - Port: `587`
   - Username: `anabilhisyam23@gmail.com`
   - Password: **App Password** (bukan password biasa)
     → Buat di https://myaccount.google.com/apppasswords
   - ✅ TLS
7. Klik **Add Account**
8. Gmail kirim kode verifikasi ke `support@paperfull.app` (yang forward ke Gmail juga) → masukkan kode
9. Selesai — saat reply, pilih **From: support@paperfull.app**

---

## Migrasi ke Email Dosen (Nanti)

Cukup ubah destination di Cloudflare:
1. Email Routing → Routes → edit `support`
2. Ganti destination ke email dosen baru
3. Done — website tidak perlu diubah
