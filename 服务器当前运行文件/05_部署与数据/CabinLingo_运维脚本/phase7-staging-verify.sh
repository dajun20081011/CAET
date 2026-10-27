#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env.staging}"
COMPOSE_FILE="${PHASE7_COMPOSE_FILE:-docker-compose.staging.yml}"
TEST_AUDIO="${PHASE7_TEST_AUDIO_FILE:-}"
BASE_URL="${PHASE7_BASE_URL:-http://127.0.0.1:28080}"
[[ -f "$ENV_FILE" ]] || { echo "Missing staging env file: $ENV_FILE" >&2; exit 1; }
[[ -f "$COMPOSE_FILE" ]] || { echo "Missing staging compose file: $COMPOSE_FILE" >&2; exit 1; }

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
export PHASE7_ENV_FILE="$ENV_FILE"
[[ "${APP_ENV:-}" == "staging" ]] || { echo "APP_ENV must be staging" >&2; exit 1; }
ai_enabled="${AI_GATEWAY_ENABLED:-false}"
if [[ "$ai_enabled" == "true" ]]; then
  [[ -f "$TEST_AUDIO" ]] || { echo "Set PHASE7_TEST_AUDIO_FILE to a non-production test recording" >&2; exit 1; }
  for name in ASR_IAT_ENDPOINT ISE_ENDPOINT SUNTONE_ENDPOINT; do
    [[ -n "${!name:-}" && "${!name}" != *'<'* ]] || { echo "$name is not configured" >&2; exit 1; }
  done
fi

compose=(docker compose -p "${PHASE7_PROJECT_NAME:-cabinlingo-phase7-staging}" --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
"${compose[@]}" config --quiet
"${compose[@]}" up -d postgres redis
for _ in $(seq 1 30); do
  "${compose[@]}" exec -T postgres pg_isready -U "${POSTGRES_USER:?}" -d "${POSTGRES_DB:?}" >/dev/null 2>&1 && break
  sleep 1
done
for migration in backend-package/backend/migrations/*.sql; do
  echo "Applying $migration"
  "${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$migration"
done
"${compose[@]}" up -d --build api nginx
curl -fsS "$BASE_URL/api/v1/core/health" | grep -q '"status":"ok"'
curl -fsS "$BASE_URL/openapi.json" | grep -q '/api/v1/ai/status'

if [[ "$ai_enabled" == "true" ]]; then
  container_audio="/tmp/phase7-provider-smoke.${TEST_AUDIO##*.}"
  "${compose[@]}" cp "$TEST_AUDIO" "api:$container_audio"
  "${compose[@]}" exec -T -e PHASE7_REFERENCE_TEXT="${PHASE7_REFERENCE_TEXT:-Ladies and gentlemen, welcome aboard.}" api \
    python -m app.integrations.provider_smoke "$container_audio"
  "${compose[@]}" exec -T api rm -f "$container_audio"
  echo 'PHASE7_PROVIDER_CONTRACT=PASS'
else
  echo 'PHASE7_PROVIDER_CONTRACT=SKIP_AI_DISABLED'
fi

echo 'PHASE7_MIGRATION=PASS'
echo 'PHASE7_STORAGE=PASS'
echo 'PHASE7_HEALTH=PASS'
echo '>>> CABINLINGO PHASE7 STAGING VERIFY GO <<<'
