-- Unify the administrator course-content entry while preserving all existing course history.
-- Video remains a reserved content mode until its learner progress flow is enabled.

ALTER TABLE cl_course_details
  ADD COLUMN IF NOT EXISTS course_kind text NOT NULL DEFAULT 'lesson';

ALTER TABLE cl_course_details
  ADD COLUMN IF NOT EXISTS content_mode text NOT NULL DEFAULT 'audio_text';

ALTER TABLE cl_course_details
  ADD COLUMN IF NOT EXISTS training_enabled boolean NOT NULL DEFAULT true;

ALTER TABLE cl_course_details
  ADD COLUMN IF NOT EXISTS content_config jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE cl_course_details
  ADD COLUMN IF NOT EXISTS zh_audio_file_id uuid REFERENCES files(id);

ALTER TABLE cl_course_details
  ADD COLUMN IF NOT EXISTS zh_audio_filename text;

ALTER TABLE cl_course_details
  ADD COLUMN IF NOT EXISTS en_audio_file_id uuid REFERENCES files(id);

ALTER TABLE cl_course_details
  ADD COLUMN IF NOT EXISTS en_audio_filename text;

DO $$ BEGIN
  ALTER TABLE cl_course_details ADD CONSTRAINT ck_cl_course_details_kind
    CHECK (course_kind IN ('lesson','expression_skill'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE cl_course_details ADD CONSTRAINT ck_cl_course_details_mode
    CHECK (content_mode IN ('audio_text','video'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_cl_course_details_kind_mode
  ON cl_course_details(course_kind, content_mode);
