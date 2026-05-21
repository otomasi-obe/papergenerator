# Laporan Integrasi Lanjutan — SLR + Literatur Paper Generator

Tanggal: 2026-05-21  
Project: `/home/sirobo/papergenerator`  
Scope: Integrasi sistem pencarian SLR, ranking paper, AI summarization, Tab Literatur, chat trigger, dan penggunaan data literatur untuk generate paper.

---

## 1. Tujuan Integrasi

Integrasi ini bertujuan menambahkan sistem **Systematic Literature Review (SLR)** ke backend dan frontend Paper Generator.

Target utama:

1. Mencari paper dari banyak API akademik.
2. Menggunakan sistem antrian karena pencarian SLR lama.
3. Membatasi worker maksimal 10.
4. Mendukung IEEE.
5. Mendukung SINTA/Garuda dari `/home/sirobo/sinta-scraping`.
6. Melakukan ranking otomatis.
7. Mengambil 50 paper terbaik.
8. Meringkas 50 paper terbaik dengan AI `V-OPUS`.
9. Menyimpan hasil ke Tab Literatur.
10. Literatur bisa dibaca dari file PDF/DOCX.
11. Literatur bisa ditambah, diedit, dihapus.
12. Data literatur dipakai sebagai sumber saat generate full paper.

---

## 2. Status Implementasi Saat Ini

| Area | Status |
|---|---|
| Fetcher IEEE | Selesai |
| Fetcher SINTA/Garuda | Selesai |
| Topic-aware source routing | Selesai |
| Ranking paper | Selesai |
| AI summarizer V-OPUS | Selesai |
| Job queue SLR max 10 worker | Selesai |
| REST endpoint SLR job | Selesai |
| REST endpoint Literature CRUD | Selesai |
| DB model `SlrJob` | Selesai |
| DB model `LiteratureItem` | Selesai |
| Alembic migration | Selesai |
| Chat tool `RunSLR` | Selesai |
| Chat tool `GetLiterature` | Selesai |
| Literature injected to full-paper prompt | Selesai |
| Frontend Tab Literatur | Selesai |
| Frontend polling SLR job | Selesai |
| Frontend table edit/delete/add | Selesai |
| Build frontend | Passed |
| Backend import smoke test | Passed |

---

## 3. File yang Ditambahkan / Diubah

### 3.1 Backend — SLR Core

#### `backend/SLR/fetchers/__init__.py`

Perubahan:

- Registry fetcher diperbaiki.
- Import lama yang rusak diganti.
- Source baru ditambahkan:
  - `ieee`
  - `sinta`
- Ditambahkan `SOURCE_TOPICS` untuk pemetaan topic ke API.

Source saat ini:

