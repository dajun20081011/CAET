#!/usr/bin/env bash
# CAET V1.2 生产验收：适配 Compose services api/nginx/postgres/redis。
# 默认只读；--with-backup 会执行一次真实备份验证。
set -uo pipefail

CAET_DIR="${CAET_DIR:-/opt/caet}"
DOMAIN="${DOMAIN:-crew.cabinvoice.cn}"
WITH_BACKUP=false
for arg in "$@"; do
  case "$arg" in
    --with-backup) WITH_BACKUP=true ;;
    -h|--help) sed -n '1,12p' "$0"; exit 0 ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

cd "$CAET_DIR" 2>/dev/null || { echo "❌ 生产目录不存在: $CAET_DIR" >&2; exit 1; }
[ -f docker-compose.yml ] || { echo "❌ docker-compose.yml 不存在" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ docker 不可用" >&2; exit 1; }

COMPOSE=(docker compose -f "$CAET_DIR/docker-compose.yml")
PASS=0; FAIL=0; SKIPPED=0; FAIL_LIST=()
ok() { echo "  ✅ $1"; PASS=$((PASS+1)); }
bad() { echo "  ❌ $1 — $2"; FAIL=$((FAIL+1)); FAIL_LIST+=("$1: $2"); }
skip() { echo "  ⏭ $1 — $2"; SKIPPED=$((SKIPPED+1)); }
section() { printf '\n[%s] %s\n' "$1" "$2"; }
http_code() { curl -sS -o /dev/null -w '%{http_code}' --max-time 12 "$1" 2>/dev/null || printf '000'; }

echo "============================================================"
echo " CAET V1.2 Production Acceptance"
echo " TIME=$(date '+%Y-%m-%d %H:%M:%S')"
echo " DIR=$CAET_DIR DOMAIN=$DOMAIN WITH_BACKUP=$WITH_BACKUP"
echo "============================================================"

section 1 "Docker services"
CONFIG_OUT=$("${COMPOSE[@]}" config 2>&1)
CONFIG_RC=$?
if [ "$CONFIG_RC" -ne 0 ]; then bad "docker compose config" "$CONFIG_OUT"; else ok "docker compose config"; fi
PS_OUT=$("${COMPOSE[@]}" ps 2>&1)
PS_RC=$?
if [ "$PS_RC" -ne 0 ]; then bad "docker compose ps" "$PS_OUT"; else ok "docker compose ps"; fi
RUNNING=$("${COMPOSE[@]}" ps --services --status running 2>/dev/null || true)
for service in api nginx postgres redis; do
  if printf '%s\n' "$RUNNING" | grep -qx "$service"; then ok "service $service running"; else bad "service $service running" "未出现在运行服务列表"; fi
done

section 2 "Nginx"
NGINX_OUT=$("${COMPOSE[@]}" exec -T nginx nginx -t 2>&1)
if [ $? -eq 0 ] && printf '%s' "$NGINX_OUT" | grep -q 'test is successful'; then ok "nginx -t"; else bad "nginx -t" "$NGINX_OUT"; fi

section 3 "HTTP / HTTPS / API"
HTTP_CODE=$(http_code "http://$DOMAIN/")
HTTPS_CODE=$(http_code "https://$DOMAIN/")
case "$HTTP_CODE" in 301|308) ok "HTTP redirects to HTTPS ($HTTP_CODE)" ;; *) bad "HTTP redirect" "code=$HTTP_CODE" ;; esac
[ "$HTTPS_CODE" = "200" ] && ok "HTTPS home 200" || bad "HTTPS home" "code=$HTTPS_CODE"
HEALTH_BODY=$(curl -sS --max-time 12 "https://$DOMAIN/api/health" 2>/dev/null || true)
HEALTH_CODE=$(http_code "https://$DOMAIN/api/health")
if [ "$HEALTH_CODE" = "200" ] && printf '%s' "$HEALTH_BODY" | grep -q '"status"'; then ok "API health 200"; else bad "API health" "code=$HEALTH_CODE body=$HEALTH_BODY"; fi

section 4 "PostgreSQL"
PG_USER=$("${COMPOSE[@]}" exec -T postgres sh -c 'printf "%s" "${POSTGRES_USER:-}"' 2>/dev/null || true)
PG_DB=$("${COMPOSE[@]}" exec -T postgres sh -c 'printf "%s" "${POSTGRES_DB:-}"' 2>/dev/null || true)
if [ -z "$PG_USER" ] || [ -z "$PG_DB" ]; then
  bad "PostgreSQL environment" "POSTGRES_USER 或 POSTGRES_DB 为空"
else
  ok "PostgreSQL environment discovered"
  PG_CONNECT=$("${COMPOSE[@]}" exec -T postgres psql -U "$PG_USER" -d "$PG_DB" -tAc 'SELECT 1' 2>&1)
  [ "$PG_CONNECT" = "1" ] && ok "PostgreSQL connection" || bad "PostgreSQL connection" "$PG_CONNECT"
  TABLE_OUT=$("${COMPOSE[@]}" exec -T postgres psql -U "$PG_USER" -d "$PG_DB" -c '\dt' 2>&1)
  if [ $? -eq 0 ] && ! printf '%s' "$TABLE_OUT" | grep -qi 'Did not find any relations' && printf '%s' "$TABLE_OUT" | grep -q '|'; then ok "PostgreSQL business tables exist"; else bad "PostgreSQL business tables" "$TABLE_OUT"; fi
fi

section 5 "Redis"
REDIS_OUT=$("${COMPOSE[@]}" exec -T redis redis-cli ping 2>&1)
[ "$REDIS_OUT" = "PONG" ] && ok "Redis PING=PONG" || bad "Redis PING" "$REDIS_OUT"

