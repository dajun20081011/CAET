-- CAET Learning Platform V1 staging schema.
-- Empty database only; no production data, credentials or seed users are included.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS products (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL,
  name text NOT NULL, status text NOT NULL CHECK (status IN ('implemented','reserved'))
);
CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), external_ref text UNIQUE,
  display_name text NOT NULL, email text UNIQUE, is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS organizations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS departments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid NOT NULL REFERENCES organizations(id), name text NOT NULL
);
CREATE TABLE IF NOT EXISTS classes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id uuid REFERENCES organizations(id), code text NOT NULL, name text NOT NULL
);
CREATE TABLE IF NOT EXISTS roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_id uuid REFERENCES products(id), code text NOT NULL, name text NOT NULL,
  UNIQUE(product_id, code)
);
CREATE TABLE IF NOT EXISTS permissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), product_id uuid REFERENCES products(id), code text NOT NULL, name text NOT NULL,
  UNIQUE(product_id, code)
);
CREATE TABLE IF NOT EXISTS user_roles (
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE, role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_overrides jsonb NOT NULL DEFAULT '[]'::jsonb, PRIMARY KEY(user_id, role_id)
);
CREATE TABLE IF NOT EXISTS product_memberships (
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE, product_id uuid NOT NULL REFERENCES products(id),
  class_id uuid REFERENCES classes(id), status text NOT NULL DEFAULT 'active', PRIMARY KEY(user_id, product_id)
);
CREATE TABLE IF NOT EXISTS files (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), owner_id uuid REFERENCES users(id), object_key text UNIQUE NOT NULL,
  mime_type text NOT NULL, byte_size bigint, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), actor_id uuid REFERENCES users(id), product_code text,
  action text NOT NULL, resource_type text NOT NULL, resource_id uuid, metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cl_broadcasts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text UNIQUE NOT NULL, title text NOT NULL,
  language text NOT NULL DEFAULT 'en-US', status text NOT NULL DEFAULT 'published' CHECK (status IN ('draft','published','archived')),
  created_by uuid REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cl_segments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), broadcast_id uuid NOT NULL REFERENCES cl_broadcasts(id) ON DELETE CASCADE,
  sequence_no integer NOT NULL CHECK (sequence_no > 0), reference_text text NOT NULL, audio_file_id uuid REFERENCES files(id),
  UNIQUE(broadcast_id, sequence_no)
);

-- Practice has its own lifecycle and repeat-attempt history.
CREATE TABLE IF NOT EXISTS cl_practice_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), broadcast_id uuid NOT NULL REFERENCES cl_broadcasts(id), title text NOT NULL,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','closed')),
  completion_rule jsonb NOT NULL DEFAULT '{"min_attempts":1}'::jsonb, due_at timestamptz, created_by uuid REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cl_practice_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), task_id uuid NOT NULL REFERENCES cl_practice_tasks(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id), status text NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started','in_progress','completed')),
  assigned_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz, UNIQUE(task_id, user_id)
);
CREATE TABLE IF NOT EXISTS cl_practice_attempts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), assignment_id uuid NOT NULL REFERENCES cl_practice_assignments(id) ON DELETE CASCADE,
  segment_id uuid NOT NULL REFERENCES cl_segments(id), recording_id uuid, attempt_no integer NOT NULL CHECK (attempt_no > 0),
  transcript text, ai_result_id uuid, feedback jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(assignment_id, attempt_no)
);

-- Exam is a separate whole-paper, limited-recording and publishable assessment workflow.
CREATE TABLE IF NOT EXISTS cl_exam_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), broadcast_id uuid NOT NULL REFERENCES cl_broadcasts(id), title text NOT NULL,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','open','closed')),
  max_recordings integer NOT NULL DEFAULT 1 CHECK (max_recordings BETWEEN 1 AND 10), due_at timestamptz,
  created_by uuid REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cl_exam_packages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), exam_task_id uuid NOT NULL REFERENCES cl_exam_tasks(id) ON DELETE CASCADE,
  version integer NOT NULL DEFAULT 1, title text NOT NULL, UNIQUE(exam_task_id, version)
);
CREATE TABLE IF NOT EXISTS cl_exam_papers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), package_id uuid NOT NULL REFERENCES cl_exam_packages(id) ON DELETE CASCADE,
  segment_id uuid NOT NULL REFERENCES cl_segments(id), sequence_no integer NOT NULL CHECK (sequence_no > 0),
  UNIQUE(package_id, sequence_no)
);
CREATE TABLE IF NOT EXISTS cl_exam_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), exam_task_id uuid NOT NULL REFERENCES cl_exam_tasks(id) ON DELETE CASCADE,
  package_id uuid REFERENCES cl_exam_packages(id), user_id uuid NOT NULL REFERENCES users(id),
  status text NOT NULL DEFAULT 'not_started' CHECK (status IN ('not_started','in_progress','submitted','graded','published')),
  submitted_at timestamptz, UNIQUE(exam_task_id, user_id)
);
CREATE TABLE IF NOT EXISTS cl_recordings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES users(id), file_id uuid REFERENCES files(id),
  purpose text NOT NULL CHECK (purpose IN ('practice','exam')), duration_ms integer, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cl_ai_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), recording_id uuid REFERENCES cl_recordings(id), adapter text NOT NULL,
  provider text NOT NULL, provider_version text NOT NULL, status text NOT NULL, payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cl_manual_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), exam_assignment_id uuid NOT NULL REFERENCES cl_exam_assignments(id) ON DELETE CASCADE,
  reviewer_id uuid NOT NULL REFERENCES users(id), status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','completed')),
  comments text, reviewed_at timestamptz
);
CREATE TABLE IF NOT EXISTS cl_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), exam_assignment_id uuid NOT NULL REFERENCES cl_exam_assignments(id) ON DELETE CASCADE,
  ai_score numeric(5,2), manual_score numeric(5,2), final_score numeric(5,2), status text NOT NULL DEFAULT 'unpublished' CHECK (status IN ('unpublished','published')),
  published_at timestamptz
);
CREATE TABLE IF NOT EXISTS cl_progress (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  broadcast_id uuid NOT NULL REFERENCES cl_broadcasts(id), segment_id uuid REFERENCES cl_segments(id),
  practice_attempts integer NOT NULL DEFAULT 0, last_ai_status text, last_practiced_at timestamptz,
  UNIQUE(user_id, broadcast_id, segment_id)
);

CREATE INDEX IF NOT EXISTS idx_cl_practice_assignments_user ON cl_practice_assignments(user_id, status);
CREATE INDEX IF NOT EXISTS idx_cl_practice_attempts_assignment ON cl_practice_attempts(assignment_id, created_at);
CREATE INDEX IF NOT EXISTS idx_cl_exam_assignments_user ON cl_exam_assignments(user_id, status);
CREATE INDEX IF NOT EXISTS idx_cl_recordings_user_purpose ON cl_recordings(user_id, purpose, created_at);
CREATE INDEX IF NOT EXISTS idx_cl_progress_user ON cl_progress(user_id, broadcast_id);
