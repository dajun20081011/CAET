-- Phase 16: immutable Learning Card package snapshots linked to the existing course catalog.
-- Additive and history-preserving. No existing course, task or learner record is removed.

BEGIN;

CREATE TABLE IF NOT EXISTS cl_learning_cards (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  category text NOT NULL DEFAULT '',
  package_format text NOT NULL CHECK (package_format = 'cabinlingo-learning-card'),
  package_version text NOT NULL CHECK (package_version = '1.0'),
  entry_file text NOT NULL CHECK (entry_file = 'index.html'),
  storage_prefix text NOT NULL UNIQUE,
  package_sha256 text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  resource_count integer NOT NULL DEFAULT 0 CHECK (resource_count >= 2),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  archived_at timestamptz
);

CREATE TABLE IF NOT EXISTS cl_learning_card_resources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  learning_card_id uuid NOT NULL REFERENCES cl_learning_cards(id) ON DELETE RESTRICT,
  resource_path text NOT NULL,
  object_ref text NOT NULL,
  mime_type text NOT NULL,
  byte_size bigint NOT NULL CHECK (byte_size >= 0),
  sha256 text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(learning_card_id, resource_path)
);

ALTER TABLE cl_content_items
  ADD COLUMN IF NOT EXISTS learning_card_id uuid
    REFERENCES cl_learning_cards(id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS idx_cl_learning_cards_status_created
  ON cl_learning_cards(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cl_learning_card_resources_card_path
  ON cl_learning_card_resources(learning_card_id, resource_path);

CREATE INDEX IF NOT EXISTS idx_cl_content_items_learning_card
  ON cl_content_items(learning_card_id)
  WHERE learning_card_id IS NOT NULL;

COMMIT;
