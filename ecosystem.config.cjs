// PM2 ecosystem config untuk PaperGenerator.
// DATABASE_URL menggunakan PostgreSQL peer auth (Unix socket) —
// PM2 process berjalan sebagai user sistem, bukan via TCP/password.
// Kalau butuh TCP: ganti ke postgresql://user:pass@localhost:5432/papergenerator
module.exports = {
  apps: [
    {
      name: 'paper-backend-flask',
      cwd: '/home/sirobo/papergenerator/backend',
      script: '/home/sirobo/papergenerator/backend/.venv/bin/python',
      args: '-m gunicorn -c gunicorn.conf.py main:app',
      interpreter: 'none',
      exec_mode: 'fork',
      max_restarts: 10,
      min_uptime: '30s',
      restart_delay: 5000,
      env: {
        // PostgreSQL peer auth via Unix socket (bukan TCP+password)
        DATABASE_URL: 'postgresql://papergenerator@/papergenerator',
        // Redis local untuk session, rate limit, job queue
        REDIS_URL: 'redis://localhost:6379/0'
      }
    },
    {
      name: 'paper-worker',
      cwd: '/home/sirobo/papergenerator/backend',
      script: '/home/sirobo/papergenerator/backend/.venv/bin/python',
      args: '/home/sirobo/papergenerator/backend/worker.py',
      interpreter: 'none',
      exec_mode: 'fork',
      env: {
        // PostgreSQL peer auth via Unix socket
        DATABASE_URL: 'postgresql://papergenerator@/papergenerator',
        // Redis untuk RQ job queue (wajib, worker tidak bisa konek tanpanya)
        REDIS_URL: 'redis://localhost:6379/0'
      }
    }
  ]
};