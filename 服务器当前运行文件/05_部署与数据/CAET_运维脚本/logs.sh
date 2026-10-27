#!/usr/bin/env bash
# CAET V1.2 日志查看（默认 200 行，绝不无限输出）
# 用法:
#   bash scripts/logs.sh                # 全部
#   bash scripts/logs.sh frontend       # 前端容器（含 nginx）
#   bash scripts/logs.sh backend        # 后端 FastAPI
#   bash scripts/logs.sh postgres
#   bash scripts/logs.sh redis
#   bash scripts/logs.sh nginx          # 同 frontend（容器内 nginx）
#   TAIL=500 bash scripts/logs.sh backend
set -euo pipefail

CAET_DIR="${CAET_DIR:-/opt/caet}"
cd "$CAET_DIR" 2>/dev/null || CAET_DIR="$(pwd)"

SVC="${1:-all}"
TAIL="${TAIL:-200}"

case "$SVC" in
    frontend|backend|postgres|redis|nginx|api|all) ;;
    *)
        echo "用法: $0 [frontend|backend|postgres|redis|nginx|api|all]  (TAIL 默认 200)" >&2
        exit 2
        ;;
esac

# 用户语义 -> compose 服务名映射
map_svc() {
    case "$1" in
        frontend|nginx) echo "caet-frontend" ;;
        backend|api)    echo "caet-backend" ;;
        postgres)       echo "caet-postgres" ;;
        redis)          echo "caet-redis" ;;
    esac
}

COMPOSE=(docker compose -f "$CAET_DIR/docker-compose.yml")

echo "============================================================"
echo " CAET V1.2 日志   service=$SVC   tail=$TAIL   $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

if [ "$SVC" = "all" ]; then
    "${COMPOSE[@]}" logs --tail="$TAIL" --no-color --no-log-prefix
else
    REAL=$(map_svc "$SVC")
    "${COMPOSE[@]}" logs --tail="$TAIL" --no-color --no-log-prefix "$REAL"
fi

echo
echo "(最近 $TAIL 行；TAIL=N 自定义)"