CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS training_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS training_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name VARCHAR(120),
    employee_no VARCHAR(80),
    role VARCHAR(20) NOT NULL DEFAULT 'learner',
    group_id UUID REFERENCES training_groups(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT training_users_role_check CHECK (role IN ('learner','instructor','admin'))
);

CREATE TABLE IF NOT EXISTS training_tasks (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    task_type VARCHAR(20) NOT NULL,
    course_id BIGINT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    chapter_from INTEGER NOT NULL DEFAULT 1,
    chapter_to INTEGER NOT NULL DEFAULT 1,
    day_from INTEGER NOT NULL DEFAULT 1,
    day_to INTEGER NOT NULL DEFAULT 1,
    start_at TIMESTAMPTZ NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    completion_rule JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_by UUID NOT NULL REFERENCES training_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT training_tasks_type_check CHECK (task_type IN ('practice','exam')),
    CONSTRAINT training_tasks_status_check CHECK (status IN ('draft','active','closed')),
    CONSTRAINT training_tasks_time_check CHECK (due_at > start_at)
);

CREATE TABLE IF NOT EXISTS training_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id BIGINT NOT NULL REFERENCES training_tasks(id) ON DELETE CASCADE,
    learner_id UUID NOT NULL REFERENCES training_users(id) ON DELETE CASCADE,
    instructor_id UUID REFERENCES training_users(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'not_started',
    progress_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(task_id, learner_id),
    CONSTRAINT training_assignments_status_check CHECK (status IN ('not_started','in_progress','completed'))
);

CREATE TABLE IF NOT EXISTS training_progress (
    id BIGSERIAL PRIMARY KEY,
    assignment_id UUID NOT NULL REFERENCES training_assignments(id) ON DELETE CASCADE,
    lesson_id BIGINT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    effective_seconds INTEGER NOT NULL DEFAULT 0,
    last_position JSONB,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(assignment_id, lesson_id)
);

CREATE TABLE IF NOT EXISTS training_events (
    id BIGSERIAL PRIMARY KEY,
    learner_id UUID NOT NULL REFERENCES training_users(id) ON DELETE CASCADE,
    assignment_id UUID REFERENCES training_assignments(id) ON DELETE SET NULL,
    course_id BIGINT REFERENCES courses(id) ON DELETE SET NULL,
    lesson_id BIGINT REFERENCES lessons(id) ON DELETE SET NULL,
    event_type VARCHAR(80) NOT NULL,
    event_value JSONB,
    client_timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS practice_attempts (
    id BIGSERIAL PRIMARY KEY,
    assignment_id UUID NOT NULL REFERENCES training_assignments(id) ON DELETE CASCADE,
    learner_id UUID NOT NULL REFERENCES training_users(id) ON DELETE CASCADE,
    lesson_id BIGINT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL,
    audio_url TEXT,
    transcript TEXT NOT NULL DEFAULT '',
    reference_text TEXT NOT NULL DEFAULT '',
    feedback JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(assignment_id, lesson_id, attempt_no)
);

CREATE TABLE IF NOT EXISTS exam_submissions (
    id BIGSERIAL PRIMARY KEY,
    assignment_id UUID NOT NULL REFERENCES training_assignments(id) ON DELETE CASCADE,
    learner_id UUID NOT NULL REFERENCES training_users(id) ON DELETE CASCADE,
    attempt_no INTEGER NOT NULL,
    answers JSONB NOT NULL DEFAULT '{}'::jsonb,
    ai_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    ai_score NUMERIC(6,2),
    manual_score NUMERIC(6,2),
    final_score NUMERIC(6,2),
    feedback TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'submitted',
    instructor_id UUID REFERENCES training_users(id) ON DELETE SET NULL,
    graded_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(assignment_id, attempt_no),
    CONSTRAINT exam_submissions_status_check CHECK (status IN ('submitted','graded','resubmit','published'))
);

CREATE INDEX IF NOT EXISTS idx_training_users_role ON training_users(role);
CREATE INDEX IF NOT EXISTS idx_training_tasks_type ON training_tasks(task_type);
CREATE INDEX IF NOT EXISTS idx_training_assignments_learner ON training_assignments(learner_id);
CREATE INDEX IF NOT EXISTS idx_training_progress_assignment ON training_progress(assignment_id);
CREATE INDEX IF NOT EXISTS idx_practice_attempts_assignment ON practice_attempts(assignment_id);
CREATE INDEX IF NOT EXISTS idx_exam_submissions_assignment ON exam_submissions(assignment_id);
