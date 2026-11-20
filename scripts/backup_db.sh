#!/bin/sh
# pg_dump the bot database into BACKUP_DIR, then drop dumps older than
# BACKUP_RETENTION_DAYS. Never prints the password or the full URL.
set -eu

BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

url="$DATABASE_URL"
url="${url#*://}"
userpass="${url%%@*}"
hostpart="${url#*@}"
dbuser="${userpass%%:*}"
dbpass="${userpass#*:}"
hostport="${hostpart%%/*}"
dbname="${hostpart#*/}"
dbname="${dbname%%\?*}"
dbhost="${hostport%%:*}"
dbport="${hostport##*:}"
if [ "$dbport" = "$dbhost" ]; then
  dbport=5432
fi

mkdir -p "$BACKUP_DIR"
stamp=$(date -u +%Y%m%d-%H%M%S)
target="$BACKUP_DIR/ritm-${stamp}.dump"

# shellcheck disable=SC2034
export PGPASSWORD="$dbpass"
case "$DATABASE_URL" in
  *sslmode=*|*[?\&]ssl=*|*neon.tech*)
    export PGSSLMODE="${PGSSLMODE:-require}"
    ;;
esac
if ! pg_dump -Fc -h "$dbhost" -p "$dbport" -U "$dbuser" -d "$dbname" -f "$target"; then
  unset PGPASSWORD
  echo "pg_dump failed" >&2
  exit 1
fi
unset PGPASSWORD
echo "backup written"

if [ "$BACKUP_RETENTION_DAYS" -gt 0 ] 2>/dev/null; then
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'ritm-*.dump'     -mtime +$((BACKUP_RETENTION_DAYS - 1)) -delete 2>/dev/null || true
fi
