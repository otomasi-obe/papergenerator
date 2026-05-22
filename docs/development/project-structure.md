# Project Structure

Understanding the PaperFull codebase organization.

## Repository Overview

```
papergenerator/
├── backend/                    # Flask API & workers
├── frontend/                   # Vue 3 SPA
├── docs/                       # Documentation
├── infra/                      # Infrastructure configs
├── prompt/                     # AI prompt templates
├── logs/                       # Application logs
├── backups/                    # Database backups
├── certs/                      # SSL certificates
├── server.sh                   # Server management script
├── ecosystem.config.cjs        # PM2 configuration
└── README.md                   # Project README
```

## Backend Structure

```
backend/
├── alembic/                    # Database migrations
│   ├── versions/               # Migration files
│   └── env.py                  # Alembic config
│
├── imageGenerator/             # Image generation module
│   ├── CreateImageGemini.py    # Gemini API client
│   ├── compress.py             # Image compression
│   └── GeminiCookies.py        # Cookie management
│
├── prompt/                     # Prompt templates
│   ├── prompt.txt              # Main paper generation prompt
│   ├── humanize.txt            # Humanization instructions
│   ├── style/                  # Writing style templates
│   └── topic/                  # Topic-specific prompts
│
├── SLR/                        # Systematic Literature Review
│   ├── scoring.py              # Relevance scoring (TF-IDF)
│   ├── summarizer.py           # AI summarization
│   └── searchPaper.py          # Paper search logic
│
├── template/                   # Journal templates
│   ├── JTMMgen.py              # JTMM template
│   ├── IJEECSgen.py            # IJEECS template
│   └── ...                     # Other journal templates
│
├── tests/                      # Test suite
│   ├── conftest.py             # Pytest fixtures & config
│   ├── test_chat_tools.py      # Chat tools tests
│   ├── test_generate_paper_*.py # Paper generation tests
│   ├── test_slr_*.py           # SLR tests
│   └── test_playwright_*.py    # E2E tests
│
├── app.py                      # Main Flask application
├── auth.py                     # Authentication (OAuth, JWT)
├── chat.py                     # Chat API endpoints
├── chat_tools.py               # 37 chat tools implementation
├── mode_prompts.py             # Mode-specific prompts
├── slr_bp.py                   # SLR blueprint (routes)
├── slr_worker.py               # SLR async worker
├── charts_bp.py                # Chart generation routes
├── chart_generator.py          # Chart generation logic
├── files_bp.py                 # File upload routes
├── image_worker.py             # Image generation worker
├── generate_paper_single.py    # Single-shot paper generation
├── generate_paper_chunked.py   # Chunked paper generation (legacy)
├── models.py                   # SQLAlchemy models
├── env_loader.py               # Environment variable loader
├── worker.py                   # Main worker process
├── requirements.txt            # Python dependencies
├── alembic.ini                 # Alembic configuration
└── .env                        # Environment variables (not in git)
```

### Key Backend Files

#### Core Application
- **`app.py`** (1200+ lines) - Main Flask app, routes, job orchestration
- **`models.py`** - SQLAlchemy models (13 tables)
- **`env_loader.py`** - Environment variable loading with validation

#### Authentication & Authorization
- **`auth.py`** - Google OAuth flow, JWT token management, user CRUD

#### Chat System
- **`chat.py`** - Chat API, conversation management, model lock (V-DEEPSEEK)
- **`chat_tools.py`** - 37 tools (GetLiterature, ProposeSection, etc.)
- **`mode_prompts.py`** - Mode definitions (discovery, revisi, slr, edit, etc.)

#### Paper Generation
- **`generate_paper_single.py`** - Single-shot generation (V-OPUS, 900s timeout)
- **`generate_paper_chunked.py`** - Legacy chunked generation

#### SLR (Systematic Literature Review)
- **`slr_bp.py`** - SLR routes, job management, long-polling
- **`slr_worker.py`** - Async SLR execution, parallel processing
- **`SLR/scoring.py`** - TF-IDF relevance scoring
- **`SLR/summarizer.py`** - AI summarization (V-DEEPSEEK)

#### Charts & Images
- **`charts_bp.py`** - Chart generation routes
- **`chart_generator.py`** - Matplotlib chart generation
- **`image_worker.py`** - Async image generation (Gemini API)
- **`imageGenerator/`** - Image generation utilities

#### Workers
- **`worker.py`** - Main worker process (paper, SLR, image jobs)

## Frontend Structure

