#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env.staging}"
COMPOSE_FILE="${PHASE5_COMPOSE_FILE:-docker-compose.staging.yml}"
BASE_URL="${PHASE5_BASE_URL:-http://127.0.0.1:18080}"
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
for migration in 0006_admin_course_catalog.sql 0007_learner_training_loop.sql 0008_instructor_review_loop.sql; do
  "${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "backend-package/backend/migrations/$migration"
done
"${compose[@]}" up -d --build api nginx
curl -fsS "$BASE_URL/api/v1/core/health" | grep -q '"status":"ok"'
openapi=$(curl -fsS "$BASE_URL/openapi.json")
grep -q '/api/v1/cabinlingo/instructor/reviews/queue' <<<"$openapi"
grep -q '/api/v1/cabinlingo/instructor/audio/{recording_id}' <<<"$openapi"
grep -q '/api/v1/cabinlingo/instructor/analytics/classes' <<<"$openapi"
"${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('cl_instructor_reviews','cl_remediation_requests');" | grep -qx '2'
"${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
  "SELECT count(*) FROM permissions WHERE code IN ('cabinlingo:review.practice','cabinlingo:review.exam','cabinlingo:analytics.class');" | grep -qx '3'
[[ "$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/api/v1/cabinlingo/instructor/reviews/queue")" == "401" ]]

echo 'PHASE5_MIGRATION=PASS'
echo 'PHASE5_RBAC=PASS'
echo 'PHASE5_OPENAPI=PASS'
echo 'PHASE5_HEALTH=PASS'
echo '>>> CABINLINGO PHASE5 STAGING VERIFY GO <<<'
