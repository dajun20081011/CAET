export type UserRole = 'learner' | 'instructor' | 'admin'
export type CourseType = 'broadcast' | 'caet2' | 'caet3'
export type AssessmentType = 'broadcast_recording' | 'english_qa' | 'zh_to_en'

export interface Profile {
  id: string
  display_name: string | null
  employee_no: string | null
  role: UserRole
  group_id: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface LearnerGroup {
  id: string
  name: string
  created_at: string
}

export interface Course {
  id: string
  code: string
  title: string
  description: string | null
  cover_url: string | null
  course_type: CourseType
  status: string
  created_at: string
  updated_at: string
}

export interface CourseContent {
  id: string
  course_id: string
  chapter_no: number
  chapter_title: string
  day_no: number
  content_order: number
  content_type: 'hero' | 'explanation' | 'sentence' | 'vocabulary' | 'scenario' | 'practice' | 'summary' | 'weekly_test'
  payload: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface Task {
  id: string
  title: string
  course_id: string
  course_type: CourseType
  chapter_from: number
  chapter_to: number
  day_from: number
  day_to: number
  start_at: string
  due_at: string
  completion_rule: Record<string, unknown>
  status: string
  created_by: string
  created_at: string
  updated_at: string
}

export type AssignmentStatus = 'not_started' | 'in_progress' | 'completed' | 'overdue'

export interface TaskAssignment {
  id: string
  task_id: string
  learner_id: string
  status: AssignmentStatus
  started_at: string | null
  completed_at: string | null
  progress_percent: number
  updated_at: string
}

export interface LearnerProgress {
  id: string
  assignment_id: string
  content_id: string
  learner_id: string
  completed: boolean
  effective_seconds: number
  last_position: Record<string, unknown> | null
  attempt_count: number
  updated_at: string
}

export interface LearningEvent {
  id: number
  learner_id: string
  assignment_id: string | null
  course_id: string | null
  content_id: string | null
  event_type: string
  event_value: Record<string, unknown> | null
  client_timestamp: string
  created_at: string
}

export interface LearnerGroup {
  id: string
  name: string
  created_at: string
  learner_count?: number
}

export interface AdminUser {
  id: string
  email: string
  display_name: string | null
  employee_no: string | null
  role: UserRole
  group_id: string | null
  group_name?: string | null
  is_active: boolean
  created_at: string
}

export interface Assessment {
  id: number
  assignment_id: string
  learner_id: string
  content_id: string | null
  course_id: string | null
  assessment_type: AssessmentType
  attempt_no: number
  status: 'submitted' | 'graded' | 'resubmit'
  answers: Record<string, unknown>
  score: number | null
  feedback: string | null
  instructor_id: string | null
  graded_at: string | null
  created_at: string
  learner_name?: string | null
  task_title?: string | null
  course_title?: string | null
}

export type EventType =
  | 'audio_standard_play'
  | 'audio_slow_play'
  | 'copy'
  | 'eudic_lookup'
  | 'favorite_word'
  | 'recording_start'
  | 'recording_complete'
  | 'speech_transcription'
  | 'answer_submit'
  | 'weekly_test_submit'
  | 'learning_heartbeat'
