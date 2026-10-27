#!/usr/bin/env bash
# CAET V1.2 升级前自动备份（正式仓库结构 + uploads 命名卷 + SHA256）
# 备份路径:
#   caet-backend/app/                  -> src/caet-backend-app.tar.gz
#   caet-backend/database/             -> src/caet-backend-database.tar.gz
#   caet-backend/requirements.txt      -> src/requirements.txt
#   根 dist/                           -> dist/dist.tar.gz
#   根 Dockerfile                       -> config/Dockerfile
#   根 docker-compose.yml               -> config/docker-compose.yml
#   根 nginx.caet.conf                 -> config/nginx.caet.conf
#   根 package.json                     -> config/package.json
#   根 package-lock.json                -> config/package-lock.json
#   Docker 卷 caet_uploads 全部内容     -> uploads/uploads-volume.tar.gz
#   PostgreSQL 逻辑备份                 -> db/caet_<时间戳>.sql.gz
# 每个备份文件生成 SHA256，校验失败必须 exit 1
# 明确不备份: .env / *.pem / *.key / *.crt / Redis dump.rdb
set -euo pipefail

CAET_DIR="${CAET_DIR:-/opt/caet}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/caet/backups}"
cd "$CAET_DIR" 2>/dev/null || { echo "❌ CAET 目录不存在" >&2; exit 1; }

