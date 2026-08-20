# CAET 统一训练平台 · 部署指南（Docker Compose 版）

> 适用版本：**v2.0（Docker 化重构）** · 交付物 `CAET_V1.2_Docker.zip`
> 技术栈：**Vue 3 前端（容器内 Nginx 托管）+ FastAPI 后端 + PostgreSQL 16 + Redis 7（轻量）**
> 部署方式：**docker compose 一键启动**，与服务器上既有 **Cabin Voice** 完全隔离。
> 设计目标：**快速部署 + 环境一致性**（镜像构建固定 Node 20 / Python 3.11 / PG 16 / Redis 7 版本）。

---

## 0. 目标架构与隔离原则

```
阿里云轻量服务器
├── Cabin Voice          （既有生产环境，完全不动）
└── CAET                 （Docker Compose，独立项目名 caet）
    ├── caet-frontend     Nginx 容器：托管 Vue3 构建产物 + 反代 /api、/uploads、/health
    │                     仅此容器暴露宿主机端口 ${CAET_HTTP_PORT:-8080}
    ├── caet-backend      FastAPI 容器：业务 API + 启动自举（建表/种子/管理员）
    ├── caet-postgres     PostgreSQL 16 容器：独立库 caet / 独立用户 caet_user
    └── caet-redis        Redis 7 容器：用户会话 / 简单缓存 / AI 任务扩展预留
```

**隔离维度一览（与 Cabin Voice 互不干扰）**：

| 隔离维度 | 实现 |
|---------|------|
| 进程/容器 | 独立 compose 项目 `name: caet`，独立 bridge 网络 `caet_net` |
| 端口 | 仅前端暴露 `CAET_HTTP_PORT`（默认 **8080**），避开 Cabin Voice 的 80/443 及其后端端口 |
| 数据卷 | 独立命名卷 `caet_pgdata` / `caet_redis` / `caet_uploads`，不与 Cabin Voice 数据目录相交 |
| 数据库 | 容器内独立 PostgreSQL 实例（库 `caet`、用户 `caet_user`），不连接/不修改宿主 PG 或 Cabin Voice 库 |
| 文件 | 代码独立目录（建议 `/opt/caet` 或 `/var/www/caet`），不写入 Cabin Voice 目录 |
| 回滚 | 停掉/删掉 `caet` 项目即可整体移除，对 Cabin Voice 零影响 |

---

## 1. 前置要求（服务器一次性准备）

| 项 | 要求 |
|----|------|
| 系统 | Linux（Debian/Ubuntu 系或 CentOS/阿里云镜像均可） |
| Docker | ≥ 24（`docker --version` 确认） |
| Docker Compose | 插件版 `docker compose version`（v2，非 `docker-compose`） |
| 资源 | 2C4G 以上即可流畅运行（含镜像构建） |
| 外网 | 服务器需能访问 Docker Hub（拉取 `node:20-alpine` / `python:3.11-slim` / `postgres:16-alpine` / `redis:7-alpine` / `nginx:alpine`） |

未安装 Docker 时：

```bash
# Debian/Ubuntu
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # 重新登录生效，或后续命令加 sudo

# 验证
docker --version && docker compose version
```

> 若服务器已有 Docker（如 Cabin Voice 曾用），直接复用 Docker 引擎即可，CAET 的容器/网络/卷均独立命名，不会冲突。

---

## 2. 快速部署（5 步）

### 2.1 上传代码

将本仓库（或部署包内 `CAET_V1.2_Docker/` 内容）上传到服务器独立目录：

```bash
sudo mkdir -p /opt/caet
# scp/rsync 上传仓库内容到 /opt/caet，例如：
# rsync -az --delete ./  user@your-server:/opt/caet/
# （排除 node_modules、dist、.env 等，见 .gitignore）
cd /opt/caet
```

### 2.2 生成并修改环境变量

```bash
cp .env.example .env
vim .env
```

**至少修改 4 项**（生产必改）：

