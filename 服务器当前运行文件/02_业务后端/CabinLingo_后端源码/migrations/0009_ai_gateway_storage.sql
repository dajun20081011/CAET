BEGIN;

ALTER TABLE cl_recordings ADD COLUMN IF NOT EXISTS storage_provider text NOT NULL DEFAULT 'local';
ALTER TABLE cl_recordings ADD COLUMN IF NOT EXISTS object_key text;
ALTER TABLE cl_recordings ADD COLUMN IF NOT EXISTS checksum_sha256 text;

ALTER TABLE cl_ai_results ADD COLUMN IF NOT EXISTS provider_request_id text;
ALTER TABLE cl_ai_results ADD COLUMN IF NOT EXISTS latency_ms integer;
ALTER TABLE cl_ai_results ADD COLUMN IF NOT EXISTS attempt_count integer NOT NULL DEFAULT 0;
ALTER TABLE cl_ai_results ADD COLUMN IF NOT EXISTS error_code text;
ALTER TABLE cl_ai_results ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_cl_ai_results_status_created
  ON cl_ai_results(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cl_ai_results_request
  ON cl_ai_results(provider, provider_request_id)
  WHERE provider_request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cl_recordings_storage
  ON cl_recordings(storage_provider, object_key)
  WHERE object_key IS NOT NULL;

COMMIT;
