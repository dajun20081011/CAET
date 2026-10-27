#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/backup/app" "$TMP/project"
printf 'safe\n' > "$TMP/backup/app/version.txt"
tar -czf "$TMP/backup/production-files.tar.gz" -C "$TMP/backup" app
printf 'placeholder\n' > "$TMP/backup/postgresql.dump"
(cd "$TMP/backup" && sha256sum production-files.tar.gz postgresql.dump > SHA256SUMS)
bash "$ROOT/scripts/rollback.sh" --backup "$TMP/backup" --project-dir "$TMP/project" | grep -q 'ROLLBACK_DRY_RUN=PASS'
echo "ROLLBACK_VERIFY=PASS"
