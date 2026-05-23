# Paper Builder Workflow — Connected Sessions Framework v2.0

---

## Overview

Framework 9 sesi berurutan. Setiap sesi memberikan **4 opsi rekomendasi AI** berdasarkan jawaban sesi sebelumnya, **+1 isian bebas user**. Struktur ini memastikan setiap keputusan terinformasi oleh keputusan sebelumnya, dan setiap sesi bisa di-_backward-adjust_ jika ditemukan inkonsistensi.

**Struktur setiap pertanyaan:**

```
[A] Opsi Rekomendasi 1   [B] Opsi Rekomendasi 2
[C] Opsi Rekomendasi 3   [D] Opsi Rekomendasi 4
[E] Isian bebas user
```

---

## Fase 0: Pre-Questionnaire — Status Awal

> *Onboarding cepat. Menentukan entry point & progress yang sudah ada.*

### Pertanyaan

| #   | Pertanyaan                         | Rekomendasi Berdasarkan | 4 Opsi AI + 1 User                                                                                                                       | Tujuan & Koneksi                                                              |
| --- | ---------------------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 0.1 | Sejauh mana progress paper Anda?   | —                      | [A] Masih ide/konsep / [B] Sudah ada judul & outline / [C] Sudah ada draft sebagian / [D] Draft hampir selesai / [E] Ceritakan detailnya | Menentukan starting point: apakah AI mulai dari 0, atau refine draft yang ada |
| 0.2 | Sudah punya data/hasil eksperimen? | `0.1`                 | [A] Belum ada / [B] Ada data mentah / [C] Ada hasil olahan / [D] Hasil final sudah siap / [E] Upload file                                | Menentukan apakah Sesi 6 (Data & Viz) aktif penuh, ringan, atau skip          |
| 0.3 | Ini paper individu atau tim?       | —                      | [A] Individu (tugas akhir) / [B] Tim 2-3 orang / [C] Tim 4-5 orang / [D] Kolaborasi lintas institusi / [E] Ceritakan detail              | Menentukan kebutuhan author contribution statement di Sesi 8                  |

**Output:** `StatusAwal` = {progress_level, data_readiness, team_size}
**Koneksi:** → `StatusAwal` digunakan untuk **menyesuaikan bobot & urgensi** di setiap sesi berikutnya.

---

## Fase 1: Profil Dasar Paper

> *Menentukan identitas dasar paper.*