| 变量 | 必改 | 说明 |
|------|------|------|
| `POSTGRES_PASSWORD` | ✅ | 强密码，≥16 位随机串 |
| `SECRET_KEY` | ✅ | JWT 签名密钥，≥32 位随机串（`openssl rand -hex 32` 生成） |
| `INIT_ADMIN_PASSWORD` | ✅ | 首个管理员密码（仅首次启动生效） |
| `CORS_ORIGINS` | ✅ | 改为你的前端访问地址，如 `https://caet.example.com`，逗号分隔多个 |

其余保持默认即可：`DATABASE_URL` / `REDIS_URL` 指向 compose 内部服务名，**不要改**。

### 2.3 构建并启动

```bash
docker compose up -d --build
```

启动过程：compose 先拉起 postgres/redis（健康检查通过）→ 构建并启动 backend（容器 CMD 先执行 `python -m app.db_init` 幂等建表/种子/建管理员，再启动 uvicorn）→ 构建并启动 frontend（Nginx）。

### 2.4 验证

```bash
# 查看全部服务状态（应全部 healthy / running）
docker compose ps

# 后端健康检查（含 Redis 状态）
curl -fsS http://127.0.0.1:8080/health
# => {"status":"ok", ..., "redis":"ok"}

# 查看启动日志（db_init 应打印 schema/seed/admin 完成）
docker compose logs caet-backend | tail -30
```

### 2.5 登录试用

浏览器打开 `http://服务器IP:8080`，用 `.env` 中的 `INIT_ADMIN_*` 登录管理员后台；或用种子账号体验三角色（见 README「演示账号」）。

---

## 3. 环境变量总表（.env.example）

| 变量 | 默认 | 说明 |
|------|------|------|
| `POSTGRES_PASSWORD` | 占位弱密码 | **生产必改**；postgres 容器与 backend 的 DATABASE_URL 共用 |
| `DATABASE_URL` | compose 内部地址 | 指向 `caet-postgres:5432/caet`，一般不动 |
| `REDIS_URL` | compose 内部地址 | 指向 `caet-redis:6379/0`，一般不动 |
| `SECRET_KEY` | 占位 | **生产必改**，≥32 字符随机串 |
| `ALGORITHM` / `ACCESS_TOKEN_EXPIRE_MINUTES` | HS256 / 1440 | JWT 配置 |
| `CORS_ORIGINS` | https://caet.example.com | **生产必改**为真实前端域名，逗号分隔 |
| `INIT_ADMIN_EMAIL` / `_PASSWORD` / `_NAME` | 默认值 | 首次启动自动创建管理员；创建成功后可注释掉 |
| `UPLOAD_DIR` | /app/uploads | 容器内上传目录（映射到命名卷 caet_uploads） |
| `HOST` / `PORT` | 0.0.0.0 / 8000 | 容器内后端监听，一般不动 |
| `CACHE_TTL_SECONDS` | 300 | Redis 简单缓存 TTL |
| `CAET_HTTP_PORT` | 8080 | **宿主机对外端口**；如需改端口（避开其它服务）改这里 |

---

## 4. 接入域名 + HTTPS（可选，推荐）

默认通过 `http://IP:8080` 访问。如需域名访问，在**宿主 Nginx**（Cabin Voice 同款 Nginx）新增独立 server block，反代到 CAET 的 8080：

```nginx
# /etc/nginx/conf.d/caet.conf（新增，不修改 Cabin Voice 配置）
server {
    listen 80;
    server_name caet.example.com;
    location / { proxy_pass http://127.0.0.1:8080; proxy_set_header Host $host; }
}
```

启用 HTTPS（certbot 或阿里云证书，与 Cabin Voice 证书管理方式一致）：

```bash
sudo certbot --nginx -d caet.example.com
```

> 域名反代层放宿主 Nginx、CAET 容器内 Nginx 只服务自身——两层职责清晰，Cabin Voice 的 server block 零改动。

---

## 5. 日常运维

