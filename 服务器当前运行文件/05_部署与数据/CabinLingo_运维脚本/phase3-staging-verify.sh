#!/usr/bin/env bash
set -euo pipefail

# Explicit staging-only verifier. It never targets production implicitly.
ENV_FILE="${1:-.env.staging}"
COMPOSE_FILE="${PHASE3_COMPOSE_FILE:-docker-compose.staging.yml}"
BASE_URL="${PHASE3_BASE_URL:-http://127.0.0.1:18080}"

[[ -f "$ENV_FILE" ]] || { echo "Missing staging env file: $ENV_FILE" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
[[ "${APP_ENV:-}" == "staging" ]] || { echo "APP_ENV must be staging" >&2; exit 1; }
[[ -f "$COMPOSE_FILE" ]] || { echo "Missing staging compose file: $COMPOSE_FILE" >&2; exit 1; }

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
"${compose[@]}" config --quiet
"${compose[@]}" up -d postgres redis

for _ in $(seq 1 30); do
  if "${compose[@]}" exec -T postgres pg_isready -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:?}" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
"${compose[@]}" exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
"${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < backend-package/backend/migrations/0006_admin_course_catalog.sql
"${compose[@]}" up -d --build api nginx

curl -fsS "$BASE_URL/api/v1/core/health" | grep -q '"status":"ok"'
"${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('cl_courses','cl_course_versions','cl_chapters','cl_content_items','class_memberships');" | grep -qx '5'

echo 'PHASE3_MIGRATION=PASS'
echo 'PHASE3_HEALTH=PASS'
echo '>>> CABINLINGO PHASE3 STAGING VERIFY GO <<<'

