BEGIN;

-- Preserve every course-standard revision and record who created it.
ALTER TABLE cl_course_standards
  ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES users(id);
ALTER TABLE cl_course_standards
  ADD COLUMN IF NOT EXISTS change_summary text NOT NULL DEFAULT '';
ALTER TABLE cl_course_standards
  ADD COLUMN IF NOT EXISTS standard_audio_filename text;

CREATE INDEX IF NOT EXISTS idx_cl_course_standards_content_created
  ON cl_course_standards(content_item_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cl_practice_tasks_status
  ON cl_practice_tasks(status);
CREATE INDEX IF NOT EXISTS idx_cl_exam_tasks_status
  ON cl_exam_tasks(status);

COMMIT;
