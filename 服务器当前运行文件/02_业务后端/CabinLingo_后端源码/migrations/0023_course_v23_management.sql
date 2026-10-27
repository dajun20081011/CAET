-- Course V2.3: structured course detail, media roles and auditable batch imports.
-- Additive only. Existing courses, versions, content, tasks and learner history are preserved.

CREATE TABLE IF NOT EXISTS cl_course_details (
  course_version_id uuid PRIMARY KEY REFERENCES cl_course_versions(id) ON DELETE CASCADE,
  title_en text NOT NULL DEFAULT '',
  summary text NOT NULL DEFAULT '',
  language_code text NOT NULL DEFAULT 'bilingual'
    CHECK (language_code IN ('zh','en','bilingual')),
  delivery_tone jsonb NOT NULL DEFAULT '[]'::jsonb,
  delivery_pace text NOT NULL DEFAULT '',
  delivery_rhythm jsonb NOT NULL DEFAULT '[]'::jsonb,
  explanation text NOT NULL DEFAULT '',
  annotated_scripts jsonb NOT NULL DEFAULT '{}'::jsonb,
  mistake_words jsonb NOT NULL DEFAULT '[]'::jsonb,
  cover_file_id uuid REFERENCES files(id),
  cover_filename text,
  video_file_id uuid REFERENCES files(id),
  video_filename text,
  standard_audio_file_id uuid REFERENCES files(id),
  standard_audio_filename text,
  source_import_batch_id uuid,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cl_course_import_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  excel_filename text NOT NULL,
  media_zip_filename text,
  status text NOT NULL DEFAULT 'processing'
    CHECK (status IN ('processing','completed','completed_with_errors','failed')),
  row_count integer NOT NULL DEFAULT 0,
  draft_count integer NOT NULL DEFAULT 0,
  error_count integer NOT NULL DEFAULT 0,
  errors jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

DO $$ BEGIN
  ALTER TABLE cl_course_details ADD CONSTRAINT fk_cl_course_details_import_batch
    FOREIGN KEY (source_import_batch_id) REFERENCES cl_course_import_batches(id);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_cl_course_details_import_batch
  ON cl_course_details(source_import_batch_id) WHERE source_import_batch_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cl_course_import_batches_created
  ON cl_course_import_batches(created_at DESC);

