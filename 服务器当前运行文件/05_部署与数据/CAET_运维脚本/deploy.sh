#!/usr/bin/env bash
# CAET V1.2 灰度部署（Git Tag 严格模式）
# 流程: precheck → 工作区检查 → 记录旧 commit → git fetch →
#       解析目标 commit → git checkout → 校验新 commit →
#       backup → build → nginx -t → up -d → healthcheck → 最终校验 → GO/NO-GO
# 用法:
#   bash scripts/deploy.sh
#   VERSION=v1.2.1-production bash scripts/deploy.sh
# 铁律:
#   - /opt/caet 必须是 Git 仓库
#   - 工作区必须干净（git status --porcelain 为空）
#   - git fetch / checkout 任一步失败立即退出
#   - 默认部署固定 Tag v1.2.0-production
#   - 禁止 merge / rebase / force reset
#   - 部署后实际 commit 必须等于目标 Tag 对应 commit
set -euo pipefail

CAET_DIR="${CAET_DIR:-/opt/caet}"
VERSION="${VERSION:-v1.2.0-production}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-0756ba83c085207934d11b05c97a39c8cb8b6519}"

cd "$CAET_DIR" 2>/dev/null || { echo "❌ CAET 目录不存在: $CAET_DIR" >&2; exit 1; }

