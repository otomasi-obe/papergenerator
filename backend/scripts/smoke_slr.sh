#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:8001/api/papers/testpaper/slr"
JOB="$BASE/jobs"
NEW="$BASE/new"
WAIT="$BASE/jobs/wait"

sample_response() {
  local label="$1"; shift
  echo "=== $label ==="
  out="$("$@")"
  echo "$out" | head -c 200
  echo
  echo "$out" | python3 -m json.tool 2>/dev/null | head -n 40 || true
}

# Terlihat dari gunicorn log lebih dulu ada endpoint lama /api/papers/.../slr/jobs.
sample_response "LIST OLD" curl -sS -H "Authorization: Bearer test" "$JOB"
sample_response "START NEW" curl -sS -X POST -H 'Content-Type: application/json' -H 'Authorization: Bearer test' -d '{"query":"reinforcement learning AGV","top_k":5}' "$NEW"
sample_response "LIST NEW" curl -sS -H "Authorization: Bearer test" "$JOB/testpaper/jobs"
sample_response "WAIT NEW" curl -sS --max-time 5 -H "Authorization: Bearer test" "${WAIT}?after=0"