```python
ALL = {
    "openalex": openalex,
    "crossref": crossref,
    "semantic_scholar": semantic_scholar,
    "arxiv": arxiv,
    "dblp": dblp,
    "europepmc": europepmc,
    "ieee": ieee,
    "sinta": sinta,
}
backend/SLR/fetchers/ieee.py
Status: baru.

Fungsi:

Fetch paper dari IEEE Xplore Metadata API.
Butuh env:

IEEE_API_KEY=...
Jika IEEE_API_KEY kosong:

Fetcher skip diam-diam.
Pipeline tetap lanjut dengan source lain.
Endpoint IEEE:


https://ieeexploreapi.ieee.org/api/v1/search/articles
Metadata yang diambil:

title
authors
year
venue
DOI
URL
citations
abstract
open access flag
publication type
publisher
backend/SLR/fetchers/sinta.py
Status: baru.

Fungsi:

Integrasi SINTA/Garuda.
Membaca offline data dari:

/home/sirobo/sinta-scraping/papers.jsonl
Default env:


SINTA_OFFLINE_DIR=/home/sirobo/sinta-scraping
Strategi:

Cari dulu di papers.jsonl.
Jika hasil kurang, fallback scrape Garuda HTML.
Parse detail paper dari Garuda.
Return ke format Paper.
Sumber:


https://garuda.kemdiktisaintek.go.id/documents/
Metadata yang diambil:

title
authors
year
journal / venue
DOI
URL
abstract
publisher
source = sinta
backend/SLR/orchestrator.py
Status: diubah total.

Fungsi utama:


pick_sources_for_topic(query)
fetch_titles(query, sources=None, limit_per_source=60, ...)
Fitur:

Max worker: 10.
Topic-aware source selection.
Dedup by DOI/title.
Round-robin source merge.
Predatory publisher filtering.
Progress callback ke worker.
Topic routing:

Topic	Source utama
AI / CS	arxiv, dblp, ieee, semantic_scholar
Engineering	ieee, openalex, crossref
Medical	europepmc, openalex, crossref
Indonesia	sinta, openalex, crossref
General	openalex, crossref, semantic_scholar, sinta
backend/SLR/scoring.py
Status: existing, dipakai.

Ranking signal:

SBERT similarity.
TF-IDF similarity.
Citation score.
Recency score.
Venue quality score.
Signal penalty jika abstract kosong/pendek.
Bobot:


total = (
    0.45 * sbert
    + 0.15 * tfidf
    + 0.15 * citation
    + 0.10 * recency
    + 0.15 * venue
) - signal_penalty
backend/SLR/summarizer.py
Status: diubah.

Fungsi utama:


summarize(text, query=None, n_sentences=3)
summarize_with_ai(papers, query, model="V-OPUS", batch_size=8)
Mode:

Extractive summary:

SBERT sentence scoring.
Tanpa API.
Fallback.
AI summary:

Default model: V-OPUS.
Batch 8 paper.
Output wajib JSON.
Fallback ke extractive jika AI gagal.
Prompt AI:

Faithful literature summary.
Tidak boleh invent data.
Jika abstract kosong → summary dari title dengan prefix [based on title].
backend/SLR/pipeline.py
Status: diubah total.

Pipeline utama:


search all sources
→ dedup
→ score/rank
→ take top_k
→ summarize top_k with V-OPUS
→ return payload
Default:


per_source = 60
top_k = 50
ai_model = "V-OPUS"
Output:


{
  "query": "...",
  "generated_at": "...",
  "stats": {},
  "papers": [],
  "top_k": []
}
4. Backend — Queue + Job System
4.1 backend/slr_worker.py
Status: baru.

Fungsi:

DB-backed SLR queue.
Max 10 worker.
FIFO job processing.
Polling DB setiap 1.5 detik.
Persist result ke LiteratureItem.
Env:


SLR_MAX_WORKERS=10
Main API internal:


start_slr_workers(app)
enqueue_slr_job(...)
Lifecycle job:


queued
→ running
→ done
Error/cancel:


error
cancelled
Progress stage:

Stage	Progress
fetching	5%
source_done	5–50%
dedup_done	55%
scoring	60%
scored	65%
summarizing	68%
summarized	68–95%
complete	100%
Setelah job selesai:

Top-K result disimpan ke tabel literature_items.
slr_jobs.result menyimpan full payload pipeline.
4.2 backend/app.py
Status: diubah.

Ditambahkan boot worker:


from slr_worker import start_slr_workers as _start_slr_workers
_start_slr_workers(app)
Efek:

Saat backend start, SLR worker pool otomatis aktif.
Job yang queued akan diproses.
5. Backend — REST API
5.1 backend/slr_bp.py
Status: rewrite.

Blueprint menyediakan endpoint:

Enqueue SLR Job

POST /api/papers/<paper_id>/slr/jobs
Body:


{
  "query": "reinforcement learning for AGV navigation",
  "sources": ["openalex", "ieee", "sinta"],
  "per_source": 60,
  "top_k": 50,
  "year_from": 2020,
  "ai_summarize": true,
  "ai_model": "V-OPUS"
}
Response:


{
  "id": "abc123...",
  "paper_id": "...",
  "query": "...",
  "status": "queued",
  "progress": 0,
  "stage": "queued"
}
List SLR Jobs

GET /api/papers/<paper_id>/slr/jobs
Response:


[
  {
    "id": "...",
    "query": "...",
    "status": "running",
    "progress": 45,
    "progress_message": "ieee → 50 hasil (5/8)"
  }
]
Get Job Status

GET /api/slr/jobs/<job_id>
Optional:


GET /api/slr/jobs/<job_id>?include_result=true
Cancel/Delete Job

DELETE /api/slr/jobs/<job_id>
List Literature

GET /api/papers/<paper_id>/literature
Add Literature Manual

POST /api/papers/<paper_id>/literature
Body:


{
  "title": "Paper title",
  "authors": ["Author A", "Author B"],
  "year": 2024,
  "venue": "IEEE Access",
  "doi": "10.xxxx/xxxx",
  "url": "https://...",
  "summary": "Short summary",
  "source_kind": "manual",
  "source": "manual"
}
Update Literature

PATCH /api/papers/<paper_id>/literature/<item_id>
Editable fields:


title
authors
year
venue
publisher
doi
url
abstract
summary
citations
must_read
is_relevant
notes
pinned
source
source_kind
Delete Literature

DELETE /api/papers/<paper_id>/literature/<item_id>
Import Attached Files to Literature

POST /api/papers/<paper_id>/literature/from-files
Fungsi:

Baca PaperFile.
Ambil extracted_text.
Buat LiteratureItem source_kind = file.
Skip jika file_id sudah pernah diimport.
Legacy SLR Endpoint
Masih ada untuk kompatibilitas:


POST /api/papers/<paper_id>/slr
Perilaku:

Queue job.
Tunggu max 25 detik.
Kalau belum selesai, return 202 + job_id.
6. Database
6.1 Model Baru: SlrJob
File:


backend/models.py
Table:


slr_jobs
Fields utama:

Field	Fungsi
id	job id
user_id	owner
paper_id	target paper
conversation_id	optional chat source
query	query SLR
sources	selected source list
top_k	jumlah paper terbaik
per_source	limit per API
year_from	filter tahun
ai_summarize	pakai AI summary
ai_model	default V-OPUS
status	queued/running/done/error/cancelled
stage	stage berjalan
progress	0–100
progress_message	text progress
result	full JSON pipeline
error	error message
queued_at	timestamp
started_at	timestamp
finished_at	timestamp
6.2 Model Baru: LiteratureItem
Table:


literature_items
Fields utama:

Field	Fungsi
id	row id
paper_id	target paper
user_id	owner
source_kind	slr/file/manual
source	openalex/ieee/sinta/etc
title	judul
authors	JSON list
year	tahun
venue	journal/conference
publisher	publisher
doi	DOI
url	URL
abstract	abstract
summary	AI summary
citations	citation count
score_total	ranking score
score_breakdown	detail ranking
must_read	flag
is_relevant	flag
notes	catatan user
pinned	pin ke atas
file_id	link ke uploaded file
slr_job_id	link ke job asal
6.3 Migration
File:


backend/alembic/versions/7a4f2c91d8e5_add_literature_and_slr_jobs.py
Command wajib:


cd /home/sirobo/papergenerator/backend
alembic upgrade head
7. Chat Integration
7.1 File

backend/chat_tools.py
backend/chat.py
7.2 Tool Baru: RunSLR
Fungsi:

Dipanggil AI chat saat user minta:
literatur review
systematic review
tinjauan pustaka
cari paper
kumpulkan referensi
studi pustaka
Tool ini:

Membuat SLR job.
Mengembalikan proposal payload.
Frontend/chat bisa menampilkan job progress.
Hasil otomatis masuk Tab Literatur.
Payload:


{
  "kind": "slr_job",
  "job_id": "...",
  "query": "...",
  "top_k": 50,
  "ai_model": "V-OPUS",
  "sources": "auto"
}
7.3 Tool Baru: GetLiterature
Fungsi:

Membaca isi Tab Literatur.
Dipakai AI untuk:
menampilkan ringkasan tabel literatur
memeriksa referensi sebelum generate paper
menjawab “literatur saya apa saja?”
Output:


[
  {
    "id": 1,
    "title": "...",
    "year": 2024,
    "authors": "...",
    "venue": "...",
    "doi": "...",
    "summary": "...",
    "must_read": true,
    "score": 0.82
  }
]
7.4 Generate Full Paper Integration
Di chat_tools.py, fungsi _generate_full_paper() sekarang menambahkan block:


## Literature catalog
Berisi:

title
authors
year
venue
DOI/URL
summary
Efek:

AI writer memakai data dari Tab Literatur sebagai sumber referensi.
AI diminta tidak membuat referensi palsu di luar list.
8. Frontend
8.1 File Baru

frontend/src/components/LiteratureTab.vue
Fitur:

Jalankan SLR dari UI.
Polling job tiap 4 detik.
Progress bar.
Cancel job.
Import dari file.
Tambah manual.
Edit inline.
Delete row.
Pin row.
Toggle must-read.
Filter by text/source/must-read.
Table lengkap.
Kolom tabel:

Kolom	Isi
Pin	pinned
#	nomor
Judul	title + summary
Penulis	authors
Tahun	year
Venue	journal/conference
DOI / URL	link
Sumber	source
Sitasi	citations
Skor	score_total
Star	must_read
Aksi	edit/delete
8.2 File Diubah

frontend/src/views/PaperEditorPage.vue
Perubahan:

Import LiteratureTab.
Tambah tab:

{ id: 'literature', label: '📖 Literatur' }
Tambah panel:

<div v-show="activeTab === 'literature'">
  <LiteratureTab />
</div>
Tab Literatur sekarang ada di samping kanan Journal.

9. Environment Variables
Tambahkan ke .env:


# Optional tapi disarankan
IEEE_API_KEY=ISI_API_KEY_IEEE

# Fixed by requirement
SLR_MAX_WORKERS=10

# SINTA offline cache
SINTA_OFFLINE_DIR=/home/sirobo/sinta-scraping
Existing AI env tetap dibutuhkan:


AIOTOMASI_API=...
AIOTOMASI_APIKEY=...
AIOTOMASI_MODEL=V-OPUS
10. Perintah Deploy
10.1 Backend Migration

cd /home/sirobo/papergenerator/backend
alembic upgrade head
10.2 Restart Backend
Jika pakai script project:


cd /home/sirobo/papergenerator
bash server.sh restart
Jika pakai PM2:


pm2 restart ecosystem.config.cjs
Atau backend manual:


cd /home/sirobo/papergenerator/backend
python3 app.py
10.3 Build Frontend

cd /home/sirobo/papergenerator/frontend
npm run build
Build sebelumnya sudah passed via:


npx vite build
11. Smoke Test
11.1 Backend Import Test

cd /home/sirobo/papergenerator/backend

python3 -c "
import os
os.environ.setdefault('DATABASE_URL', 'sqlite:///mydatabase.db')
os.environ.setdefault('JWT_SECRET_KEY', 'dev-12345')
os.environ.setdefault('SECRET_KEY', 'dev-67890')
os.environ.setdefault('JWT_COOKIE_SECURE', 'false')
os.environ.setdefault('SESSION_COOKIE_SECURE', 'false')

import models
import slr_worker
import slr_bp
import chat
import chat_tools
import SLR.fetchers as fs

print('models OK   | SlrJob:', hasattr(models, 'SlrJob'), 'LiteratureItem:', hasattr(models, 'LiteratureItem'))
print('chat tools  :', len(chat_tools.CHAT_TOOLS))
print('RunSLR      :', 'RunSLR' in [t['name'] for t in chat_tools.CHAT_TOOLS])
print('GetLiterature:', 'GetLiterature' in [t['name'] for t in chat_tools.CHAT_TOOLS])
print('SLR workers :', slr_worker.SLR_MAX_WORKERS)
print('fetchers    :', list(fs.ALL.keys()))
"
Expected:


models OK | SlrJob: True LiteratureItem: True
RunSLR: True
GetLiterature: True
SLR workers: 10
fetchers: ['openalex', 'crossref', 'semantic_scholar', 'arxiv', 'dblp', 'europepmc', 'ieee', 'sinta']
11.2 Frontend Build Test

cd /home/sirobo/papergenerator/frontend
npx vite build
Expected:


✓ built
11.3 SLR Job API Test
Butuh auth cookie/JWT.


curl -X POST "http://localhost:1001/api/papers/<paper_id>/slr/jobs" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <JWT>" \
  -d '{
    "query": "reinforcement learning for AGV navigation",
    "top_k": 50,
    "per_source": 60,
    "ai_summarize": true,
    "ai_model": "V-OPUS"
  }'
Expected:


{
  "id": "...",
  "status": "queued",
  "progress": 0
}
Poll:


curl "http://localhost:1001/api/slr/jobs/<job_id>" \
  -H "Authorization: Bearer <JWT>"
List literature:


curl "http://localhost:1001/api/papers/<paper_id>/literature" \
  -H "Authorization: Bearer <JWT>"
12. End-to-End Acceptance Test
Test 1 — Jalankan SLR dari Tab Literatur
Buka Paper Editor.
Buka Tab 📖 Literatur.
Isi query:

reinforcement learning for AGV navigation
Pilih Top 50.
Klik Jalankan SLR.
Pastikan:
progress card muncul
progress naik
status berubah
tabel terisi setelah job selesai
Expected:

Minimal beberapa row muncul.
Source campuran:
openalex
crossref
semantic_scholar
arxiv/dblp/ieee jika match
sinta jika offline cache match
Test 2 — Edit Literature
Klik edit row.
Ubah title/summary/year/DOI.
Klik save.
Reload page.
Expected:

Data tetap tersimpan.
Test 3 — Pin + Must Read
Klik pin.
Klik star.
Reload page.
Expected:

Pin tetap.
Must-read tetap.
Row pinned di atas.
Test 4 — Tambah Manual
Klik Tambah Manual.
Isi:
title
authors
year
venue
Save.
Expected:

Row source manual muncul.
Test 5 — Import dari File
Upload file PDF/DOCX di Tab Files.
Buka Tab Literatur.
Klik Import dari File.
Expected:

Row baru source file.
abstract/summary dari extracted text.
Tidak duplikat jika klik ulang.
Test 6 — Trigger dari Chat
Prompt:


buatkan literatur review lengkap tentang reinforcement learning untuk navigasi AGV
Expected:

AI memanggil RunSLR.
Job SLR muncul.
Tab Literatur terisi.
Chat memberi info job dimulai, bukan dump semua hasil.
Test 7 — Generate Full Paper Pakai Literatur
Setelah Tab Literatur berisi data, prompt:


generate paper lengkap berdasarkan literatur yang sudah ada
Expected:

_generate_full_paper() inject ## Literature catalog.
AI writer memakai title/DOI dari LiteratureItem.
Referensi tidak invent bebas.
13. Risiko Teknis
13.1 IEEE API Key
Jika IEEE_API_KEY tidak ada:

IEEE fetcher skip.
Tidak error.
Tapi hasil IEEE native tidak muncul.
Mitigasi:


IEEE_API_KEY=...
13.2 SINTA/Garuda Scraping
Risiko:

HTML Garuda berubah.
Rate limit / block scraping.
Offline file stale.
Mitigasi:

Gunakan SINTA_OFFLINE_DIR.
Jadwalkan refresh dari /home/sirobo/sinta-scraping.
Tambah parser test.
13.3 AI Summary Lama
Top-50 dengan V-OPUS bisa makan waktu.

Mitigasi:

Job queue async.
Batch 8.
Progress visible.
Fallback extractive.
13.4 Multi-worker Gunicorn
Saat ini tiap process punya worker pool sendiri.

Efek:

Jika gunicorn punya 4 worker, total potensi SLR thread bisa 4 × 10.
DB optimistic claim mengurangi double-pick, tapi concurrency total bisa lebih tinggi dari 10 global.
Mitigasi lanjutan:

Jalankan SLR worker sebagai proses terpisah.
Atau pakai Redis Queue / RQ / Celery.
Atau set SLR_MAX_WORKERS per process rendah jika gunicorn multi-worker.
Rekomendasi prod:


SLR_MAX_WORKERS=3
jika gunicorn 4 worker, atau pisahkan worker.

13.5 DB Migration Required
Tanpa migrasi:

Endpoint literature crash.
Worker gagal insert.
Wajib:


alembic upgrade head
14. Integrasi Lanjutan yang Disarankan
Prioritas P0 — Wajib Sebelum Production
 Jalankan migration di server.
 Tambah rate limit ke endpoint SLR job.
 Tambah quota/token accounting untuk summarize_with_ai.
 Pisahkan SLR worker dari Flask web process.
 Tambah job sweeper untuk job stuck/running terlalu lama.
 Tambah retry job error.
 Tambah unique/dedup logic antar literature row by DOI/title.
Prioritas P1 — Penting
 Export BibTeX/RIS dari Tab Literatur.
 Bulk delete/select.
 Advanced filter:
tahun
source
citations
score
must-read
 Modal detail paper:
abstract full
score breakdown
source metadata
 Fetch PDF otomatis dari URL paper.
 Extract PDF paper hasil SLR untuk summary lebih dalam.
 SLR cache per query.
 PubMed fetcher.
 DOAJ fetcher.
 HAL / Zenodo fetcher.
Prioritas P2 — Polish
 WebSocket/SSE progress real-time.
 Admin dashboard SLR jobs.
 Metrics:
job duration
source success/fail
AI summary fail rate
paper count/source
 Source badge warna beda per API.
 Inline citation mapping:
[L1], [L2]
tooltip di editor.
 Auto-suggest query dari:
title
abstract
project memory topik
keywords
15. Rekomendasi Arsitektur Lanjutan
Saat ini

Flask app
 ├─ REST endpoints
 ├─ Chat streaming
 ├─ Image workers
 └─ SLR worker threads
Cocok untuk dev/staging.

Rekomendasi production
Pisahkan:


Flask web process
 ├─ REST API
 ├─ Chat streaming
 └─ UI backend

SLR worker process
 └─ pulls slr_jobs from DB/Redis

Image worker process
 └─ handles image jobs
Lebih aman karena:

Web request tidak terganggu SLR berat.
Worker bisa diskalakan terpisah.
Limit 10 worker benar-benar global.
Restart worker tidak restart web.
16. Command untuk Integrasi Berikutnya
16.1 Jalankan Migrasi

cd /home/sirobo/papergenerator/backend
alembic upgrade head
16.2 Tambah Env

cat >> /home/sirobo/papergenerator/.env <<'EOF'

# SLR integration
SLR_MAX_WORKERS=10
SINTA_OFFLINE_DIR=/home/sirobo/sinta-scraping

# Optional: IEEE Xplore
IEEE_API_KEY=
EOF
16.3 Restart

cd /home/sirobo/papergenerator
bash server.sh restart
Atau:


pm2 restart ecosystem.config.cjs
16.4 Build Frontend

cd /home/sirobo/papergenerator/frontend
npm run build
16.5 Smoke Test

cd /home/sirobo/papergenerator/backend

python3 -c "
import models, slr_worker, slr_bp, chat_tools
from SLR.fetchers import ALL
print('SlrJob', hasattr(models, 'SlrJob'))
print('LiteratureItem', hasattr(models, 'LiteratureItem'))
print('workers', slr_worker.SLR_MAX_WORKERS)
print('fetchers', list(ALL.keys()))
print('RunSLR', 'RunSLR' in [t['name'] for t in chat_tools.CHAT_TOOLS])
print('GetLiterature', 'GetLiterature' in [t['name'] for t in chat_tools.CHAT_TOOLS])
"
17. Definition of Done
Integrasi dianggap selesai penuh jika:

 Migration sukses.
 Backend start tanpa error.
 Tab Literatur tampil.
 User bisa enqueue SLR job.
 Progress job terlihat.
 Worker memproses job.
 Hasil top-50 masuk literature_items.
 User bisa edit/delete/add/pin/must-read.
 Chat bisa memanggil RunSLR.
 Chat bisa membaca GetLiterature.
 Generate full paper memakai Literature catalog.
 Build frontend passed.
 Tidak ada crash di log backend selama test E2E.
18. Catatan Penting
Summary SLR sekarang meringkas abstract jika tersedia.
Jika abstract kosong, summary dibuat dari title only dan diberi tanda [based on title].
Ranking tetap bisa jalan walau abstract kosong, tapi ada signal_penalty.
IEEE native hanya aktif jika IEEE_API_KEY diset.
SINTA/Garuda paling cepat jika memakai offline cache /home/sirobo/sinta-scraping/papers.jsonl.
Hasil Literature menjadi sumber utama generate full paper supaya referensi tidak random.
19. Quick Prompt untuk User
User bisa pakai chat:


buatkan literatur review lengkap tentang reinforcement learning untuk navigasi AGV
atau:


cari 50 paper terbaik tentang deteksi penyakit daun menggunakan deep learning, lalu simpan ke tab literatur
atau:


gunakan literatur yang sudah ada untuk generate paper lengkap
20. Penutup
Integrasi dasar SLR + Tab Literatur sudah selesai dan build frontend berhasil.

Langkah berikutnya:

Jalankan migrasi DB.
Restart backend.
Test E2E dari Tab Literatur.
Test trigger dari chat.
Pastikan generate full paper memakai data literatur.