log()  { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
err()  { printf '[%s] ❌ %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }
warn() { printf '[%s] ⚠  %s\n' "$(date '+%H:%M:%S')" "$*"; }

echo "============================================================"
echo " CAET 部署   $(date '+%Y-%m-%d %H:%M:%S')"
echo " CAET_DIR=$CAET_DIR"
echo " VERSION=$VERSION"
echo " EXPECTED_COMMIT=$EXPECTED_COMMIT"
echo "============================================================"

# === 1. precheck ===
echo
log "STEP 1/9 precheck"
[ -d "$CAET_DIR/.git" ]                 || { err "/opt/caet 不是 Git 仓库"; exit 1; }
[ -f "$CAET_DIR/docker-compose.yml" ]   || { err "docker-compose.yml 缺失"; exit 1; }
[ -f "$CAET_DIR/nginx.caet.conf" ]      || { err "nginx.caet.conf 缺失"; exit 1; }
[ -f "$CAET_DIR/Dockerfile" ]           || { err "Dockerfile 缺失"; exit 1; }
[ -d "$CAET_DIR/dist" ]                 || { err "dist/ 不存在"; exit 1; }
[ -d "$CAET_DIR/caet-backend" ]         || { err "caet-backend/ 不存在"; exit 1; }
command -v docker >/dev/null 2>&1 || { err "docker 未安装"; exit 1; }
AVAIL_GB=$(df -BG "$CAET_DIR" | awk 'NR==2 {gsub("G","",$4); print $4}')
[ "${AVAIL_GB:-0}" -ge 2 ] || { err "磁盘 < 2GB（${AVAIL_GB}G），拒绝"; exit 1; }
log "  ✅ 目录 / 文件 / docker / 磁盘全部就绪"

# === 2. 工作区干净 ===
echo
log "STEP 2/9 工作区干净检查"
DIRTY=$(git -C "$CAET_DIR" status --porcelain 2>/dev/null || echo "")
if [ -n "$DIRTY" ]; then
    err "工作区不干净:"
    echo "$DIRTY" | head -5
    err "请先 git commit 或 git stash 后重试"
    exit 1
fi
log "  ✅ 工作区干净"

# === 3. 记录旧 commit ===
echo
log "STEP 3/9 记录旧 commit"
OLD_COMMIT=$(git -C "$CAET_DIR" rev-parse HEAD 2>/dev/null || echo "")
OLD_TAG=$(git -C "$CAET_DIR" describe --tags --exact-match HEAD 2>/dev/null || echo "detached")
[ -n "$OLD_COMMIT" ] || { err "无法读取 HEAD"; exit 1; }
log "  old_commit=$OLD_COMMIT  old_tag=$OLD_TAG"

# === 4. git fetch ===
echo
log "STEP 4/9 git fetch --tags --prune"
git -C "$CAET_DIR" fetch --tags --prune 2>&1 | tail -5 \
    || { err "git fetch 失败；拒绝部署"; exit 1; }
log "  ✅ fetch 成功"

# === 5. 解析目标 commit ===
echo
log "STEP 5/9 解析目标 commit（VERSION=$VERSION）"
TARGET_COMMIT=$(git -C "$CAET_DIR" rev-parse "${VERSION}^{commit}" 2>/dev/null) \
    || { err "Tag $VERSION 不存在或解析失败"; exit 1; }
log "  target_commit=$TARGET_COMMIT"

# 比对 EXPECTED_COMMIT（若显式提供）
if [ -n "$EXPECTED_COMMIT" ] && [ "$TARGET_COMMIT" != "$EXPECTED_COMMIT" ]; then
    err "目标 commit 与 EXPECTED_COMMIT 不一致:"
    err "  target=$TARGET_COMMIT  expected=$EXPECTED_COMMIT"
    err "拒绝部署，防止误升级"
    exit 1
fi

# === 6. git checkout ===
echo
log "STEP 6/9 git checkout $VERSION"
if [ "$OLD_COMMIT" = "$TARGET_COMMIT" ]; then
    log "  已是目标 commit，跳过 checkout"
else
    # 禁止 merge / rebase / force reset；只允许 checkout Tag
    git -C "$CAET_DIR" checkout --detach "$VERSION" 2>&1 | tail -5 \
        || { err "git checkout 失败，拒绝部署"; exit 1; }
fi
log "  ✅ checkout 成功"

# === 7. 校验实际 commit ===
echo
log "STEP 7/9 校验实际 commit"
NEW_COMMIT=$(git -C "$CAET_DIR" rev-parse HEAD)
if [ "$NEW_COMMIT" != "$TARGET_COMMIT" ]; then
    err "commit 校验失败: 期望 $TARGET_COMMIT 实际 $NEW_COMMIT"
    err "回滚 checkout 到旧 commit $OLD_COMMIT"
    git -C "$CAET_DIR" checkout --detach "$OLD_COMMIT" >/dev/null 2>&1 || true
    exit 1
fi
log "  ✅ new_commit=$NEW_COMMIT 匹配 target"

# === 8. backup ===
echo
log "STEP 8/9 backup"
bash "$CAET_DIR/scripts/backup.sh" \
    || { err "backup 失败，拒绝继续部署"; exit 1; }
log "  ✅ backup 成功"

# === 9. build + nginx -t + up -d + healthcheck ===
echo
log "STEP 9a build"
docker compose -f "$CAET_DIR/docker-compose.yml" build \
    || { err "docker compose build 失败"; exit 1; }

log "STEP 9b nginx -t"
# 用临时 nginx 容器校验根 nginx.caet.conf
docker run --rm \
    -v "$CAET_DIR/nginx.caet.conf:/etc/nginx/conf.d/default.conf:ro" \
    nginx:alpine sh -c "nginx -t" 2>&1 \
    || { err "nginx -t 失败"; exit 1; }

log "STEP 9c docker compose up -d"
# 严禁 down -v；只 up -d 增量重启
docker compose -f "$CAET_DIR/docker-compose.yml" up -d \
    || { err "docker compose up -d 失败"; exit 1; }

log "STEP 9d healthcheck（等 10 秒）"
sleep 10
if ! bash "$CAET_DIR/scripts/healthcheck.sh"; then
    err "healthcheck 未通过，部署失败"
    err "建议: bash scripts/rollback.sh --dry-run  →  bash scripts/rollback.sh"
    exit 1
fi

# === 10. 最终 commit 校验 ===
FINAL_COMMIT=$(git -C "$CAET_DIR" rev-parse HEAD)
if [ "$FINAL_COMMIT" != "$TARGET_COMMIT" ]; then
    err "部署后 commit 漂移: 期望 $TARGET_COMMIT 实际 $FINAL_COMMIT"
    exit 1
fi

echo
echo "============================================================"
log " >>> GO <<<  部署成功"
log "  $OLD_COMMIT ($OLD_TAG) → $NEW_COMMIT ($VERSION)"
echo "============================================================"
exit 0