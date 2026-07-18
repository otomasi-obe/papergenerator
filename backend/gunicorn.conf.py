"""
Gunicorn production config for PaperFull backend.
Optimized for 40-core Xeon with 23GB RAM.
"""
import multiprocessing
import os

# === Server Socket ===
bind = "127.0.0.1:8001"
backlog = 4096  # Doubled for 1000+ concurrent users; nginx queues overflow

# === Worker Processes ===
# 24 gevent workers = scalable to 1000+ concurrent users.
# gevent async workers handle many concurrent connections without threads.
# worker_connections=100: max concurrent connections per gevent worker.
workers = 24
worker_class = "gevent"
worker_connections = 100
# SO_REUSEPORT disabled: with True, old workers survive PM2 restart on port 8001,
# causing orphan processes that block the new master from binding.
reuse_port = False

# === Timeouts ===
timeout = 1800       # 30min for AI generation tasks
graceful_timeout = 30
keepalive = 5

# === Logging ===
accesslog = "/home/sirobo/papergenerator/backend/log/gunicorn-access.log"
errorlog = "/home/sirobo/papergenerator/backend/log/gunicorn-error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# === Process ===
preload_app = False          # DO NOT enable: with preload_app=True gunicorn preloads the app
                             # in the master BEFORE forking workers. The import-time
                             # side-effects (image worker threads, SLR pool checks) cause
                             # the master to crash silently during fork → PM2 loses PID
                             # tracking → restart loop → orphan workers on port 8001.
                             # Without preload, each worker loads the app independently
                             # (~150MB × 24 = 3.6GB, system has 23GB — ample headroom).
max_requests = 2000         # Recycle workers after N requests (prevent leaks)
max_requests_jitter = 200   # Randomize to avoid thundering herd

# === Log Rotation ===
# Built-in log rotation via USR1 signal: kill -USR1 <master_pid>
# Also add to cron: 0 3 * * * kill -USR1 $(cat /tmp/gunicorn.pid 2>/dev/null || echo 0) 2>/dev/null
# Manual truncation if logs grow beyond 10MB:
#   truncate -s 0 /home/sirobo/papergenerator/backend/log/gunicorn-error.log
#   truncate -s 0 /home/sirobo/papergenerator/backend/log/gunicorn-access.log

# === Security ===
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# === PID ===
# pidfile = "/home/sirobo/papergenerator/backend/gunicorn.pid"
# Disabled — PM2 manages the process lifecycle. The stale PID file caused
# restart loops ("Already running on PID X") because PM2 sends SIGKILL and
# gunicorn cannot clean up its own PID file.

# === Working Directory ===
chdir = "/home/sirobo/papergenerator/backend"

# === Temp files ===
worker_tmp_dir = "/dev/shm"  # RAM-based tmp for heartbeat (faster)


def on_starting(server):
    """Create log directory if needed."""
    import os
    os.makedirs("/home/sirobo/papergenerator/backend/log", exist_ok=True)


def post_fork(server, worker):
    import random
    random.seed(os.urandom(32))
    server.log.info("Worker spawned (pid: %s)", worker.pid)
    # Image workers now run as a separate PM2 process (paper-image-worker).
    # See worker_runner.py. Do not start them inside gunicorn workers.
    # The old lock-based startup is kept for reference but skipped.


def pre_exec(server):
    server.log.info("Forked child, re-executing.")


def when_ready(server):
    server.log.info("Server is ready. Spawning workers: %d (gevent, conn=%d)",
                    server.cfg.workers, server.cfg.worker_connections)
