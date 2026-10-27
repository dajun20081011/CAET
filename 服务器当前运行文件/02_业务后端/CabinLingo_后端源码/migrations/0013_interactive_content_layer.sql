-- Phase 13: custom interactive learning layer for imported HTML/PPT content.
-- Additive and history-preserving: answer attempts are append-only.

BEGIN;

CREATE TABLE IF NOT EXISTS cl_content_interactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  content_item_id uuid NOT NULL REFERENCES cl_content_items(id),
  interaction_type text NOT NULL CHECK (interaction_type IN ('choice','hotspot','fill_blank')),
  title text NOT NULL DEFAULT '互动练习',
  prompt text NOT NULL,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  sequence_no integer NOT NULL DEFAULT 1,
  required boolean NOT NULL DEFAULT true,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
  version_no integer NOT NULL DEFAULT 1,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cl_content_interactions_content
  ON cl_content_interactions(content_item_id, status, sequence_no);

CREATE TABLE IF NOT EXISTS cl_interaction_attempts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id uuid NOT NULL REFERENCES cl_practice_assignments(id),
  user_id uuid NOT NULL REFERENCES users(id),
  content_item_id uuid NOT NULL REFERENCES cl_content_items(id),
  interaction_id uuid NOT NULL REFERENCES cl_content_interactions(id),
  answer jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_correct boolean NOT NULL,
  score numeric(6,3) NOT NULL DEFAULT 0,
  feedback text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cl_interaction_attempts_assignment
  ON cl_interaction_attempts(assignment_id, content_item_id, interaction_id, created_at DESC);

COMMIT;
