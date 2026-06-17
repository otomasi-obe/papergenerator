# Paper Generator

AI-powered academic paper generation system with multi-journal template support, literature research tools, and image generation.

## Architecture

```
papergenerator/
├── backend/              # Python Flask API (port 8001)
│   ├── api/              # Blueprint routes (auth, papers, chat, jobs, admin)
│   ├── core/             # Core utilities (cache, retry, storage)
│   ├── database/         # SQLAlchemy models, Alembic migrations
│   ├── tools/            # Tool modules
│   │   ├── Journal/      # 40+ journal template generators (ACM, APA, IEEE, Elsevier, MDPI, etc.)
│   │   ├── Literatur/    # Literature search & topic generation (Crossref, DOAJ, OpenAlex, etc.)
│   │   ├── image_generation/  # AI image generation with multi-account support
│   │   ├── chat/         # Chat & drafting tools
│   │   ├── grammar/      # Grammar checking
│   │   ├── humanizer/    # AI text humanizer
│   │   ├── paraphrase/   # Paraphrasing engine
│   │   ├── plagiarism/   # Plagiarism detection
│   │   ├── preview/      # Paper preview & normalization
│   │   ├── summarize/    # Summarization
│   │   ├── translator/   # Multi-language translation
│   │   ├── editor/       # Rich text editing
│   │   ├── File/         # File extraction & processing
│   │   └── data/         # Data formatting & worker
│   ├── tests/            # Unit, integration, performance tests
│   ├── main.py           # Flask app entry point
│   └── worker.py         # Background job worker (RQ)
├── frontend/             # Vue.js 3 SPA (port 8000)
│   ├── src/
│   │   ├── api/          # API client
│   │   ├── components/   # Vue components
│   │   ├── composables/  # Composition API hooks
│   │   ├── router/       # Vue Router config
│   │   ├── services/     # Business logic services
│   │   ├── stores/       # Pinia state stores
│   │   ├── types/        # TypeScript types
│   │   ├── views/        # Page views
│   │   └── utils/        # Utility functions
│   └── e2e/              # Playwright E2E + load tests
├── deploy/               # Deployment configs (PgBouncer, nginx)
├── server.sh             # Service manager
└── .env                  # Environment variables (not tracked)
```

## Quick Start

```bash
# Option 1: Interactive menu
./server.sh

# Option 2: Direct commands
./server.sh start    # Start all services (skip build)
./server.sh build    # Build + start all services
./server.sh stop     # Stop all services
./server.sh status   # Check service status
```

## Services & Ports

| Service  | Port | PM2 Name             | Description                  |
|----------|------|----------------------|------------------------------|
| Frontend | 8000 | paper-frontend       | Vue.js 3 SPA (Vite)         |
| Backend  | 8001 | paper-backend-flask  | Flask API (Gunicorn)         |
| Worker   | -    | paper-worker         | RQ background job processor  |

## Tech Stack

- **Backend:** Python, Flask, SQLAlchemy, PostgreSQL, Redis, RQ
- **Frontend:** Vue 3, Vite, TypeScript, Pinia, Tailwind CSS
- **Infra:** Gunicorn, PgBouncer, PM2, Nginx
- **Testing:** Pytest (backend), Vitest (unit), Playwright (E2E + load)
- **Paper Templates:** 40+ journals — ACM, APA, IEEE, Elsevier, MDPI, Springer, Vancouver, and more
- **AI Features:** Paper generation, image generation, grammar check, paraphrasing, plagiarism detection, summarization, translation

## Development

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py              # Dev server
# or
gunicorn -c gunicorn.conf.py main:app   # Production
```

### Frontend

```bash
cd frontend
npm install                  # or: pnpm install
npm run dev                  # Dev server (port 8000)
npm run build                # Production build
npm run type-check           # TypeScript check
```

### Tests

```bash
# Backend unit + integration
cd backend && pytest

# Frontend unit tests
cd frontend && npm run test:unit

# Frontend E2E
cd frontend && npx playwright test

# Load tests
cd frontend && npm run test:load
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

```
DATABASE_URL=postgresql://user:pass@localhost/papergenerator
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-secret
OPENAI_API_KEY=sk-...
# ...see .env.example for full list
```

## Deployment

Production deployment uses PM2 with Gunicorn behind PgBouncer connection pooling:

```bash
# Full stack start (build + deploy)
./server.sh build

# PgBouncer config
deploy/pgbouncer.ini → /etc/pgbouncer/pgbouncer.ini
```

## License

Private project — ZOO Company
