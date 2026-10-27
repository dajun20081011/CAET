#!/usr/bin/env bash
# CAET V1.2 回滚（正式仓库结构 + uploads 命名卷恢复）
# 默认行为: 仅恢复代码 / 根 dist/ / 根配置 / uploads 卷
# 数据库回滚: 必须 --with-db + 两次 yes 人工确认
# 用法:
#   bash scripts/rollback.sh --dry-run
#   bash scripts/rollback.sh
#   bash scripts/rollback.sh --with-db
#   bash scripts/rollback.sh --target=20260820_093000
# 铁律:
#   - 默认先 --dry-run
#   - SHA256 校验必须通过才执行
#   - 找不到完整备份立即停止
#   - 数据库恢复失败必须返回非零（不能只警告）
#   - 回滚后自动 healthcheck
#   - healthcheck 失败 → NO-GO
set -euo pipefail

CAET_DIR="${CAET_DIR:-/opt/caet}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/caet/backups/releases}"

DRY_RUN=false
ROLLBACK_DB=false
TARGET=""

for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY_RUN=true ;;
        --with-db)  ROLLBACK_DB=true ;;
        --target=*) TARGET="${arg#*=}" ;;
        -h|--help)
            sed -n '2,18p' "$0"; exit 0 ;;
        *) echo "未知参数: $arg" >&2; exit 2 ;;
    esac
done

