-- Reading is separate from recording/AI attempts. Existing history is unchanged.
BEGIN;
CREATE TABLE IF NOT EXISTS cl_learning_card_reads (
  assignment_id uuid NOT NULL REFERENCES cl_practice_assignments(id) ON DELETE RESTRICT,
  content_item_id uuid NOT NULL REFERENCES cl_content_items(id) ON DELETE RESTRICT,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  read_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (assignment_id, content_item_id)
);
CREATE INDEX IF NOT EXISTS idx_cl_learning_card_reads_user ON cl_learning_card_reads(user_id, read_at DESC);
COMMIT;
