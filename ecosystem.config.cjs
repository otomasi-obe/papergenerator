// PM2 ecosystem config untuk PaperGenerator.
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
        DATABASE_URL: 'postgresql://papergenerator@/papergenerator',
        REDIS_URL: 'redis://:5b393a50e4a92d7d2713967c5d4fa38a458994980a0e4572582809f7479c18e3@localhost:6379/0',
        RATELIMIT_STORAGE_URI: 'redis://:5b393a50e4a92d7d2713967c5d4fa38a458994980a0e4572582809f7479c18e3@localhost:6379/1',
        CORS_ORIGINS: 'https://paperfull.app',
        DOMAIN: 'paperfull.app',
        FRONTEND_URL: 'https://paperfull.app'
      }
    },
    {
      name: 'paper-proxy-server',
      cwd: '/home/sirobo/papergenerator/frontend',
      script: 'proxy-server.cjs',
      interpreter: 'node',
      exec_mode: 'fork',
      max_restarts: 10,
      min_uptime: '30s',
      restart_delay: 5000,
      env: {
        FRONTEND_PORT: '8000',
        BACKEND_PORT: '8001',
      }
    },
    ]
};
