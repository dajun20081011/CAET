-- Phase 11: class types, learner/instructor assignments and instructor evaluation routing.
-- Additive and history-preserving. Classes remain learner grouping only; there is
-- intentionally no class-to-instructor relation.

BEGIN;

ALTER TABLE classes ADD COLUMN IF NOT EXISTS class_type text NOT NULL DEFAULT 'training';
ALTER TABLE classes ADD COLUMN IF NOT EXISTS description text NOT NULL DEFAULT '';
ALTER TABLE classes ADD COLUMN IF NOT EXISTS start_date date;
ALTER TABLE classes ADD COLUMN IF NOT EXISTS end_date date;
ALTER TABLE classes ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

DO $$ BEGIN
  ALTER TABLE classes ADD CONSTRAINT ck_classes_class_type
    CHECK (class_type IN ('training','assessment'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_classes_type_status ON classes(class_type, status);
CREATE INDEX IF NOT EXISTS idx_class_memberships_class_status ON class_memberships(class_id, status);

CREATE TABLE IF NOT EXISTS student_instructor_assignments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id uuid NOT NULL REFERENCES users(id),
  instructor_id uuid NOT NULL REFERENCES users(id),
  assignment_type text NOT NULL CHECK (assignment_type IN ('training','assessment','both')),
  course_id uuid REFERENCES cl_courses(id),
  effective_from date,
  effective_to date,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_student_instructor_assignment_active
  ON student_instructor_assignments(
    student_id,
    instructor_id,
    assignment_type,
    COALESCE(course_id, '00000000-0000-0000-0000-000000000000'::uuid)
  ) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_student_instructor_student
  ON student_instructor_assignments(student_id, status, assignment_type);
CREATE INDEX IF NOT EXISTS idx_student_instructor_instructor
  ON student_instructor_assignments(instructor_id, status, assignment_type);

CREATE TABLE IF NOT EXISTS cl_evaluation_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  review_type text NOT NULL CHECK (review_type IN ('practice','exam')),
  practice_attempt_id uuid REFERENCES cl_practice_attempts(id),
  exam_assignment_id uuid REFERENCES cl_exam_assignments(id),
  learner_id uuid NOT NULL REFERENCES users(id),
  instructor_id uuid REFERENCES users(id),
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','in_progress','completed','waiting_assignment','cancelled','resolved')),
  claimed_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (
    (review_type='practice' AND practice_attempt_id IS NOT NULL AND exam_assignment_id IS NULL) OR
    (review_type='exam' AND exam_assignment_id IS NOT NULL AND practice_attempt_id IS NULL)
  ),
  CHECK (instructor_id IS NOT NULL OR status IN ('waiting_assignment','resolved','cancelled'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_task_practice_instructor
  ON cl_evaluation_tasks(practice_attempt_id, instructor_id)
  WHERE practice_attempt_id IS NOT NULL AND instructor_id IS NOT NULL AND status <> 'cancelled';
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_task_exam_instructor
  ON cl_evaluation_tasks(exam_assignment_id, instructor_id)
  WHERE exam_assignment_id IS NOT NULL AND instructor_id IS NOT NULL AND status <> 'cancelled';
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_task_waiting_practice
  ON cl_evaluation_tasks(practice_attempt_id)
  WHERE practice_attempt_id IS NOT NULL AND instructor_id IS NULL AND status='waiting_assignment';
CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_task_waiting_exam
  ON cl_evaluation_tasks(exam_assignment_id)
  WHERE exam_assignment_id IS NOT NULL AND instructor_id IS NULL AND status='waiting_assignment';
CREATE INDEX IF NOT EXISTS idx_eval_task_instructor_queue
  ON cl_evaluation_tasks(instructor_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_eval_task_waiting
  ON cl_evaluation_tasks(status, created_at DESC) WHERE status='waiting_assignment';

-- A submission may have one independent review per assigned instructor.
ALTER TABLE cl_instructor_reviews ADD COLUMN IF NOT EXISTS evaluation_task_id uuid REFERENCES cl_evaluation_tasks(id);
DROP INDEX IF EXISTS uq_cl_instructor_review_practice_revision;
DROP INDEX IF EXISTS uq_cl_instructor_review_exam_revision;
DROP INDEX IF EXISTS uq_cl_instructor_review_active_practice;
DROP INDEX IF EXISTS uq_cl_instructor_review_active_exam;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cl_instructor_review_practice_revision_v2
  ON cl_instructor_reviews(practice_attempt_id, reviewer_id, revision_no)
  WHERE practice_attempt_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cl_instructor_review_exam_revision_v2
  ON cl_instructor_reviews(exam_assignment_id, reviewer_id, revision_no)
  WHERE exam_assignment_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_cl_instructor_review_active_practice_v2
  ON cl_instructor_reviews(practice_attempt_id, reviewer_id)
  WHERE practice_attempt_id IS NOT NULL AND status IN ('draft','published');
CREATE UNIQUE INDEX IF NOT EXISTS uq_cl_instructor_review_active_exam_v2
  ON cl_instructor_reviews(exam_assignment_id, reviewer_id)
  WHERE exam_assignment_id IS NOT NULL AND status IN ('draft','published');

-- Keep each examiner's published score separate; existing score rows remain valid.
ALTER TABLE cl_manual_reviews ADD COLUMN IF NOT EXISTS evaluation_task_id uuid REFERENCES cl_evaluation_tasks(id);
ALTER TABLE cl_scores ADD COLUMN IF NOT EXISTS evaluation_task_id uuid REFERENCES cl_evaluation_tasks(id);
ALTER TABLE cl_scores ADD COLUMN IF NOT EXISTS reviewer_id uuid REFERENCES users(id);

-- Route existing submissions once without rewriting any attempt or review rows.
INSERT INTO cl_evaluation_tasks(review_type,practice_attempt_id,learner_id,instructor_id,status)
SELECT 'practice',attempt.id,assignment.user_id,sia.instructor_id,'pending'
FROM cl_practice_attempts attempt
JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
JOIN student_instructor_assignments sia ON sia.student_id=assignment.user_id
WHERE sia.status='active' AND sia.assignment_type IN ('training','both')
  AND (sia.effective_from IS NULL OR sia.effective_from<=CURRENT_DATE)
  AND (sia.effective_to IS NULL OR sia.effective_to>=CURRENT_DATE)
ON CONFLICT DO NOTHING;

INSERT INTO cl_evaluation_tasks(review_type,exam_assignment_id,learner_id,instructor_id,status)
SELECT 'exam',assignment.id,assignment.user_id,sia.instructor_id,'pending'
FROM cl_exam_assignments assignment
JOIN student_instructor_assignments sia ON sia.student_id=assignment.user_id
WHERE assignment.status IN ('submitted','graded','published')
  AND sia.status='active' AND sia.assignment_type IN ('assessment','both')
  AND (sia.effective_from IS NULL OR sia.effective_from<=CURRENT_DATE)
  AND (sia.effective_to IS NULL OR sia.effective_to>=CURRENT_DATE)
ON CONFLICT DO NOTHING;

INSERT INTO cl_evaluation_tasks(review_type,practice_attempt_id,learner_id,status)
SELECT 'practice',attempt.id,assignment.user_id,'waiting_assignment'
FROM cl_practice_attempts attempt
JOIN cl_practice_assignments assignment ON assignment.id=attempt.assignment_id
WHERE NOT EXISTS (
  SELECT 1 FROM student_instructor_assignments sia
  WHERE sia.student_id=assignment.user_id AND sia.status='active'
    AND sia.assignment_type IN ('training','both')
    AND (sia.effective_from IS NULL OR sia.effective_from<=CURRENT_DATE)
    AND (sia.effective_to IS NULL OR sia.effective_to>=CURRENT_DATE)
)
ON CONFLICT DO NOTHING;

INSERT INTO cl_evaluation_tasks(review_type,exam_assignment_id,learner_id,status)
SELECT 'exam',assignment.id,assignment.user_id,'waiting_assignment'
FROM cl_exam_assignments assignment
WHERE assignment.status IN ('submitted','graded','published')
  AND NOT EXISTS (
    SELECT 1 FROM student_instructor_assignments sia
    WHERE sia.student_id=assignment.user_id AND sia.status='active'
      AND sia.assignment_type IN ('assessment','both')
      AND (sia.effective_from IS NULL OR sia.effective_from<=CURRENT_DATE)
      AND (sia.effective_to IS NULL OR sia.effective_to>=CURRENT_DATE)
  )
ON CONFLICT DO NOTHING;

COMMIT;