section 6 "Frontend and SPA"
DIST_DIR="$CAET_DIR/frontend/dist"
INDEX="$DIST_DIR/index.html"
if [ -f "$INDEX" ]; then
  ok "frontend/dist/index.html exists"
  JS_PATH=$(grep -oE '/assets/[^" ]+\.js' "$INDEX" | head -1 || true)
  CSS_PATH=$(grep -oE '/assets/[^" ]+\.css' "$INDEX" | head -1 || true)
  [ -n "$JS_PATH" ] && [ -f "$DIST_DIR$JS_PATH" ] && ok "frontend JS exists" || bad "frontend JS" "path=$JS_PATH"
  [ -n "$CSS_PATH" ] && [ -f "$DIST_DIR$CSS_PATH" ] && ok "frontend CSS exists" || bad "frontend CSS" "path=$CSS_PATH"
  [ -n "$JS_PATH" ] && [ "$(http_code "https://$DOMAIN$JS_PATH")" = "200" ] && ok "frontend JS HTTP 200" || bad "frontend JS HTTP" "path=$JS_PATH"
  [ -n "$CSS_PATH" ] && [ "$(http_code "https://$DOMAIN$CSS_PATH")" = "200" ] && ok "frontend CSS HTTP 200" || bad "frontend CSS HTTP" "path=$CSS_PATH"
else
  bad "frontend dist" "缺失 $INDEX"
fi
for route in /login /student/tasks /admin/dashboard; do
  ROUTE_BODY=$(curl -sS --max-time 12 "https://$DOMAIN$route" 2>/dev/null || true)
  ROUTE_CODE=$(http_code "https://$DOMAIN$route")
  if [ "$ROUTE_CODE" = "200" ] && printf '%s' "$ROUTE_BODY" | grep -q '<div id="app">'; then ok "SPA route $route"; else bad "SPA route $route" "code=$ROUTE_CODE"; fi
done

section 7 "Storage mount"
API_CID=$("${COMPOSE[@]}" ps -q api 2>/dev/null || true)
if [ -z "$API_CID" ]; then
  bad "api container" "无法从 Compose service api 获取容器 ID"
else
  MOUNTS=$(docker inspect --format '{{range .Mounts}}{{println .Type .Name .Source .Destination}}{{end}}' "$API_CID" 2>/dev/null || true)
  UPLOAD_MOUNT=$(printf '%s\n' "$MOUNTS" | awk '$NF=="/app/uploads" {print; exit}')
  if [ -n "$UPLOAD_MOUNT" ]; then
    ok "uploads mount discovered"
    WRITE_OUT=$("${COMPOSE[@]}" exec -T api sh -c 'test -d /app/uploads && test -w /app/uploads && f=/app/uploads/.caet_accept_$$ && : > "$f" && rm -f "$f"' 2>&1)
    [ $? -eq 0 ] && ok "uploads mount writable" || bad "uploads writable" "$WRITE_OUT"
  else
    bad "uploads mount" "未发现挂载到 /app/uploads 的卷或目录"
  fi
fi

section 8 "Security and Git"
if [ -d "$CAET_DIR/.git" ]; then
  TRACKED=$(git -C "$CAET_DIR" ls-files 2>/dev/null | grep -Ei '(^|/)\.env$|\.(key|crt|pem|csr)$' || true)
  [ -z "$TRACKED" ] && ok "Git tracks no secrets/certificates" || bad "Git tracked sensitive files" "$TRACKED"
  HEAD_NOW=$(git -C "$CAET_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)
  TAG_NOW=$(git -C "$CAET_DIR" describe --tags --always 2>/dev/null || echo unknown)
  ok "Git information: $HEAD_NOW ($TAG_NOW)"
else
  skip "Git inspection" "$CAET_DIR is not a Git repository"
fi

section 9 "Published ports"
PORTS=$("${COMPOSE[@]}" ps --format '{{.Ports}}' 2>/dev/null || true)
UNEXPECTED=$(printf '%s\n' "$PORTS" | grep -oE '(^|[,:])([0-9]{1,5})->' | grep -vE '(^|[,:])(80|443)->' || true)
[ -z "$UNEXPECTED" ] && ok "Only ports 80/443 published" || bad "Unexpected published ports" "$UNEXPECTED"

section 10 "Backup"
if [ "$WITH_BACKUP" = "true" ]; then
  BACKUP_LOG=$(mktemp)
  if bash "$CAET_DIR/scripts/backup.sh" >"$BACKUP_LOG" 2>&1; then
    ok "backup.sh completed"
    if grep -q 'SHA256' "$BACKUP_LOG" || find "$CAET_DIR/backups" -name 'SHA256SUMS*' -type f -print -quit 2>/dev/null | grep -q .; then ok "backup checksum metadata exists"; else bad "backup checksum" "未发现 SHA256 校验信息"; fi
  else
    bad "backup.sh" "$(tail -20 "$BACKUP_LOG")"
  fi
  rm -f "$BACKUP_LOG"
else
  skip "Backup verification" "use --with-backup for final production acceptance"
fi

echo
echo "============================================================"
echo "RESULT: PASS=$PASS FAIL=$FAIL SKIPPED=$SKIPPED"
if [ "$FAIL" -gt 0 ]; then printf ' - %s\n' "${FAIL_LIST[@]}"; fi
if [ "$FAIL" -eq 0 ] && [ "$SKIPPED" -eq 0 ]; then echo ">>> GO <<<"; exit 0; fi
echo ">>> NO-GO <<<"
exit 1