| #   | Pertanyaan                      | Rekomendasi Berdasarkan     | 4 Opsi AI + 1 User                                                                                                                              | Tujuan & Koneksi                                                                                     |
| --- | ------------------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| 1.1 | Bidang ilmu?                    | —                          | [A] Ilmu Komputer & IT / [B] Teknik & Rekayasa / [C] Kedokteran & Kesehatan / [D] Sosial & Humaniora / [E] Bidang lain                          | **Root dari semua rekomendasi** — menentukan terminologi, format sitasi, standar penulisan    |
| 1.2 | Jenis paper?                    | `1.1`                     | [A] Literature Review*/* [B] Research Paper / [C] Case Study / [D] Systematic Review / [E] Jenis lain (Thesis chapter, Technical Report, dll) | Menentukan template struktur & semua conditional branching                                           |
| 1.3 | Target publikasi?               | `1.1` + `1.2`           | [A] Tugas Akhir / Skripsi / Tesis / [B] Jurnal Sinta 2-6 / [C] Jurnal Sinta 1 / [D] Jurnal Scopus / [E] Konferensi internasional                | Menentukan panjang, gaya bahasa, template, jumlah referensi, dan**estimasi timeline + budget** |
| 1.4 | Judul paper (bisa provisional)? | `1.1` + `1.2` + `1.3` | AI generate 4 judul provisional sesuai bidang + jenis + target                                                                                  | Identitas paper; akan direfin di Sesi 2 setelah topik konkret                                        |

**Output:** `Profil` = {bidang, jenis, target_publikasi, judul_provisional}

---

## Fase 2: Topik & Research Gap

> *Menggali fokus riset secara mendalam.*

| #   | Pertanyaan                              | Rekomendasi Berdasarkan | 4 Opsi AI + 1 User                                                                         | Tujuan & Koneksi              |
| --- | --------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------ | ----------------------------- |
| 2.1 | Topik spesifik?                         | `1.1` + `1.4`       | AI generate 4 topik yang sedang tren di bidang tsb (dengan konteks dari judul provisional) | Fokus utama                   |
| 2.2 | Problem statement?                      | `2.1`                 | AI susun 4 problem statement berdasarkan topik                                             | Latar belakang                |
| 2.3 | Research gap — apa yang belum dijawab? | `2.1` + `2.2`       | 4 celah riset yang belum terjawab + rekomendasi literatur penguat                          | Novelty / kontribusi          |
| 2.4 | Research question(s)?                   | `2.2` + `2.3`       | 4 RQ yang logis dan terukur                                                                | Struktur pembahasan           |
| 2.5 | Tujuan penelitian?                      | `2.3` + `2.4`       | 4 rumusan tujuan yang alignment dengan RQ                                                  | Alignment metode & kesimpulan |
| 2.6 | Keywords?                               | `2.1` + `2.4`       | AI generate 4 set keywords (masing-masing 4-6 kata kunci) yang optimal untuk SEO jurnal    | Discoverability               |

**Output:** `RisetCore` = {topik, problem, gap, RQs, tujuan, keywords}
**Koneksi:** → Fase 3 (metode ditentukan oleh topik & RQ); Fase 5 (referensi berdasarkan gap & keywords)

---

## Fase 3: Metodologi & Data

> *Menentukan pendekatan dan teknis penelitian.*

| #   | Pertanyaan               | Rekomendasi Berdasarkan     | 4 Opsi AI + 1 User                                                                                                                        | Tujuan & Koneksi                                                                                                 |
| --- | ------------------------ | --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| 3.1 | Pendekatan penelitian?   | `1.1` + `1.2` + `2.4` | [A] Kuantitatif / [B] Kualitatif / [C] Mixed-Method / [D] R&D (Research & Development) / [E] Pendekatan lain                              | **Gatekeeper** — menentukan cabang Sesi 6 (Kuantitatif → statistik, Kualitatif → tematik, LR → PRISMA) |
| 3.2 | Metode spesifik?         | `3.1` + `2.1`           | AI rekomendasikan 4 metode spesifik. Contoh: CS+ML → SVM/BERT/LSTM/RF. Sosial+Etnografi → Observasi/Wawancara/FGD/Etnodigital           | Detail teknis;**akan divalidasi konsistensinya dengan RQ di Fase 9**                                       |
| 3.3 | Sumber data?             | `3.1` + `3.2`           | 4 sumber data yang sesuai. Contoh: Survei/Data publik/Eksperimen/Studi literatur                                                          | Validitas                                                                                                        |
| 3.4 | Jumlah sampel / dataset? | `3.1` + `3.2` + `1.1` | 4 rekomendasi rentang sampel sesuai standar bidang. Contoh: CS → 500-1000 instance, Sosial → 100-200 responden, Medis → power analysis | Statistik deskriptif                                                                                             |
| 3.5 | Tools?                   | `3.2` + `1.1`           | 4 tools populer di bidang: Python/SPSS/Matlab/NVivo/ATLAS.ti/R/STATA                                                                      | Reproducibility                                                                                                  |
| 3.6 | Etika penelitian?        | `3.1` + `3.3` + `1.1` | [A] Tidak perlu etik / [B] Butuh ethical clearance (institusi) / [C] Butuh informed consent / [D] Butuh keduanya / [E] Ceritakan detail   | —Muncul jika— subjeknya manusia/hewan.**Krusial untuk publikasi**                                        |

**Output:** `Metodologi` = {pendekatan, metode, sumber_data, sampel, tools, etika}

---

## Fase 4: Struktur & Konten Paper

> *Menentukan kerangka dan kedalaman konten.*

| #   | Pertanyaan                      | Rekomendasi Berdasarkan     | 4 Opsi AI + 1 User                                                                                                                                                    | Tujuan & Koneksi                                            |
| --- | ------------------------------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| 4.1 | Template struktur utama?        | `1.2` + `1.3`           | [A] IMRAD (Research Paper) / [B] IRD (Intro-Review-Discussion — untuk Literature Review) / [C] Swales (untuk Case Study) / [D] Struktur Thesis / [E] Struktur kustom | Template outline otomatis                                   |
| 4.2 | Kompleksitas konten?            | `1.3` + `3.1`           | [A] Dasar (Tugas Akhir/Sinta 4-6) / [B] Menengah (Sinta 1-3) / [C] Tinggi (Scopus Q3-Q4) / [D] Sangat Tinggi (Scopus Q1-Q2)                                           | Menentukan seberapa dalam setiap bab                        |
| 4.3 | Jumlah bab/section target?      | `4.1` + `1.2`           | 4 rekomendasi jumlah. Contoh: IMRAD → 5-7 bab, Thesis → 6-8                                                                                                         | Scope                                                       |
| 4.4 | Bab mana yang perlu diperdalam? | `2.3` + `2.4` + `3.2` | Prioritas bab yang membutuhkan elaborasi ekstra (berdasarkan gap & metode)                                                                                            | Alokasi effort                                              |
| 4.5 | Outline detail?                 | `4.1` + `4.2` + `4.3` | AI generate outline per-bab lengkap dengan poin-poin konten                                                                                                           | **Output utama** — langsung bisa dipakai mulai nulis |

**Output:** `Struktur` = {template, kompleksitas, jumlah_bab, prioritas, outline}
**Koneksi:** → Fase 5 (jumlah referensi disesuaikan dengan jumlah bab & kompleksitas)

---

## Fase 5: Literatur & Sitasi

> *Membangun fondasi referensi.*

| #   | Pertanyaan                      | Rekomendasi Berdasarkan | 4 Opsi AI + 1 User                                                                                                             | Tujuan & Koneksi                |
| --- | ------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------- |
| 5.1 | Gaya sitasi?                    | `1.1`                 | [A] APA 7th (Sosial, Psikologi) / [B] IEEE (Teknik, CS) / [C] Vancouver (Kedokteran) / [D] Chicago (Humaniora) / [E] Gaya lain | Format daftar pustaka           |
| 5.2 | Jumlah referensi target?        | `1.3` + `4.2`       | 4 rentang: [A] 15-25 / [B] 25-40 / [C] 40-60 / [D] 60-80+                                                                      | Scope literatur                 |
| 5.3 | Key papers yang wajib disitasi? | `2.1` + `2.3`       | AI rekomendasikan 4 penulis/paper penting yang harus dikutip (berdasarkan standingilitas di bidang)                            | Literature review yang kredibel |
| 5.4 | Rentang tahun referensi?        | `1.1` + `2.1`       | 4 rekomendasi: [A] 5 tahun terakhir (CS, Teknik) / [B] 10 tahun / [C] Classic + terbaru / [D] Semua tahun relevan              | Relevansi                       |
| 5.5 | Tool manajemen referensi?       | —                      | [A] Mendeley / [B] Zotero / [C] EndNote / [D] PaperPile / [E] Lainnya                                                          | Produktivitas                   |

**Output:** `Referensi` = {gaya_sitasi, jumlah, key_papers, rentang_tahun, tool}
**Koneksi:** → Fase 9 (validasi — apakah referensi cukup untuk menjawab gap?)

---

## Fase 6: Data & Visualisasi

> *Conditional session — muncul dengan konten berbeda tergantung `3.1` Pendekatan.*

### Cabang A: Kuantitatif / Mixed-Method

| #   | Pertanyaan                    | Rekomendasi Berdasarkan | 4 Opsi AI + 1 User                                                                       |
| --- | ----------------------------- | ----------------------- | ---------------------------------------------------------------------------------------- |
| 6.1 | Jenis visualisasi utama?      | `3.2` + `3.4`       | Tabel statistik / Grafik batang-garis / Heatmap-confusion matrix / Scatter-plot box-plot |
| 6.2 | Jumlah tabel & figuur target? | `4.2`                 | [A] 3-5 total / [B] 5-8 / [C] 8-12 / [D] >12                                             |
| 6.3 | Format data mentah?           | —                      | CSV / Excel / JSON / Database                                                            |
| 6.4 | Platform visualisasi?         | `3.5`                 | matplotlib/Seaborn/Tableau/SPSS/R ggplot                                                 |

### Cabang B: Kualitatif

| #   | Pertanyaan                    | Rekomendasi Berdasarkan | 4 Opsi AI + 1 User                                               |
| --- | ----------------------------- | ----------------------- | ---------------------------------------------------------------- |
| 6.1 | Jenis visualisasi utama?      | `3.2` + `3.3`       | Thematic map / Network diagram / Quote matrix / Timeline chart   |
| 6.2 | Jumlah tabel & figuur target? | `4.2`                 | [A] 2-4 / [B] 4-6 / [C] 6-8 / [D] >8                             |
| 6.3 | Coding framework?             | `3.2`                 | Deductive coding / Inductive coding / Hybrid / Template analysis |
| 6.4 | Platform analisis?            | `3.5`                 | NVivo / ATLAS.ti / MAXQDA / Dedoose                              |

### Cabang C: Literature Review / Systematic Review

| #   | Pertanyaan                    | Rekomendasi Berdasarkan | 4 Opsi AI + 1 User                                                   |
| --- | ----------------------------- | ----------------------- | -------------------------------------------------------------------- |
| 6.1 | Jenis visualisasi utama?      | `1.2` + `2.3`       | PRISMA flowchart / Bibliometric map / Synthesis matrix / Concept map |
| 6.2 | Jumlah tabel & figuur target? | `4.2`                 | [A] 3-5 / [B] 5-8 / [C] 8-10 / [D] >10                               |
| 6.3 | Screening strategy?           | `2.1`                 | PRISMA 2020 / SWiM / ENTREQ / Mixed-method                           |
| 6.4 | Tool review?                  | —                      | Covidence / Rayyan / VosViewer / ASReview                            |

**Output:** `Visualisasi` = {jenis_viz, jumlah, platform/cabang_khusus}

---

## Fase 7: Output & Preferensi Penulisan

> *Menyesuaikan gaya dan bahasa output.*

| #   | Pertanyaan                            | Rekomendasi Berdasarkan | 4 Opsi AI + 1 User                                                                                                                                                                                      | Tujuan & Koneksi                |
| --- | ------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| 7.1 | Bahasa?                               | `1.3`                 | [A] Indonesia / [B] Inggris / [C] Inggris (American) / [D] Bilingual (untuk tesis) / [E] Bahasa lain                                                                                                    | Medium output                   |
| 7.2 | Tone / gaya penulisan?                | `1.3` + `1.2`       | [A] Formal akademik baku / [B] Semi-formal (untuk tugas akhir) / [C] Kritis-argumentatif (untuk review paper) / [D] Deskriptif-ekspositori / [E] Sesuai panduan jurnal spesifik                         | Voice consistency               |
| 7.3 | Spesifikasi gaya tambahan?            | `1.3`                 | [A] Pasif voice (scientific standard) / [B] Aktif diperbolehkan / [C] First-person allowed / [D] Impersonal (tidak pakai "kami/saya") / [E] Lainnya                                                     | Detail yang sering dilupakan    |
| 7.4 | Prioritas?                            | —                      | [A] Kecepatan (draft cepat, direfine kemudian) / [B] Kualitas (setiap bab ditulis rapi dari awal) / [C] Originalitas tinggi (minim bantuan AI, lebih sebagai co-writer) / [D] Keseimbangan / [E] Kustom | Trade-off dalam generasi konten |
| 7.5 | Butuh parafrase/plagiarisme checking? | `7.4`                 | [A] Ya, otomatis / [B] Tidak, saya cek manual / [C] Nanti di tahap final / [D] Tidak perlu                                                                                                              | Tool tambahan                   |

**Output:** `PreferensiOutput` = {bahasa, tone, spesifikasi, prioritas, anti_plagiarism}

---

## Fase 8: Supplementary & Production Readiness

> *NEW — Hal-hal yang sering terlambat disiapkan.*

| #   | Pertanyaan                               | Rekomendasi Berdasarkan | 4 Opsi AI + 1 User                                                                                                                                                               | Tujuan & Koneksi                         |
| --- | ---------------------------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| 8.1 | Tim penulis & kontribusi?                | `0.3`                 | [A] Single author / [B] Daftar kontribusi CRediT taxonomy / [C] Equal contribution / [D] First & corresponding author ditentukan / [E] Kustom                                    | Author contribution statement            |
| 8.2 | Supplementary statements?                | `1.3`                 | [A] Conflict of Interest / [B] Data Availability / [C] Funding statement / [D] Acknowledgement + Institutional Affiliations / [E] Semuanya                                       | **Syarat wajib** jurnal bereputasi |
| 8.3 | Apakah ada biaya yang perlu dianggarkan? | `1.3` + `8.2`       | AI infokan estimasi: [A] APC journal ([range harga]) / [B] Biaya proofreading /editing / [C] Biaya terjemahan / [D] Biaya pendaftaran konferensi / [E] Tidak ada anggaran khusus | Feasibility                              |
| 8.4 | Timeline & milestone?                    | `0.1` + `4.2`       | AI buatkan 4 skenario timeline: [A] 1 minggu (sprint) / [B] 2-4 minggu / [C] 1-3 bulan / [D] >3 bulan                                                                            | Manajemen waktu                          |
| 8.5 | Siapa reviewer internal?                 | —                      | [A] Dosen pembimbing / [B] Rekan sejawat / [C] Proofreader profesional / [D] Tidak ada (self-review) / [E] Lainnya                                                               | Quality gate                             |
| 8.6 | Format pengiriman akhir?                 | `1.3`                 | [A] PDF / [B] DOCX (template jurnal) / [C] LaTeX / [D] Markdown+export / [E] Format lain                                                                                         | Deliverable                              |

**Output:** `Produksi` = {authors, statements, budget, timeline, reviewer, format_lampiran}

---

## Fase 9: Validasi & Finalisasi

> *NEW — Cross-check menyeluruh & backward adjustment.*

### 9.1 Validasi Konsistensi Otomatis

AI memeriksa kontradiksi antar-jawaban:

| Pengecekan               | Detail                                                                                                                     |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| RQ vs Metode             | Apakah RQ bisa dijawab oleh metode yang dipilih? Contoh: RQ "Seberapa besar pengaruh X?" tapi metode Kualitatif → Warning |
| Sampel vs Metode         | Apakah jumlah sampel memadai untuk metode tsb? Contoh: SVM dengan 20 sampel → Warning                                     |
| Sitasi vs Target         | Apakah jumlah referensi sesuai standar target publikasi?                                                                   |
| Tone vs Target           | Apakah tone sesuai dengan ekspektasi jurnal?                                                                               |
| Etika vs Subjek          | Apakah etika clearance sudah diurus jika melibatkan manusia/hewan?                                                         |
| Anggaran vs Target       | Apakah budget realistis (terutama APC)?                                                                                    |
| Timeline vs Kompleksitas | Apakah timeline cukup untuk tingkat kompleksitas yang dipilih?                                                             |

### 9.2 Backward Adjustment

> Setiap sesi bisa di-revisit. Jika ada warning, user bisa memilih:

- [A] **Accept warning & lanjut** (dengan catatan)
- [B] **Backward adjust ke sesi terkait** (AI arahkan ke sesi spesifik)
- [C] **Minta AI refine rekomendasi** (dengan konteks tambahan dari user)
- [D] **Override paksa** (user yakin dengan pilihannya)

### 9.3 Ringkasan Eksekutif

> AI generate ringkasan 1 halaman dari seluruh jawaban:

- Judul final & keywords
- Tujuan & RQ
- Metode & data
- Struktur (outline)
- Timeline & milestone
- Checklist final: [profil] [topik] [metode] [struktur] [referensi] [visualisasi] [output] [produksi]

**Output:** `FinalPackage` = {validation_report, adjustments, executive_summary, checklist}

---

## Diagram Alur Lengkap

```
Fase 0: Status Awal ───→ menentukan entry point
     │
     ↓
Fase 1: Profil Dasar ───→ bidang, jenis, target, judul
     │
     ↓
Fase 2: Topik & Gap ───→ topik, problem, gap, RQ, tujuan, keywords
     │
     ↓
Fase 3: Metodologi ───→ pendekatan, metode, data, etika
     │
     ├──────────────────────────┐
     ↓                          ↓ (cabang)
Fase 4: Struktur          ╔══════╗
     │                    ║ Sesi 6 ║ (conditional)
     ↓                    ╚══════╝
Fase 5: Referensi              │
     │                          │
     ├──────────────────────────┘
     ↓
Fase 7: Output & Preferensi
     │
     ↓
Fase 8: Supplementary & Production
     │
     ↓
Fase 9: Validasi & Finalisasi
     │
     ├──→ Warning? → Backward adjust ke fase terkait
     └──→ Clear → Executive Summary + Checklist
```

### Aturan Koneksi & Aliran Data

| Fase              | Input dari Fase  | Memberi Input ke Fase          |
| ----------------- | ---------------- | ------------------------------ |
| 0 — Status Awal  | —               | 3, 8 (timeline)                |
| 1 — Profil Dasar | 0                | 2, 3, 4, 5, 6 (cabang)         |
| 2 — Topik & Gap  | 1                | 3, 4, 5, 6                     |
| 3 — Metodologi   | 1, 2             | 4, 6 (cabang: pilih jenis viz) |
| 4 — Struktur     | 1, 2, 3          | 5, 8 (timeline)                |
| 5 — Referensi    | 1, 2, 4          | 9 (validasi)                   |
| 6 — Visualisasi  | 1, 2, 3 (cabang) | 9 (validasi)                   |
| 7 — Output       | 1, 2             | 9 (finalisasi)                 |
| 8 — Production   | 0, 4, 7          | 9 (finalisasi)                 |
| 9 — Validasi     | 2, 3, 5, 6, 7, 8 | —                             |

---

## Evaluasi Kelengkapan: Apakah Ini Sudah Cukup?

### Checklist Gap Analysis

| Aspek                           | Status di v1           | Status di v2                                                    | Catatan                                    |
| ------------------------------- | ---------------------- | --------------------------------------------------------------- | ------------------------------------------ |
| **Profil dasar**          | ✅                     | ✅                                                              |                                            |
| **Topik & gap**           | ✅                     | ✅                                                              | +Keywords                                  |
| **Metodologi**            | ✅                     | ✅                                                              | +Etika                                     |
| **Struktur & template**   | ✅                     | ✅                                                              |                                            |
| **Referensi & sitasi**    | ✅                     | ✅                                                              |                                            |
| **Data & visualisasi**    | ⚠️ Hanya kuantitatif | ✅ 3 cabang (Kuant/Kual/LR)                                     |                                            |
| **Output preferensi**     | ✅                     | ✅                                                              | +Spesifikasi gaya (pasif/aktif/impersonal) |
| **Supplementary**         | ❌                     | ✅ Baru: author, statements, budget, timeline, reviewer, format |                                            |
| **Validasi konsistensi**  | ❌                     | ✅ Baru: cross-check RQ↔Metode, sampel, anggaran, dll          |                                            |
| **Backward adjustment**   | ❌                     | ✅ Baru: loop correction                                        |                                            |
| **Ringkasan eksekutif**   | ❌                     | ✅ Baru: 1-pager beserta checklist                              |                                            |
| **Pre-questionnaire**     | ❌                     | ✅ Baru: status awal & progress                                 |                                            |
| **Conditional branching** | ⚠️ Parsial           | ✅ Setiap Fase 6 punya 3 cabang berbeda                         |                                            |
| **Dependency mapping**    | ❌                     | ✅ Tabel input-output antar fase                                |                                            |

### ✅ v2 dinilai **LENGKAP** untuk cakupan paper akademik tingkat Tugas Akhir hingga Scopus Q1.

---

## Rekomendasi Pengembangan ke Depan (Optional — Jika Ingin Ditambahkan)

| Fitur                                       | Deskripsi                                                                                                                        | Prioritas |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | --------- |
| **Rekomendasi berbasis AI eksternal** | Setelah Fase 5, AI bisa melakukan pencarian literatur nyata via web scraping untuk merekomendasikan paper aktual (bukan generik) | ⭐⭐⭐    |
| **Plagiarism check integration**      | API ke Turnitin/iThenticate untuk cross-check per-bab                                                                            | ⭐⭐      |
| **Multi-language abstract**           | Generate abstrak otomatis dalam 2 bahasa setelah semua sesi selesai                                                              | ⭐⭐      |
| **Export template langsung**          | Output langsung dalam format .docx atau .tex sesuai template jurnal                                                              | ⭐⭐⭐    |
| **Progress tracker**                  | Setelah Fase 9, user bisa track progress penulisan per-bab dengan status [Belum/Proses/Selesai/Review]                           | ⭐⭐      |
| **AI Co-writer mode**                 | Per-bab, AI bantu menulis berdasarkan outline dari Fase 4 — user bisa edit iteratively                                          | ⭐⭐⭐    |
| **Review simulator**                  | AI mensimulasikan peer review — memberikan review fiktif berdasarkan standar jurnal target                                      | ⭐        |
| **Cost calculator**                   | Kalkulasi estimasi total biaya publikasi (APC + editing +翻译) berdasarkan target jurnal                                         | ⭐⭐      |
