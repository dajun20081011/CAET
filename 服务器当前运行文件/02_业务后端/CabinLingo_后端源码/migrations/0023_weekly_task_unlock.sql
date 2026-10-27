-- Optional per-learner weekly task chains. Existing tasks remain immediately available.
ALTER TABLE cl_practice_tasks ADD COLUMN IF NOT EXISTS week_no integer;
ALTER TABLE cl_practice_tasks ADD COLUMN IF NOT EXISTS unlock_after_task_type text;
ALTER TABLE cl_practice_tasks ADD COLUMN IF NOT EXISTS unlock_after_task_id uuid;
ALTER TABLE cl_exam_tasks ADD COLUMN IF NOT EXISTS week_no integer;
ALTER TABLE cl_exam_tasks ADD COLUMN IF NOT EXISTS unlock_after_task_type text;
ALTER TABLE cl_exam_tasks ADD COLUMN IF NOT EXISTS unlock_after_task_id uuid;

DO $$ BEGIN
  ALTER TABLE cl_practice_tasks ADD CONSTRAINT ck_cl_practice_tasks_week_no
    CHECK (week_no IS NULL OR week_no BETWEEN 1 AND 52);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE cl_exam_tasks ADD CONSTRAINT ck_cl_exam_tasks_week_no
    CHECK (week_no IS NULL OR week_no BETWEEN 1 AND 52);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE cl_practice_tasks ADD CONSTRAINT ck_cl_practice_tasks_unlock_rule
    CHECK ((unlock_after_task_type IS NULL AND unlock_after_task_id IS NULL)
       OR (week_no IS NOT NULL AND unlock_after_task_type IN ('practice','exam') AND unlock_after_task_id IS NOT NULL));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE cl_exam_tasks ADD CONSTRAINT ck_cl_exam_tasks_unlock_rule
    CHECK ((unlock_after_task_type IS NULL AND unlock_after_task_id IS NULL)
       OR (week_no IS NOT NULL AND unlock_after_task_type IN ('practice','exam') AND unlock_after_task_id IS NOT NULL));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_cl_practice_tasks_unlock_after
  ON cl_practice_tasks(unlock_after_task_type, unlock_after_task_id)
  WHERE unlock_after_task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cl_exam_tasks_unlock_after
  ON cl_exam_tasks(unlock_after_task_type, unlock_after_task_id)
  WHERE unlock_after_task_id IS NOT NULL;
