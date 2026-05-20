#!/bin/bash
# infra/scripts/pg-restore-staging.sh — DR drill helper.
#
# Restores the latest backup file to a temporary database so you can verify
# the dump is intact without touching production. Cleans up after itself.
#
# Usage:
#   bash infra/scripts/pg-restore-staging.sh [path-to-dump.sql.gz]
#
# Without arg, picks newest daily backup.
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/home/sirobo/papergenerator/backups}"
ENV_FILE="${ENV_FILE:-/home/sirobo/papergenerator/backend/.env}"

DUMP="${1:-}"
if [ -z "$DUMP" ]; then
  DUMP=$(ls -1t "${BACKUP_ROOT}/daily"/pg-*.sql.gz 2>/dev/null | head -1 || true)
fi
if [ -z "$DUMP" ] || [ ! -r "$DUMP" ]; then
  echo "No dump file found" >&2
  exit 1
fi

DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"')
PG_USER=$(echo "$DATABASE_URL" | sed -E 's|postgres(ql)?://([^:]+):([^@]+)@([^:/]+)(:[0-9]+)?/.*|\2|')
PG_PASS=$(echo "$DATABASE_URL" | sed -E 's|postgres(ql)?://([^:]+):([^@]+)@([^:/]+)(:[0-9]+)?/.*|\3|')
PG_HOST=$(echo "$DATABASE_URL" | sed -E 's|postgres(ql)?://([^:]+):([^@]+)@([^:/]+)(:[0-9]+)?/.*|\4|')

STAGING_DB="paperfull_dr_$(date +%Y%m%d%H%M%S)"
echo "[$(date -Is)] creating staging db: $STAGING_DB"
PGPASSWORD="$PG_PASS" createdb -h "$PG_HOST" -U "$PG_USER" "$STAGING_DB"

cleanup() {
  echo "[$(date -Is)] dropping staging db: $STAGING_DB"
  PGPASSWORD="$PG_PASS" dropdb -h "$PG_HOST" -U "$PG_USER" --if-exists "$STAGING_DB" || true
}
trap cleanup EXIT

echo "[$(date -Is)] restoring $DUMP → $STAGING_DB"
gunzip -c "$DUMP" | PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -U "$PG_USER" -d "$STAGING_DB" -q

# Sanity row counts
echo "[$(date -Is)] sanity check — table counts:"
PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -U "$PG_USER" -d "$STAGING_DB" -At <<'SQL'
SELECT 'users:'         || count(*) FROM users
UNION ALL SELECT 'papers:'        || count(*) FROM papers
UNION ALL SELECT 'conversations:' || count(*) FROM conversations
UNION ALL SELECT 'chat_messages:' || count(*) FROM chat_messages
UNION ALL SELECT 'paper_files:'   || count(*) FROM paper_files
UNION ALL SELECT 'paper_images:'  || count(*) FROM paper_images;
SQL

echo "[$(date -Is)] DR drill PASS"
