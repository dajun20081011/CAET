#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://localhost}"
curl --fail --silent --show-error --insecure "$BASE_URL/api/v1/core/health"
printf '\n'
curl --fail --silent --show-error --insecure -I "$BASE_URL/" | head -n 1
echo 'SMOKE=PASS'
