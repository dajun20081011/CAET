-- Phase 3: organization/class management and versioned course catalog.
-- Additive migration only. Existing users, broadcasts, tasks and training history are preserved.

ALTER TABLE organizations ADD COLUMN IF NOT EXISTS code text;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active';
ALTER TABLE classes ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active';

CREATE UNIQUE INDEX IF NOT EXISTS uq_organizations_code
  ON organizations(lower(code)) WHERE code IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_classes_org_code
  ON classes(organization_id, lower(code));

CREATE TABLE IF NOT EXISTS class_memberships (
  class_id uuid NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
  joined_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(class_id, user_id)
);

INSERT INTO class_memberships(class_id,user_id,status)
SELECT class_id,id,'active' FROM users WHERE class_id IS NOT NULL
ON CONFLICT(class_id,user_id) DO UPDATE SET status='active';

CREATE TABLE IF NOT EXISTS cl_courses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid REFERENCES organizations(id),
  code text NOT NULL,
  title text NOT NULL,
  description text NOT NULL DEFAULT '',
  category text NOT NULL DEFAULT 'broadcast',
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(organization_id, code)
);

CREATE TABLE IF NOT EXISTS cl_course_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id uuid NOT NULL REFERENCES cl_courses(id) ON DELETE CASCADE,
  version_no integer NOT NULL CHECK (version_no > 0),
  version_label text NOT NULL,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
  change_summary text NOT NULL DEFAULT '',
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  published_by uuid REFERENCES users(id),
  published_at timestamptz,
  UNIQUE(course_id, version_no),
  UNIQUE(course_id, version_label)
);

CREATE TABLE IF NOT EXISTS cl_chapters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  course_version_id uuid NOT NULL REFERENCES cl_course_versions(id) ON DELETE CASCADE,
  code text NOT NULL,
  title text NOT NULL,
  sequence_no integer NOT NULL CHECK (sequence_no > 0),
  learning_objective text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(course_version_id, code),
  UNIQUE(course_version_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS cl_content_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chapter_id uuid NOT NULL REFERENCES cl_chapters(id) ON DELETE CASCADE,
  content_type text NOT NULL CHECK (content_type IN ('html','broadcast','audio','document')),
  title text NOT NULL,
  sequence_no integer NOT NULL CHECK (sequence_no > 0),
  source_filename text,
  sanitized_html text,
  original_sha256 text,
  sanitized_sha256 text,
  validation_report jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(chapter_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS cl_content_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  content_item_id uuid NOT NULL REFERENCES cl_content_items(id) ON DELETE CASCADE,
  file_id uuid REFERENCES files(id),
  asset_role text NOT NULL DEFAULT 'attachment',
  original_filename text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cl_course_standards (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  content_item_id uuid NOT NULL REFERENCES cl_content_items(id) ON DELETE CASCADE,
  standard_text text NOT NULL DEFAULT '',
  standard_audio_file_id uuid REFERENCES files(id),
  pronunciation_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
  prosody_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
  expression_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
  rule_version text NOT NULL DEFAULT '1.0',
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE cl_practice_tasks ADD COLUMN IF NOT EXISTS course_version_id uuid REFERENCES cl_course_versions(id);
ALTER TABLE cl_exam_tasks ADD COLUMN IF NOT EXISTS course_version_id uuid REFERENCES cl_course_versions(id);
ALTER TABLE cl_practice_tasks ALTER COLUMN broadcast_id DROP NOT NULL;
ALTER TABLE cl_exam_tasks ALTER COLUMN broadcast_id DROP NOT NULL;

DO $$ BEGIN
  ALTER TABLE cl_practice_tasks ADD CONSTRAINT ck_cl_practice_task_source
    CHECK (num_nonnulls(broadcast_id, course_version_id) = 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE cl_exam_tasks ADD CONSTRAINT ck_cl_exam_task_source
    CHECK (num_nonnulls(broadcast_id, course_version_id) = 1);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_cl_course_versions_course_status ON cl_course_versions(course_id, status);
CREATE INDEX IF NOT EXISTS idx_cl_chapters_version_sequence ON cl_chapters(course_version_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_cl_content_items_chapter_sequence ON cl_content_items(chapter_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_class_memberships_user ON class_memberships(user_id, status);

WITH product AS (SELECT id FROM products WHERE code='cabinlingo')
INSERT INTO permissions(product_id,code,name)
SELECT product.id,item.code,item.name FROM product CROSS JOIN (VALUES
  ('cabinlingo:course.manage','Manage CabinLingo course catalog'),
  ('cabinlingo:organization.manage','Manage CabinLingo organizations and classes')
) AS item(code,name)
ON CONFLICT(product_id,code) DO UPDATE SET name=excluded.name;

INSERT INTO role_permissions(role_id,permission_id)
SELECT role.id,permission.id
FROM roles role
JOIN products product ON product.id=role.product_id AND product.code='cabinlingo'
JOIN permissions permission ON permission.product_id=product.id
WHERE (role.code='admin' AND permission.code IN ('cabinlingo:course.manage','cabinlingo:organization.manage'))
   OR (role.code='instructor' AND permission.code='cabinlingo:course.manage')
ON CONFLICT DO NOTHING;
