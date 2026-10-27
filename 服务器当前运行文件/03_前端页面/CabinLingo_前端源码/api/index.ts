import axios from 'axios'

const TOKEN_KEY = 'cabinlingo_access_token'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

export function readAccessToken(): string {
  return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || ''
}

export function writeAccessToken(token: string, remember: boolean): void {
  sessionStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(TOKEN_KEY)
  ;(remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token)
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(TOKEN_KEY)
}

http.interceptors.request.use((config) => {
  if (config.url === '/core/auth/login') return config
  const token = readAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export function isUnauthorizedError(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 401
}

export function authErrorMessage(error: unknown, login = false): string {
  const status = axios.isAxiosError(error) ? error.response?.status : undefined
  if (login && status === 401) return '账号或密码错误，请重新输入。'
  if (status === 403) return '当前账号暂时没有访问权限，请联系管理员。'
  if (status === 429) return '请求过于频繁，请稍后重试。'
  if (login) return '网络或登录服务暂时不可用，请稍后重试。'
  return '网络或身份服务暂时不可用，登录信息已保留，请重试。'
}

let onUnauthorized: ((token: string) => void) | undefined
export function setUnauthorizedHandler(handler: (token: string) => void): void {
  onUnauthorized = handler
}

http.interceptors.response.use((response) => response, (error: unknown) => {
  // /me is owned by bootstrap; a failed login must not expire another session.
  if (axios.isAxiosError(error) && isUnauthorizedError(error)
    && error.config?.url !== '/core/auth/login' && error.config?.url !== '/core/me') {
    const token = readAccessToken()
    if (token && error.config?.headers?.Authorization === `Bearer ${token}`) {
      onUnauthorized?.(token)
    }
  }
  return Promise.reject(error)
})

export interface Membership { product: string; roles: string[]; permissions: string[] }
export interface CurrentUser { id: string; display_name: string; memberships: Membership[] }
export interface LoginResponse { access_token: string; token_type: string; expires_in: number; user: CurrentUser }
export interface Broadcast { id: string; code: string; title: string; language: string; segment_count: number; status: 'draft' | 'published' | 'archived' }
export interface Assignment { id: string; task_id: string; user_id: string; status: string; task_type: 'practice' | 'exam' }
export interface Progress { user_id: string; assignment_id: string; task_id: string; attempts: number; status: string }
export interface TaskListItem { id: string; title: string; broadcast_id: string | null; course_version_id: string | null; broadcast_script_id: string | null; broadcast_script_count: number; due_at: string | null; week_no: number | null; unlock_after_task_type: 'practice' | 'exam' | null; unlock_after_task_id: string | null; status: string; task_type: 'practice' | 'exam'; assignment_count: number; completed_count: number }
export interface DashboardSummary { task_count: number; practice_count: number; exam_count: number; published_count: number; assignment_count: number; completed_count: number; completion_rate: number }
export interface UserSummary { id: string; external_ref: string | null; display_name: string; email: string | null; is_active: boolean; roles: string[]; class_id: string | null }
export interface UserImportError { row: number; account: string; message: string }
export interface UserImportResult { imported: number; failed: number; users: UserSummary[]; errors: UserImportError[] }
export interface ReviewQueueItem { assignment_id: string; task_id: string; user_id: string; status: string; submitted_at: string | null; ai_status: string; manual_status: string }
export interface Organization { id: string; code: string; name: string; status: 'active' | 'inactive'; class_count: number }
export interface TrainingClass { id: string; organization_id: string; code: string; name: string; class_type: 'training' | 'assessment'; description: string; start_date: string | null; end_date: string | null; status: 'active' | 'inactive'; member_count: number }
export interface ClassMember { id: string; display_name: string; employee_no: string | null; email: string | null; organization_id: string | null; class_id: string | null; status: 'active' | 'inactive'; training_instructors: string[]; assessment_instructors: string[] }
export interface ClassDetail extends TrainingClass { members: ClassMember[] }
export interface InstructorAssignment { id: string; student_id: string; instructor_id: string; assignment_type: 'training' | 'assessment' | 'both'; course_id: string | null; effective_from: string | null; effective_to: string | null; status: 'active' | 'inactive'; instructor_name: string; instructor_account: string | null; course_title: string | null; created_at: string; updated_at: string }
export interface InstructorAssignmentBatchResult { selected: number; created: number; reactivated: number; unchanged: number; evaluation_tasks_created: number }
export interface Course { id: string; organization_id: string | null; code: string; title: string; description: string; category: string; status: 'draft' | 'published' | 'archived'; version_count: number; published_version_id: string | null }
export interface CourseVersion { id: string; course_id: string; version_no: number; version_label: string; status: 'draft' | 'published' | 'archived'; change_summary: string; chapter_count: number; content_count: number; published_at: string | null }
export interface CourseMistakeWord { language: 'zh' | 'en'; term: string; pronunciation: string; meaning: string; common_mistake: string; tip: string }
export interface CourseAudioSentenceTiming { index: number; start_ms: number; end_ms: number; precision: 'aligned' | 'interpolated' }
export interface CourseAudioAlignment {
  version: number; status: 'ready'; source_hash: string; provider: string
  duration_ms: number; sentence_count: number; sentences: CourseAudioSentenceTiming[]
}
export interface CourseV23DraftPayload {
  course_id: string; title_zh: string; title_en: string; category: string; summary: string
  language: 'zh' | 'en' | 'bilingual'; version_label: string; organization_id?: string | null
  course_kind: 'lesson' | 'expression_skill'; content_mode: 'audio_text' | 'video'
  training_enabled: boolean; content_config: Record<string, string>
  explanation: string; annotated_scripts: Record<string, string>; delivery_tone: string[]
  delivery_pace: string; delivery_rhythm: string[]; pronunciation_notes: string
  mistake_words: CourseMistakeWord[]
  cos_video_key?: string | null; cos_video_filename?: string | null; cos_video_size?: number | null; cos_video_etag?: string | null
  sort_order: number; publish_scope: 'all_authorized' | 'classes'; publish_class_ids: string[]
}
export interface CourseV23Detail extends CourseV23DraftPayload {
  id: string; course_version_id: string; content_item_id: string; code: string
  status: 'draft' | 'published' | 'archived'; cover_filename: string | null; cover_url: string | null
  course_status: 'draft' | 'published' | 'archived'; has_published_version: boolean
  task_count: number; active_task_count: number
  video_filename: string | null; video_url: string | null; audio_filename: string | null; audio_url: string | null
  audio_zh_filename: string | null; audio_zh_url: string | null; audio_en_filename: string | null; audio_en_url: string | null
  audio_tracks: Array<{
    file_id?: string; role: string; label: string; language: 'zh' | 'en' | 'bilingual'
    sequence_no?: number; filename: string; url: string
    alignment?: Partial<Record<'zh' | 'en', CourseAudioAlignment>>
  }>
  validation_errors: string[]; published_at: string | null; updated_at?: string | null
}
export interface CosVideoObject { key: string; filename: string; size: number; etag: string; last_modified: string }
export interface CosVideoList { bucket: string; prefix: string; items: CosVideoObject[]; next_marker: string; is_truncated: boolean }
const learnerCourseCache = new Map<string, { course: CourseV23Detail; cachedAt: number }>()
const courseMediaPlaybackCache = new Map<string, { url: string; expiresAt: number }>()
export interface CourseImportError { row: number | null; course_id: string; message: string }
export interface CourseImportResult { batch_id: string | null; total: number; created: number; failed: number; drafts: CourseV23Detail[]; errors: CourseImportError[] }
export interface CourseMistakeImportError { row: number | null; course_id: string; language: string; term: string; message: string }
export interface CourseMistakeImportPreview { incoming: number; created: number; updated: number; skipped: number; invalid: number; total_after_merge: number; mistake_words: CourseMistakeWord[]; errors: CourseMistakeImportError[] }
export interface PPTImportResult { course_version_id: string; chapter_id: string; chapter_title: string; slides_imported: number; content_ids: string[]; warnings: string[] }
export interface PDFImportResult { course_version_id: string; chapter_id: string; chapter_title: string; pages_imported: number; content_ids: string[]; warnings: string[] }
export interface Chapter { id: string; course_version_id: string; code: string; title: string; sequence_no: number; learning_objective: string; content_count: number }
export interface ContentItem { id: string; chapter_id: string; content_type: 'html' | 'broadcast' | 'audio' | 'document'; title: string; sequence_no: number; source_filename: string | null; sanitized_html: string | null; original_sha256: string | null; sanitized_sha256: string | null; validation_report: Record<string, unknown>; interaction_count: number; learning_card_id: string | null }
export interface ContentAsset { id: string; content_item_id: string; asset_role: string; original_filename: string | null; mime_type: string; byte_size: number; url: string }
export interface TTSVoiceOption {
  id: string; label: string; languages: Array<'zh' | 'en'>
  gender?: 'female' | 'male' | 'unknown'; category?: string; trait?: string; age?: number | null
  source?: 'system' | 'basic' | 'custom'; preview_file?: string
}
export interface TTSRateControl { min: number; max: number; step: number; default: number; recommended_min: number; recommended_max: number }
export interface TTSPronunciationItem { phrase: string; pinyin: string; source: 'builtin' | 'manual' | 'context'; confidence: 'confirmed' | 'predicted'; note: string; occurrences: Array<{ start: number; end: number }>; applied: boolean }
export interface TTSPronunciationPreview { items: TTSPronunciationItem[]; confirmed_count: number; predicted_count: number; requires_review: boolean }
export interface TTSPronunciationEntry { id: string; phrase: string; pinyin: string; note: string; enabled: boolean; priority: number; source: 'builtin' | 'manual'; editable: boolean; overrides_builtin?: boolean; updated_at?: string | null }
export interface TTSPronunciationDictionary { items: TTSPronunciationEntry[]; total: number; builtin_count: number; manual_count: number }
export interface TTSOptions { enabled: boolean; model: string; languages: Array<{ id: 'zh' | 'en'; label: string }>; voices: TTSVoiceOption[]; voice_count?: number; voice_source_counts?: Record<string, number>; rates: number[]; rate_control?: TTSRateControl; formats: Array<'mp3' | 'wav'>; max_text_chars: number; pronunciation?: { enabled: boolean; dictionary_version: string; builtin_count: number; automatic_context: boolean } }
export interface TTSProsodyScene { id: string; label: string; description: string; rate: number; pitch: number; energy: number }
export interface TTSProsodySceneResponse { version: string; scenes: TTSProsodyScene[] }
export interface TTSProsodyAnalysisSegment { index: number; text: string; rate: number; pitch: number; energy: number; pause_after_ms: number; emphasis: string[] }
export interface TTSProsodyAnalysis { version: string; scene: string; normalized_text: string; sentence_count: number; segments: TTSProsodyAnalysisSegment[] }
export interface TTSProsodySegment { source?: string; text: string; tone: string | null; pace: string | null; emphasis: string[]; intonation: 'rise' | 'fall' | 'level' | null; pause_after_ms: number; instruction?: string }
export interface TTSProsodyPreview { segments: TTSProsodySegment[]; summary: { segment_count: number; emphasis_count: number; pause_count: number; tone_count?: number; pace_count?: number; intonation_count?: number } }
export interface TTSProsodyAssembleItem { index: number; pause_after_ms: number }
export type InteractionType = 'choice' | 'hotspot' | 'fill_blank'
export interface ContentInteraction { id: string; content_item_id: string; interaction_type: InteractionType; title: string; prompt: string; options: string[]; correct_answer: string; accepted_answers: string[]; feedback_correct: string; feedback_incorrect: string; required: boolean; sequence_no: number; status: 'draft' | 'published' | 'archived'; version_no: number; created_at: string; updated_at: string }
export interface LearnerInteraction { id: string; content_item_id: string; interaction_type: InteractionType; title: string; prompt: string; options: string[]; required: boolean; sequence_no: number; completed: boolean; attempt_count: number }
export interface InteractionAnswer { interaction_id: string; assignment_id: string; content_item_id: string; is_correct: boolean; score: number; feedback: string; completed: boolean; attempt_count: number; answer: string }
export interface CourseStandard { id: string; content_item_id: string; standard_text: string; stress_rules: string; pronunciation_notes: string; pause_rules: string; tone_requirements: string; rule_version: string; change_summary: string; standard_audio_file_id: string | null; standard_audio_filename: string | null; standard_audio_url: string | null; created_at: string }
export interface LearnerTask { assignment_id: string; task_id: string; task_type: 'practice' | 'exam'; title: string; status: string; due_at: string | null; week_no: number | null; locked: boolean; unlock_reason: string | null; course_version_id: string | null; course_title: string; version_label: string | null; total_items: number; completed_items: number; attempt_count: number; progress_percent: number; next_content_item_id: string | null }
export interface AdminLearnerBroadcastItem { assignment_id: string; task_id: string; task_title: string; content_item_id: string; content_title: string; chapter_title: string; chapter_sequence: number; sequence_no: number; progress_status: 'not_started' | 'in_progress' | 'completed'; attempt_count: number; required_attempts: number; completed_interactions: number; required_interactions: number; latest_attempt_id: string | null; latest_attempt_at: string | null; latest_ai_status: string | null; latest_score: number | null; review_status: 'not_submitted' | 'pending_review' | 'draft' | 'published' }
export interface TaskRosterLearner { assignment_id: string; learner_id: string; display_name: string; external_ref: string | null; class_name: string | null; assignment_status: string; progress_status: 'not_started' | 'in_progress' | 'completed'; final_status: 'passed' | 'pending_review' | 'not_passed'; total_items: number; completed_items: number; attempt_count: number; progress_percent: number; pending_review: boolean; needs_retraining: boolean }
export interface TaskRoster { task_id: string; task_type: 'practice' | 'exam'; task_title: string; task_status: string; total_count: number; passed_count: number; pending_review_count: number; not_passed_count: number; not_started_count: number; in_progress_count: number; completed_count: number; learners: TaskRosterLearner[] }
export interface LearnerHome { practice_count: number; exam_count: number; completed_count: number; total_attempts: number; pending_feedback: number; next_task: LearnerTask | null }
export interface LearnerContent { id: string; chapter_id: string; chapter_title: string; chapter_sequence: number; title: string; sequence_no: number; content_type: 'html' | 'broadcast' | 'audio' | 'document'; learning_card_id: string | null; sanitized_html: string; reference_text: string; document_url: string | null; document_page_no: number | null; document_page_count: number | null; assets: ContentAsset[]; standard_audio_url: string | null; stress_rules: string; pronunciation_notes: string; pause_rules: string; tone_requirements: string; rule_version: string | null; attempt_count: number; latest_attempt_id: string | null; latest_ai_status: string | null; completed: boolean; interactions: LearnerInteraction[]; required_interactions: number; completed_interactions: number }
export interface LearningCard { id: string; title: string; category: string; package_format: 'cabinlingo-learning-card'; package_version: '1.0'; entry_file: 'index.html'; metadata: Record<string, unknown>; resource_count: number; status: 'active' | 'archived'; created_by: string | null; created_at: string; updated_at: string; archived_at: string | null; course_count: number }
export interface LearningCardViewer { learning_card_id: string; title: string; category: string; viewer_url: string; expires_in: number }
export interface LearningCardCourseLink { learning_card_id: string; course_id: string; course_version_id: string; chapter_id: string; content_item_id: string; course_title: string; version_status: string }
export interface PracticeWorkspace { assignment_id: string; task_id: string; task_title: string; assignment_status: string; course_title: string; version_label: string; minimum_attempts: number; progress_percent: number; contents: LearnerContent[] }
export interface AudioUpload { recording_id: string; audio_ref: string; audio_url: string; mime_type: string; byte_size: number }
export interface LearnerIssue { dimension?: string; source?: string; type?: string; message?: string; severity?: string; issue_status?: 'confirmed' | 'pending_review' | 'filtered'; word?: string; expected?: string; actual?: string; reference_index?: number; start_ms?: number; end_ms?: number; confidence?: number | null; filter_reason?: string | null; evidence?: Array<{ kind?: string; message?: string; value?: unknown; [key: string]: unknown }>; training_advice?: string; question?: string; inferred?: boolean; [key: string]: unknown }
export interface WordPhoneme { phoneme?: string; phone?: string; start_ms?: number; end_ms?: number; pronunciation?: number; tone_index?: number }
export interface WordDetail { word: string; read_type: number | null; start_ms: number; end_ms: number; overall?: number; pronunciation?: number; tone?: number; prominence?: number; pinyin?: string; expected_pinyin?: string; expected_tone?: string; detected_tone?: string; char_type?: number; reference_index?: number; detail_level?: 'word' | 'sentence'; pause?: { type: number | null; duration_ms: number }; phonemes?: WordPhoneme[] }
export interface TextAlignmentItem { type: 'matched' | 'omission' | 'insertion' | 'substitution'; reference: string | null; recognized: string | null; start_ms: number | null; provider_bg?: number | null; iat_token_index?: number | null; reference_index: number | null; recognized_index: number | null; source?: string; provider?: string }
export interface LearnerAttempt { attempt_id: string; assignment_id: string; content_item_id: string | null; content_title: string; attempt_no: number; ai_status: string; score_summary: Record<string, number>; issues: LearnerIssue[]; overall_score: number | null; speed: number | null; duration_seconds: number | null; rear_tone: string | null; word_details: WordDetail[]; word_detail_level?: 'word' | 'sentence' | null; word_detail_count?: number; recognized_text: string | null; browser_transcript?: string | null; iat_transcript?: string | null; transcript_source?: 'iat' | 'browser_speech' | null; alignment?: TextAlignmentItem[]; alignment_source?: string | null; alignment_provider?: string | null; next_action: string; recording_url: string | null; correction_of_attempt_id: string | null; teacher_feedback: Record<string, unknown> | null; created_at: string }
export interface TeacherFeedback { id: string; practice_attempt_id: string | null; exam_assignment_id: string | null; teacher_name: string; summary: string; correction_advice: string; required_retraining: boolean; status: string; published_at: string | null }
export interface GrowthProfile { total_attempts: number; completed_tasks: number; corrected_attempts: number; feedback_count: number; issue_counts: Record<string, number>; trend: Array<{ date: string; attempts: number; completed_tasks: number; average_score: number | null }> }
export interface InstructorQueueItem { review_type: 'practice' | 'exam'; target_id: string; assignment_id: string; task_id: string; task_title: string; learner_id: string; learner_name: string; class_id: string | null; class_name: string | null; content_title: string | null; submitted_at: string; ai_status: string; review_status: 'pending' | 'draft' | 'published'; priority: 'normal' | 'overdue' | 'retraining' }
export interface InstructorLearner { learner_id: string; learner_name: string; external_ref: string | null; class_id: string | null; class_name: string | null; assignment_types: Array<'training' | 'assessment' | 'both'>; assigned_at: string; submitted_count: number; pending_review_count: number; published_review_count: number; retraining_count: number; latest_submitted_at: string | null }
export interface InstructorRecentPass { learner_id: string; learner_name: string; passed_at: string }
export interface InstructorDashboard { pending_reviews: number; retraining_followups: number; today_completed: number; week_completed: number; week_total: number; week_retraining_completed: number; total_evaluations: number; month_evaluations: number; total_mentored: number; current_mentoring: number; passed_mentoring: number; active_mentoring: number; recent_passed: InstructorRecentPass[] }
export interface InstructorRecording { id: string; audio_url: string; mime_type: string | null; duration_ms: number | null; created_at: string }
export interface InstructorFeedbackAudioUpload { audio_ref: string; audio_url: string; mime_type: string; byte_size: number; duration_ms: number }
export interface InstructorReviewPayload { completeness_score: number | null; pronunciation_score: number | null; fluency_score: number | null; expression_score: number | null; final_score: number | null; evidence: Record<string, unknown>; summary: string; correction_advice: string; required_retraining: boolean; remediation_due_at?: string | null }
export interface InstructorReviewDetail { review_type: 'practice' | 'exam'; target_id: string; assignment_id: string; task_id: string; task_title: string; learner_id: string; learner_name: string; class_name: string | null; content_title: string | null; reference_text: string; recording_id: string | null; recording_url: string | null; recordings: InstructorRecording[]; submitted_at: string; ai_status: string; ai_scores: Record<string, number>; ai_issues: LearnerIssue[]; ai_evidence: Record<string, unknown>; overall_score: number | null; speed: number | null; duration_seconds: number | null; rear_tone: string | null; word_details: WordDetail[]; word_detail_level: 'word' | 'sentence' | null; word_detail_count: number; recognized_text: string | null; alignment: TextAlignmentItem[]; alignment_source: string | null; alignment_provider: string | null; review: (InstructorReviewPayload & { id: string; status: string }) | null }
export interface ClassReviewAnalytics { class_id: string; class_name: string; learner_count: number; submitted_count: number; pending_review_count: number; published_review_count: number; remediation_count: number; average_score: number | null }
export interface AIAdapterStatus { name: string; provider?: string; version?: string; configured: boolean }
export interface AIGatewayStatus { enabled: boolean; adapters: AIAdapterStatus[]; object_storage: string }
export type AIProviderCode = 'qwen_tts' | 'asr_iat' | 'suntone' | 'ise'
export interface AIProviderSetting {
  code: AIProviderCode; label: string; enabled: boolean; source: 'environment' | 'database'
  config: Record<string, string>
  secret_status: Record<string, boolean>; updated_at: string | null
}
export interface AIProviderSettingsResponse { writable: boolean; providers: AIProviderSetting[] }
export interface BroadcastScript {
  id: string; title: string; language: string; script_type: string; category: string | null
  company_id: string | null; company_name: string | null; status: 'draft' | 'archived'
  latest_version_id: string; latest_version: number; frozen: boolean; slice_count: number; ready: boolean; enabled: boolean
  created_by?: string | null; created_at: string; updated_at: string; archived_at: string | null
}
export interface BroadcastScriptPage { items: BroadcastScript[]; total: number; page: number; page_size: number }
export interface BroadcastVersion {
  id: string; script_id: string; version: number; full_text: string; frozen: boolean
  slices_stale: boolean; slice_count: number; created_by: string | null
  created_at: string; updated_at: string; frozen_at: string | null
}
export interface BroadcastSlice {
  id: string; version_id: string; slice_no: number; text: string; start_char: number
  end_char: number; verified: boolean; created_at: string; updated_at: string
}

export const cabinlingoApi = {
  async login(account: string, password: string): Promise<LoginResponse> {
    const { data } = await http.post<LoginResponse>('/core/auth/login', { account, password })
    return data
  },
  async me(): Promise<CurrentUser> {
    const { data } = await http.get('/core/me')
    return { id: data.user_id, display_name: data.display_name, memberships: data.memberships }
  },
  async health(): Promise<{ status: string; environment: string; database: string }> {
    const { data } = await http.get('/core/health')
    return data
  },
  async aiStatus(): Promise<AIGatewayStatus> {
    const { data } = await http.get<AIGatewayStatus>('/ai/status')
    return data
  },
  async broadcasts(query?: string): Promise<Broadcast[]> {
    const { data } = await http.get<Broadcast[]>('/cabinlingo/broadcasts', { params: query ? { query } : undefined })
    return data
  },
  async broadcastScripts(params: { keyword?: string; language?: string; script_type?: string; company_id?: string; frozen?: boolean; enabled?: boolean; archived?: boolean; page?: number; page_size?: number } = {}): Promise<BroadcastScriptPage> {
    const { data } = await http.get<BroadcastScriptPage>('/cabinlingo/admin/broadcast-scripts', { params })
    return data
  },
  async createBroadcastScript(payload: { title: string; language: string; script_type: string; category?: string | null; company_id?: string | null; full_text: string }): Promise<BroadcastScript> {
    const { data } = await http.post<BroadcastScript>('/cabinlingo/admin/broadcast-scripts', payload)
    return data
  },
  async broadcastScript(id: string): Promise<BroadcastScript> {
    const { data } = await http.get<BroadcastScript>(`/cabinlingo/admin/broadcast-scripts/${id}`)
    return data
  },
  async updateBroadcastScript(id: string, payload: Partial<Pick<BroadcastScript, 'title' | 'language' | 'script_type' | 'category' | 'company_id' | 'enabled'>>): Promise<BroadcastScript> {
    const { data } = await http.patch<BroadcastScript>(`/cabinlingo/admin/broadcast-scripts/${id}`, payload)
    return data
  },
  async archiveBroadcastScript(id: string): Promise<BroadcastScript> {
    const { data } = await http.delete<BroadcastScript>(`/cabinlingo/admin/broadcast-scripts/${id}`)
    return data
  },
  async broadcastVersions(scriptId: string): Promise<BroadcastVersion[]> {
    const { data } = await http.get<BroadcastVersion[]>(`/cabinlingo/admin/broadcast-scripts/${scriptId}/versions`)
    return data
  },
  async createBroadcastVersion(scriptId: string, fullText?: string): Promise<BroadcastVersion> {
    const { data } = await http.post<BroadcastVersion>(`/cabinlingo/admin/broadcast-scripts/${scriptId}/versions`, fullText === undefined ? {} : { full_text: fullText })
    return data
  },
  async broadcastVersion(versionId: string): Promise<BroadcastVersion> {
    const { data } = await http.get<BroadcastVersion>(`/cabinlingo/admin/broadcast-script-versions/${versionId}`)
    return data
  },
  async saveBroadcastFullText(versionId: string, fullText: string): Promise<{ status: 'updated'; slice_count: number; requires_slice_regeneration: boolean; version: BroadcastVersion }> {
    const { data } = await http.put(`/cabinlingo/admin/broadcast-script-versions/${versionId}/full-text`, { full_text: fullText })
    return data
  },
  async freezeBroadcastVersion(versionId: string): Promise<BroadcastVersion> {
    const { data } = await http.post<BroadcastVersion>(`/cabinlingo/admin/broadcast-script-versions/${versionId}/freeze`)
    return data
  },
  async broadcastSlices(versionId: string): Promise<BroadcastSlice[]> {
    const { data } = await http.get<BroadcastSlice[]>(`/cabinlingo/admin/broadcast-script-versions/${versionId}/slices`)
    return data
  },
  async generateBroadcastSlices(versionId: string, maxChars = 900): Promise<BroadcastSlice[]> {
    const { data } = await http.post<BroadcastSlice[]>(`/cabinlingo/admin/broadcast-script-versions/${versionId}/slices/generate`, { max_chars: maxChars })
    return data
  },
  async createBroadcastSlice(versionId: string, payload: { text: string; position?: number; verified?: boolean }): Promise<BroadcastSlice> {
    const { data } = await http.post<BroadcastSlice>(`/cabinlingo/admin/broadcast-script-versions/${versionId}/slices`, payload)
    return data
  },
  async updateBroadcastSlice(sliceId: string, payload: { text?: string; verified?: boolean }): Promise<BroadcastSlice> {
    const { data } = await http.put<BroadcastSlice>(`/cabinlingo/admin/broadcast-slices/${sliceId}`, payload)
    return data
  },
  async deleteBroadcastSlice(sliceId: string): Promise<BroadcastSlice> {
    const { data } = await http.delete<BroadcastSlice>(`/cabinlingo/admin/broadcast-slices/${sliceId}`)
    return data
  },
  async orderBroadcastSlices(versionId: string, sliceIds: string[]): Promise<BroadcastSlice[]> {
    const { data } = await http.put<BroadcastSlice[]>(`/cabinlingo/admin/broadcast-script-versions/${versionId}/slices/order`, { slice_ids: sliceIds })
    return data
  },
  async createBroadcast(payload: { code: string; title: string; language: string; status: 'draft' | 'published' }): Promise<Broadcast> {
    const { data } = await http.post<Broadcast>('/cabinlingo/broadcasts', payload)
    return data
  },
  async updateBroadcast(id: string, payload: Partial<Pick<Broadcast, 'title' | 'language' | 'status'>>): Promise<Broadcast> {
    const { data } = await http.patch<Broadcast>(`/cabinlingo/broadcasts/${id}`, payload)
    return data
  },
  async tasks(): Promise<TaskListItem[]> {
    const { data } = await http.get<TaskListItem[]>('/cabinlingo/tasks')
    return data
  },
  async createPracticeTask(payload: { title: string; broadcast_id?: string | null; course_version_id?: string | null; broadcast_script_id?: string | null; broadcast_script_ids?: string[] | null; due_at?: string | null; week_no?: number | null; unlock_after_task_type?: 'practice' | 'exam' | null; unlock_after_task_id?: string | null; completion_rule: Record<string, unknown> }): Promise<TaskListItem> {
    const { data } = await http.post('/cabinlingo/practice/tasks', payload)
    return { ...data, broadcast_script_count: payload.broadcast_script_ids?.length || (payload.broadcast_script_id ? 1 : 0), assignment_count: 0, completed_count: 0 }
  },
  async aiProviderSettings(): Promise<AIProviderSettingsResponse> {
    const { data } = await http.get<AIProviderSettingsResponse>('/cabinlingo/admin/ai-providers')
    return data
  },
  async saveAiProviderSettings(code: AIProviderCode, payload: { enabled: boolean; config: Record<string, string>; api_key?: string; api_secret?: string }): Promise<AIProviderSettingsResponse> {
    const { data } = await http.put<AIProviderSettingsResponse>(`/cabinlingo/admin/ai-providers/${code}`, payload)
    return data
  },
  async createExamTask(payload: { title: string; broadcast_id?: string | null; course_version_id?: string | null; broadcast_script_id?: string | null; broadcast_script_ids?: string[] | null; due_at?: string | null; week_no?: number | null; unlock_after_task_type?: 'practice' | 'exam' | null; unlock_after_task_id?: string | null; max_recordings: number }): Promise<TaskListItem> {
    const { data } = await http.post('/cabinlingo/exams/tasks', payload)
    return { ...data, broadcast_script_count: payload.broadcast_script_ids?.length || (payload.broadcast_script_id ? 1 : 0), assignment_count: 0, completed_count: 0 }
  },
  async updateTaskStatus(taskType: 'practice' | 'exam', id: string, action: 'publish' | 'close'): Promise<TaskListItem> {
    const { data } = await http.post<TaskListItem>(`/cabinlingo/tasks/${taskType}/${id}/${action}`)
    return data
  },
  async deleteTask(taskType: 'practice' | 'exam', id: string): Promise<void> {
    await http.delete(`/cabinlingo/tasks/${taskType}/${id}`)
  },
  async dashboard(): Promise<DashboardSummary> {
    const { data } = await http.get<DashboardSummary>('/cabinlingo/dashboard')
    return data
  },
  async users(): Promise<UserSummary[]> {
    const { data } = await http.get<UserSummary[]>('/core/users')
    return data
  },
  async createUser(payload: { account: string; display_name: string; password: string; role: 'learner' | 'evaluator' | 'instructor' | 'admin'; email?: string; class_id?: string }): Promise<UserSummary> {
    const { data } = await http.post<UserSummary>('/core/users', payload)
    return data
  },
  async importUsers(rows: Array<{ account: string; display_name: string; password: string; role: string; email?: string; class_id?: string }>): Promise<UserImportResult> {
    const { data } = await http.post<UserImportResult>('/core/users/import', { rows })
    return data
  },
  async deactivateUser(userId: string): Promise<UserSummary> {
    const { data } = await http.delete<UserSummary>(`/core/users/${userId}`)
    return data
  },
  async resetUserPassword(userId: string, password: string): Promise<UserSummary> {
    const { data } = await http.post<UserSummary>(`/core/users/${userId}/password-reset`, { password })
    return data
  },
  async batchAssign(taskType: 'practice' | 'exam', taskId: string, userIds: string[], classIds: string[] = []): Promise<Assignment[]> {
    const path = taskType === 'practice' ? `/cabinlingo/practice/tasks/${taskId}/assignments/batch` : `/cabinlingo/exams/tasks/${taskId}/assignments/batch`
    const { data } = await http.post<Assignment[]>(path, { user_ids: userIds, class_ids: classIds })
    return data
  },
  async practiceTask(id: string): Promise<{ id: string; title: string; broadcast_id: string; due_at: string | null; completion_rule: Record<string, unknown>; status: string; task_type: 'practice' }> {
    const { data } = await http.get(`/cabinlingo/practice/tasks/${id}`)
    return data
  },
  async examTask(id: string): Promise<{ id: string; title: string; broadcast_id: string; due_at: string | null; max_recordings: number; status: string; task_type: 'exam' }> {
    const { data } = await http.get(`/cabinlingo/exams/tasks/${id}`)
    return data
  },
  async submitPracticeAttempt(payload: { assignment_id: string; segment_id: string; audio_ref: string; reference_text: string }): Promise<{ attempt_id: string; ai_status: string; issues: Array<Record<string, unknown>>; next_action: string; attempt_no: number }> {
    const { data } = await http.post('/cabinlingo/practice/attempts', payload)
    return data
  },
  async submitExam(taskId: string, payload: { assignment_id: string; recording_refs: string[]; paper_item_ids: string[] }): Promise<{ status: string; recording_count: number; max_recordings: number }> {
    const { data } = await http.post(`/cabinlingo/exams/tasks/${taskId}/submit`, payload)
    return data
  },
  async createRecording(payload: { assignment_id: string; purpose: 'practice' | 'exam'; audio_ref: string; duration_ms?: number }): Promise<{ id: string; assignment_id: string; purpose: 'practice' | 'exam'; audio_ref: string; status: string }> {
    const { data } = await http.post('/cabinlingo/recordings', payload)
    return data
  },
  async reviewQueue(): Promise<ReviewQueueItem[]> {
    const { data } = await http.get<ReviewQueueItem[]>('/cabinlingo/review/queue')
    return data
  },
  async saveReview(assignmentId: string, payload: { manual_score: number; comments: string; publish: boolean }): Promise<{ assignment_id: string; status: string }> {
    const { data } = await http.post(`/cabinlingo/review/${assignmentId}`, payload)
    return data
  },
  async practiceAssignments(): Promise<Assignment[]> {
    const { data } = await http.get<Assignment[]>('/cabinlingo/practice/assignments')
    return data
  },
  async examAssignments(): Promise<Assignment[]> {
    const { data } = await http.get<Assignment[]>('/cabinlingo/exams/assignments')
    return data
  },
  async progress(): Promise<Progress[]> {
    const { data } = await http.get<Progress[]>('/cabinlingo/progress')
    return data
  },
  async organizations(): Promise<Organization[]> {
    const { data } = await http.get<Organization[]>('/core/organizations')
    return data
  },
  async createOrganization(payload: { code: string; name: string }): Promise<Organization> {
    const { data } = await http.post<Organization>('/core/organizations', payload)
    return data
  },
  async classes(organizationId?: string): Promise<TrainingClass[]> {
    const { data } = await http.get<TrainingClass[]>('/core/classes', { params: organizationId ? { organization_id: organizationId } : undefined })
    return data
  },
  async createClass(payload: { organization_id: string; code: string; name: string; class_type: 'training' | 'assessment'; description: string; start_date?: string | null; end_date?: string | null }): Promise<TrainingClass> {
    const { data } = await http.post<TrainingClass>('/core/classes', payload)
    return data
  },
  async classDetail(classId: string): Promise<ClassDetail> {
    const { data } = await http.get<ClassDetail>(`/core/classes/${classId}`)
    return data
  },
  async updateClass(classId: string, payload: Partial<Pick<TrainingClass, 'code' | 'name' | 'class_type' | 'description' | 'start_date' | 'end_date' | 'status'>>): Promise<TrainingClass> {
    const { data } = await http.put<TrainingClass>(`/core/classes/${classId}`, payload)
    return data
  },
  async addClassStudents(classId: string, studentIds: string[]): Promise<ClassMember[]> {
    const { data } = await http.post<ClassMember[]>(`/core/classes/${classId}/students`, { student_ids: studentIds })
    return data
  },
  async removeClassStudent(classId: string, studentId: string): Promise<TrainingClass> {
    const { data } = await http.delete<TrainingClass>(`/core/classes/${classId}/students/${studentId}`)
    return data
  },
  async learnerInstructors(studentId: string): Promise<InstructorAssignment[]> {
    const { data } = await http.get<InstructorAssignment[]>(`/core/learners/${studentId}/instructors`)
    return data
  },
  async createInstructorAssignment(studentId: string, payload: { instructor_id: string; assignment_type: 'training' | 'assessment' | 'both'; course_id?: string | null; effective_from?: string | null; effective_to?: string | null }): Promise<InstructorAssignment> {
    const { data } = await http.post<InstructorAssignment>(`/core/learners/${studentId}/instructors`, payload)
    return data
  },
  async updateInstructorAssignment(studentId: string, assignmentId: string, payload: Partial<Pick<InstructorAssignment, 'assignment_type' | 'course_id' | 'effective_from' | 'effective_to' | 'status'>>): Promise<InstructorAssignment> {
    const { data } = await http.put<InstructorAssignment>(`/core/learners/${studentId}/instructors/${assignmentId}`, payload)
    return data
  },
  async deactivateInstructorAssignment(studentId: string, assignmentId: string): Promise<InstructorAssignment> {
    const { data } = await http.delete<InstructorAssignment>(`/core/learners/${studentId}/instructors/${assignmentId}`)
    return data
  },
  async reassignEvaluationTasks(studentId: string): Promise<{ learner_id: string; created: number; waiting_assignment: number; practice_targets: number; exam_targets: number }> {
    const { data } = await http.post(`/core/learners/${studentId}/evaluation-tasks/reassign`)
    return data
  },
  async unassignedEvaluationTasks(): Promise<Array<{ id: string; review_type: 'practice' | 'exam'; learner_id: string; learner_name: string; status: string; created_at: string }>> {
    const { data } = await http.get('/core/evaluation-tasks/unassigned')
    return data
  },
  async courses(): Promise<Course[]> {
    const { data } = await http.get<Course[]>('/cabinlingo/admin/courses')
    return data
  },
  async createCourse(payload: { code: string; title: string; description: string; category: string; organization_id?: string | null }): Promise<Course> {
    const { data } = await http.post<Course>('/cabinlingo/admin/courses', payload)
    return data
  },
  async courseVersions(courseId: string): Promise<CourseVersion[]> {
    const { data } = await http.get<CourseVersion[]>(`/cabinlingo/admin/courses/${courseId}/versions`)
    return data
  },
  async publishedCourseVersions(): Promise<CourseVersion[]> {
    const { data } = await http.get<CourseVersion[]>('/cabinlingo/admin/course-versions/published')
    return data
  },
  async createCourseVersion(courseId: string, payload: { version_label: string; change_summary: string }): Promise<CourseVersion> {
    const { data } = await http.post<CourseVersion>(`/cabinlingo/admin/courses/${courseId}/versions`, payload)
    return data
  },
  async chapters(courseVersionId: string): Promise<Chapter[]> {
    const { data } = await http.get<Chapter[]>(`/cabinlingo/admin/course-versions/${courseVersionId}/chapters`)
    return data
  },
  async createChapter(courseVersionId: string, payload: { code: string; title: string; sequence_no: number; learning_objective: string }): Promise<Chapter> {
    const { data } = await http.post<Chapter>(`/cabinlingo/admin/course-versions/${courseVersionId}/chapters`, payload)
    return data
  },
  async contents(chapterId: string): Promise<ContentItem[]> {
    const { data } = await http.get<ContentItem[]>(`/cabinlingo/admin/chapters/${chapterId}/contents`)
    return data
  },
  async contentInteractions(contentId: string): Promise<ContentInteraction[]> {
    const { data } = await http.get<ContentInteraction[]>(`/cabinlingo/admin/contents/${contentId}/interactions`)
    return data
  },
  async createContentInteraction(contentId: string, payload: Omit<ContentInteraction, 'id' | 'content_item_id' | 'status' | 'version_no' | 'created_at' | 'updated_at'>): Promise<ContentInteraction> {
    const { data } = await http.post<ContentInteraction>(`/cabinlingo/admin/contents/${contentId}/interactions`, payload)
    return data
  },
  async updateContentInteraction(interactionId: string, payload: Omit<ContentInteraction, 'id' | 'content_item_id' | 'status' | 'version_no' | 'created_at' | 'updated_at'>): Promise<ContentInteraction> {
    const { data } = await http.put<ContentInteraction>(`/cabinlingo/admin/interactions/${interactionId}`, payload)
    return data
  },
  async archiveContentInteraction(interactionId: string): Promise<ContentInteraction> {
    const { data } = await http.delete<ContentInteraction>(`/cabinlingo/admin/interactions/${interactionId}`)
    return data
  },
  async importHtml(chapterId: string, payload: { title: string; source_filename: string; source_html: string; sequence_no: number }): Promise<ContentItem> {
    const { data } = await http.post<ContentItem>(`/cabinlingo/admin/chapters/${chapterId}/html-import`, payload)
    return data
  },
  async importPpt(courseVersionId: string, file: File): Promise<PPTImportResult> {
    const form = new FormData()
    form.append('file', file, file.name)
    const { data } = await http.post<PPTImportResult>(`/cabinlingo/admin/course-versions/${courseVersionId}/ppt-import`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    return data
  },
  async importPdf(courseVersionId: string, file: File): Promise<PDFImportResult> {
    const form = new FormData()
    form.append('file', file, file.name)
    const { data } = await http.post<PDFImportResult>(`/cabinlingo/admin/course-versions/${courseVersionId}/pdf-import`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000,
    })
    return data
  },
  async learningCards(includeArchived = false): Promise<LearningCard[]> {
    const { data } = await http.get<LearningCard[]>('/cabinlingo/admin/learning-cards', { params: { include_archived: includeArchived } })
    return data
  },
  async importLearningCard(file: File): Promise<LearningCard> {
    const form = new FormData()
    form.append('file', file, file.name)
    const { data } = await http.post<LearningCard>('/cabinlingo/admin/learning-cards/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 180000,
    })
    return data
  },
  async previewLearningCard(id: string): Promise<LearningCardViewer> {
    const { data } = await http.get<LearningCardViewer>(`/cabinlingo/admin/learning-cards/${id}/preview`)
    return data
  },
  async addLearningCardToCourse(id: string, courseId: string): Promise<LearningCardCourseLink> {
    const { data } = await http.post<LearningCardCourseLink>(`/cabinlingo/admin/learning-cards/${id}/add-to-course`, { course_id: courseId })
    return data
  },
  async archiveLearningCard(id: string): Promise<LearningCard> {
    const { data } = await http.delete<LearningCard>(`/cabinlingo/admin/learning-cards/${id}`)
    return data
  },
  async removeLearningCardFromCourse(contentId: string): Promise<void> {
    await http.delete(`/cabinlingo/admin/learning-card-contents/${contentId}`)
  },
  async moveLearningCardInCourse(contentId: string, direction: 'up' | 'down'): Promise<void> {
    await http.post(`/cabinlingo/admin/learning-card-contents/${contentId}/move`, null, { params: { direction } })
  },
  async assignmentLearningCards(assignmentId: string): Promise<Array<{ id: string; title: string; learning_card_id: string }>> {
    const { data } = await http.get(`/cabinlingo/learner/assignments/${assignmentId}/learning-cards`)
    return data
  },
  async markLearningCardRead(contentId: string, assignmentId: string): Promise<{ read: boolean; progress_percent: number }> {
    const { data } = await http.post(`/cabinlingo/learner/learning-cards/${contentId}/read`, null, { params: { assignment_id: assignmentId } })
    return data
  },
  async learnerLearningCard(contentId: string, assignmentId: string): Promise<LearningCardViewer> {
    const { data } = await http.get<LearningCardViewer>(`/cabinlingo/learner/learning-cards/${contentId}`, { params: { assignment_id: assignmentId } })
    return data
  },
  async contentAssets(contentId: string): Promise<ContentAsset[]> {
    const { data } = await http.get<ContentAsset[]>(`/cabinlingo/admin/contents/${contentId}/assets`)
    return data
  },
  async uploadContentAsset(contentId: string, file: File, assetRole: 'audio' | 'video' = file.type.startsWith('video/') ? 'video' : 'audio'): Promise<ContentAsset> {
    const { data } = await http.post<ContentAsset>(`/cabinlingo/admin/contents/${contentId}/assets`, file, {
      params: { source_filename: file.name, asset_role: assetRole },
      headers: { 'Content-Type': file.type },
      timeout: 180000,
    })
    return data
  },
  async courseStandard(contentId: string): Promise<CourseStandard | null> {
    const { data } = await http.get<CourseStandard | null>(`/cabinlingo/admin/contents/${contentId}/standard`)
    return data
  },
  async saveCourseStandard(contentId: string, payload: { standard_text: string; stress_rules: string; pronunciation_notes: string; pause_rules: string; tone_requirements: string; rule_version: string; change_summary: string }): Promise<CourseStandard> {
    const { data } = await http.put<CourseStandard>(`/cabinlingo/admin/contents/${contentId}/standard`, payload)
    return data
  },
  async uploadCourseStandardAudio(contentId: string, standardId: string, file: File): Promise<CourseStandard> {
    const { data } = await http.post<CourseStandard>(`/cabinlingo/admin/contents/${contentId}/standards/${standardId}/audio`, file, {
      params: { source_filename: file.name },
      headers: { 'Content-Type': file.type || 'audio/mpeg' },
      timeout: 120000,
    })
    return data
  },
  async publishCourseVersion(courseVersionId: string): Promise<CourseVersion> {
    const { data } = await http.post<CourseVersion>(`/cabinlingo/admin/course-versions/${courseVersionId}/publish`)
    return data
  },
  async learnerHome(): Promise<LearnerHome> {
    const { data } = await http.get<LearnerHome>('/cabinlingo/learner/home')
    return data
  },
  async learnerTasks(): Promise<LearnerTask[]> {
    const { data } = await http.get<LearnerTask[]>('/cabinlingo/learner/tasks')
    return data
  },
  async adminLearnerTasks(learnerId: string): Promise<LearnerTask[]> {
    const { data } = await http.get<LearnerTask[]>(`/cabinlingo/admin/learners/${encodeURIComponent(learnerId)}/tasks`)
    return data
  },
  async adminLearnerBroadcastProgress(learnerId: string): Promise<AdminLearnerBroadcastItem[]> {
    const { data } = await http.get<AdminLearnerBroadcastItem[]>(`/cabinlingo/admin/learners/${encodeURIComponent(learnerId)}/broadcast-progress`)
    return data
  },
  async adminLearnerAttemptDetail(learnerId: string, attemptId: string): Promise<InstructorReviewDetail> {
    const { data } = await http.get<InstructorReviewDetail>(`/cabinlingo/admin/learners/${encodeURIComponent(learnerId)}/attempts/${encodeURIComponent(attemptId)}`)
    return data
  },
  async adminTaskRoster(taskType: 'practice' | 'exam', taskId: string): Promise<TaskRoster> {
    const { data } = await http.get<TaskRoster>(`/cabinlingo/admin/tasks/${taskType}/${encodeURIComponent(taskId)}/learners`)
    return data
  },
  async practiceWorkspace(assignmentId: string): Promise<PracticeWorkspace> {
    const { data } = await http.get<PracticeWorkspace>(`/cabinlingo/learner/practice/workspace/${assignmentId}`)
    return data
  },
  async submitInteractionAnswer(interactionId: string, payload: { assignment_id: string; content_item_id: string; answer: string }): Promise<InteractionAnswer> {
    const { data } = await http.post<InteractionAnswer>(`/cabinlingo/learner/interactions/${interactionId}/answers`, payload)
    return data
  },
  async uploadAudio(payload: { assignment_id: string; purpose: 'practice' | 'exam'; blob: Blob; content_item_id?: string; duration_ms?: number }): Promise<AudioUpload> {
    const { data } = await http.post<AudioUpload>('/cabinlingo/learner/audio', payload.blob, {
      params: { assignment_id: payload.assignment_id, purpose: payload.purpose, content_item_id: payload.content_item_id, duration_ms: payload.duration_ms },
      headers: { 'Content-Type': payload.blob.type || 'audio/webm' },
      timeout: 120000,
    })
    return data
  },
  async submitCoursePractice(payload: { assignment_id: string; content_item_id: string; recording_id: string; correction_of_attempt_id?: string | null; recognized_text?: string | null }): Promise<LearnerAttempt> {
    const { data } = await http.post<LearnerAttempt>('/cabinlingo/learner/practice/attempts', payload, { timeout: 120000 })
    return data
  },
  async courseV23(includeDeleted = false): Promise<CourseV23Detail[]> {
    const { data } = await http.get<CourseV23Detail[]>('/cabinlingo/admin/course-v23', { params: { include_deleted: includeDeleted } })
    return data
  },
  async cosVideos(search = '', marker = ''): Promise<CosVideoList> {
    const { data } = await http.get<CosVideoList>('/cabinlingo/admin/cos-videos', { params: { search, marker, limit: 100 } })
    return data
  },
  async previewCosVideo(key: string): Promise<{ url: string; expires_in: number; video: CosVideoObject }> {
    const { data } = await http.post<{ url: string; expires_in: number; video: CosVideoObject }>('/cabinlingo/admin/cos-videos/preview', { key })
    return data
  },
  async createCourseV23(payload: CourseV23DraftPayload, media: { cover?: File | null; video?: File | null; audio?: File | null; audio_zh?: File | null; audio_zh_2?: File | null; audio_en?: File | null; audio_en_2?: File | null }): Promise<CourseV23Detail> {
    const form = new FormData()
    form.append('payload', JSON.stringify(payload))
    if (media.cover) form.append('cover', media.cover, media.cover.name)
    if (media.video) form.append('video', media.video, media.video.name)
    if (media.audio) form.append('audio', media.audio, media.audio.name)
    if (media.audio_zh) form.append('audio_zh', media.audio_zh, media.audio_zh.name)
    if (media.audio_zh_2) form.append('audio_zh_2', media.audio_zh_2, media.audio_zh_2.name)
    if (media.audio_en) form.append('audio_en', media.audio_en, media.audio_en.name)
    if (media.audio_en_2) form.append('audio_en_2', media.audio_en_2, media.audio_en_2.name)
    const { data } = await http.post<CourseV23Detail>('/cabinlingo/admin/course-v23/drafts', form, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 240000,
    })
    return data
  },
  async updateCourseV23(courseVersionId: string, payload: CourseV23DraftPayload, media: { cover?: File | null; video?: File | null; audio?: File | null; audio_zh?: File | null; audio_zh_2?: File | null; audio_en?: File | null; audio_en_2?: File | null }, expectedUpdatedAt?: string | null): Promise<CourseV23Detail> {
    const form = new FormData()
    form.append('payload', JSON.stringify(payload))
    if (expectedUpdatedAt) form.append('expected_updated_at', expectedUpdatedAt)
    if (media.cover) form.append('cover', media.cover, media.cover.name)
    if (media.video) form.append('video', media.video, media.video.name)
    if (media.audio) form.append('audio', media.audio, media.audio.name)
    if (media.audio_zh) form.append('audio_zh', media.audio_zh, media.audio_zh.name)
    if (media.audio_zh_2) form.append('audio_zh_2', media.audio_zh_2, media.audio_zh_2.name)
    if (media.audio_en) form.append('audio_en', media.audio_en, media.audio_en.name)
    if (media.audio_en_2) form.append('audio_en_2', media.audio_en_2, media.audio_en_2.name)
    const { data } = await http.put<CourseV23Detail>(`/cabinlingo/admin/course-v23/drafts/${courseVersionId}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 240000,
    })
    return data
  },
  async importCourseV23(excel: File, mediaZip?: File | null): Promise<CourseImportResult> {
    const form = new FormData()
    form.append('excel', excel, excel.name)
    if (mediaZip) form.append('media_zip', mediaZip, mediaZip.name)
    const { data } = await http.post<CourseImportResult>('/cabinlingo/admin/course-v23/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000,
    })
    return data
  },
  async courseV23Template(): Promise<Blob> {
    const { data } = await http.get<Blob>('/cabinlingo/admin/course-v23/template', { responseType: 'blob' })
    return data
  },
  async enableCourseV23(courseId: string): Promise<CourseV23Detail> {
    const { data } = await http.post<CourseV23Detail>(`/cabinlingo/admin/course-v23/${courseId}/enable`)
    return data
  },
  async disableCourseV23(courseId: string): Promise<CourseV23Detail> {
    const { data } = await http.post<CourseV23Detail>(`/cabinlingo/admin/course-v23/${courseId}/disable`)
    return data
  },
  async deleteCourseV23(courseId: string): Promise<CourseV23Detail> {
    const { data } = await http.delete<CourseV23Detail>(`/cabinlingo/admin/course-v23/${courseId}`)
    return data
  },
  async restoreCourseV23(courseId: string): Promise<CourseV23Detail> {
    const { data } = await http.post<CourseV23Detail>(`/cabinlingo/admin/course-v23/${courseId}/restore`)
    return data
  },
  async mistakeWordsTemplate(): Promise<Blob> {
    const { data } = await http.get<Blob>('/cabinlingo/admin/course-v23/mistake-words/template', { responseType: 'blob' })
    return data
  },
  async exportCourseMistakeWords(courseVersionId: string): Promise<Blob> {
    const { data } = await http.get<Blob>(`/cabinlingo/admin/course-v23/${courseVersionId}/mistake-words/export`, { responseType: 'blob' })
    return data
  },
  async previewCourseMistakeWordsImport(courseVersionId: string, excel: File): Promise<CourseMistakeImportPreview> {
    const form = new FormData()
    form.append('excel', excel, excel.name)
    const { data } = await http.post<CourseMistakeImportPreview>(`/cabinlingo/admin/course-v23/${courseVersionId}/mistake-words/import/preview`, form, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000,
    })
    return data
  },
  async previewNewCourseMistakeWordsImport(courseId: string, existing: CourseMistakeWord[], excel: File): Promise<CourseMistakeImportPreview> {
    const form = new FormData()
    form.append('course_id', courseId)
    form.append('existing', JSON.stringify(existing))
    form.append('excel', excel, excel.name)
    const { data } = await http.post<CourseMistakeImportPreview>('/cabinlingo/admin/course-v23/mistake-words/import/preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000,
    })
    return data
  },
  async importCourseMistakeWords(courseVersionId: string, excel: File): Promise<CourseV23Detail> {
    const form = new FormData()
    form.append('excel', excel, excel.name)
    const { data } = await http.post<CourseV23Detail>(`/cabinlingo/admin/course-v23/${courseVersionId}/mistake-words/import`, form, {
      headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000,
    })
    return data
  },
  async previewCourseV23(courseVersionId: string): Promise<CourseV23Detail> {
    const { data } = await http.get<CourseV23Detail>(`/cabinlingo/admin/course-v23/${courseVersionId}/preview`)
    return data
  },
  async createCourseV23Revision(courseVersionId: string): Promise<CourseV23Detail> {
    const { data } = await http.post<CourseV23Detail>(`/cabinlingo/admin/course-v23/${courseVersionId}/revision`)
    return data
  },
  async publishCourseV23(courseVersionId: string): Promise<CourseV23Detail> {
    const { data } = await http.post<CourseV23Detail>(`/cabinlingo/admin/course-v23/${courseVersionId}/publish`)
    return data
  },
  async learnerCourseV23(courseVersionId: string): Promise<CourseV23Detail> {
    const { data } = await http.get<CourseV23Detail>(`/cabinlingo/learner/course-v23/${courseVersionId}`)
    learnerCourseCache.set(courseVersionId, { course: data, cachedAt: Date.now() })
    return data
  },
  async learnerCourseV23VideoPlayback(courseVersionId: string): Promise<{ url: string; expiresAt: number }> {
    const cacheKey = `cos:${courseVersionId}`
    const cached = courseMediaPlaybackCache.get(cacheKey)
    if (cached && cached.expiresAt - Date.now() > 60_000) return cached
    const { data } = await http.post<{ url: string; expires_in: number }>(`/cabinlingo/learner/course-v23/${courseVersionId}/video-playback`)
    const playback = { url: data.url, expiresAt: Date.now() + data.expires_in * 1000 }
    courseMediaPlaybackCache.set(cacheKey, playback)
    return playback
  },
  async learnerCourseV23Catalog(): Promise<CourseV23Detail[]> {
    const { data } = await http.get<CourseV23Detail[]>('/cabinlingo/learner/course-v23')
    const cachedAt = Date.now()
    for (const course of data) learnerCourseCache.set(course.course_version_id, { course, cachedAt })
    return data
  },
  async courseV23AudioAlignment(courseVersionId: string, fileId: string, language: 'zh' | 'en'): Promise<CourseAudioAlignment> {
    const { data } = await http.post<CourseAudioAlignment>(
      `/cabinlingo/learner/course-v23/${courseVersionId}/audio-alignment/${fileId}`,
      undefined,
      { params: { language }, timeout: 360000 },
    )
    return data
  },
  async ttsOptions(): Promise<TTSOptions> {
    const { data } = await http.get<TTSOptions>('/cabinlingo/admin/tts/options')
    return data
  },
  async prosodyScenes(): Promise<TTSProsodySceneResponse> {
    const { data } = await http.get<TTSProsodySceneResponse>('/cabinlingo/admin/tts/prosody/scenes')
    return data
  },
  async analyzeProsody(payload: { text: string; scene: string }): Promise<TTSProsodyAnalysis> {
    const { data } = await http.post<TTSProsodyAnalysis>('/cabinlingo/admin/tts/prosody/analyze', payload, { timeout: 60000 })
    return data
  },
  async previewProsodyTts(script: string, language: 'zh' | 'en'): Promise<TTSProsodyPreview> {
    const { data } = await http.post<TTSProsodyPreview>('/cabinlingo/admin/tts/prosody/preview', { script, language })
    return data
  },
  async generateProsodyTts(payload: { script: string; language: 'zh' | 'en'; voice: string; base_rate: number }): Promise<Blob> {
    const { data } = await http.post<Blob>('/cabinlingo/admin/tts/prosody/generate', payload, {
      responseType: 'blob', timeout: 180000,
    })
    return data
  },
  async assembleProsodyTts(clips: Blob[], manifest: TTSProsodyAssembleItem[]): Promise<Blob> {
    const form = new FormData()
    form.append('manifest', JSON.stringify(manifest))
    clips.forEach((clip, index) => form.append('clips', clip, `sentence-${index + 1}.wav`))
    const { data } = await http.post<Blob>('/cabinlingo/admin/tts/prosody/assemble', form, {
      headers: { 'Content-Type': 'multipart/form-data' }, responseType: 'blob', timeout: 180000,
    })
    return data
  },
  async previewTtsPronunciation(text: string, language: 'zh' | 'en'): Promise<TTSPronunciationPreview> {
    const { data } = await http.post<TTSPronunciationPreview>('/cabinlingo/admin/tts/pronunciation-preview', { text, language })
    return data
  },
  async ttsPronunciations(): Promise<TTSPronunciationDictionary> {
    const { data } = await http.get<TTSPronunciationDictionary>('/cabinlingo/admin/tts/pronunciations')
    return data
  },
  async saveTtsPronunciation(payload: { phrase: string; pinyin: string; note: string; enabled: boolean; priority: number }): Promise<TTSPronunciationEntry> {
    const { data } = await http.put<TTSPronunciationEntry>('/cabinlingo/admin/tts/pronunciations', payload)
    return data
  },
  async deleteTtsPronunciation(id: string): Promise<void> {
    await http.delete(`/cabinlingo/admin/tts/pronunciations/${id}`)
  },
  async generateTts(payload: { text: string; language: 'zh' | 'en'; voice: string; rate: number; format: 'mp3' | 'wav'; pronunciations?: Array<{ phrase: string; pinyin: string; applied: boolean }> }): Promise<Blob> {
    const { data } = await http.post<Blob>('/cabinlingo/admin/tts/generate', payload, {
      responseType: 'blob', timeout: 180000,
    })
    return data
  },
  async warmStandardPronunciations(payload: { text: string; language: 'zh' | 'en'; voice?: string; rate?: number }): Promise<{ status: string; token_count: number; unique_token_count: number; queued_token_count: number; truncated: boolean; dictionary_version: string }> {
    const { data } = await http.post('/cabinlingo/admin/tts/standard-pronunciations/warm', payload, { timeout: 30000 })
    return data
  },
  async learnerStandardPronunciation(payload: { attempt_id: string; text: string; reference_index?: number | null }): Promise<Blob> {
    const { data } = await http.post<Blob>('/cabinlingo/learner/tts/standard-pronunciation', payload, {
      responseType: 'blob', timeout: 180000,
    })
    return data
  },
  async learnerCoursePronunciation(courseVersionId: string, payload: { text: string; language: 'zh' | 'en' }): Promise<Blob> {
    const { data } = await http.post<Blob>(`/cabinlingo/learner/course-v23/${courseVersionId}/pronunciation`, payload, {
      responseType: 'blob', timeout: 180000,
    })
    return data
  },
  async batchCreateInstructorAssignments(payload: { student_ids: string[]; class_ids: string[]; instructor_id: string; assignment_type: 'training' | 'assessment' | 'both'; course_id?: string | null; effective_from?: string | null; effective_to?: string | null }): Promise<InstructorAssignmentBatchResult> {
    const { data } = await http.post<InstructorAssignmentBatchResult>('/core/learner-instructor-assignments/batch', payload)
    return data
  },
  async learnerAttempts(): Promise<LearnerAttempt[]> {
    const { data } = await http.get<LearnerAttempt[]>('/cabinlingo/learner/practice/attempts')
    return data
  },
  async learnerAttempt(attemptId: string): Promise<LearnerAttempt> {
    const { data } = await http.get<LearnerAttempt>(`/cabinlingo/learner/practice/attempts/${attemptId}`)
    return data
  },
  async reanalyzeLearnerAttempt(attemptId: string): Promise<LearnerAttempt> {
    const { data } = await http.post<LearnerAttempt>(`/cabinlingo/learner/practice/attempts/${attemptId}/reanalyze`, undefined, { timeout: 180000 })
    return data
  },
  async learnerFeedback(): Promise<TeacherFeedback[]> {
    const { data } = await http.get<TeacherFeedback[]>('/cabinlingo/learner/feedback')
    return data
  },
  async learnerGrowth(): Promise<GrowthProfile> {
    const { data } = await http.get<GrowthProfile>('/cabinlingo/learner/growth')
    return data
  },
  async instructorQueue(params?: { review_type?: 'practice' | 'exam'; review_status?: 'pending' | 'draft' | 'published'; class_id?: string }): Promise<InstructorQueueItem[]> {
    const { data } = await http.get<InstructorQueueItem[]>('/cabinlingo/instructor/reviews/queue', { params })
    return data
  },
  async instructorLearners(): Promise<InstructorLearner[]> {
    const { data } = await http.get<InstructorLearner[]>('/cabinlingo/instructor/learners')
    return data
  },
  async instructorDashboard(): Promise<InstructorDashboard> {
    const { data } = await http.get<InstructorDashboard>('/cabinlingo/instructor/dashboard')
    return data
  },
  async instructorLearnerSubmissions(learnerId: string): Promise<InstructorQueueItem[]> {
    const { data } = await http.get<InstructorQueueItem[]>(`/cabinlingo/instructor/learners/${learnerId}/submissions`)
    return data
  },
  async instructorReview(reviewType: 'practice' | 'exam', targetId: string): Promise<InstructorReviewDetail> {
    const { data } = await http.get<InstructorReviewDetail>(`/cabinlingo/instructor/reviews/${reviewType}/${targetId}`)
    return data
  },
  async saveInstructorReview(reviewType: 'practice' | 'exam', targetId: string, payload: InstructorReviewPayload): Promise<Record<string, unknown>> {
    const { data } = await http.put(`/cabinlingo/instructor/reviews/${reviewType}/${targetId}`, payload)
    return data
  },
  async publishInstructorReview(reviewType: 'practice' | 'exam', targetId: string, payload: InstructorReviewPayload): Promise<Record<string, unknown>> {
    const { data } = await http.post(`/cabinlingo/instructor/reviews/${reviewType}/${targetId}/publish`, payload)
    return data
  },
  async uploadInstructorFeedbackAudio(reviewType: 'practice' | 'exam', targetId: string, blob: Blob, durationMs: number): Promise<InstructorFeedbackAudioUpload> {
    const { data } = await http.post<InstructorFeedbackAudioUpload>(`/cabinlingo/instructor/reviews/${reviewType}/${targetId}/feedback-audio`, blob, {
      params: { duration_ms: Math.max(0, Math.round(durationMs)) },
      headers: { 'Content-Type': blob.type || 'audio/webm' },
      timeout: 120000,
    })
    return data
  },
  async classReviewAnalytics(): Promise<ClassReviewAnalytics[]> {
    const { data } = await http.get<ClassReviewAnalytics[]>('/cabinlingo/instructor/analytics/classes')
    return data
  },
  async protectedAudio(url: string): Promise<Blob> {
    const path = url.startsWith('/api/v1') ? url.slice('/api/v1'.length) : url
    const { data } = await http.get<Blob>(path, { responseType: 'blob', timeout: 120000 })
    return data
  },
  async courseDocumentPdf(contentId: string): Promise<Uint8Array> {
    const { data } = await http.get<ArrayBuffer>(`/cabinlingo/learner/course-documents/${contentId}`, { responseType: 'arraybuffer', timeout: 180000 })
    return new Uint8Array(data)
  },
  async protectedMedia(url: string): Promise<Blob> {
    const path = url.startsWith('/api/v1') ? url.slice('/api/v1'.length) : url
    const { data } = await http.get<Blob>(path, { responseType: 'blob', timeout: 180000 })
    return data
  },
  async courseV23MediaPlayback(url: string): Promise<{ url: string; expiresAt: number }> {
    const cached = courseMediaPlaybackCache.get(url)
    if (cached && cached.expiresAt - Date.now() > 60_000) return cached
    const path = url.startsWith('/api/v1') ? url.slice('/api/v1'.length) : url
    const { data } = await http.post<{ url: string; expires_in: number }>(`${path}/playback`)
    const playback = { url: data.url, expiresAt: Date.now() + data.expires_in * 1000 }
    courseMediaPlaybackCache.set(url, playback)
    return playback
  },
}