```
frontend/
├── public/                     # Static assets
│   ├── favicon.ico             # Favicon
│   ├── manifest.webmanifest    # PWA manifest
│   └── *.png                   # Icon sizes
│
├── src/
│   ├── api/                    # API client modules
│   │   └── client.js           # Axios instance & interceptors
│   │
│   ├── components/             # Vue components
│   │   ├── AppHeader.vue       # Header with quota display
│   │   ├── ChatTab.vue         # Chat interface (800+ lines)
│   │   ├── ChatMessage.vue     # Message rendering
│   │   ├── MultiQuestionCard.vue # Multi-question UI
│   │   ├── RevisiProposalCard.vue # Revision proposals
│   │   ├── LiteratureTab.vue   # SLR results table
│   │   ├── PaperTab.vue        # Paper editor
│   │   └── ...                 # Other components
│   │
│   ├── directives/             # Vue directives
│   │   └── clickOutside.js     # Click outside directive
│   │
│   ├── image/                  # Image assets
│   │   └── logo.svg            # PaperFull logo
│   │
│   ├── router/                 # Vue Router
│   │   └── index.js            # Route definitions
│   │
│   ├── stores/                 # Pinia stores
│   │   ├── auth.js             # Authentication state
│   │   ├── chat.js             # Chat state & logic
│   │   ├── paper.js            # Paper state
│   │   ├── paperJobs.js        # Job polling & updates
│   │   └── quota.js            # Token quota state
│   │
│   ├── utils/                  # Utility functions
│   │   ├── markdown.js         # Markdown rendering
│   │   └── format.js           # Formatting helpers
│   │
│   ├── views/                  # Page components
│   │   ├── LoginView.vue       # Login page
│   │   ├── DashboardView.vue   # Dashboard (paper list)
│   │   ├── EditorView.vue      # Paper editor (main app)
│   │   └── NotFoundView.vue    # 404 page
│   │
│   ├── App.vue                 # Root component
│   ├── main.js                 # Application entry point
│   └── style.css               # Global styles (Tailwind)
│
├── tests/                      # Frontend tests
│   └── e2e/                    # Playwright E2E tests
│
├── package.json                # Node dependencies
├── vite.config.js              # Vite configuration
├── tailwind.config.js          # TailwindCSS config
├── postcss.config.js           # PostCSS config
└── .env                        # Environment variables (not in git)
```

### Key Frontend Files

#### Entry Point
- **`main.js`** - App initialization, Pinia, Router, global config

#### Views (Pages)
- **`LoginView.vue`** - Google OAuth login
- **`DashboardView.vue`** - Paper list, create new paper
- **`EditorView.vue`** - Main editor with tabs (Chat, Paper, Literature)

#### Core Components
- **`ChatTab.vue`** (800+ lines) - Chat interface, message handling, tool execution
- **`ChatMessage.vue`** - Message rendering, card components (multi-question, proposals)
- **`PaperTab.vue`** - Paper editor, section management, export
- **`LiteratureTab.vue`** - SLR interface, job management, results table

#### State Management (Pinia)
- **`auth.js`** - User authentication, login/logout, token management
- **`chat.js`** - Chat state, send messages, tool execution, model lock
- **`paper.js`** - Paper CRUD, content management, export
- **`paperJobs.js`** - Job polling, status updates, deduplication
- **`quota.js`** - Token quota tracking, usage display

## Infrastructure

```
infra/
├── grafana/                    # Grafana dashboards
│   └── dashboards/             # Dashboard JSON files
│
├── prometheus/                 # Prometheus config
│   ├── prometheus.yml          # Scrape configs
│   └── alerts.yml              # Alert rules
│
├── promtail/                   # Promtail (log shipping)
│   └── promtail-config.yml     # Log collection config
│
└── scripts/                    # Utility scripts
    ├── backup.sh               # Database backup script
    └── restore.sh              # Database restore script
```

## Documentation

```
docs/
├── README.md                   # Documentation index
├── architecture/               # Architecture docs
├── api/                        # API documentation
├── development/                # Development guides
├── deployment/                 # Deployment guides
├── features/                   # Feature documentation
├── troubleshooting/            # Troubleshooting guides
├── operations/                 # Operational runbooks
└── reference/                  # Reference docs
```

## Logs

```
logs/
├── chat_calls/                 # Per-call JSONL logs
│   └── <paper_id>/
│       └── <YYYY-MM-DD>.jsonl  # Daily log files
└── generator/                  # Paper generation logs
```

## Prompts

