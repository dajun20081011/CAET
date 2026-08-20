-- ============================================================
-- CAET 数据库 Schema（幂等，可重复执行）
-- 课程类型：course_type ∈ {broadcast, caet2, caet3}
-- 测评类型：assessment_type ∈ {broadcast_recording, english_qa, zh_to_en}
-- 学习流程共享；测评类型独立。
-- 注：uuid-ossp 扩展由 db_init.py 在导入本文件前创建。
-- ============================================================

-- 统一的 updated_at 触发器函数
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------- profiles ----------------
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    employee_no TEXT,
    role TEXT NOT NULL DEFAULT 'learner',   -- admin | instructor | learner
    group_id UUID,
    avatar_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------- learner_groups（班级） ----------------
CREATE TABLE IF NOT EXISTS learner_groups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------- courses（课程，含课程类型） ----------------
CREATE TABLE IF NOT EXISTS courses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    cover_url TEXT,
    course_type TEXT NOT NULL DEFAULT 'broadcast',  -- broadcast | caet2 | caet3
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 兼容已有部署：若 courses 已存在但无 course_type 列则补上
ALTER TABLE courses ADD COLUMN IF NOT EXISTS course_type TEXT NOT NULL DEFAULT 'broadcast';

-- ---------------- course_content（课程内容，按课程类型组织） ----------------
CREATE TABLE IF NOT EXISTS course_content (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    chapter_no INT NOT NULL,
    chapter_title TEXT NOT NULL,
    day_no INT NOT NULL,
    content_order INT DEFAULT 0,
    content_type TEXT NOT NULL,  -- passage | standard_audio | hard_words | key_sentences | in_lesson_test | weekly_test | qa_item | translate_item
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------- tasks（任务/作业） ----------------
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    course_id UUID NOT NULL REFERENCES courses(id),
    chapter_from INT DEFAULT 1,
    chapter_to INT DEFAULT 1,
    day_from INT DEFAULT 1,
    day_to INT DEFAULT 7,
    start_at TIMESTAMPTZ NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    completion_rule JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'active',
    created_by UUID NOT NULL REFERENCES profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------- task_assignments（任务分配） ----------------
CREATE TABLE IF NOT EXISTS task_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    learner_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    instructor_id UUID REFERENCES profiles(id) ON DELETE SET NULL,  -- 指派测评教员
    status TEXT DEFAULT 'not_started',  -- not_started | in_progress | completed
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    progress_percent NUMERIC(5,2) DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (task_id, learner_id)
);

-- ---------------- learner_progress（学习进度） ----------------
CREATE TABLE IF NOT EXISTS learner_progress (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    assignment_id UUID NOT NULL REFERENCES task_assignments(id) ON DELETE CASCADE,
    content_id UUID NOT NULL REFERENCES course_content(id) ON DELETE CASCADE,
    learner_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    completed BOOLEAN DEFAULT FALSE,
    effective_seconds INT DEFAULT 0,
    last_position JSONB,
    attempt_count INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------- learning_events（学习事件埋点） ----------------
CREATE TABLE IF NOT EXISTS learning_events (
    id BIGSERIAL PRIMARY KEY,
    learner_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    assignment_id UUID REFERENCES task_assignments(id) ON DELETE SET NULL,
    course_id UUID REFERENCES courses(id) ON DELETE SET NULL,
    content_id UUID REFERENCES course_content(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    event_value JSONB,
    client_timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------- assessments（测评记录，按类型独立） ----------------
CREATE TABLE IF NOT EXISTS assessments (
    id BIGSERIAL PRIMARY KEY,
    assignment_id UUID NOT NULL REFERENCES task_assignments(id) ON DELETE CASCADE,
    learner_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    content_id UUID REFERENCES course_content(id) ON DELETE SET NULL,
    course_id UUID REFERENCES courses(id) ON DELETE SET NULL,
    assessment_type TEXT NOT NULL,  -- broadcast_recording | english_qa | zh_to_en
    attempt_no INT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'submitted',  -- submitted | graded | resubmit
    answers JSONB NOT NULL DEFAULT '{}'::jsonb,
    score NUMERIC(6,2),
    feedback TEXT,
    instructor_id UUID REFERENCES profiles(id) ON DELETE SET NULL,
    graded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------- 索引 ----------------
CREATE INDEX IF NOT EXISTS idx_profiles_role ON profiles(role);
CREATE INDEX IF NOT EXISTS idx_profiles_group ON profiles(group_id);
CREATE INDEX IF NOT EXISTS idx_courses_type ON courses(course_type);
CREATE INDEX IF NOT EXISTS idx_content_course ON course_content(course_id);
CREATE INDEX IF NOT EXISTS idx_tasks_course ON tasks(course_id);
CREATE INDEX IF NOT EXISTS idx_assignments_task ON task_assignments(task_id);
CREATE INDEX IF NOT EXISTS idx_assignments_learner ON task_assignments(learner_id);
CREATE INDEX IF NOT EXISTS idx_progress_assignment ON learner_progress(assignment_id);
CREATE INDEX IF NOT EXISTS idx_events_learner ON learning_events(learner_id);
CREATE INDEX IF NOT EXISTS idx_events_assignment ON learning_events(assignment_id);
CREATE INDEX IF NOT EXISTS idx_assessments_assignment ON assessments(assignment_id);
CREATE INDEX IF NOT EXISTS idx_assessments_learner ON assessments(learner_id);
CREATE INDEX IF NOT EXISTS idx_assessments_type ON assessments(assessment_type);

-- ---------------- updated_at 触发器绑定 ----------------
DROP TRIGGER IF EXISTS trg_profiles_updated ON profiles;
CREATE TRIGGER trg_profiles_updated BEFORE UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_courses_updated ON courses;
CREATE TRIGGER trg_courses_updated BEFORE UPDATE ON courses
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_content_updated ON course_content;
CREATE TRIGGER trg_content_updated BEFORE UPDATE ON course_content
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_tasks_updated ON tasks;
CREATE TRIGGER trg_tasks_updated BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_assignments_updated ON task_assignments;
CREATE TRIGGER trg_assignments_updated BEFORE UPDATE ON task_assignments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_progress_updated ON learner_progress;
CREATE TRIGGER trg_progress_updated BEFORE UPDATE ON learner_progress
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_assessments_updated ON assessments;
CREATE TRIGGER trg_assessments_updated BEFORE UPDATE ON assessments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
