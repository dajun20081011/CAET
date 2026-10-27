-- Expression-skill video courses backed by private Tencent COS objects.
-- Additive and idempotent; signed URLs and credentials are never persisted.
BEGIN;

ALTER TABLE cl_course_details ADD COLUMN IF NOT EXISTS cos_video_key text;
ALTER TABLE cl_course_details ADD COLUMN IF NOT EXISTS cos_video_filename text;
ALTER TABLE cl_course_details ADD COLUMN IF NOT EXISTS cos_video_size bigint;
ALTER TABLE cl_course_details ADD COLUMN IF NOT EXISTS cos_video_etag text;
ALTER TABLE cl_course_details ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 0;
ALTER TABLE cl_course_details ADD COLUMN IF NOT EXISTS publish_scope text NOT NULL DEFAULT 'all_authorized';
ALTER TABLE cl_course_details ADD COLUMN IF NOT EXISTS publish_class_ids uuid[] NOT NULL DEFAULT '{}'::uuid[];

DO $$ BEGIN
  ALTER TABLE cl_course_details ADD CONSTRAINT ck_cl_course_details_publish_scope
    CHECK (publish_scope IN ('all_authorized','classes'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE cl_course_details ADD CONSTRAINT ck_cl_course_details_cos_size
    CHECK (cos_video_size IS NULL OR cos_video_size >= 0);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_cl_course_details_sort
  ON cl_course_details(sort_order, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_cl_course_details_publish_classes
  ON cl_course_details USING gin(publish_class_ids);

COMMIT;
