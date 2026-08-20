# CAET 管理员初始化指南

## 创建第一个管理员账号

### 方法 1：通过 Supabase Dashboard (推荐)

1. 登录 Supabase Dashboard
2. 进入 Authentication > Users
3. 点击 "Add User" > "Send magic link" 或 "Create new user"
4. 填写管理员邮箱，创建密码
5. 在 SQL Editor 执行：

```sql
UPDATE profiles SET role = 'admin' WHERE id = '该用户的-uuid';
```

### 方法 2：通过 SQL 直接创建

```sql
-- 创建 auth 用户 (需要 Supabase Dashboard 权限或 service_role)
-- 之后更新 profile 角色
UPDATE profiles SET role = 'admin', display_name = '管理员' WHERE id = 'user-uuid';
```

### 方法 3：注册后提升权限

1. 在登录页注册新账号（默认 role = learner）
2. 在 SQL Editor 执行：

```sql
UPDATE profiles SET role = 'admin' WHERE email = 'your-email@example.com';
```

## 创建学员账号

管理员可在后台管理学员，或通过以下方式批量创建：

```sql
-- 批量创建 (需结合 auth.users 插入，建议在 Dashboard 中操作)
-- 或让学员自行注册，管理员在后台分配分组
```

## 创建分组

在管理员后台「系统设置」或直接在数据库中：

```sql
INSERT INTO learner_groups (name) VALUES ('乘务一组'), ('乘务二组'), ('新入职');
```

## 发布第一个任务

1. 管理员登录后进入「任务管理」
2. 点击「新建任务」
3. 选择课程、章节范围、日期
4. 选择学员（全部/分组/指定）
5. 确认发布

## 验证学习闭环

1. 管理员发布任务 → 学员收到任务
2. 学员进入课程学习 → 产生 learning_events
3. 学员完成 Day 7 周测 → 进度更新
4. 管理员查看数据看板 → 统计完成率、时长
5. 导出 CSV 验证数据完整性

## 开发测试账号

测试账号必须由开发人员通过本地环境变量临时创建，不在源码、文档或提交历史中保存账号和密码。生产环境禁止启用测试账号。
