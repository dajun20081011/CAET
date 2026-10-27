-- Cache word-timestamp-derived sentence ranges for precise course audio seeking.
-- Additive and idempotent; published course text and media are not modified.

BEGIN;

ALTER TABLE cl_course_audio_tracks
  ADD COLUMN IF NOT EXISTS alignment jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE cl_course_audio_tracks
  ADD COLUMN IF NOT EXISTS alignment_updated_at timestamptz;

COMMIT;
