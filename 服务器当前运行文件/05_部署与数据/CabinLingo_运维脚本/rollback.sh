#!/usr/bin/env bash
set -euo pipefail

BACKUP_PATH=""
PROJECT_DIR="/opt/caet"
EXECUTE=false
WITH_DATABASE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup) BACKUP_PATH="$2"; shift 2 ;;
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    --execute) EXECUTE=true; shift ;;
    --with-database) WITH_DATABASE=true; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$BACKUP_PATH" ]] || { echo "--backup is required" >&2; exit 2; }
BACKUP_PATH=$(realpath "$BACKUP_PATH")
PROJECT_DIR=$(realpath "$PROJECT_DIR")
[[ -f "$BACKUP_PATH/SHA256SUMS" ]] || { echo "Missing SHA256SUMS" >&2; exit 1; }
[[ -f "$BACKUP_PATH/production-files.tar.gz" ]] || { echo "Missing production-files.tar.gz" >&2; exit 1; }
[[ -f "$BACKUP_PATH/postgresql.dump" ]] || { echo "Missing postgresql.dump" >&2; exit 1; }
(cd "$BACKUP_PATH" && sha256sum -c SHA256SUMS)
if tar -tzf "$BACKUP_PATH/production-files.tar.gz" | grep -Eq '(^|/)\.env($|\.)'; then
  echo "Backup archive unexpectedly contains .env" >&2
  exit 1
fi

echo "ROLLBACK_BACKUP=$BACKUP_PATH"
echo "ROLLBACK_PROJECT=$PROJECT_DIR"
echo "ROLLBACK_DATABASE=$WITH_DATABASE"

if [[ "$EXECUTE" != true ]]; then
  echo "ROLLBACK_DRY_RUN=PASS"
  exit 0
fi

case "$BACKUP_PATH" in
  "$PROJECT_DIR"/releases/backups/*) ;;
  *) echo "Execute mode requires a backup under $PROJECT_DIR/releases/backups" >&2; exit 1 ;;
esac

cd "$PROJECT_DIR"
docker compose stop api nginx
tar -xzf "$BACKUP_PATH/production-files.tar.gz" -C "$PROJECT_DIR"
if [[ "$WITH_DATABASE" == true ]]; then
  docker compose exec -T postgres sh -lc \
    'pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    < "$BACKUP_PATH/postgresql.dump"
fi
docker compose up -d
docker compose exec -T nginx nginx -t
docker compose ps
echo "ROLLBACK_EXECUTE=PASS"
