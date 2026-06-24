"""
Gunicorn production config for PaperFull backend.
Optimized for 40-core Xeon with 23GB RAM.
"""
import multiprocessing
import os

# === Server Socket ===
bind = "0.0.0.0:8001"
backlog = 4096  # Doubled for 1000+ concurrent users; nginx queues overflow

# === Worker Processes ===
# 12 workers × 4 threads = 48 concurrent request slots.
# Increased from 4 to 12 for better throughput under 1000+ concurrent users.
# Image workers use separate pool (~2 GB). 12×~150MB = ~1.8 GB + 2 GB image = ~3.8 GB,
# well within 23 GB RAM. Previous OOM was from 16 sync workers (no threads) + Chrome.
workers = 12
worker_class = "gthread"
threads = 4  # Reduced from 8 to 4 — still enough for I/O-bound AI API calls
worker_connections = 1000  # Used by gevent/eventlet; no-op for gthread but harmless
# SO_REUSEPORT: prevent orphan workers from blocking new gunicorn on port 8001
reuse_port = True

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
preload_app = False          # DO NOT enable: with preload_app=True gunicorn preloads the app
                             # in the master BEFORE forking workers. The import-time
                             # side-effects (image worker threads, SLR pool checks) cause
                             # the master to crash silently during fork → PM2 loses PID
                             # tracking → restart loop → orphan workers on port 8001.
                             # Without preload, each worker loads the app independently
                             # (~150MB × 16 = 2.4GB, system has 23GB — ample headroom).
max_requests = 2000         # Recycle workers after N requests (prevent leaks)
max_requests_jitter = 200   # Randomize to avoid thundering herd

# === Log Rotation ===
# Built-in log rotation via USR1 signal: kill -USR1 <master_pid>
# Also add to cron: 0 3 * * * kill -USR1 $(cat /tmp/gunicorn.pid 2>/dev/null || echo 0) 2>/dev/null
# Manual truncation if logs grow beyond 10MB:
#   truncate -s 0 /home/sirobo/papergenerator/backend/logs/gunicorn-error.log
#   truncate -s 0 /home/sirobo/papergenerator/backend/logs/gunicorn-access.log

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
    os.makedirs("/home/sirobo/papergenerator/backend/logs", exist_ok=True)


def post_fork(server, worker):
    import random
    random.seed(os.urandom(32))
    server.log.info("Worker spawned (pid: %s)", worker.pid)
    # Start image generation worker pool on exactly ONE gunicorn worker.
    # Uses a marker file so only the first worker to reach this point starts
    # the pool. The pool uses persistent Chrome profiles that cannot be shared
    # across processes. Jobs are DB-persisted so the dispatcher in one worker
    # can serve requests received by any gunicorn worker.
    _img_marker = "/tmp/papergenerator-img-workers.lock"
    try:
        import fcntl as _fcntl
        _lock_fd = open(_img_marker, "w")
        try:
            _fcntl.flock(_lock_fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            # We got the lock — this is the first worker. Hold the fd open
            # in a module-level var so it's not GC'd (which would release lock).
            import builtins
            builtins._img_lock_fd = _lock_fd
            _lock_fd.write(str(os.getpid()))
            _lock_fd.flush()
            server.log.info("Acquired image worker lock, calling start_image_workers...")
            from main import app  # noqa: PLC0415
            from tools.image_generation.worker import start_image_workers  # noqa: PLC0415
            start_image_workers(app)
            server.log.info("Image worker pool started in worker pid=%s", worker.pid)
        except (IOError, OSError):
            # Another worker already has the lock — skip
            _lock_fd.close()
            server.log.info("Image worker pool already started by another worker, skipping")
        except Exception as e:
            server.log.exception("Exception in start_image_workers: %s", e)
            _lock_fd.close()
    except Exception:
        server.log.exception("Failed to start image worker pool in worker pid=%s", worker.pid)


def pre_exec(server):
    server.log.info("Forked child, re-executing.")


def when_ready(server):
    server.log.info("Server is ready. Spawning workers: %d × %d threads",
                    server.cfg.workers, server.cfg.threads)
