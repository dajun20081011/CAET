#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WITH_DOCKER=false
[[ "${1:-}" == "--with-docker" ]] && WITH_DOCKER=true

bash "$ROOT/scripts/secret-scan.sh"
bash -n "$ROOT/scripts/rollback.sh"
bash -n "$ROOT/scripts/candidate-e2e.sh"
bash "$ROOT/scripts/verify-rollback.sh"

if grep -RIE 'X-User-Id|X-Product-Code|X-Permissions' "$ROOT/backend-package/backend/app" "$ROOT/frontend/src"; then
  echo "HEADER_TRUST_SCAN=FAIL"
  exit 1
fi
echo "HEADER_TRUST_SCAN=PASS"

if grep -RIE 'staging-learner|staging-admin|staging-evaluator|CABIN-DEMO-001' "$ROOT/frontend/src" "$ROOT/backend-package/backend/app"; then
  echo "DEMO_RUNTIME_SCAN=FAIL"
  exit 1
fi
echo "DEMO_RUNTIME_SCAN=PASS"

if [[ "$WITH_DOCKER" == true ]]; then
  bash "$ROOT/scripts/candidate-e2e.sh"
else
  echo "DOCKER_E2E=SKIPPED"
fi
