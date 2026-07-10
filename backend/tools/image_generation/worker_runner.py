"""Standalone image generation worker runner.

Run outside gunicorn/gevent:
  python -m tools.image_generation.worker_runner
"""
import signal
import time

from main import app
from tools.image_generation.worker import start_image_workers

_stop = False


def _handle_stop(signum, frame):  # noqa: ARG001
    global _stop
    _stop = True


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    start_image_workers(app)
    print("paper image worker started", flush=True)
    while not _stop:
        time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
