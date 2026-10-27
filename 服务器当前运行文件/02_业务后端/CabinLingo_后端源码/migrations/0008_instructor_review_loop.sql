-- Phase 5: instructor review loop. Additive and history-preserving.

CREATE TABLE IF NOT EXISTS cl_instructor_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  review_type text NOT NULL CHECK (review_type IN ('practice','exam')),
  practice_attempt_id uuid REFERENCES cl_practice_attempts(id),
  exam_assignment_id uuid REFERENCES cl_exam_assignments(id),
  reviewer_id uuid NOT NULL REFERENCES users(id),
  revision_no integer NOT NULL DEFAULT 1 CHECK (revision_no > 0),
  completeness_score numeric(5,2) CHECK (completeness_score BETWEEN 0 AND 100),
  pronunciation_score numeric(5,2) CHECK (pronunciation_score BETWEEN 0 AND 100),
  fluency_score numeric(5,2) CHECK (fluency_score BETWEEN 0 AND 100),
  expression_score numeric(5,2) CHECK (expression_score BETWEEN 0 AND 100),
  final_score numeric(5,2) CHECK (final_score BETWEEN 0 AND 100),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  summary text NOT NULL DEFAULT '',
  correction_advice text NOT NULL DEFAULT '',
  required_retraining boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','superseded')),
  reviewed_at timestamptz,
  published_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (
    (review_type='practice' AND practice_attempt_id IS NOT NULL AND exam_assignment_id IS NULL) OR
    (review_type='exam' AND exam_assignment_id IS NOT NULL AND practice_attempt_id IS NULL)
  )
);

CREATE TABLE IF NOT EXISTS cl_remediation_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  review_id uuid NOT NULL UNIQUE REFERENCES cl_instructor_reviews(id),
  learner_id uuid NOT NULL REFERENCES users(id),
  practice_assignment_id uuid REFERENCES cl_practice_assignments(id),
  exam_assignment_id uuid REFERENCES cl_exam_assignments(id),
  content_item_id uuid REFERENCES cl_content_items(id),
  instructions text NOT NULL,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','completed','cancelled')),
  due_at timestamptz,
  completed_attempt_id uuid REFERENCES cl_practice_attempts(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  CHECK (num_nonnulls(practice_assignment_id, exam_assignment_id) = 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cl_instructor_review_practice_revision
  ON cl_instructor_reviews(practice_attempt_id, revision_no) WHERE practice_attempt_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cl_instructor_review_exam_revision
  ON cl_instructor_reviews(exam_assignment_id, revision_no) WHERE exam_assignment_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cl_instructor_review_active_practice
  ON cl_instructor_reviews(practice_attempt_id) WHERE practice_attempt_id IS NOT NULL AND status IN ('draft','published');
CREATE UNIQUE INDEX IF NOT EXISTS uq_cl_instructor_review_active_exam
  ON cl_instructor_reviews(exam_assignment_id) WHERE exam_assignment_id IS NOT NULL AND status IN ('draft','published');
CREATE INDEX IF NOT EXISTS idx_cl_instructor_reviews_queue
  ON cl_instructor_reviews(review_type, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cl_remediation_learner
  ON cl_remediation_requests(learner_id, status, created_at DESC);

WITH product AS (SELECT id FROM products WHERE code='cabinlingo')
INSERT INTO permissions(product_id,code,name)
SELECT product.id,item.code,item.name FROM product CROSS JOIN (VALUES
  ('cabinlingo:review.practice','Review practice attempts'),
  ('cabinlingo:review.exam','Review exam submissions'),
  ('cabinlingo:analytics.class','View class learning analytics')
) AS item(code,name)
ON CONFLICT(product_id,code) DO UPDATE SET name=excluded.name;

INSERT INTO role_permissions(role_id,permission_id)
SELECT role.id,permission.id
FROM roles role
JOIN products product ON product.id=role.product_id AND product.code='cabinlingo'
JOIN permissions permission ON permission.product_id=product.id
WHERE role.code IN ('evaluator','instructor','admin')
  AND permission.code IN ('cabinlingo:review.practice','cabinlingo:review.exam','cabinlingo:analytics.class')
ON CONFLICT DO NOTHING;
