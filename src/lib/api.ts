// ============================================================
// CAET 前端 API 客户端
// 统一调用自建 FastAPI 后端，契约与 caet-backend/app/routers/* 一一对应。
// ============================================================

const BASE: string = (import.meta as any).env?.VITE_API_BASE || '/api'
const TOKEN_KEY = 'caet_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(t: string): void {
  localStorage.setItem(TOKEN_KEY, t)
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}${path}`, { ...options, headers })
  if (res.status === 401) {
    clearToken()
    if (typeof window !== 'undefined') {
      // 仅在非登录页时跳转，避免登录页死循环
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    throw new ApiError('登录已失效，请重新登录', 401)
  }
  if (!res.ok) {
    let detail = '请求失败'
    try {
      const body = await res.json()
      detail = body.detail || (typeof body === 'string' ? body : '请求失败')
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

async function upload<T>(path: string, file: File | Blob, filename?: string): Promise<T> {
  const fd = new FormData()
  fd.append('file', file, filename || (file as any).name || 'upload')
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: fd,
  })
  if (res.status === 401) {
    clearToken()
    if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
      window.location.href = '/login'
    }
    throw new ApiError('登录已失效，请重新登录', 401)
  }
  if (!res.ok) {
    let detail = '上传失败'
    try { detail = (await res.json()).detail || detail } catch { /* ignore */ }
    throw new ApiError(detail, res.status)
  }
  return (await res.json()) as T
}

function qs(params: Record<string, any>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') sp.append(k, String(v))
  })
  const s = sp.toString()
  return s ? `?${s}` : ''
}

// ---------------- 类型（与后端 Pydantic 对齐，参考 src/types/database.ts） ----------------
export interface ApiUser {
  id: string
  email: string
  display_name: string | null
  employee_no: string | null
  role: 'learner' | 'instructor' | 'admin'
  group_id: string | null
  avatar_url: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AssignmentVM {
  assignment_id: string
  task_id: string
  task_title: string
  course_id: string
  course_title: string
  chapter_from: number
  chapter_to: number
  day_from: number
  day_to: number
  status: string
  progress_percent: number
  started_at: string | null
  completed_at: string | null
  due_at: string
}

export interface TaskDetailVM {
  task: any
  course: any
  days: any[]
  assignment: any
}

export const api = {
  auth: {
    login: (email: string, password: string) =>
      request<{ access_token: string; token_type: string; user: ApiUser }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }),
    register: (payload: { email: string; password: string; display_name?: string; employee_no?: string }) =>
      request<ApiUser>('/auth/register', { method: 'POST', body: JSON.stringify(payload) }),
    me: () => request<ApiUser>('/auth/me'),
    initAdmin: (payload: { email: string; password: string; display_name: string }) =>
      request<ApiUser>('/auth/init-admin', { method: 'POST', body: JSON.stringify(payload) }),
    logout: () => request<void>('/auth/logout', { method: 'POST' }),
  },
  tasks: {
    my: () => request<AssignmentVM[]>('/tasks/my'),
    detail: (taskId: string) => request<TaskDetailVM>(`/tasks/${taskId}/detail`),
    create: (payload: { task: any; learner_ids: string[] }) =>
      request<any>('/admin/tasks', { method: 'POST', body: JSON.stringify(payload) }),
    list: () => request<any[]>('/admin/tasks'),
  },
  content: {
    get: (params: { course_id?: string; chapter_no?: number; day_no?: number }) =>
      request<any[]>(`/content${qs(params)}`),
  },
  courses: {
    list: () => request<any[]>('/courses'),
  },
  progress: {
    get: (assignmentId: string) => request<any>(`/progress${qs({ assignment_id: assignmentId })}`),
    upsert: (payload: {
      assignment_id: string
      content_id: string
      completed?: boolean
      effective_seconds?: number
      last_position?: any
    }) => request<any>('/progress', { method: 'POST', body: JSON.stringify(payload) }),
  },
  events: {
    add: (payload: {
      event_type: string
      event_value?: any
      assignment_id?: string
      course_id?: string
      content_id?: string
      client_timestamp?: string
    }) => request<any>('/events', { method: 'POST', body: JSON.stringify(payload) }),
  },
  record: {
    get: () => request<any>('/record'),
  },
  weeklyTest: {
    get: (params: { course_id?: string; chapter_no?: number }) =>
      request<any>(`/weekly-test${qs(params)}`),
  },
  admin: {
    dashboard: () => request<any>('/admin/dashboard'),
    learners: () => request<any[]>('/admin/learners'),
    learnerDetail: (id: string) => request<any>(`/admin/learners/${id}`),
    events: (params: { learner_id?: string; event_type?: string; limit?: number; offset?: number }) =>
      request<any[]>(`/admin/events${qs(params)}`),
    exportCSV: (type: 'events' | 'progress' | 'assignments') => `${BASE}/admin/export/${type}`,
  },
  groups: {
    list: () => request<any[]>('/admin/groups'),
    create: (name: string) => request<any>('/admin/groups', { method: 'POST', body: JSON.stringify({ name }) }),
    detail: (id: string) => request<any>(`/admin/groups/${id}`),
    rename: (id: string, name: string) =>
      request<any>(`/admin/groups/${id}`, { method: 'PUT', body: JSON.stringify({ name }) }),
    remove: (id: string) => request<void>(`/admin/groups/${id}`, { method: 'DELETE' }),
    addMember: (id: string, learnerId: string) =>
      request<void>(`/admin/groups/${id}/members/${learnerId}`, { method: 'POST' }),
    removeMember: (id: string, learnerId: string) =>
      request<void>(`/admin/groups/${id}/members/${learnerId}`, { method: 'DELETE' }),
  },
  users: {
    list: () => request<any[]>('/admin/users'),
    create: (payload: { email: string; password: string; display_name?: string; employee_no?: string; role: string; group_id?: string | null }) =>
      request<any>('/admin/users', { method: 'POST', body: JSON.stringify(payload) }),
    update: (id: string, payload: Record<string, any>) =>
      request<any>(`/admin/users/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  },
  assessments: {
    submit: (payload: { assessment_type: string; assignment_id: string; content_id?: string | null; answers: any; attempt_no?: number }) =>
      request<any>('/assessments/submit', { method: 'POST', body: JSON.stringify(payload) }),
    my: () => request<any[]>('/assessments/my'),
    task: (taskId: string) => request<any[]>(`/assessments/task/${taskId}`),
    pending: () => request<any[]>('/assessments/pending'),
    get: (id: number) => request<any>(`/assessments/${id}`),
    grade: (id: number, payload: { score?: number | null; feedback?: string | null; status?: string }) =>
      request<any>(`/assessments/${id}/grade`, { method: 'POST', body: JSON.stringify(payload) }),
    setInstructor: (assignmentId: string, instructorId: string) =>
      request<void>(`/admin/assignments/${assignmentId}/instructor?instructor_id=${instructorId}`, { method: 'PUT' }),
  },
  upload: {
    // 管理员上传音频（用作课程标准音频）
    audio: (file: File | Blob, filename?: string) => upload<{ url: string; filename: string }>('/upload/audio', file, filename),
    // 学员/教员上传录音（测评用），文件名以 rec_{userid}_ 前缀
    recording: (file: File | Blob, filename?: string) => upload<{ url: string; filename: string }>('/upload/recording', file, filename),
  },
}

export default api
