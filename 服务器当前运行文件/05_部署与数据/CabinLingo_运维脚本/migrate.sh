#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
ENV_FILE="${ENV_FILE:-.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "缺少 ${ENV_FILE}，停止迁移" >&2
  exit 1
fi

# Compose reads the env file for interpolation, but the psql command below
# also needs POSTGRES_USER/POSTGRES_DB in this shell.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

for migration in backend-package/backend/migrations/*.sql; do
  echo "Applying ${migration}"
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:?POSTGRES_USER required}" -d "${POSTGRES_DB:?POSTGRES_DB required}" < "$migration"
done
echo 'MIGRATION=PASS'
