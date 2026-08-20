import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/lib/api'

export const useAdminStore = defineStore('admin', () => {
  const learners = ref<any[]>([])
  const tasks = ref<any[]>([])
  const events = ref<any[]>([])
  const dashboard = ref<any | null>(null)
  const learnerDetail = ref<any | null>(null)
  const loading = ref(false)
  const loadingDetail = ref(false)

  const stats = computed(() => {
    const d = dashboard.value
    if (!d) {
      return { totalLearners: 0, totalTasks: 0, completionRate: 0, totalHours: 0 }
    }
    return {
      totalLearners: d.learning_people_count || 0,
      totalTasks: 0,
      completionRate: d.overall_completion_rate || 0,
      totalHours: Math.round((d.total_effective_seconds || 0) / 3600 * 10) / 10,
    }
  })

  // 任务状态分布（用于仪表盘环形图）
  const taskDistribution = computed(() => {
    const list = tasks.value
    const completed = list.filter((t) => t.status === 'completed').length
    const active = list.filter((t) => t.status === 'active').length
    const draft = list.filter((t) => t.status === 'draft').length
    return { completed, active, draft, total: list.length }
  })

  async function loadDashboard() {
    loading.value = true
    try {
      dashboard.value = await api.admin.dashboard()
    } finally {
      loading.value = false
    }
  }

  async function loadTasks() {
    loading.value = true
    try {
      const data = await api.tasks.list()
      const courseMap = new Map<string, string>()
      try {
        const courses = await api.courses.list()
        for (const c of courses || []) courseMap.set(c.id, c.title)
      } catch {
        /* 课程目录可选 */
      }
      tasks.value = (data || []).map((t: any) => ({
        id: t.task?.id,
        title: t.task?.title || '',
        course_id: t.task?.course_id || '',
        course_title: courseMap.get(t.task?.course_id) || '',
        start_at: t.task?.start_at || '',
        due_at: t.task?.due_at || '',
        status: t.task?.status || 'active',
        rate: Math.round((t.completion_rate || 0) * 100) / 100,
        assigned: t.assignment_count || 0,
        completed: t.completed_count || 0,
      }))
    } finally {
      loading.value = false
    }
  }

  async function createTask(task: any, learnerIds: string[]) {
    try {
      await api.tasks.create({ task, learner_ids: learnerIds })
      return { success: true }
    } catch (err: any) {
      return { success: false, error: err?.message || '创建失败' }
    }
  }

  async function loadLearners() {
    loading.value = true
    try {
      learners.value = await api.admin.learners()
    } finally {
      loading.value = false
    }
  }

  async function loadLearnerDetail(id: string) {
    loadingDetail.value = true
    try {
      learnerDetail.value = await api.admin.learnerDetail(id)
    } finally {
      loadingDetail.value = false
    }
  }

  async function loadEvents(learnerId?: string) {
    loading.value = true
    try {
      const res = await api.admin.events({ learner_id: learnerId })
      const arr = Array.isArray(res)
        ? res
        : res && Array.isArray((res as any).items)
          ? (res as any).items
          : []
      events.value = arr
    } finally {
      loading.value = false
    }
  }

  // 返回导出 CSV 的 URL（带 /api 前缀，需 fetch + Authorization 下载）
  function exportCSV(type: 'events' | 'progress' | 'assignments'): string {
    return api.admin.exportCSV(type)
  }

  return {
    learners,
    tasks,
    events,
    dashboard,
    learnerDetail,
    loading,
    loadingDetail,
    stats,
    taskDistribution,
    loadDashboard,
    loadTasks,
    createTask,
    loadLearners,
    loadLearnerDetail,
    loadEvents,
    exportCSV,
  }
})
