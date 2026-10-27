-- Broadcast Script Library V1.
-- Additive only: legacy cl_broadcasts/cl_segments, tasks and training history are untouched.

CREATE TABLE IF NOT EXISTS cl_broadcast_scripts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title varchar(160) NOT NULL,
  language varchar(20) NOT NULL,
  category varchar(60),
  script_type varchar(60) NOT NULL DEFAULT 'general',
  company_id uuid REFERENCES organizations(id) ON DELETE SET NULL,
  status varchar(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','archived')),
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  archived_at timestamptz
);

CREATE TABLE IF NOT EXISTS cl_broadcast_script_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  script_id uuid NOT NULL REFERENCES cl_broadcast_scripts(id) ON DELETE RESTRICT,
  version integer NOT NULL CHECK (version > 0),
  full_text text NOT NULL,
  frozen boolean NOT NULL DEFAULT false,
  slices_stale boolean NOT NULL DEFAULT false,
  created_by uuid REFERENCES users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  frozen_at timestamptz,
  UNIQUE(script_id, version)
);

CREATE TABLE IF NOT EXISTS cl_broadcast_script_slices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES cl_broadcast_script_versions(id) ON DELETE RESTRICT,
  slice_no integer NOT NULL CHECK (slice_no > 0),
  text text NOT NULL CHECK (char_length(text) BETWEEN 1 AND 1024),
  start_char integer NOT NULL CHECK (start_char >= 0),
  end_char integer NOT NULL CHECK (end_char >= start_char),
  verified boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(version_id, slice_no)
);

CREATE INDEX IF NOT EXISTS idx_cl_broadcast_scripts_filters
  ON cl_broadcast_scripts(status, language, script_type, company_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cl_broadcast_versions_script
  ON cl_broadcast_script_versions(script_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_cl_broadcast_versions_frozen
  ON cl_broadcast_script_versions(frozen, script_id);
CREATE INDEX IF NOT EXISTS idx_cl_broadcast_slices_version
  ON cl_broadcast_script_slices(version_id, slice_no);