cd "$CAET_DIR" 2>/dev/null || { echo "❌ CAET 目录不存在" >&2; exit 1; }

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
err() { printf '[%s] ❌ %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }

echo "============================================================"
echo " CAET V1.2 回滚   $(date '+%Y-%m-%d %H:%M:%S')"
echo " CAET_DIR=$CAET_DIR"
echo " BACKUP_ROOT=$BACKUP_ROOT"
echo "============================================================"

# ---- 找目标备份 ----
if [ -z "$TARGET" ]; then
    if [ ! -d "$BACKUP_ROOT" ]; then
        err "未发现备份目录 $BACKUP_ROOT"
        exit 1
    fi
    TARGET=$(ls -1 "$BACKUP_ROOT" 2>/dev/null | grep -E '^[0-9]{8}_[0-9]{6}$' | sort | tail -1)
fi

if [ -z "$TARGET" ] || [ ! -d "$BACKUP_ROOT/$TARGET" ]; then
    err "未找到有效备份: $BACKUP_ROOT/$TARGET"
    exit 1
fi

SRC="$BACKUP_ROOT/$TARGET"

# ---- 完整性前置检查 ----
log "[1/4] 备份完整性前置检查"
[ -f "$SRC/INFO.txt" ]      || { err "INFO.txt 缺失"; exit 1; }
[ -f "$SRC/sha256/VERIFY.txt" ] || { err "sha256/VERIFY.txt 缺失"; exit 1; }
grep -q "^OK" "$SRC/sha256/VERIFY.txt" || { err "原备份 SHA256 校验失败标记，无法回滚"; exit 1; }

for f in \
    "$SRC/src/caet-backend-app.tar.gz" \
    "$SRC/src/caet-backend-database.tar.gz" \
    "$SRC/src/requirements.txt" \
    "$SRC/dist/dist.tar.gz" \
    "$SRC/config/Dockerfile" \
    "$SRC/config/docker-compose.yml" \
    "$SRC/config/nginx.caet.conf" \
    "$SRC/config/package.json" \
    "$SRC/config/package-lock.json" \
    "$SRC/uploads/uploads-volume.tar.gz" \
    "$SRC/db/caet_${TARGET}.sql.gz" ; do
    if [ ! -f "$f" ]; then
        err "关键备份文件缺失: $f"
        exit 1
    fi
done

# ---- SHA256 重新校验 ----
log "[2/4] SHA256 重新校验"
cd "$SRC"
MISMATCH=0
while IFS= read -r sf; do
    REL="${sf#sha256/}"; REL="${REL%.sha256}"
    EXPECTED=$(awk '{print $1}' "$sf")
    [ -f "$REL" ] || { err "文件缺失: $REL"; MISMATCH=$((MISMATCH+1)); continue; }
    ACTUAL=$(sha256sum "$REL" | awk '{print $1}')
    [ "$EXPECTED" = "$ACTUAL" ] || { err "SHA256 不一致: $REL"; MISMATCH=$((MISMATCH+1)); }
done < <(find sha256 -name '*.sha256')
cd "$CAET_DIR"
[ "$MISMATCH" -eq 0 ] || { err "SHA256 校验失败 ($MISMATCH 个)，拒绝回滚"; exit 1; }
log "  ✅ SHA256 全 PASS"

# ---- DB 回滚 SQL 文件确认 ----
DB_SQL="$SRC/db/caet_${TARGET}.sql.gz"
if [ "$ROLLBACK_DB" = "true" ]; then
    [ -f "$DB_SQL" ] || { err "DB 文件不存在: $DB_SQL"; exit 1; }
fi

# ---- 列出将执行的动作 ----
echo
echo "▶ 目标备份: $SRC"
[ -f "$SRC/INFO.txt" ] && sed -n '1,8p' "$SRC/INFO.txt"

echo
echo "▶ 将执行的操作:"
ACTIONS=()
ACTIONS+=("stop: docker compose stop（不删卷）")
ACTIONS+=("src:  tar -xzf $SRC/src/caet-backend-app.tar.gz -> $CAET_DIR/caet-backend/app")
ACTIONS+=("src:  tar -xzf $SRC/src/caet-backend-database.tar.gz -> $CAET_DIR/caet-backend/database")
ACTIONS+=("src:  cp $SRC/src/requirements.txt -> $CAET_DIR/caet-backend/")
ACTIONS+=("dist: tar -xzf $SRC/dist/dist.tar.gz -> $CAET_DIR/dist/")
ACTIONS+=("conf: cp $SRC/config/Dockerfile -> $CAET_DIR/")
ACTIONS+=("conf: cp $SRC/config/docker-compose.yml -> $CAET_DIR/")
ACTIONS+=("conf: cp $SRC/config/nginx.caet.conf -> $CAET_DIR/")
ACTIONS+=("conf: cp $SRC/config/package.json -> $CAET_DIR/")
ACTIONS+=("conf: cp $SRC/config/package-lock.json -> $CAET_DIR/")
ACTIONS+=("uploads: docker run alpine tar -xzf ... -> caet_uploads 卷")
ACTIONS+=("up: docker compose up -d")
ACTIONS+=("check: bash scripts/healthcheck.sh")

if [ "$ROLLBACK_DB" = "true" ]; then
    ACTIONS+=("db ⚠️:  gunzip -c $DB_SQL | docker exec -i caet-postgres psql -U caet_user -d caet")
else
    ACTIONS+=("db:  跳过（需 --with-db）")
fi

for a in "${ACTIONS[@]}"; do echo "  - $a"; done

# ---- DRY-RUN ----
if [ "$DRY_RUN" = "true" ]; then
    echo
    echo "============================================================"
    echo " DRY-RUN 完成，未做任何修改"
    echo " 真实回滚: bash scripts/rollback.sh$([ "$ROLLBACK_DB" = "true" ] && echo " --with-db")"
    echo "============================================================"
    exit 0
fi

# ---- 第一次确认 ----
echo
read -rp "确认执行回滚？(yes/no): " CONFIRM
[ "$CONFIRM" = "yes" ] || { echo "已取消"; exit 0; }

# ---- 数据库二次确认 ----
if [ "$ROLLBACK_DB" = "true" ]; then
    echo
    echo "⚠️  数据库回滚将覆盖当前 caet 库全部数据！"
    read -rp "再次确认回滚数据库？(yes/no): " DB_CONFIRM
    if [ "$DB_CONFIRM" != "yes" ]; then
        echo "  数据库回滚已取消，其他部分继续"
        ROLLBACK_DB=false
    fi
fi

# ---- 执行回滚 ----
echo
log "[3/4] 执行回滚"
docker compose -f "$CAET_DIR/docker-compose.yml" stop || true

log "  恢复 caet-backend/app"
tar -xzf "$SRC/src/caet-backend-app.tar.gz" -C "$CAET_DIR/caet-backend"
log "  恢复 caet-backend/database"
tar -xzf "$SRC/src/caet-backend-database.tar.gz" -C "$CAET_DIR/caet-backend"
log "  恢复 requirements.txt"
cp "$SRC/src/requirements.txt" "$CAET_DIR/caet-backend/"

log "  恢复 根 dist/"
tar -xzf "$SRC/dist/dist.tar.gz" -C "$CAET_DIR"

log "  恢复 根配置"
for f in Dockerfile docker-compose.yml nginx.caet.conf package.json package-lock.json; do
    cp "$SRC/config/$f" "$CAET_DIR/" || { err "$f 恢复失败"; exit 1; }
done

log "  恢复 caet_uploads 卷"
# 先清空卷再解 tar（确保旧文件不残留）
docker run --rm \
    -v caet_uploads:/data \
    -v "$SRC/uploads":/backup \
    alpine sh -c "rm -rf /data/* /data/.[!.]* 2>/dev/null; tar xzf /backup/uploads-volume.tar.gz -C /data" \
    || { err "caet_uploads 卷恢复失败"; exit 1; }

# 数据库回滚
if [ "$ROLLBACK_DB" = "true" ]; then
    log "  回滚数据库（严格：失败必须非零）"
    set -e
    gunzip -c "$DB_SQL" | docker exec -i caet-postgres psql -U caet_user -d caet -v ON_ERROR_STOP=1 \
        || { err "❌ 数据库恢复失败，立即停止回滚（exit 1）"; exit 1; }
    set +e
    log "  ✅ 数据库恢复完成"
fi

log "  启动服务"
docker compose -f "$CAET_DIR/docker-compose.yml" up -d \
    || { err "docker compose up -d 失败"; exit 1; }

# ---- 健康检查 ----
echo
log "[4/4] 健康检查（等待 10 秒）"
sleep 10
if ! bash "$CAET_DIR/scripts/healthcheck.sh"; then
    err "❌ healthcheck 未通过 → NO-GO"
    err "  建议人工检查: docker compose ps / docker compose logs"
    exit 1
fi

echo
echo "============================================================"
log " ✅ 回滚完成 + healthcheck 通过"
echo "============================================================"
exit 0