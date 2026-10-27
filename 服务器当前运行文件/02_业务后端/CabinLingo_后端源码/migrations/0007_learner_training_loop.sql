-- Phase 4: learner training loop. Additive and history-preserving.

ALTER TABLE cl_practice_attempts ALTER COLUMN segment_id DROP NOT NULL;
ALTER TABLE cl_practice_attempts ADD COLUMN IF NOT EXISTS content_item_id uuid REFERENCES cl_content_items(id);
ALTER TABLE cl_practice_attempts ADD COLUMN IF NOT EXISTS correction_of_attempt_id uuid REFERENCES cl_practice_attempts(id);
ALTER TABLE cl_practice_attempts ADD COLUMN IF NOT EXISTS ai_status text NOT NULL DEFAULT 'pending';
ALTER TABLE cl_practice_attempts ADD COLUMN IF NOT EXISTS score_summary jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE cl_practice_attempts ADD COLUMN IF NOT EXISTS issues jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE cl_recordings ADD COLUMN IF NOT EXISTS assignment_id uuid;
ALTER TABLE cl_recordings ADD COLUMN IF NOT EXISTS content_item_id uuid REFERENCES cl_content_items(id);
ALTER TABLE cl_recordings ADD COLUMN IF NOT EXISTS mime_type text;
ALTER TABLE cl_recordings ADD COLUMN IF NOT EXISTS byte_size bigint;

CREATE TABLE IF NOT EXISTS cl_teacher_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  learner_id uuid NOT NULL REFERENCES users(id),
  practice_attempt_id uuid REFERENCES cl_practice_attempts(id),
  exam_assignment_id uuid REFERENCES cl_exam_assignments(id),
  teacher_id uuid NOT NULL REFERENCES users(id),
  summary text NOT NULL,
  correction_advice text NOT NULL DEFAULT '',
  required_retraining boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'published' CHECK (status IN ('draft','published','acknowledged')),
  published_at timestamptz,
  acknowledged_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(practice_attempt_id, exam_assignment_id) = 1)
);

CREATE TABLE IF NOT EXISTS cl_growth_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  learner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type text NOT NULL CHECK (event_type IN ('practice_submitted','practice_corrected','task_completed','feedback_received','feedback_acknowledged')),
  assignment_id uuid,
  practice_attempt_id uuid REFERENCES cl_practice_attempts(id),
  content_item_id uuid REFERENCES cl_content_items(id),
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cl_course_standard_content_version
  ON cl_course_standards(content_item_id, rule_version);
CREATE INDEX IF NOT EXISTS idx_cl_practice_attempts_content
  ON cl_practice_attempts(assignment_id, content_item_id, created_at);
CREATE INDEX IF NOT EXISTS idx_cl_teacher_feedback_learner
  ON cl_teacher_feedback(learner_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cl_growth_events_learner
  ON cl_growth_events(learner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cl_recordings_assignment
  ON cl_recordings(assignment_id, created_at DESC);

