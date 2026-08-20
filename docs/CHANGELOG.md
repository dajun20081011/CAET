# CAET 变更日志

## [2.0.0] - 2026-08-19

### 架构重构（以《客舱英语培训平台_V0.1_MVP开发部署包需求说明书》为准）
- **部署**：docker compose 四服务（caet-postgres 16 / caet-redis 7 / caet-backend / caet-frontend），独立网络 `caet_net` + 命名卷，仅前端暴露 `CAET_HTTP_PORT`（默认 8080）。与 Cabin Voice 物理隔离，快速部署 + 环境一致性。
- **前端 UI**：管理后台 Element Plus（全局注册）；学员端 Tailwind + 自定义组件（390px 手机优先）；教员端混合布局（Element Plus 图标 + 自定义边栏）。
- **课程模型**：`courses.course_type ∈ {broadcast, caet2, caet3}`——广播词/CAET2/CAET3 为不同课程类型，学习流程共享，测评类型独立（broadcast_recording / english_qa / zh_to_en）。
- **测评体系**：新表 `assessments`（提交/评分/成绩/反馈）；`task_assignments.instructor_id` 指派测评教员。
- **Redis 轻量接入**：`app/redis_client.py` 会话(jti)/简单缓存/AI 任务扩展预留；不可用时静默降级，JWT 自包含。
- **数据库自举**：后端容器 CMD 先 `python -m app.db_init`（幂等 schema + seed + 管理员），`docker compose up -d` 即可用。
- **前端数据层**：`src/lib/api.ts`（fetch + JWT 注入 + upload 多部分 helper）取代 Supabase 客户端；已清除 supabase/mockData 全部残留。

### 新增功能
- 管理员：用户管理（CRUD/启停）、班级管理（成员增删）、测评列表（筛选/指派教员）、创建任务可选评分教员、课程类型 badge
- 教员：评分队列（按测评类型过滤）、评分页（播放录音 / 文本作答 + score/feedback/status）
- 学员：我的测评（状态/成绩/反馈）、DayStudy 广播词测评提交闭环（中文+英文双录音 → 上传 → 提交）、底部导航「测评」tab
- 后端：`routers/groups.py`、`users.py`（含 PUT 指派教员）、`assessments.py`（submit/my/task/pending/grade）、`upload.py`（audio/recording）、auth 登出（jti 会话吊销）

### 验证
- 前端 `vue-tsc` 0 错误；`vite build` 通过（element-plus/vendor 分包）；构建产物无 supabase/mock 残留
- 后端 import 通过；40 条 `/api/*` 路由注册 PASS；前端契约与后端路由一一对应
- 详见 `TEST_REPORT.md`

## [1.0.1] - 2026-08-14

### 修复（真实冒烟测试发现）
- **[严重] 整页白屏**：`supabase.ts` 在空环境变量时 `createClient('')` 抛 `supabaseUrl is required`。改为始终用合法占位构造 `supabase` 客户端，行为开关交由 `isSupabaseConfigured`，未配置时前端完全走 Mock。
- **[严重] Store 崩溃**：auth / learning / admin 三个 store 未接 Mock 兜底，未配置 Supabase 时直接 `supabase.from(...)` 崩溃。已加 `isSupabaseConfigured` 守卫，未配置时静默返回，视图层 Mock 兜底接管。
- **[体验] 刷新掉登录**：Mock 登录态原仅存内存，整页刷新后丢失导致学员端空白。已持久化到 `localStorage`，`initSession` 自动恢复。

### 验证
- 无头浏览器（Chrome + puppeteer-core）冒烟测试 **13/13 通过**：登录、学员端任务中心（7 卡片）、学习记录、管理员看板/任务/学员页均渲染，0 控制台报错、0 页面异常、390px 无横向滚动。
- 详见 `TEST_REPORT.md`。

## [1.0.0] - 2024-08-13

### 新增

#### 学员端
- 统一登录页（支持邮箱登录 + 角色分流）
- 任务中心（本周任务列表、进度、状态、截止日）
- 课程目录/章节首页（7天学习网格）
- Day 学习流程（Hero → 讲解 → 核心句 → 重难点词 → 练习 → 总结）
- 标准/慢速范读播放（TTS 兜底）
- 重难点词发音、中文释义、音标
- 复制功能（剪贴板 + 降级方案）
- 欧陆词典跳转（eudic:// 协议，失败保留复制）
- 难词收藏（本地状态 + 事件记录）
- 录音跟读与回放（MediaRecorder API）
- 浏览器语音转写（Web Speech API）+ 关键词匹配/内容一致度
- 情景/听力/选择练习（单选题 + 得分反馈）
- Day 完成页（学习总结、有效时长）
- Day 7 周测（中译英口述 + 听力/词汇/情景选择）
- 学习记录页（学习日历、统计数据、最近学习、事件统计）

#### 管理员端
- 数据看板（指标卡、任务图表、Top 5、最近任务表）
- 发布任务（5步表单：课程 → 范围 → 日期 → 学员 → 确认）
- 任务分配（全体/分组/指定学员）
- 发布摘要确认
- 任务管理（列表、筛选、状态查看）
- 学员详情（进度、时长趋势、事件明细）
- 学习事件监控（筛选、类型徽章、CSV 导出）

#### 后端
- Supabase 数据库 Schema（8 张核心表）
- RLS 安全策略（按角色隔离数据）
- 自动用户创建触发器（auth.users → profiles）
- 学习事件记录（11 种事件类型）
- 有效学习时长心跳机制（20s 间隔，2分钟无操作暂停）

#### 设计系统
- Apple 风格紫色主题（#7C3AED）
- 移动端优先响应式（390px / 768px / 1024px+）
- 触控区域 >= 44px
- 圆角 <= 8px 的业务卡片
- 状态色与品牌色分离

### 技术栈
- Vue 3 + Vite + TypeScript
- Tailwind CSS
- Pinia 状态管理
- Vue Router 4
- Supabase JS Client
- Web Speech API
- MediaRecorder API

### 数据
- 6 门课程结构（Warm Up, In-flight Care, IFE & Wi-Fi, Catering, Chitchat, Incident）
- 4 个学员分组
- 6 天 Warm Up 示例内容（Day 1-6）
- 完整 mock 数据层（所有页面可独立运行）