```
prompt/
├── prompt.txt                  # Main paper generation prompt
├── humanize.txt                # Humanization instructions
├── style/                      # Writing style templates
│   ├── formal.txt
│   ├── academic.txt
│   └── ...
└── topic/                      # Topic-specific prompts
    ├── computer_science.txt
    ├── engineering.txt
    └── ...
```

## Configuration Files

### Root Level
- **`ecosystem.config.cjs`** - PM2 process configuration
- **`server.sh`** - Server management script (start/stop/restart)
- **`.gitignore`** - Git ignore rules
- **`DOCUMENTATION_PLAN.md`** - Documentation strategy

### Backend
- **`requirements.txt`** - Python dependencies
- **`alembic.ini`** - Alembic migration config
- **`.env`** - Environment variables (not in git)
- **`.env.example`** - Environment variable template

### Frontend
- **`package.json`** - Node dependencies & scripts
- **`vite.config.js`** - Vite build configuration
- **`tailwind.config.js`** - TailwindCSS configuration
- **`postcss.config.js`** - PostCSS configuration
- **`.env`** - Environment variables (not in git)

## Code Organization Principles

### Backend
- **Blueprints**: Separate blueprints for different API domains (SLR, charts, files)
- **Workers**: Async workers for long-running tasks (paper, SLR, image)
- **Models**: Single `models.py` with all SQLAlchemy models
- **Tools**: Chat tools in `chat_tools.py` with clear naming
- **Prompts**: External prompt files for easy editing

### Frontend
- **Component-based**: Reusable Vue components
- **Store-based state**: Pinia stores for global state
- **Route-based views**: One view per route
- **API abstraction**: Centralized API client
- **Utility functions**: Shared utilities in `utils/`

## Import Patterns

### Backend
```python
# Flask app
from app import app, db

# Models
from models import User, Paper, AIJob

# Tools
from chat_tools import CHAT_TOOLS, execute_tool

# Config
from env_loader import get_env
```

### Frontend
```javascript
// Stores
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'

// API
import api from '@/api/client'

// Components
import ChatMessage from '@/components/ChatMessage.vue'
```

## Testing Structure

### Backend Tests
```
tests/
├── conftest.py                 # Fixtures (app, db, client)
├── test_auth.py                # Auth tests
├── test_chat_*.py              # Chat tests
├── test_generate_*.py          # Generation tests
├── test_slr_*.py               # SLR tests
└── test_playwright_*.py        # E2E tests
```

### Frontend Tests
```
tests/
└── e2e/                        # Playwright E2E tests
    ├── login.spec.js
    ├── paper-generation.spec.js
    └── slr.spec.js
```

## Build Artifacts

### Backend
- **`.venv/`** - Python virtual environment (not in git)
- **`__pycache__/`** - Python bytecode cache (not in git)
- **`*.pyc`** - Compiled Python files (not in git)

### Frontend
- **`node_modules/`** - Node dependencies (not in git)
- **`dist/`** - Production build output (not in git)
- **`.vite/`** - Vite cache (not in git)

## Environment-Specific Files

### Development
- Backend runs on port 5000 (Flask dev server)
- Frontend runs on port 5173 (Vite dev server)
- Hot reload enabled

### Production
- Backend runs via Gunicorn (managed by PM2)
- Frontend served as static files (managed by PM2)
- Nginx reverse proxy
- Environment variables in `.env`

## Navigation Tips

### Finding Features
1. **Chat tools**: `backend/chat_tools.py` - Search for tool name
2. **API endpoints**: `backend/app.py` or `backend/*_bp.py` - Search for route
3. **UI components**: `frontend/src/components/` - Search by name
4. **Database models**: `backend/models.py` - All models in one file

### Finding Configuration
1. **Backend config**: `backend/.env` or `backend/env_loader.py`
2. **Frontend config**: `frontend/.env` or `frontend/vite.config.js`
3. **Database config**: `backend/alembic.ini` or `DATABASE_URL` env var
4. **PM2 config**: `ecosystem.config.cjs`

### Finding Documentation
1. **Architecture**: `docs/architecture/`
2. **API**: `docs/api/` or `backend/` (inline docstrings)
3. **Features**: `docs/features/`
4. **Setup**: `docs/development/`

## Related Documentation

- [Quick Start](quick-start.md) - Get started quickly
- [Setup Guide](setup.md) - Detailed setup
- [System Overview](../architecture/system-overview.md) - Architecture
- [Coding Standards](coding-standards.md) - Code style
- [Testing Guide](testing.md) - Testing strategy

---

**Last Updated**: 2026-05-22  
**Lines of Code**: ~15,000 (backend), ~8,000 (frontend)  
**File Count**: ~150 Python files, ~50 Vue files
