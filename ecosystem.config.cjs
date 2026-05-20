const fs = require('fs');
const path = require('path');

// Read .env file
let env = {};
try {
  const envFile = fs.readFileSync(path.join(__dirname, '.env'), 'utf8');
  envFile.split('\n').forEach(line => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx > 0) {
      env[trimmed.slice(0, eqIdx).trim()] = trimmed.slice(eqIdx + 1).trim();
    }
  });
} catch (e) { /* use defaults */ }

const BACKEND_PORT = env.BACKEND_PORT || '8001';
const FRONTEND_PORT = env.FRONTEND_PORT || '8000';

module.exports = {
  apps: [
    {
      name: 'paper-frontend',
      script: 'proxy-server.cjs',
      cwd: path.join(__dirname, 'frontend'),
      interpreter: 'node',
      env: {
        PORT: FRONTEND_PORT,
      },
      log_file: path.join(__dirname, 'logs/frontend.log'),
      out_file: path.join(__dirname, 'logs/frontend-out.log'),
      error_file: path.join(__dirname, 'logs/frontend-err.log'),
      max_memory_restart: '500M',
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
    },
    {
      // Gunicorn + gevent: 5 workers × 200 greenlets = handles 500+ concurrent users
      name: 'paper-backend',
      script: path.join(__dirname, 'backend/start.sh'),
      cwd: path.join(__dirname, 'backend'),
      interpreter: '/bin/bash',
      env: {
        FLASK_PORT: BACKEND_PORT,
        FLASK_DEBUG: 'false',
      },
      log_file: path.join(__dirname, 'logs/backend.log'),
      out_file: path.join(__dirname, 'logs/backend-out.log'),
      error_file: path.join(__dirname, 'logs/backend-err.log'),
      max_memory_restart: '1500M',   // gunicorn with 5 workers uses more RAM
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
    },
    {
      // RQ worker — long-running paper generation off the request thread so
      // HTTP stays responsive and progress survives restarts (rofiq.txt #4).
      name: 'paper-worker',
      script: path.join(__dirname, 'backend/worker.sh'),
      cwd: path.join(__dirname, 'backend'),
      interpreter: '/bin/bash',
      env: {
        REDIS_URL: env.REDIS_URL || 'redis://localhost:6379/0',
      },
      log_file: path.join(__dirname, 'logs/worker.log'),
      out_file: path.join(__dirname, 'logs/worker-out.log'),
      error_file: path.join(__dirname, 'logs/worker-err.log'),
      max_memory_restart: '1000M',
      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: '10s',
    }
  ]
};
