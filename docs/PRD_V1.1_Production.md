# CAET 学练测平台 V1.1 生产版 PRD

> 本文是 `01_Product/CAET_V1_PRD.md`（V1 输入规格）的**下一阶段定义**，专门覆盖从「Mock 演示」到「真实生产系统」之间的缺口。
> V1 PRD 中的产品目标、角色、周测题型、非目标均继续有效，本文不再重复，仅补充生产约束与未交付项。

## 0. 当前状态（写作基准）

| 项 | 状态 | 说明 |
|----|------|------|
| 前端工程 | ✅ 已构建 | Vue 3 + Vite + TS + Tailwind，13 页面 + 2 布局 + 3 store |
| 演示部署 | ✅ 已上线（Mock） | CloudStudio 公开链接，7/7 无头浏览器验证通过 |
| 后端 Schema | 🟡 已起草未上线 | `supabase/migrations/000001` + `000002` + `seed.sql` |
| 认证 | ❌ 未接 | 仅 Mock 快速登录，依赖 localStorage |
| 音频 | ❌ TTS 兜底 | 无真实 MP3，不符合 `AUDIO_ASSET_SPEC` |
| 课程内容 | 🟡 仅 Warm Up Ch1 | Day1–6 + Day7 周测结构化，其余为空 |
| 学习统计 | 🟡 前端已实现 | 心跳/事件逻辑就绪，未落库验证 |

## 1. 产品目标（生产约束补充）

在 V1 目标（任务发布、学练测、进度与投入跟踪）之上，V1.1 新增**生产约束**：

- **真实多用户**：学员/管理员各自独立账户，数据隔离。
- **持久化与可审计**：所有学习行为、时长、进度写入数据库，管理员可回溯。
- **可运营**：学员开通、任务发布、内容更新均可在后台完成，无需改代码。

## 2. 非目标（V1.1）

- 与 V1 一致：正式语音评分、人工评审、排行榜、积分商城、等级体系。
- **本版不做**：其余 5 门课程（In-flight Care / IFE & Wi-Fi / Catering / Chitchat / Incident）的完整内容生产——仅完成骨架接入与内容生产计划（见 §7）。

## 3. 角色与权限

- 角色：`learner` / `admin`（见 `profiles.role`）。
- RLS 已起草（`supabase/migrations/000002_rls_policies.sql`）：
  - 读：**own or admin-all**；`learner_groups / courses / course_content` 全体认证用户可读。
  - 写：`tasks / task_assignments / learner_progress / learning_events` 仅 admin 全写；learner 仅可 INSERT/UPDATE **自己的** progress 与 events。
  - 新用户注册自动建 `profiles`（触发器 `handle_new_user`，默认 `role='learner'`）。
- **硬性安全要求**：`service_role` key 绝不进入前端；anon key 仅用于客户端，所有写受 RLS 约束。

## 4. 后端接入（Supabase）

### 4.1 已就绪的数据模型（8 张表）

`profiles` · `learner_groups` · `courses` · `course_content` · `tasks` · `task_assignments` · `learner_progress` · `learning_events`
+ 索引、`updated_at` 触发器、注册自动建档触发器。

### 4.2 V1.1 接入待办

1. 创建 Supabase 项目，按顺序执行 `000001_init_schema.sql` → `000002_rls_policies.sql` → `seed.sql`。
2. 建 Storage bucket：
   - `audio`：公开读、仅 admin/service 写；存放句子与重点词 MP3。
   - `avatars`（可选）：学员头像。
3. Auth 配置：开启邮箱确认、设定密码强度与 token 有效期。
4. 注入环境变量 **`VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`**，重新 `npm run build`（Vite `import.meta.env` 需构建期注入）。
5. 前端 `isSupabaseConfigured` 守卫自动切换为真实后端模式（代码已就绪）。

### 4.3 有效学习时长（生产级）

- 前端已实现：20s 心跳 + 活跃判定；切后台 / 页面隐藏 / 2 分钟无操作自动暂停。
- V1.1 需联调：心跳写入 `learning_events`，累计写入 `learner_progress.effective_seconds`。
- 准确性兜底：客户端时间不可信，服务端以 `created_at` 为准做去重与防刷。

## 5. 认证与账户体系

| 场景 | 方案 |
|------|------|
| 开发期 | Supabase Auth **magic link**（邮箱发登录链接） |
| 生产期 | **邮箱 + 密码** + 邮箱验证；可选企业 SSO（东航） |
| 真实邮件 | 需在 Supabase 配置 SMTP（或自定义邮件服务） |
| 首个管理员 | 通过 SQL 将某账户 `role` 置为 `admin`，或邀请制 |
| 学员开通 | 管理员「指定学员」时若邮箱未注册则发邀请；或自助注册默认 `learner` |
| 角色分流 | 登录后按 `profile.role` 路由（前端已实现） |

## 6. 音频生产管线（V1.1 核心）

遵循 `04_Course/AUDIO_ASSET_SPEC.md`：**TTS 不作实时依赖，先生产高质量 MP3 再播放。**

- **命名规范**
  - 句子：`{id}-normal.mp3` / `{id}-slow.mp3`
  - 重点词：`{word}.mp3`
