"""
Gunicorn production config for PaperFull backend.
Optimized for 40-core Xeon with 23GB RAM.
"""
import multiprocessing
import os

# === Server Socket ===
bind = "0.0.0.0:8001"
backlog = 2048

# === Worker Processes ===
# 16 workers × 4 threads = 64 concurrent request slots
# Each worker ~150MB → ~2.4GB total (safe within 14GB available)
workers = min(16, multiprocessing.cpu_count() * 2 + 1)
worker_class = "gthread"
threads = 4
worker_connections = 1000

# === Timeouts ===
timeout = 1800       # 30min for AI generation tasks
graceful_timeout = 30
keepalive = 5

# === Logging ===
accesslog = "/home/sirobo/papergenerator/backend/logs/gunicorn-access.log"
errorlog = "/home/sirobo/papergenerator/backend/logs/gunicorn-error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# === Process ===
preload_app = True          # Load app once, fork workers (saves memory)
max_requests = 2000         # Recycle workers after N requests (prevent leaks)
max_requests_jitter = 200   # Randomize to avoid thundering herd

# === Security ===
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# === PID ===
pidfile = "/home/sirobo/papergenerator/backend/gunicorn.pid"

# === Working Directory ===
chdir = "/home/sirobo/papergenerator/backend"

# === Temp files ===
worker_tmp_dir = "/dev/shm"  # RAM-based tmp for heartbeat (faster)


def on_starting(server):
    """Create log directory if needed."""
    import os
    os.makedirs("/home/sirobo/papergenerator/backend/logs", exist_ok=True)


def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)


def pre_exec(server):
    server.log.info("Forked child, re-executing.")


def when_ready(server):
    server.log.info("Server is ready. Spawning workers: %d × %d threads",
                    server.cfg.workers, server.cfg.threads)
