#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)

BAD_NAMES=$(find "$ROOT" -type f \( -name '.env' -o -name '*.key' -o -name '*.crt' -o -name '*.pem' -o -name '*.csr' \) -print)
[[ -z "$BAD_NAMES" ]] || { echo "$BAD_NAMES"; echo "SECRET_SCAN=FAIL"; exit 1; }

BAD_DIRS=$(find "$ROOT" -type d \( -name uploads -o -name backups -o -name node_modules -o -name dist \) -print)
[[ -z "$BAD_DIRS" ]] || { echo "$BAD_DIRS"; echo "SECRET_SCAN=FAIL"; exit 1; }

if grep -RIE --exclude='*.example' --exclude='package-lock.json' \
  'BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}' "$ROOT"; then
  echo "SECRET_SCAN=FAIL"
  exit 1
fi

echo "SECRET_SCAN=PASS"
