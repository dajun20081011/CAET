#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env.staging}"
COMPOSE_FILE="${PHASE4_COMPOSE_FILE:-docker-compose.staging.yml}"
BASE_URL="${PHASE4_BASE_URL:-http://127.0.0.1:18080}"
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
  "${compose[@]}" exec -T postgres pg_isready -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:?}" >/dev/null 2>&1 && break
  sleep 1
done
"${compose[@]}" exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
for migration in 0006_admin_course_catalog.sql 0007_learner_training_loop.sql; do
  "${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "backend-package/backend/migrations/$migration"
done
"${compose[@]}" up -d --build api nginx
curl -fsS "$BASE_URL/api/v1/core/health" | grep -q '"status":"ok"'
curl -fsS "$BASE_URL/openapi.json" | grep -q '/api/v1/cabinlingo/learner/practice/attempts'
"${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('cl_teacher_feedback','cl_growth_events');" | grep -qx '2'
"${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
  "SELECT count(*) FROM information_schema.columns WHERE table_name='cl_practice_attempts' AND column_name IN ('content_item_id','correction_of_attempt_id','ai_status','score_summary','issues');" | grep -qx '5'

echo 'PHASE4_MIGRATION=PASS'
echo 'PHASE4_OPENAPI=PASS'
echo 'PHASE4_HEALTH=PASS'
echo '>>> CABINLINGO PHASE4 STAGING VERIFY GO <<<'

