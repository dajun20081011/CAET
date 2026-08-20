import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/lib/api'
import type { Task, TaskAssignment, Course, CourseContent, LearnerProgress } from '@/types/database'

export const useLearningStore = defineStore('learning', () => {
  const tasks = ref<Task[]>([])
  const assignments = ref<TaskAssignment[]>([])
  const courses = ref<Course[]>([])
  const courseContents = ref<CourseContent[]>([])
  const progress = ref<LearnerProgress[]>([])
  const events = ref<any[]>([])
  const record = ref<any | null>(null)
  const loading = ref(false)

  const myAssignments = computed(() => assignments.value)
  const myTasks = computed(() => {
    return tasks.value.filter((t) => assignments.value.some((a) => a.task_id === t.id))
  })

  // 将后端的 AssignmentVM 映射为前端视图需要的 tasks / assignments / courses
  function applyAssignmentVM(list: any[]) {
    const taskMap = new Map<string, Task>()
    const assignList: TaskAssignment[] = []
    const courseMap = new Map<string, Course>()

    for (const a of list) {
      assignList.push({
        id: a.assignment_id,
        task_id: a.task_id,
        learner_id: a.learner_id,
        status: a.status,
        started_at: a.started_at,
        completed_at: a.completed_at,
        progress_percent: a.progress_percent,
        updated_at: a.updated_at || '',
      } as TaskAssignment)

      if (!taskMap.has(a.task_id)) {
        taskMap.set(a.task_id, {
          id: a.task_id,
          title: a.task_title,
          course_id: a.course_id,
          course_type: (a.course_type || 'broadcast') as Task['course_type'],
          chapter_from: a.chapter_from,
          chapter_to: a.chapter_to,
          day_from: a.day_from,
          day_to: a.day_to,
          start_at: '',
          due_at: a.due_at,
          completion_rule: {},
          status: a.status,
          created_by: '',
          created_at: '',
          updated_at: '',
        } as Task)
      }

      if (a.course_id && !courseMap.has(a.course_id)) {
        courseMap.set(a.course_id, {
          id: a.course_id,
          code: '',
          title: a.course_title,
          description: '',
          cover_url: null,
          status: '',
          created_at: '',
          updated_at: '',
        } as Course)
      }
    }

    tasks.value = [...taskMap.values()]
    assignments.value = assignList
    // 合并去重课程
    const merged = new Map(courses.value.map((c) => [c.id, c]))
    courseMap.forEach((c, id) => merged.set(id, c))
    courses.value = [...merged.values()]
  }

  async function loadTasks(_learnerId: string) {
    loading.value = true
    try {
      const data = await api.tasks.my()
      applyAssignmentVM(data || [])
    } finally {
      loading.value = false
    }
  }

  async function loadTaskDetail(taskId: string) {
    return await api.tasks.detail(taskId)
  }

  async function loadCourseContent(courseId: string, chapter: number, day: number) {
    const data = await api.content.get({ course_id: courseId, chapter_no: chapter, day_no: day })
    courseContents.value = data || []
    return data || []
  }

  async function loadProgress(assignmentId: string) {
    const data = await api.progress.get(assignmentId)
    progress.value = (data && data.items) || []
    return data
  }

  async function updateProgress(
    assignmentId: string,
    contentId: string,
    _learnerId: string,
    completed: boolean,
    effectiveSeconds?: number,
    lastPosition?: any,
  ) {
    const data = await api.progress.upsert({
      assignment_id: assignmentId,
      content_id: contentId,
      completed,
      effective_seconds: effectiveSeconds,
      last_position: lastPosition,
    })
    // 优先信任后端在 upsert 后返回的进度
    if (data && data.assignment) {
      const a = assignments.value.find((x) => x.id === data.assignment.id)
      if (a) {
        a.progress_percent = data.assignment.progress_percent
        a.status = data.assignment.status
        a.started_at = data.assignment.started_at
        a.completed_at = data.assignment.completed_at
      }
    }
    return data
  }

  // learner_id 由后端从 token 取，前端不必传
  async function addEvent(
    _learnerId: string,
    eventType: string,
    eventValue?: any,
    assignmentId?: string,
    courseId?: string,
    contentId?: string,
  ) {
    await api.events.add({
      event_type: eventType,
      event_value: eventValue,
      assignment_id: assignmentId,
      course_id: courseId,
      content_id: contentId,
      client_timestamp: new Date().toISOString(),
    })
  }

  async function updateAssignmentProgress(assignmentId: string, _percent: number) {
    const data = await api.progress.get(assignmentId)
    if (data && data.assignment) {
      const a = assignments.value.find((x) => x.id === data.assignment.id)
      if (a) {
        a.progress_percent = data.assignment.progress_percent
        a.status = data.assignment.status
      }
    }
  }

  async function loadRecord() {
    loading.value = true
    try {
      const data = await api.record.get()
      record.value = data
      events.value = (data && data.event_distribution) || []
    } finally {
      loading.value = false
    }
  }

  return {
    tasks,
    assignments,
    courses,
    courseContents,
    progress,
    events,
    record,
    loading,
    myAssignments,
    myTasks,
    loadTasks,
    loadTaskDetail,
    loadCourseContent,
    loadProgress,
    updateProgress,
    addEvent,
    updateAssignmentProgress,
    loadRecord,
  }
})
