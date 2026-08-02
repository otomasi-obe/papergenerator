# PaperFull — Preserve User Draft Verbatim di "Generate Full"

## Konteks Masalah

Di fitur "Generate Full", slot upload sebelumnya berjudul **"Data"** dengan deskripsi untuk data mentah. Namun user juga mengunggah draft paper mereka sendiri, misalnya DOCX/PDF berisi section akademik yang sudah ditulis manusia.

Risikonya: teks draft masuk sebagai `## DATA SUMBER`, lalu model dapat menulis ulang seluruh paper. Ini mengubah teks human-written dan mengalahkan tujuan user untuk hanya melengkapi bagian kosong.

Prinsip implementasi:

> Draft user adalah ground truth. Setiap section draft yang terdeteksi harus tersimpan verbatim (karakter-per-karakter) dalam paper akhir. AI hanya menghasilkan bagian yang tidak tersedia pada draft.

## Implementasi — 2026-08-02

### 1. UI slot upload

File: `frontend/src/components/PaperfullTab.vue`

- Label diubah dari `Data` menjadi `Data/Draft`.
- Deskripsi sekarang membedakan:
  - data mentah (`csv`, `xlsx`, `pdf`) untuk tabel dan grafik;
  - draft paper (`docx`, `pdf`) yang teksnya dipertahankan apa adanya.

### 2. Klasifikasi deterministic sebelum prompt

File baru: `backend/tools/paperfull/draft_preservation.py`

Upload pada bucket `data_files` diklasifikasikan deterministik menjadi:

- `raw_data`
  - format `csv`, `xls`, `xlsx`, `tsv` selalu data;
  - atau konten numerik/tabel-dominan;
- `narrative_draft`
  - memiliki minimal dua heading akademik yang dikenal dan sinyal naratif;
  - heading Indonesia/Inggris yang didukung: Abstract/Abstrak, Introduction/Pendahuluan, Literature Review/Tinjauan Pustaka, Methodology/Metode, Results/Hasil, Discussion/Pembahasan, Conclusion/Kesimpulan;
- `reference_context`
  - jika tidak cukup bukti untuk menyebutnya data atau draft.

Draft naratif dipindahkan keluar dari `data_texts`, sehingga tidak lagi diinjeksi sebagai `## DATA SUMBER` atau dipakai sebagai sumber angka/tabel/grafik.

### 3. Prompt verbatim lock

Files:

- `backend/tools/paperfull/jobs.py`
- `backend/tools/paperfull/prompt/prompt.txt`

Setiap section dari draft diberi blok `## USER DRAFT — PROTECTED VERBATIM TEXT`, berisi title, isi asli, dan SHA-256. Prompt melarang model melakukan parafrase, terjemahan, grammar correction, humanization, perubahan tanda baca, atau reordering paragraf.

Instruksi prompt hanya guidance. Jaminan utama berada pada overlay deterministic berikutnya.

### 4. Programmatic verbatim overlay dan fail-closed gate

Setelah respons AI dinormalisasi dan post-processing/humanizer selesai:

1. Sistem mencari section output yang ekuivalen dengan section draft.
2. Isi output section diganti dengan teks asli draft yang di-extract.
3. SHA-256 dan equality exact diperiksa lagi.
4. Audit disimpan pada `paper.data._draft_preservation`.
5. Jika section protected tidak ditemukan atau hasil tidak exact, job mengirim SSE error dan tidak menyimpan paper hasil.

Urutan overlay yang sengaja dipakai setelah humanizer memastikan prose-quality postprocessor tidak dapat mengubah tulisan user.

Untuk section yang mengandung placeholder eksplisit (`[TODO]`, `[LENGKAPI]`, `[FILL HERE]`, atau `...`), versi ini masih mengunci seluruh section secara aman. Ini lebih ketat daripada requirement sementara editor span-aware belum tersedia: tidak ada teks user yang akan disentuh.

## Bukti Verifikasi

### Automated tests

File: `backend/tests/test_draft_preservation.py`

Perintah:

```bash
cd /home/sirobo/papergenerator/backend
.venv/bin/python -m pytest -q tests/test_draft_preservation.py -v
```

Hasil nyata:

```text
10 passed in 0.66s
```

Cakupan test:

- parsing marker source extracted;
- CSV menjadi `raw_data`;
- DOCX naratif dengan heading menjadi `narrative_draft`;
- reference ambigu menjadi `reference_context`;
- parsing section Indonesia/Inggris;
- pemisahan manifest data vs draft;
- overlay exact;
- AI output yang berbeda diganti dengan konten draft exact;
- case tanpa draft;
- prompt protection block.

### Static / build / runtime

- `py_compile tools/paperfull/jobs.py tools/paperfull/draft_preservation.py`: PASS.
- `npm run build` frontend: PASS, selesai dalam 15.56 detik.
- `paper-backend-flask` dan `paper-worker` direstart secara spesifik.
- `GET http://127.0.0.1:8001/api/health`: `{"service":"papergenerator","status":"healthy", ...}`.

## Batasan yang Sengaja Dipertahankan

- Tidak ada perubahan pada payment, auth, atau fitur generate selain jalur `Generate Full`.
- Tidak ada commit dibuat karena working tree sudah mengandung WIP dari area lain.
- E2E dengan provider AI live tidak dijalankan terhadap paper user yang ada agar tidak menimpa dokumen/progres pengguna. Tes overlay menjalankan pipeline preservation secara deterministic dan membuktikan output AI yang berbeda dikembalikan ke teks draft exact.

## Acceptance Criteria Status

| Kriteria | Status |
|---|---|
| Label slot menjadi Data/Draft | PASS |
| Draft tidak diperlakukan sebagai data eksperimen | PASS |
| Draft dipisahkan dari raw data sebelum prompt | PASS |
| Instruksi verbatim pada prompt | PASS |
| Section draft di-overlay exact setelah AI/humanizer | PASS |
| Mismatch/unmatched fail closed sebelum persistence | PASS |
| Diff exact 0 perubahan untuk preserved section | PASS via automated deterministic overlay test |
| Frontend build/backend health | PASS |

## File yang Diubah/Ditambah

```text
frontend/src/components/PaperfullTab.vue
backend/tools/paperfull/jobs.py
backend/tools/paperfull/prompt/prompt.txt
backend/tools/paperfull/draft_preservation.py
backend/tests/test_draft_preservation.py
Root Cause MD/paperfull-preserve-draft-verbatim.md
```

## Manual Live E2E yang Direkomendasikan

Untuk menguji provider AI tanpa menyentuh draft user asli:

1. Buat paper test kosong.
2. Upload DOCX berisi Abstract, Introduction, dan Methodology yang berisi marker unik/whitespace disengaja.
3. Jalankan Generate Full dengan image generation dimatikan.
4. Setelah selesai, inspect `paper.data._draft_preservation`:
   - `status: verified`;
   - `mismatches: 0`;
   - seluruh protected section memiliki hash expected/actual sama.
5. Bandingkan text section akhir dengan source extracted; hasil wajib byte-for-byte sama.

Jika `status` bukan `verified`, backend harus menolak persistence hasil Generate Full.
