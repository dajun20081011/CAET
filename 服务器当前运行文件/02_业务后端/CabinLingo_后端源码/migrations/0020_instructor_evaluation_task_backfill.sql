-- Repair instructor visibility for submissions created before or around a
-- learner/instructor binding. Additive and idempotent: recordings, attempts,
-- scores, reviews and assignments are not changed.

BEGIN;

INSERT INTO cl_evaluation_tasks
  (review_type,practice_attempt_id,learner_id,instructor_id,status)
SELECT 'practice',attempt.id,assignment.user_id,binding.instructor_id,'pending'
FROM student_instructor_assignments binding
JOIN cl_practice_assignments assignment ON assignment.user_id=binding.student_id
JOIN cl_practice_attempts attempt ON attempt.assignment_id=assignment.id
JOIN cl_practice_tasks task ON task.id=assignment.task_id
LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
WHERE binding.status='active'
  AND binding.assignment_type IN ('training','both')
  AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
  AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
  AND (binding.course_id IS NULL OR binding.course_id=version.course_id)
  AND task.deleted_at IS NULL
ON CONFLICT DO NOTHING;

INSERT INTO cl_evaluation_tasks
  (review_type,exam_assignment_id,learner_id,instructor_id,status)
SELECT 'exam',assignment.id,assignment.user_id,binding.instructor_id,'pending'
FROM student_instructor_assignments binding
JOIN cl_exam_assignments assignment ON assignment.user_id=binding.student_id
JOIN cl_exam_tasks task ON task.id=assignment.exam_task_id
LEFT JOIN cl_course_versions version ON version.id=task.course_version_id
WHERE binding.status='active'
  AND binding.assignment_type IN ('assessment','both')
  AND (binding.effective_from IS NULL OR binding.effective_from<=CURRENT_DATE)
  AND (binding.effective_to IS NULL OR binding.effective_to>=CURRENT_DATE)
  AND (binding.course_id IS NULL OR binding.course_id=version.course_id)
  AND assignment.status IN ('submitted','graded','published')
  AND task.deleted_at IS NULL
ON CONFLICT DO NOTHING;

UPDATE cl_evaluation_tasks waiting
SET status='resolved',updated_at=now()
WHERE waiting.instructor_id IS NULL
  AND waiting.status='waiting_assignment'
  AND EXISTS (
    SELECT 1
    FROM cl_evaluation_tasks assigned
    WHERE assigned.instructor_id IS NOT NULL
      AND assigned.status<>'cancelled'
      AND (
        (waiting.practice_attempt_id IS NOT NULL
          AND assigned.practice_attempt_id=waiting.practice_attempt_id) OR
        (waiting.exam_assignment_id IS NOT NULL
          AND assigned.exam_assignment_id=waiting.exam_assignment_id)
      )
  );

COMMIT;
