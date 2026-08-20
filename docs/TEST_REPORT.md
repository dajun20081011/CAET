# CAET 测试报告（v2.0 · Docker Compose 版）

> 适用版本：**v2.0**（Docker 化重构：Vue3 + Element Plus 后台 / FastAPI / PostgreSQL 16 / Redis 7 轻量 / docker compose 四服务）
> 交付物：`CAET_V1.2_Docker.zip`
> 目标：**可部署、可运行、可试用**，与服务器既有 Cabin Voice 完全隔离，不做静态 Demo。

## 1. 本次变更摘要（相对 v1.1 systemd 方案）

| 维度 | v1.1（旧） | v2.0（本版） |
|------|-----------|-------------|
| 部署 | systemd + 宿主 Nginx + 复用宿主 PG | **docker compose 四服务**（postgres/redis/backend/frontend），独立网络 `caet_net` + 命名卷 |
| 前端 UI | Tailwind 全局 | 管理后台 **Element Plus**（全局注册）；学员端 Tailwind 手机优先；教员端混合布局 |
| 课程模型 | 单课程类型 | `courses.course_type ∈ {broadcast, caet2, caet3}`，三课程类型共享学习流程 |
| 测评模型 | 无独立测评 | 新表 `assessments`，`assessment_type ∈ {broadcast_recording, english_qa, zh_to_en}` |
| 任务指派 | 无 | `task_assignments.instructor_id` 指定测评教员；管理员建任务时可指派 |
| Redis | 未引入 | **轻量接入**：会话(jti)/简单缓存/AI 任务预留；不可用时静默降级，JWT 自包含 |
| 数据库初始化 | 手工执行 schema/seed | 容器 CMD 自动 `python -m app.db_init`（幂等建表/种子/管理员） |
| 前端请求层 | fetch 封装 | `src/lib/api.ts`：JWT 注入 + `upload()` 多部分 helper（audio/recording） |
| 对外端口 | 8100（后端） | **8080**（仅前端暴露，`CAET_HTTP_PORT` 可配） |

## 2. 验证结果

### ✅ 后端：静态验证通过（本机无 Docker/无 PG 实例，降级为 import + 路由检查）

| 项 | 结果 | 说明 |
|----|------|------|
| 依赖安装 | 通过 | `pip install -r requirements.txt`（含 `redis==5.0.8`）于隔离 venv 完成 |
| `app.main` 导入 | `IMPORT_OK` | config/database/models/schemas/security/deps/redis_client/db_init 全链路可导入 |
| 路由注册 | **40 条 `/api/*` 路由 PASS** | auth/tasks/content/courses/progress/events/record/admin/upload/groups/users/assessments 共 13 个 router |
| 前端契约一致性 | 通过 | `src/lib/api.ts` 全部调用路径在后端均有对应路由 |
| Redis 降级 | 设计确认 | `redis_client.py` 惰性连接池，连接失败静默 no-op；JWT 不依赖 Redis |
| db_init 幂等 | 代码走查 | `CREATE EXTENSION IF NOT EXISTS` + 去注释执行 schema/seed + `ON CONFLICT` 幂等保护 + INIT_ADMIN 存在性判断 |

### ✅ 前端：类型检查 + 构建通过

| 项 | 结果 | 说明 |
|----|------|------|
| `vue-tsc --noEmit` | **0 错误** | 修复历史 TS2339/TS2362/TS2322/TS1345 后全绿 |
| `vite build` | 通过 | `manualChunks` 拆分 `element-plus` / `vendor`（vue/router/pinia）独立分包，消除 >500kB 单包告警 |
| 残留扫描 | 通过 | `src/` 与构建产物无 `supabase` / `mockData` / `mockGroups` 残留（`vite.config.ts` 中 dev proxy 的 `127.0.0.1` 为本地开发合法配置） |

### 本轮新增前端功能（已含于构建）

- 教员端：`InstructorLayout` / `InstructorQueue`（评分队列，按测评类型过滤）/ `AssessmentGrade`（播录音 + 文本作答评分表单）
- 学员端：`StudentAssessments`（我的测评/成绩/反馈）；`DayStudy` 广播词测评提交闭环（中文+英文双录音 → 上传 `upload.recording` → 提交 `assessments.submit`）；底部导航新增「测评」tab
- 管理后台：`AdminUsers`（用户 CRUD/启停）、`AdminGroups`（班级/成员）、`AdminAssessments`（测评筛选 + 指派教员）；`CreateTask` 第 5 步可选评分教员、课程卡片课程类型 badge
- 布局：`AdminLayout` 菜单新增 用户/角色、班级、测评

### ⏳ 未在本机验证（需真实 Docker 环境）

| 项 | 原因 |
|----|------|
| `docker compose up -d --build` 全链路启动 | 本机沙箱无 Docker 二进制 |
| PG/Redis 容器健康检查与数据落库 | 同上 |
| 真实登录、三角色分流、录音上传、评分闭环 | 需容器化 PG + Redis 实测 |
| `/health` 返回 `redis:"ok"` | 需 Redis 容器运行 |

> 这些项已在 DEPLOYMENT.md §2.4 给出明确验证命令（`docker compose ps` / `curl /health` / 三角色登录），服务器上 `docker compose up -d --build` 后即可按步骤验收。

## 3. 与 Cabin Voice 隔离声明

- compose 项目名 `caet`、网络 `caet_net`、卷 `caet_pgdata/caet_redis/caet_uploads` 全部独立命名，不触碰 Cabin Voice 的容器/网络/卷/目录。
- 仅暴露宿主机端口 `CAET_HTTP_PORT`（默认 8080），不占用 Cabin Voice 的 80/443 及后端端口。
- 数据库使用 compose 内部独立 PostgreSQL 实例（库 `caet`、用户 `caet_user`），**不连接宿主 PG、不修改 Cabin Voice 库**。
- 部署与回滚均为 CAET 目录内操作（`docker compose down` / `down -v`），对 Cabin Voice 零影响。

## 4. 待生产补充（与路线一致，非本阶段范围）

- **AI 接口**：Redis `ai_task_push` 已预留，AI 自动评分/智能问答为开发顺序末项，第一阶段不接入。
- **真实音频**：广播词范读默认 TTS 兜底，真实 MP3 生产管线后续迭代。
- **课程内容**：广播词第 1 章已结构化；CAET2/CAET3 已有阅读材料与测评示例，全量内容后续补充。
- **邮件/SMTP**：未接入；管理员由 `.env` `INIT_ADMIN_*` 创建。

## 5. 交付物

- **`CAET_V1.2_Docker.zip`**：docker-compose.yml / .env.example / Dockerfile ×2 / nginx.caet.conf / caet-backend/（app + database + requirements.txt）/ src/（Vue3 前端全量源码）/ course-data/ / DEPLOYMENT.md / README.md / TEST_REPORT.md / PRD_V1.1_Production.md / CHANGELOG.md
- 源码另已纳入 Git 仓库（main / develop 分支，见 CHANGELOG 与 Git 提交历史）。

## 6. 下一步

1. 服务器装好 Docker → 上传代码 → `cp .env.example .env` 改 4 项 → `docker compose up -d --build`（DEPLOYMENT.md §2）。
2. 按 §2.4 验证三服务健康 + `/health` + 三角色登录试用。
3. 域名/HTTPS 接入（DEPLOYMENT.md §4）。
4. 按开发顺序继续：CAET2 闭环 → CAET3 闭环 → AI 接口。