- **存储**：Supabase Storage `audio` bucket，路径建议 `warmup/ch{chapter}/d{day}/{file}`。
- **生产流程**
  1. 从 `course-data/*.json` 抽取全部 `sentence.en` 与 `vocabulary.word`。
  2. 用 TTS 或真人录音生成 normal / slow 两套。
  3. 上传 Storage，URL 回填到 `course_content.payload.audio`。
  4. 前端由现有 `audio.normal / audio.slow` 字段改为播放 Storage URL（结构已具备，仅改数据源）。
- **兜底**：无 MP3 时前端仍可用浏览器 TTS，但 UI 必须标注「临时语音」，不得混入正式课程。
- **验收**：学员端范读 / 慢速 / 重点词发音均播放真实音频；正式课程无 TTS 临时语音。

## 7. 课程内容扩展

- **现状**：仅 Warm Up Ch1（Day1–6 + Day7 周测）结构化。
- **V1.1 目标**
  - 完整 **Warm Up** 全量章节：按教材逐章逐日，每 Day 含 `hero / explanation / sentence / vocabulary / scenario / practice / summary`，Day7 为 `weekly_test`。
  - 周测题型绑定真实题：中译英口述+转写（关键词匹配/内容一致度）、听力选择、词汇选择、情景选择（UI 已实现）。
  - 其余 5 门课程：完成**内容生产计划与骨架接入**（course_content 可写、导入脚本可用），完整生产列为后续版本。
- **内容管理**：`course_content` 表 admin 可写（RLS）；提供 `scripts/import-course.js` 从 JSON 批量导入。

## 8. 学习统计与有效时长

- 维度：学员 / 任务 / 章节 / 日；**11 类 event_type** 独立统计（音频播放、录音、复制、欧陆、收藏、练习、周测、心跳等）。
- 防作弊/准确性：切后台暂停、2 分钟无操作暂停、页面隐藏暂停（前端已实现，需联调入库）。
- 管理员看板指标：完成率、学习人数、有效时长、人均时长、任务完成数、内容完成率 Top5、活跃趋势（UI 已实现，待接真实数据）。

## 9. 管理员分析深度（V1.1 增强）

- 单学员明细：任务进度、时长趋势、事件明细（UI 已实现）。
- **分组 / cohort 对比**：`learner_groups` 已建模，本版补齐管理 UI 与对比视图。
- **CSV 导出**：events / progress / assignments（已实现，需接真实数据 + 大批量分页）。
- 预警（可选）：逾期任务、低完成率学员清单。

## 10. 验收标准

| 域 | 项 | 状态 |
|----|----|------|
| Auth | 管理员/学员登录、角色分流、未登录拦截 | 前端已验，待后端联调 |
| 管理员 | 创建/发布任务、指定学员/分组、查看明细、CSV 导出 | 前端已验，待后端联调 |
| 学员 | 被分配任务、范读/慢速/重点词（真实音频）、复制/欧陆/收藏、录音回放、转写对照、练习、周测、重登保留 | 前端已验，待后端联调 |
| 数据 | 有效时长仅活跃累计、切后台停、2min 停、event 独立统计、管理与库一致 | 前端逻辑就绪，待入库验证 |
| 响应式 | 390/iPhone/Android/iPad/桌面、无横向滚动、触控 ≥44px | 前端已验 |
| 安全 | RLS 开启、learner 不可读他人/不可发任务、service_role 不入前端 | schema 已起草，待渗透验证 |
| 音频 | 正式课程无 TTS 临时语音、真实 MP3 可播放 | ❌ 待生产 |

> 说明：「前端已验」指在 Mock 模式 + 无头浏览器下功能可达；「待后端联调」指需在真实 Supabase 上复测入库与权限。

## 11. 部署与运维

- **前端**：静态托管（CloudStudio / 同类），SPA 需配置 **history 路由回退**（否则深链 404）。
- **环境变量**：`VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`，必须**构建期**注入。
- **后端**：Supabase 托管，迁移脚本版本化、可重放。
- **监控**：前端错误日志、Supabase 配额/用量告警。
- **数据安全**：RLS 强制、service_role 仅服务端、开启 PITR 备份（Supabase 付费层）。

## 12. 里程碑（建议）

- **M1 后端上线 + 认证**：建项目 → 跑迁移 → 接 Auth → 登录分流真实验证。
- **M2 音频管线**：生产 Warm Up Ch1 音频并接入，关闭 TTS 兜底。
- **M3 内容全量**：Warm Up 完整 + 其余 5 门骨架接入。
- **M4 统计/分析联调 + 验收 + 重新部署生产版**：跑通 §10 全部「待后端联调」项。

## 13. 风险与依赖（需用户/外部）

| 依赖 | 提供方 | 阻塞项 |
|------|--------|--------|
| Supabase 项目（URL + anon key） | 用户账号 | M1 入口 |
| 音频生产（录音/TTS 资源） | 内容/语音团队 | M2 |
| SMTP（真实学员邮箱） | 邮件服务 | 生产期 Auth |
| 教材文本与版权授权 | 东航教材 | §7 内容 |
| 学员真实数据 / 工号体系 | 培训管理方 | 上线数据 |

## 14. 成功指标（KPI）

- 学员激活率、任务完成率、平均有效学习时长、周测通过率、**音频覆盖率**（已生产 MP3 / 应生产总数）。

---
*关联文档：`CAET_V1_PRD.md`（目标与范围）、`AUDIO_ASSET_SPEC.md`（音频规范）、`supabase/migrations/*`（schema 与 RLS）、`TEST_REPORT.md`（当前验证状态）。*