| 操作 | 命令 |
|------|------|
| 查看状态 | `docker compose ps` |
| 查看日志 | `docker compose logs -f --tail=100 caet-backend`（或 `caet-frontend` / `caet-postgres` / `caet-redis`） |
| 更新代码 | 拉新代码 → `docker compose up -d --build`（仅变更的镜像重建） |
| 重启 | `docker compose restart` |
| 停止（保留数据） | `docker compose down` |
| 备份数据 | `docker compose exec caet-postgres pg_dump -U caet_user caet > caet_backup_$(date +%F).sql` |
| 完整清理（删数据卷） | `docker compose down -v`（**危险**：删除全部 caet 数据，回滚时才用） |

---

## 6. 回滚

- **代码回滚**：切回上一版本代码 → `docker compose up -d --build`（数据卷保留，schema 幂等）。
- **数据回滚**：用 §5 的备份文件 `docker compose exec -T caet-postgres psql -U caet_user caet < caet_backup_xxx.sql`。
- **整体移除**：`docker compose down -v` 清空容器、网络、卷——只影响 CAET，不影响 Cabin Voice。

---

## 7. 故障排查

| 现象 | 排查 |
|------|------|
| `docker compose ps` 中 postgres/redis 一直 unhealthy | 端口/资源问题，看 `docker compose logs caet-postgres` |
| backend 反复重启 | `docker compose logs caet-backend`；常见：`POSTGRES_PASSWORD` 与 `DATABASE_URL` 不一致、端口被占用 |
| 前端 502 / api 404 | 看 `docker compose logs caet-frontend`；确认 backend 已 healthy（frontend 依赖它） |
| 登录 401 / CORS 报错 | `.env` 的 `CORS_ORIGINS` 未包含你的访问地址；改后 `docker compose up -d` 重建 backend |
| 上传音频失败 | 检查卷 `caet_uploads` 空间、`docker compose logs caet-backend` 中 upload 相关报错 |
| Redis 不可用（后端降级） | 后端设计为 JWT 自包含 + Redis 静默降级，`/health` 会显示 `redis` 状态；修复 Redis 后自动恢复 |
| 宿主机端口冲突 | 改 `.env` 的 `CAET_HTTP_PORT` 为其它空闲端口，`docker compose up -d` |

---

## 8. 与旧版（systemd 直部署）的关系

- v1.0/v1.1 曾提供 systemd + 宿主 Nginx + 复用宿主 PG 的直部署方案（`caet-backend/deploy/` 下仍保留 nginx/systemd/scripts 供参考）。
- **v2.0 起推荐 compose 方案**：环境一致性更好、回滚更干净、与 Cabin Voice 隔离更彻底（独立容器网络 + 独立 PG/Redis 实例）。
- 两种方案互斥，选择其一，不要混用。

---

## 9. 文件清单

```
CAET_V1.2_Docker/
├── docker-compose.yml          # 四服务编排（独立网络/卷/健康检查）
├── .env.example                # 环境变量模板（.env 不入库）
├── Dockerfile                  # 前端镜像：Node20 构建 → Nginx 托管
├── nginx.caet.conf             # 前端容器内 Nginx：SPA + /api /uploads /health 反代
├── caet-backend/
│   ├── Dockerfile              # 后端镜像：Python3.11 + uvicorn；CMD 先 db_init
│   ├── requirements.txt        # fastapi/uvicorn/sqlalchemy/asyncpg/redis/jose/bcrypt
│   ├── app/                    # main/config/db_init/models/schemas/security/deps/redis_client + 13 个 routers
│   ├── database/schema.sql     # 幂等建表（courses.course_type / assessments / task_assignments.instructor_id）
│   ├── database/seed.sql       # 幂等种子（班级/三角色用户/三课程/广播词内容/任务指派）
│   └── deploy/                 # （旧 systemd 方案保留，参考用）
├── src/                        # Vue3 + TS + Pinia + Tailwind + Element Plus 前端源码
├── course-data/                # 课程 JSON 与导入脚本
├── DEPLOYMENT.md               # 本文
├── README.md                   # 项目说明 + 演示账号 + 角色矩阵
├── TEST_REPORT.md              # 测试报告（v2.0）
├── PRD_V1.1_Production.md      # 产品需求文档
└── CHANGELOG.md                # 变更日志
```
