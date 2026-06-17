module.exports = {
  apps: [
    {
      name: 'paper-backend-flask',
      cwd: '/home/sirobo/papergenerator/backend',
      script: '/home/sirobo/papergenerator/backend/.venv/bin/python',
      args: '-m gunicorn -c gunicorn.conf.py main:app',
      interpreter: 'none',
      exec_mode: 'fork',
      env: {
        DATABASE_URL: 'postgresql://papergenerator@/papergenerator'
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
        DATABASE_URL: 'postgresql://papergenerator@/papergenerator'
      }
    }
  ]
};
