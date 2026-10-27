-- Course editor simplification: repeatable standard-audio tracks and lifecycle support.
-- Additive and idempotent. Existing media references are backfilled as track 1.

BEGIN;

CREATE TABLE IF NOT EXISTS cl_course_audio_tracks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  course_version_id uuid NOT NULL REFERENCES cl_course_versions(id) ON DELETE CASCADE,
  file_id uuid NOT NULL REFERENCES files(id),
  language_code text NOT NULL CHECK (language_code IN ('zh','en','bilingual')),
  sequence_no integer NOT NULL CHECK (sequence_no BETWEEN 1 AND 2),
  label text NOT NULL DEFAULT '',
  filename text NOT NULL DEFAULT '',
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(course_version_id,language_code,sequence_no)
);

CREATE INDEX IF NOT EXISTS idx_cl_course_audio_tracks_version
  ON cl_course_audio_tracks(course_version_id,language_code,sequence_no);

INSERT INTO cl_course_audio_tracks(course_version_id,file_id,language_code,sequence_no,label,filename,created_by)
SELECT course_version_id,standard_audio_file_id,'bilingual',1,'完整示范音频',COALESCE(standard_audio_filename,''),created_by
FROM cl_course_details
WHERE standard_audio_file_id IS NOT NULL
ON CONFLICT(course_version_id,language_code,sequence_no) DO NOTHING;

INSERT INTO cl_course_audio_tracks(course_version_id,file_id,language_code,sequence_no,label,filename,created_by)
SELECT course_version_id,zh_audio_file_id,'zh',1,'中文标准音频 1',COALESCE(zh_audio_filename,''),created_by
FROM cl_course_details
WHERE zh_audio_file_id IS NOT NULL
ON CONFLICT(course_version_id,language_code,sequence_no) DO NOTHING;

INSERT INTO cl_course_audio_tracks(course_version_id,file_id,language_code,sequence_no,label,filename,created_by)
SELECT course_version_id,en_audio_file_id,'en',1,'英文标准音频 1',COALESCE(en_audio_filename,''),created_by
FROM cl_course_details
WHERE en_audio_file_id IS NOT NULL
ON CONFLICT(course_version_id,language_code,sequence_no) DO NOTHING;

COMMIT;
