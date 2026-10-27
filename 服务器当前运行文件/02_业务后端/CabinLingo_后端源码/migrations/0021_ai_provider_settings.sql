BEGIN;

CREATE TABLE IF NOT EXISTS cl_ai_provider_settings (
  provider_code text PRIMARY KEY CHECK (provider_code IN ('qwen_tts','asr_iat','suntone','ise')),
  enabled boolean NOT NULL DEFAULT false,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  encrypted_secrets bytea NOT NULL,
  updated_by uuid REFERENCES users(id),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cl_ai_provider_settings_updated_at
  ON cl_ai_provider_settings(updated_at DESC);

COMMIT;
