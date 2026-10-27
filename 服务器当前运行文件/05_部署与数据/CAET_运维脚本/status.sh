#!/usr/bin/env bash
# CAET V1.2 服务状态总览（适配正式仓库结构）
# 显示: 4 Docker 服务、端口 80/443、磁盘、内存、Git commit/tag
set -euo pipefail

CAET_DIR="${CAET_DIR:-/opt/caet}"
cd "$CAET_DIR" 2>/dev/null || CAET_DIR="$(pwd)"

hr() { printf '%s\n' '============================================================'; }

hr
echo " CAET V1.2 服务状态   $(date '+%Y-%m-%d %H:%M:%S')"
hr

# ---- Git 信息 ----
echo
echo "▶ Git 版本"
if [ -d "$CAET_DIR/.git" ]; then
    HEAD=$(git -C "$CAET_DIR" rev-parse HEAD 2>/dev/null || echo "?")
    TAG=$(git -C "$CAET_DIR" describe --tags --exact-match HEAD 2>/dev/null || echo "detached")
    BR=$(git -C "$CAET_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")
    echo "  branch: $BR"
    echo "  tag:    $TAG"
    echo "  commit: ${HEAD:0:12}"
else
    echo "  非 git 仓库"
fi

# ---- Docker 服务 ----
echo
echo "▶ Docker 服务"
COMPOSE=(docker compose -f "$CAET_DIR/docker-compose.yml")
if command -v docker >/dev/null 2>&1; then
    "${COMPOSE[@]}" ps --format "table {{.Service}}\t{{.State}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null \
        || "${COMPOSE[@]}" ps
else
    echo "  ⚠️ docker 未安装"
fi

# ---- 端口 ----
echo
echo "▶ 端口 80 / 443"
if command -v ss >/dev/null 2>&1; then
    ss -tln 2>/dev/null | awk 'NR==1 || /:80 |:443 / {print "  " $0}'
elif command -v netstat >/dev/null 2>&1; then
    netstat -tln 2>/dev/null | awk 'NR<=2 || /:80 |:443 / {print "  " $0}'
fi

# ---- 磁盘 ----
echo
echo "▶ 磁盘 /"
df -h / | tail -1 | awk '{printf "  总 %s  已用 %s  可用 %s  使用率 %s\n", $2, $3, $4, $5}'
echo "▶ 磁盘 $CAET_DIR"
df -h "$CAET_DIR" | tail -1 | awk '{printf "  总 %s  已用 %s  可用 %s  使用率 %s\n", $2, $3, $4, $5}'

# ---- 内存 ----
echo
echo "▶ 内存"
free -h | awk 'NR==1 || NR==2 {print "  " $0}'

# ---- Docker 资源占用 ----
if command -v docker >/dev/null 2>&1; then
    echo
    echo "▶ Docker 资源（top 5）"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>/dev/null \
        | head -n 6 || true
fi

# ---- caet_uploads 卷 ----
if docker volume inspect caet_uploads >/dev/null 2>&1; then
    echo
    echo "▶ caet_uploads 卷"
    CNT=$(docker run --rm -v caet_uploads:/data alpine sh -c "find /data -type f | wc -l" 2>/dev/null || echo "?")
    SIZE=$(docker run --rm -v caet_uploads:/data alpine sh -c "du -sh /data | cut -f1" 2>/dev/null || echo "?")
    echo "  文件数: $CNT  体积: $SIZE"
fi

hr