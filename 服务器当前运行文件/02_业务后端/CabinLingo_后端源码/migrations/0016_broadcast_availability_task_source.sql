-- Broadcast library availability and task-source integration.
-- Additive only: existing courses, tasks and training history remain unchanged.

ALTER TABLE cl_broadcast_scripts
  ADD COLUMN IF NOT EXISTS enabled boolean NOT NULL DEFAULT false;

ALTER TABLE cl_course_versions
  ADD COLUMN IF NOT EXISTS source_broadcast_script_id uuid
    REFERENCES cl_broadcast_scripts(id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_cl_broadcast_scripts_enabled
  ON cl_broadcast_scripts(enabled, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_cl_course_versions_broadcast_source
  ON cl_course_versions(source_broadcast_script_id)
  WHERE source_broadcast_script_id IS NOT NULL;
