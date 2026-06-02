# Paper Generator

Sistem otomatis untuk generating paper akademik dengan AI.

## Arsitektur

```
papergenerator/
├── backend/          # Python Flask API (port 8001)
│   ├── api/          # Blueprint routes
│   ├── core/         # Core utilities (cache, retry, storage)
│   ├── image_generation/
│   ├── paper_generation/
│   ├── routes/
│   ├── schemas/
│   ├── templates/    # Document templates (ACM, APA, Elsevier, etc.)
│   └── tests/
├── frontend/         # Vue.js SPA (port 8000)
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── composables/
│   │   ├── stores/
│   │   └── types/
│   └── e2e/
├── logs/             # Runtime logs
├── Goal/             # Planning docs
└── server.sh         # Service manager
```

## Quick Start

```bash
# Start semua service (frontend + backend)
./server.sh start

# Cek status
./server.sh status

# Stop semua service
./server.sh stop
```

## Ports

| Service  | Port |
|----------|------|
| Frontend | 8000 |
| Backend  | 8001 |

## Development

### Backend (Python)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

### Frontend (Vue.js)

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
# Backend tests
cd backend
pytest

# Frontend E2E
cd frontend
npx playwright test
```

## Teknologi

- **Backend:** Python, Flask, SQLAlchemy, SQLite
- **Frontend:** Vue 3, Vite, Pinia, Playwright (E2E)
- **Process Manager:** PM2
- **Paper Templates:** ACM, APA, IEEE, Elsevier, MDPI, Springer, Vancouver

## Lisensi

Private project - ZOO Company
