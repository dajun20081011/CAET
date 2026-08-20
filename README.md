# CAET 统一训练平台（Cabin Attendant English Training）

面向客舱乘务员的英语训练平台：**广播词（broadcast）/ CAET2 英文问答（english_qa）/ CAET3 中译英（zh_to_en）** 三类课程，共享学习流程，独立测评类型。三角色：**管理员 / 教员 / 学员**。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Vite + TypeScript + Pinia + Vue Router |
| 管理后台 UI | Element Plus（全局注册，`src/main.ts`） |
| 学员端 UI | Tailwind CSS + 自定义组件（390px 手机优先） |
| 教员端 UI | 混合方案（Element Plus 图标 + 自定义布局，`src/layouts/InstructorLayout.vue`） |
| 后端 | FastAPI（async）+ SQLAlchemy 2.0 + asyncpg + JWT(HS256) + bcrypt |
| 缓存/会话 | Redis 7 轻量接入（`app/redis_client.py`；不可用时静默降级，JWT 自包含不依赖 Redis） |
| 数据库 | PostgreSQL 16（独立库 `caet`、用户 `caet_user`） |
| 部署 | Docker + Nginx + docker compose（四服务，独立网络/卷，仅前端暴露 8080） |
| 浏览器能力 | MediaRecorder（录音）、Web Speech API（语音转写对照，不判定准确度） |

## 架构

```
学员端(390px 手机优先)   管理员后台(Element Plus)   教员端(混合布局)
        └──────────────┬───────────────┘
                       │ /api  (JWT)
              ┌────────▼────────┐
              │  FastAPI (8100/容器8000) │── Redis(会话/缓存, 可降级)
              └────────┬────────┘
              ┌────────▼────────┐
              │  PostgreSQL 16  │
              └─────────────────┘
```

- 课程类型：`courses.course_type ∈ {broadcast, caet2, caet3}`
- 测评类型：`assessments.assessment_type ∈ {broadcast_recording, english_qa, zh_to_en}`
- 任务指派：`task_assignments.instructor_id` 指定测评教员，教员在「评分队列」评分

## 快速开始

### Docker 一键启动（推荐，详见 DEPLOYMENT.md）

```bash
cp .env.example .env        # 修改 POSTGRES_PASSWORD / SECRET_KEY / INIT_ADMIN_PASSWORD / CORS_ORIGINS
docker compose up -d --build
# 打开 http://localhost:8080 （或服务器 IP:8080）
```

后端容器启动时自动执行 `python -m app.db_init`（幂等建表 + 种子 + 创建管理员），**无需手动初始化数据库**。

### 本地开发

```bash
npm install
npm run dev                 # 前端 http://localhost:3000，/api 代理到后端

# 后端（需本机 Python 3.11 + PostgreSQL，或连 Docker 中的 PG）
cd caet-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # 修改 DATABASE_URL 指向本机 PG
uvicorn app.main:app --reload
```

本地开发后端端口默认 8000（`vite.config.ts` 的 dev proxy），可用 `CAET_DEV_API_PORT` 覆盖。

## 账号初始化

源码不包含演示账号、固定密码或密码哈希。首次管理员通过服务器 `.env` 临时初始化；教员和学员由管理员在平台内创建。

## 角色矩阵

| 能力 | 管理员 | 教员 | 学员 |
|------|:---:|:---:|:---:|
| 课程/任务/班级管理 | ✅ | | |
| 用户管理（含角色） | ✅ | | |
| 创建/指派任务（可指定测评教员） | ✅ | | |
| 查看测评列表、指派教员 | ✅ | | |
| 测评评分队列（录音/文本作答） | | ✅ | |
| 提交测评（录音+文本） | | | ✅ |
| 学习 Day 流程（讲解/句子/词/练习/总结） | | | ✅ |
| 查看测评成绩与反馈 | ✅ | ✅ | ✅(本人) |
| 数据看板/事件监控/CSV 导出 | ✅ | | |

## 目录结构

```
src/
  views/           页面组件（admin/ / instructor/ / student/）
  layouts/         三角色布局（AdminLayout / InstructorLayout / StudentLayout）
  stores/          Pinia（auth / learning / admin …）
  lib/             api.ts（fetch 封装 + JWT 注入）、eventMeta.ts
  types/           TypeScript 类型（含 Task.course_type）
  router/          路由（按角色守卫）
caet-backend/
  app/
    main.py        FastAPI 入口（/health、CORS、JWT）
    db_init.py     启动自举（幂等 schema/seed/管理员）
    models.py      SQLAlchemy ORM（Course.course_type、Assessment、TaskAssignment.instructor_id）
    routers/       auth/tasks/content/courses/progress/events/record/admin/upload/groups/users/assessments
    redis_client.py Redis 轻量封装（cache/session/ai_task_push）
  database/
    schema.sql     幂等 DDL（PG 方言）
    seed.sql       幂等种子数据
course-data/       课程 JSON + 导入脚本
docker-compose.yml 四服务编排（caet-postgres/redis/backend/frontend）
```

## 环境变量

前端：构建期无需后端地址（生产统一走 `/api` 相对路径，由 Nginx 反代）。
后端：见 `.env.example`（DATABASE_URL / REDIS_URL / SECRET_KEY / CORS_ORIGINS / INIT_ADMIN_* / UPLOAD_DIR / PORT / CACHE_TTL_SECONDS / CAET_HTTP_PORT）。

## 测试

```bash
npm run build        # vue-tsc 类型检查 + vite 构建（含 element-plus/vendor 分包）
npm run test         # vitest
```

后端验证：`python -m app.db_init`（需 PG）+ 启动后 `curl /health`。详见 TEST_REPORT.md。

## 说明与边界（V1）

- V1 不含排行榜、积分、EXP、正式 AI 语音评分；浏览器语音识别仅作内容对照。
- 广播词范读音频默认 TTS 兜底，真实 MP3 管线为后续迭代。
- AI 接口（自动评分/智能问答）为预留方向：Redis `ai_task_push` 已占位，接口开发在后续阶段。
- 部署与隔离细节见 DEPLOYMENT.md；产品背景见 PRD_V1.1_Production.md。
