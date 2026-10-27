BEGIN;

ALTER TABLE cl_practice_tasks
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
  ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES users(id);

ALTER TABLE cl_exam_tasks
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
  ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES users(id);

CREATE INDEX IF NOT EXISTS idx_cl_practice_tasks_active
  ON cl_practice_tasks(created_at DESC)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_cl_exam_tasks_active
  ON cl_exam_tasks(created_at DESC)
  WHERE deleted_at IS NULL;

COMMIT;
