# Quick Start Guide

Get PaperFull running locally in 5 minutes.

## Prerequisites

Before you begin, ensure you have:

- **Python 3.10+** - `python3 --version`
- **Node.js 18+** - `node --version`
- **PostgreSQL 14+** - `psql --version`
- **Redis 7+** - `redis-cli --version`
- **Git** - `git --version`

## Setup Steps

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/papergenerator.git
cd papergenerator
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use your preferred editor
```

**Required environment variables:**
```bash
# Database
DATABASE_URL=postgresql://papergenerator:password@localhost:5432/papergenerator

# AI API
AIOTOMASI_API=https://api.example.com
AIOTOMASI_APIKEY=your_api_key_here
AIOTOMASI_MODEL=V-OPUS

# Google OAuth
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret

# JWT
JWT_SECRET_KEY=your_random_secret_key_here

# Redis
REDIS_URL=redis://localhost:6379/0
```

### 3. Database Setup

```bash
# Create database
createdb papergenerator

# Or using psql
psql -U postgres -c "CREATE DATABASE papergenerator;"
psql -U postgres -c "CREATE USER papergenerator WITH PASSWORD 'password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE papergenerator TO papergenerator;"

# Run migrations
alembic upgrade head

# Verify tables created
psql $DATABASE_URL -c "\dt"
# Should show 13 tables
```

### 4. Frontend Setup

```bash
cd ../frontend

# Install dependencies
npm install

# Create environment file (optional)
cp .env.example .env

# Edit if needed (default values usually work)
nano .env
```

**Frontend environment variables:**
```bash
VITE_API_BASE_URL=http://localhost:5000
```

### 5. Start Services

Open **three terminal windows**:

#### Terminal 1: Backend API
```bash
cd backend
source .venv/bin/activate
flask run
# Backend running on http://localhost:5000
```

#### Terminal 2: Worker
```bash
cd backend
source .venv/bin/activate
python worker.py
# Worker listening for jobs
```

#### Terminal 3: Frontend
```bash
cd frontend
npm run dev
# Frontend running on http://localhost:5173
```

### 6. Access Application

Open your browser and navigate to:
```
http://localhost:5173
```

You should see the PaperFull login page.

## Verify Installation

### Check Backend Health
```bash
curl http://localhost:5000/api/healthz
# Expected: {"status": "healthy"}
```

### Check Database Connection
```bash
psql $DATABASE_URL -c "SELECT COUNT(*) FROM users;"
# Expected: count (initially 0)
```

### Check Redis Connection
```bash
redis-cli ping
# Expected: PONG
```

### Run Tests
```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/ -v
# Expected: 163+ tests passing
```

## Common Issues

### Issue: `ModuleNotFoundError`
**Solution**: Ensure virtual environment is activated and dependencies installed
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Issue: Database connection error
**Solution**: Check PostgreSQL is running and DATABASE_URL is correct
```bash
sudo systemctl status postgresql
psql $DATABASE_URL -c "SELECT 1;"
```

### Issue: Redis connection error
**Solution**: Check Redis is running
```bash
sudo systemctl status redis
redis-cli ping
```

### Issue: Port already in use
**Solution**: Kill process using the port
```bash
# Find process on port 5000
lsof -ti:5000 | xargs kill -9

# Or use different port
flask run --port 5001
```

### Issue: Google OAuth not working
**Solution**: 
1. Create OAuth credentials at https://console.cloud.google.com
2. Add authorized redirect URI: `http://localhost:5000/api/auth/google/callback`
3. Update GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env

## Next Steps

Now that you have PaperFull running:

1. **Explore the codebase**: [Project Structure](project-structure.md)
2. **Understand the architecture**: [System Overview](../architecture/system-overview.md)
3. **Run tests**: [Testing Guide](testing.md)
4. **Make changes**: [Contributing Guide](contributing.md)
5. **Debug issues**: [Debugging Guide](debugging.md)

## Development Workflow

### Hot Reload

Both frontend and backend support hot reload:

- **Frontend**: Vite automatically reloads on file changes
- **Backend**: Flask dev server reloads on Python file changes
- **Worker**: Restart manually after changes

### Making Changes

1. Create a feature branch
```bash
git checkout -b feature/my-feature
```

2. Make your changes

3. Run tests
```bash
cd backend && pytest tests/
cd frontend && npm run test
```

4. Commit and push
```bash
git add .
git commit -m "Add my feature"
git push origin feature/my-feature
```

5. Create a pull request

## Alternative: Docker Setup (Optional)

If you prefer Docker:

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

**Note**: Docker setup is not yet fully configured. Use manual setup for now.

## Troubleshooting

For more detailed troubleshooting, see:
- [Common Issues](../troubleshooting/common-issues.md)
- [Debugging Guide](debugging.md)
- [Database Issues](../troubleshooting/database-issues.md)

## Getting Help

- Check [Documentation](../README.md)
- Search [Issues](https://github.com/yourusername/papergenerator/issues)
- Ask in team chat

---

**Estimated Setup Time**: 5-10 minutes  
**Last Updated**: 2026-05-22  
**Tested On**: Ubuntu 22.04, macOS 13+, Windows 11 (WSL2)
