BEGIN;

CREATE TABLE IF NOT EXISTS cl_tts_pronunciations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phrase text NOT NULL UNIQUE CHECK (char_length(phrase) BETWEEN 1 AND 40),
  pinyin text NOT NULL CHECK (char_length(pinyin) BETWEEN 3 AND 400),
  note text NOT NULL DEFAULT '',
  enabled boolean NOT NULL DEFAULT true,
  priority integer NOT NULL DEFAULT 100 CHECK (priority BETWEEN 1 AND 1000),
  created_by uuid REFERENCES users(id),
  updated_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cl_tts_pronunciations_enabled_priority
  ON cl_tts_pronunciations(enabled, priority DESC, phrase);

COMMIT;