TS="$(date '+%Y%m%d_%H%M%S')"
T="$BACKUP_ROOT/releases/$TS"
mkdir -p "$T"/{src,dist,config,db,uploads,sha256,meta}

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
err() { printf '[%s] ❌ %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }

echo "============================================================"
echo " CAET V1.2 备份   $(date '+%Y-%m-%d %H:%M:%S')"
echo " CAET_DIR=$CAET_DIR"
echo " TARGET=$T"
echo "============================================================"

# ---- Git 信息（写入 meta/git.json）----
log "[meta] 读取 Git 信息"
COMMIT=$(git -C "$CAET_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
TAG=$(git -C "$CAET_DIR" describe --tags --exact-match HEAD 2>/dev/null || echo "detached")
BRANCH=$(git -C "$CAET_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")
cat > "$T/meta/git.json" <<EOF
{"commit":"$COMMIT","tag":"$TAG","branch":"$BRANCH","timestamp":"$TS","hostname":"$(hostname)"}
EOF
log "  commit=$COMMIT  tag=$TAG  branch=$BRANCH"

# ---- 1. caet-backend/app ----
log "[1/7] caet-backend/app"
[ -d "$CAET_DIR/caet-backend/app" ] || { err "caet-backend/app 不存在"; exit 1; }
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    -czf "$T/src/caet-backend-app.tar.gz" -C "$CAET_DIR/caet-backend" app \
    || { err "caet-backend/app 备份失败"; exit 1; }

# ---- 2. caet-backend/database ----
log "[2/7] caet-backend/database"
[ -d "$CAET_DIR/caet-backend/database" ] || { err "caet-backend/database 不存在"; exit 1; }
tar -czf "$T/src/caet-backend-database.tar.gz" -C "$CAET_DIR/caet-backend" database \
    || { err "caet-backend/database 备份失败"; exit 1; }

# ---- 3. requirements.txt ----
log "[3/7] caet-backend/requirements.txt"
[ -f "$CAET_DIR/caet-backend/requirements.txt" ] || { err "requirements.txt 缺失"; exit 1; }
cp "$CAET_DIR/caet-backend/requirements.txt" "$T/src/" \
    || { err "requirements.txt 拷贝失败"; exit 1; }

# ---- 4. 根 dist/ ----
log "[4/7] 根 dist/"
[ -d "$CAET_DIR/dist" ] || { err "dist/ 不存在"; exit 1; }
tar -czf "$T/dist/dist.tar.gz" -C "$CAET_DIR" dist \
    || { err "dist/ 备份失败"; exit 1; }

# ---- 5. 根配置（Dockerfile/compose/nginx/package*.json）----
log "[5/7] 根配置"
for f in Dockerfile docker-compose.yml nginx.caet.conf package.json package-lock.json; do
    [ -f "$CAET_DIR/$f" ] || { err "$f 缺失"; exit 1; }
    cp "$CAET_DIR/$f" "$T/config/" || { err "$f 拷贝失败"; exit 1; }
done

# ---- 6. caet_uploads 命名卷 ----
log "[6/7] caet_uploads 命名卷"
# 检查卷存在
if ! docker volume inspect caet_uploads >/dev/null 2>&1; then
    err "caet_uploads 卷不存在"
    exit 1
fi
# 打包卷内容到 T/uploads/uploads-volume.tar.gz
docker run --rm \
    -v caet_uploads:/data:ro \
    -v "$T/uploads":/backup \
    alpine sh -c "tar czf /backup/uploads-volume.tar.gz -C /data ." \
    || { err "caet_uploads 卷备份失败"; exit 1; }
# 文件清单与统计
docker run --rm -v caet_uploads:/data:ro alpine sh -c \
    "find /data -type f -printf '%s\t%p\n' | sort -k2" \
    > "$T/uploads/files.tsv" 2>/dev/null || true
docker run --rm -v caet_uploads:/data:ro alpine sh -c \
    "du -sb /data | cut -f1" > "$T/uploads/total_bytes" 2>/dev/null || true
UPL_COUNT=$(wc -l < "$T/uploads/files.tsv" 2>/dev/null || echo 0)
UPL_SIZE=$(cat "$T/uploads/total_bytes" 2>/dev/null || echo 0)
log "  uploads 文件数=$UPL_COUNT  总字节=$UPL_SIZE"

# ---- 7. PostgreSQL ----
log "[7/7] PostgreSQL 逻辑备份"
docker exec caet-postgres pg_isready -U caet_user -d caet >/dev/null 2>&1 \
    || { err "PostgreSQL 未就绪"; exit 1; }
SQL="$T/db/caet_${TS}.sql"
docker exec caet-postgres pg_dump -U caet_user -d caet --no-owner --clean --if-exists \
    > "$SQL" 2>/dev/null \
    || { err "pg_dump 失败"; rm -f "$SQL"; exit 1; }
gzip "$SQL" || { err "gzip 失败"; exit 1; }

# ---- SHA256 生成 ----
log "[sha256] 生成每个备份文件的 SHA256"
cd "$T"
find . -type f \
    ! -path './sha256/*' \
    ! -name '*.sha256' \
    -print0 | while IFS= read -r -d '' f; do
        REL="${f#./}"
        # 嵌套子目录需先建（如 sha256/config/）
        mkdir -p "sha256/$(dirname "$REL")"
        sha256sum "$REL" | awk '{print $1"  '"$REL"'"}' > "sha256/${REL}.sha256" \
            || { err "SHA256 生成失败: $REL"; exit 1; }
done
cd "$CAET_DIR"

# ---- SHA256 校验 ----
log "[sha256] 校验所有备份文件"
cd "$T"
MISMATCH=0
while IFS= read -r sf; do
    REL="${sf#sha256/}"
    REL="${REL%.sha256}"
    EXPECTED=$(awk '{print $1}' "$sf")
    if [ ! -f "$REL" ]; then
        err "缺失文件: $REL"
        MISMATCH=$((MISMATCH+1)); continue
    fi
    ACTUAL=$(sha256sum "$REL" | awk '{print $1}')
    if [ "$EXPECTED" != "$ACTUAL" ]; then
        err "SHA256 不一致: $REL"
        MISMATCH=$((MISMATCH+1))
    fi
done < <(find sha256 -name '*.sha256')
cd "$CAET_DIR"
if [ "$MISMATCH" -gt 0 ]; then
    err "SHA256 校验失败 ($MISMATCH 个文件不匹配)"
    echo "FAILED" > "$T/sha256/VERIFY.txt"
    exit 1
fi
echo "OK $(date '+%Y-%m-%d %H:%M:%S')  ${TS}" > "$T/sha256/VERIFY.txt"

# ---- INFO.txt ----
cat > "$T/INFO.txt" <<EOF
CAET V1.2 备份
时间:        $TS
主机:        $(hostname)
源:          $CAET_DIR
Git:         commit=$COMMIT  tag=$TAG  branch=$BRANCH

包含:
  src/caet-backend-app.tar.gz         后端 app/ 代码
  src/caet-backend-database.tar.gz   后端 database/（schema.sql + seed.sql）
  src/requirements.txt                后端 Python 依赖
  dist/dist.tar.gz                    前端构建产物（Vite build 输出）
  config/Dockerfile                   前端 nginx 镜像构建
  config/docker-compose.yml           compose 四服务配置
  config/nginx.caet.conf              nginx 反代配置
  config/package.json                 npm 依赖
  config/package-lock.json            npm lock
  uploads/uploads-volume.tar.gz       caet_uploads 卷完整内容（学员录音等）
  uploads/files.tsv                   uploads 文件清单（path + bytes）
  uploads/total_bytes                 uploads 总字节数
  db/caet_${TS}.sql.gz                PostgreSQL 完整逻辑备份
  meta/git.json                       Git commit/tag/branch 元数据
  sha256/<每个文件>.sha256            SHA256 校验值
  sha256/VERIFY.txt                   校验结果（OK / FAILED）

明确未包含（保护敏感信息）:
  .env                  密码 / SECRET_KEY / DATABASE_URL / Redis 密码
  *.pem / *.key / *.crt SSL 证书与私钥
  *.jks / *.p12         Keystore
  Redis dump.rdb / appendonly.aof   Redis 持久化（架构不依赖 Redis 数据恢复）
EOF

echo
echo "============================================================"
log " >>> 备份完成: $T"
du -sh "$T"/* 2>/dev/null
echo
log "总大小: $(du -sh "$T" | awk '{print $1}')"
log "Git: commit=$COMMIT  tag=$TAG"
log "uploads: $UPL_COUNT 个文件 / $UPL_SIZE 字节"
log "SHA256 校验: OK"
echo "============================================================"