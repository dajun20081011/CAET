#!/usr/bin/env bash
# CAET V1.2 快速健康检查；Compose services: api/nginx/postgres/redis。
set -uo pipefail
CAET_DIR="${CAET_DIR:-/opt/caet}"
DOMAIN="${DOMAIN:-crew.cabinvoice.cn}"
cd "$CAET_DIR" 2>/dev/null || { echo "❌ CAET 目录不存在" >&2; exit 1; }
COMPOSE=(docker compose -f "$CAET_DIR/docker-compose.yml")
PASS=0; FAIL=0; NOTES=()
ok(){ echo "  ✅ $1"; PASS=$((PASS+1)); }
bad(){ echo "  ❌ $1 — $2"; FAIL=$((FAIL+1)); NOTES+=("$1: $2"); }
code(){ curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$1" 2>/dev/null || printf 000; }

echo "CAET V1.2 healthcheck v5 — $(date '+%Y-%m-%d %H:%M:%S')"

RUNNING=$("${COMPOSE[@]}" ps --services --status running 2>/dev/null || true)
for service in api nginx postgres redis; do
  echo "$RUNNING" | grep -qx "$service" && ok "$service running" || bad "$service" "not running"
done

NG=$("${COMPOSE[@]}" exec -T nginx nginx -t 2>&1)
[ $? -eq 0 ] && echo "$NG" | grep -q 'test is successful' && ok "nginx -t" || bad "nginx -t" "$NG"

HC=$(code "http://$DOMAIN/"); SC=$(code "https://$DOMAIN/")
case "$HC" in 301|308) ok "HTTP redirect $HC" ;; *) bad "HTTP redirect" "$HC" ;; esac
[ "$SC" = 200 ] && ok "HTTPS 200" || bad "HTTPS" "$SC"
[ "$(code "https://$DOMAIN/api/health")" = 200 ] && ok "API health 200" || bad "API health" "not 200"

PG_USER=$("${COMPOSE[@]}" exec -T postgres sh -c 'printf "%s" "${POSTGRES_USER:-}"' 2>/dev/null || true)
PG_DB=$("${COMPOSE[@]}" exec -T postgres sh -c 'printf "%s" "${POSTGRES_DB:-}"' 2>/dev/null || true)
PG=$("${COMPOSE[@]}" exec -T postgres psql -U "$PG_USER" -d "$PG_DB" -tAc 'SELECT 1' 2>&1)
[ "$PG" = 1 ] && ok "PostgreSQL connected" || bad "PostgreSQL" "$PG"

RD=$("${COMPOSE[@]}" exec -T redis redis-cli ping 2>&1)
[ "$RD" = PONG ] && ok "Redis PONG" || bad "Redis" "$RD"

DIST="$CAET_DIR/frontend/dist/index.html"
[ -f "$DIST" ] && ok "frontend/dist/index.html" || bad "Frontend" "missing $DIST"
for route in /login /student/tasks /admin/dashboard; do
  [ "$(code "https://$DOMAIN$route")" = 200 ] && ok "SPA $route" || bad "SPA $route" "not 200"
done

API_CID=$("${COMPOSE[@]}" ps -q api 2>/dev/null || true)
MOUNTS=$(docker inspect --format '{{range .Mounts}}{{println .Destination}}{{end}}' "$API_CID" 2>/dev/null || true)
if echo "$MOUNTS" | grep -qx '/app/uploads'; then
  WR=$("${COMPOSE[@]}" exec -T api sh -c 'test -w /app/uploads && f=/app/uploads/.hc_$$ && : > "$f" && rm -f "$f"' 2>&1)
  [ $? -eq 0 ] && ok "uploads writable" || bad "uploads" "$WR"
else
  bad "uploads mount" "/app/uploads not mounted"
fi

echo "RESULT: PASS=$PASS FAIL=$FAIL"
if [ "$FAIL" -eq 0 ]; then echo ">>> GO <<<"; exit 0; fi
printf ' - %s\n' "${NOTES[@]}"
echo ">>> NO-GO <<<"
exit 1
