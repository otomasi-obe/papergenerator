#!/bin/bash
# infra/scripts/pg-backup.sh — daily PostgreSQL backup with rotation.
#
# Layout (under $BACKUP_ROOT):
#   daily/    pg-YYYY-MM-DD.sql.gz   keep 7
#   weekly/   pg-YYYY-Www.sql.gz     keep 4   (snapshot every Monday)
#   monthly/  pg-YYYY-MM.sql.gz      keep 6   (snapshot 1st of month)
#
# Each file ships a sidecar .sha256 for integrity check.
#
# Cron entry (run as the user that owns BACKUP_ROOT, e.g. sirobo):
#   0 2 * * * /home/sirobo/papergenerator/infra/scripts/pg-backup.sh >> /var/log/paperfull-backup.log 2>&1
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/home/sirobo/papergenerator}"
BACKUP_ROOT="${BACKUP_ROOT:-/home/sirobo/papergenerator/backups}"
ENV_FILE="${ENV_FILE:-${PROJECT_ROOT}/backend/.env}"

mkdir -p "${BACKUP_ROOT}/daily" "${BACKUP_ROOT}/weekly" "${BACKUP_ROOT}/monthly"

# Read DATABASE_URL from .env
if [ ! -r "$ENV_FILE" ]; then
  echo "ENV file not readable: $ENV_FILE" >&2
  exit 1
fi
DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' )
if [ -z "$DATABASE_URL" ]; then
  echo "DATABASE_URL not found in $ENV_FILE" >&2
  exit 1
fi

# Parse postgres://user:pass@host:port/db
PG_USER=$(echo "$DATABASE_URL"   | sed -E 's|postgres(ql)?://([^:]+):([^@]+)@([^:/]+)(:[0-9]+)?/([^?]+).*|\2|')
PG_PASS=$(echo "$DATABASE_URL"   | sed -E 's|postgres(ql)?://([^:]+):([^@]+)@([^:/]+)(:[0-9]+)?/([^?]+).*|\3|')
PG_HOST=$(echo "$DATABASE_URL"   | sed -E 's|postgres(ql)?://([^:]+):([^@]+)@([^:/]+)(:[0-9]+)?/([^?]+).*|\4|')
PG_PORT=$(echo "$DATABASE_URL"   | sed -E 's|postgres(ql)?://([^:]+):([^@]+)@([^:/]+):?([0-9]+)?/([^?]+).*|\5|' | tr -d ':')
PG_DB=$(echo "$DATABASE_URL"     | sed -E 's|postgres(ql)?://([^:]+):([^@]+)@([^:/]+)(:[0-9]+)?/([^?]+).*|\6|')
PG_PORT="${PG_PORT:-5432}"

today=$(date +%F)
weekly_key=$(date +%Y-W%V)
monthly_key=$(date +%Y-%m)
day_of_week=$(date +%u)   # 1=Mon..7=Sun
day_of_month=$(date +%d)

daily_path="${BACKUP_ROOT}/daily/pg-${today}.sql.gz"

echo "[$(date -Is)] starting pg_dump → $daily_path"
PGPASSWORD="$PG_PASS" pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" \
  --format=plain --no-owner --no-privileges "$PG_DB" \
  | gzip -9 > "${daily_path}.tmp"
mv "${daily_path}.tmp" "$daily_path"
sha256sum "$daily_path" | awk '{print $1}' > "${daily_path}.sha256"

# Weekly snapshot every Monday
if [ "$day_of_week" = "1" ]; then
  cp -f "$daily_path" "${BACKUP_ROOT}/weekly/pg-${weekly_key}.sql.gz"
  cp -f "${daily_path}.sha256" "${BACKUP_ROOT}/weekly/pg-${weekly_key}.sql.gz.sha256"
fi

# Monthly snapshot on the 1st
if [ "$day_of_month" = "01" ]; then
  cp -f "$daily_path" "${BACKUP_ROOT}/monthly/pg-${monthly_key}.sql.gz"
  cp -f "${daily_path}.sha256" "${BACKUP_ROOT}/monthly/pg-${monthly_key}.sql.gz.sha256"
fi

# Rotation
find "${BACKUP_ROOT}/daily"   -name "pg-*.sql.gz" -mtime +7  -delete
find "${BACKUP_ROOT}/daily"   -name "pg-*.sql.gz.sha256" -mtime +7  -delete
find "${BACKUP_ROOT}/weekly"  -name "pg-*.sql.gz" -mtime +28 -delete
find "${BACKUP_ROOT}/weekly"  -name "pg-*.sql.gz.sha256" -mtime +28 -delete
find "${BACKUP_ROOT}/monthly" -name "pg-*.sql.gz" -mtime +186 -delete
find "${BACKUP_ROOT}/monthly" -name "pg-*.sql.gz.sha256" -mtime +186 -delete

size=$(du -h "$daily_path" | cut -f1)
echo "[$(date -Is)] backup complete (${size}) → $daily_path"
