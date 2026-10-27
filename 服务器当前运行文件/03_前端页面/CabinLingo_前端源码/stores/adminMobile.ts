import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  cabinlingoApi,
  type AdminLearnerBroadcastItem,
  type DashboardSummary,
  type InstructorQueueItem,
  type LearnerTask,
  type ReviewQueueItem,
  type TaskRoster,
  type TaskListItem,
  type UserSummary,
} from '@/api'

export interface MobileReviewItem {
  key: string
  assignmentId: string
  taskId: string
  taskTitle: string
  learnerId: string
  learnerName: string
  className: string
  submittedAt: string | null
  aiStatus: string
  reviewType: 'practice' | 'exam' | null
  targetId: string | null
  priority: 'normal' | 'overdue' | 'retraining'
}

const emptySummary = (): DashboardSummary => ({
  task_count: 0,
  practice_count: 0,
  exam_count: 0,
  published_count: 0,
  assignment_count: 0,
  completed_count: 0,
  completion_rate: 0,
})

export const useAdminMobileStore = defineStore('admin-mobile', () => {
  const summary = ref<DashboardSummary>(emptySummary())
  const tasks = ref<TaskListItem[]>([])
  const users = ref<UserSummary[]>([])
  const legacyReviews = ref<ReviewQueueItem[]>([])
  const instructorReviews = ref<InstructorQueueItem[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref('')
  const reviewAvailable = ref(true)
  const learnerTasksByUser = ref<Record<string, LearnerTask[]>>({})
  const learnerTasksLoading = ref<Record<string, boolean>>({})
  const learnerTasksError = ref<Record<string, string>>({})
  const learnerBroadcastsByUser = ref<Record<string, AdminLearnerBroadcastItem[]>>({})
  const learnerBroadcastsLoading = ref<Record<string, boolean>>({})
  const learnerBroadcastsError = ref<Record<string, string>>({})
  const taskRosters = ref<Record<string, TaskRoster>>({})
  const taskRosterLoading = ref<Record<string, boolean>>({})
  const taskRosterError = ref<Record<string, string>>({})

  const learnerUsers = computed(() => users.value.filter((user) => user.roles.includes('learner')))
  const activeTasks = computed(() => tasks.value.filter((task) => ['published', 'open'].includes(task.status)))
  const reviews = computed<MobileReviewItem[]>(() => {
    if (instructorReviews.value.length) {
      return instructorReviews.value.map((item) => ({
        key: `${item.review_type}:${item.target_id}`,
        assignmentId: item.assignment_id,
        taskId: item.task_id,
        taskTitle: item.content_title || item.task_title,
        learnerId: item.learner_id,
        learnerName: item.learner_name,
        className: item.class_name || '未分组',
        submittedAt: item.submitted_at,
        aiStatus: item.ai_status,
        reviewType: item.review_type,
        targetId: item.target_id,
        priority: item.priority,
      }))
    }
    const userById = new Map(users.value.map((user) => [user.id, user]))
    const taskById = new Map(tasks.value.map((task) => [task.id, task]))
    return legacyReviews.value.map((item) => ({
      key: item.assignment_id,
      assignmentId: item.assignment_id,
      taskId: item.task_id,
      taskTitle: taskById.get(item.task_id)?.title || '训练任务',
      learnerId: item.user_id,
      learnerName: userById.get(item.user_id)?.display_name || '学员',
      className: '未分组',
      submittedAt: item.submitted_at,
      aiStatus: item.ai_status,
      reviewType: null,
      targetId: null,
      priority: item.ai_status && item.ai_status !== 'completed' ? 'overdue' : 'normal',
    }))
  })

  const totalAssignments = computed(() => summary.value.assignment_count)
  const submittedCount = computed(() => Math.min(summary.value.completed_count, totalAssignments.value))
  const pendingReviewCount = computed(() => new Set(reviews.value.map((item) => item.assignmentId)).size)
  const passedCount = computed(() => Math.max(submittedCount.value - pendingReviewCount.value, 0))
  const notPassedCount = computed(() => Math.max(totalAssignments.value - submittedCount.value, 0))
  const finalPassRate = computed(() => totalAssignments.value
    ? Math.round((passedCount.value / totalAssignments.value) * 100)
    : 0)
  const submissionRate = computed(() => totalAssignments.value
    ? Math.round((submittedCount.value / totalAssignments.value) * 100)
    : 0)

  async function refresh() {
    if (loading.value) return
    loading.value = true
    error.value = ''
    const [dashboardResult, taskResult, userResult, legacyResult, instructorResult] = await Promise.allSettled([
      cabinlingoApi.dashboard(),
      cabinlingoApi.tasks(),
      cabinlingoApi.users(),
      cabinlingoApi.reviewQueue(),
      cabinlingoApi.instructorQueue({ review_status: 'pending' }),
    ])
    if (dashboardResult.status === 'fulfilled') summary.value = dashboardResult.value
    if (taskResult.status === 'fulfilled') tasks.value = taskResult.value
    if (userResult.status === 'fulfilled') users.value = userResult.value
    if (legacyResult.status === 'fulfilled') legacyReviews.value = legacyResult.value
    if (instructorResult.status === 'fulfilled') instructorReviews.value = instructorResult.value
    reviewAvailable.value = legacyResult.status === 'fulfilled' || instructorResult.status === 'fulfilled'
    if ([dashboardResult, taskResult, userResult].some((result) => result.status === 'rejected')) {
      error.value = '部分管理数据暂时无法读取，当前筛选条件已保留。'
    }
    if (taskResult.status === 'fulfilled') {
      await Promise.all(activeTasks.value.map((task) => loadTaskRoster(task)))
    }
    loaded.value = true
    loading.value = false
  }

  async function changeTaskStatus(task: TaskListItem, action: 'publish' | 'close') {
    await cabinlingoApi.updateTaskStatus(task.task_type, task.id, action)
    await refreshAfterMutation()
  }

  async function loadLearnerTasks(userId: string, force = false) {
    if (learnerTasksLoading.value[userId]) return
    if (!force && Object.prototype.hasOwnProperty.call(learnerTasksByUser.value, userId)) return
    learnerTasksLoading.value = { ...learnerTasksLoading.value, [userId]: true }
    learnerTasksError.value = { ...learnerTasksError.value, [userId]: '' }
    try {
      const items = await cabinlingoApi.adminLearnerTasks(userId)
      learnerTasksByUser.value = { ...learnerTasksByUser.value, [userId]: items }
    } catch {
      learnerTasksError.value = { ...learnerTasksError.value, [userId]: '学员进度暂时无法读取，请检查权限或网络后重试。' }
    } finally {
      learnerTasksLoading.value = { ...learnerTasksLoading.value, [userId]: false }
    }
  }

  async function loadLearnerBroadcasts(userId: string, force = false) {
    if (learnerBroadcastsLoading.value[userId]) return
    if (!force && Object.prototype.hasOwnProperty.call(learnerBroadcastsByUser.value, userId)) return
    learnerBroadcastsLoading.value = { ...learnerBroadcastsLoading.value, [userId]: true }
    learnerBroadcastsError.value = { ...learnerBroadcastsError.value, [userId]: '' }
    try {
      const items = await cabinlingoApi.adminLearnerBroadcastProgress(userId)
      learnerBroadcastsByUser.value = { ...learnerBroadcastsByUser.value, [userId]: items }
    } catch {
      learnerBroadcastsError.value = { ...learnerBroadcastsError.value, [userId]: '广播词完成明细暂时无法读取，请检查权限或网络后重试。' }
    } finally {
      learnerBroadcastsLoading.value = { ...learnerBroadcastsLoading.value, [userId]: false }
    }
  }

  async function loadTaskRoster(task: TaskListItem, force = false) {
    const key = `${task.task_type}:${task.id}`
    if (taskRosterLoading.value[key]) return
    if (!force && Object.prototype.hasOwnProperty.call(taskRosters.value, key)) return
    taskRosterLoading.value = { ...taskRosterLoading.value, [key]: true }
    taskRosterError.value = { ...taskRosterError.value, [key]: '' }
    try {
      const roster = await cabinlingoApi.adminTaskRoster(task.task_type, task.id)
      taskRosters.value = { ...taskRosters.value, [key]: roster }
    } catch {
      taskRosterError.value = { ...taskRosterError.value, [key]: '任务人员名单暂时无法读取，请检查权限或网络后重试。' }
    } finally {
      taskRosterLoading.value = { ...taskRosterLoading.value, [key]: false }
    }
  }

  async function refreshAfterMutation() {
    loaded.value = false
    await refresh()
  }

  return {
    summary,
    tasks,
    users,
    reviews,
    learnerUsers,
    activeTasks,
    loading,
    loaded,
    error,
    reviewAvailable,
    learnerTasksByUser,
    learnerTasksLoading,
    learnerTasksError,
    learnerBroadcastsByUser,
    learnerBroadcastsLoading,
    learnerBroadcastsError,
    taskRosters,
    taskRosterLoading,
    taskRosterError,
    totalAssignments,
    submittedCount,
    pendingReviewCount,
    passedCount,
    notPassedCount,
    finalPassRate,
    submissionRate,
    refresh,
    changeTaskStatus,
    loadLearnerTasks,
    loadLearnerBroadcasts,
    loadTaskRoster,
    refreshAfterMutation,
  }
})
