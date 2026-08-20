<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLearningStore } from '@/stores/learning'
import { useAuthStore } from '@/stores/auth'
import type { AssignmentStatus } from '@/types/database'

const route = useRoute()
const router = useRouter()
const learningStore = useLearningStore()
const authStore = useAuthStore()

const taskId = computed(() => route.params.taskId as string)

interface DayItem {
  day: number
  title: string
  status: 'locked' | 'available' | 'completed'
  isQuiz: boolean
}

interface TaskDetailVM {
  courseId: string
  courseTitle: string
  description: string
  progress: number
  status: AssignmentStatus
  chapterFrom: number
  dayCount: number
}

const loading = ref(false)
const error = ref('')
const notFound = ref(false)

const detail = ref<TaskDetailVM>({
  courseId: '',
  courseTitle: '',
  description: '',
  progress: 0,
  status: 'not_started',
  chapterFrom: 1,
  dayCount: 7,
})

const days = computed<DayItem[]>(() => {
  const total = detail.value.dayCount
  const completedDays = Math.floor((detail.value.progress / 100) * (total - 1))
  const result: DayItem[] = []
  for (let i = 1; i <= total; i++) {
    const isQuiz = i === total
    let status: DayItem['status']
    if (detail.value.status === 'completed') status = 'completed'
    else if (i <= completedDays) status = 'completed'
    else if (i === completedDays + 1) status = 'available'
    else status = 'locked'
    result.push({
      day: i,
      title: isQuiz ? '周测 Quiz' : `Day ${i}`,
      status,
      isQuiz,
    })
  }
  return result
})

const firstAvailableDay = computed(() => days.value.find((d) => d.status !== 'locked') || days.value[0])

function dayRoute(day: DayItem) {
  const base = `/student/course/${detail.value.courseId}/chapter/${detail.value.chapterFrom}/day/${day.day}`
  return day.isQuiz ? `${base}/weekly-test` : base
}

function statusMeta(status: AssignmentStatus) {
  switch (status) {
    case 'completed': return { label: '已完成', cls: 'bg-success/10 text-success' }
    case 'in_progress': return { label: '进行中', cls: 'bg-warning/10 text-warning' }
    case 'overdue': return { label: '已逾期', cls: 'bg-danger/10 text-danger' }
    default: return { label: '未开始', cls: 'bg-gray-100 text-text-secondary' }
  }
}

function goDay(day: DayItem) {
  if (day.status === 'locked') return
  router.push(dayRoute(day))
}

function startLearning() {
  if (firstAvailableDay.value) router.push(dayRoute(firstAvailableDay.value))
}

function loadDetail() {
  const task = learningStore.tasks.find((t) => t.id === taskId.value)
  const assign = learningStore.assignments.find((a) => a.task_id === taskId.value)
  if (task) {
    const course = learningStore.courses.find((c) => c.id === task.course_id)
    detail.value = {
      courseId: task.course_id,
      courseTitle: course?.title || '课程',
      description: course?.description || '完成本任务中的每日训练与周末周测。',
      progress: assign?.progress_percent || 0,
      status: (assign?.status || 'not_started') as AssignmentStatus,
      chapterFrom: task.chapter_from,
      dayCount: Math.max(1, task.day_to - task.day_from + 1),
    }
  } else {
    notFound.value = true
  }
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    if (authStore.user?.id) {
      await learningStore.loadTasks(authStore.user.id)
    }
  } catch (e: any) {
    error.value = e?.message || '任务加载失败'
  } finally {
    loading.value = false
    loadDetail()
  }
})
</script>

<template>
  <div class="min-h-[100dvh] bg-background pb-28">
    <!-- Top bar -->
    <div class="flex items-center gap-3 px-5 pt-12 pb-4">
      <button @click="router.back()" class="w-9 h-9 rounded-full bg-white shadow-sm flex items-center justify-center touch-target">
        <svg class="w-5 h-5 text-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>
      <h1 class="text-base font-semibold text-text">任务详情</h1>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
    </div>
    <div v-else-if="error" class="px-5">
      <div class="card p-6 text-center text-sm text-danger">{{ error }}</div>
    </div>
    <div v-else-if="notFound" class="px-5">
      <div class="card p-8 text-center text-text-secondary text-sm">未找到该任务</div>
    </div>
    <template v-else>
    <div class="px-5">
      <!-- Course info card -->
      <section class="card p-5">
        <div class="flex items-center justify-between">
          <p class="text-xs text-primary font-medium">第 {{ detail.chapterFrom }} 章</p>
          <span class="text-[11px] px-2 py-1 rounded-full font-medium" :class="statusMeta(detail.status).cls">
            {{ statusMeta(detail.status).label }}
          </span>
        </div>
        <h2 class="text-lg font-bold text-text mt-1">{{ detail.courseTitle }}</h2>
        <p class="text-sm text-text-secondary mt-2 leading-relaxed">{{ detail.description }}</p>

        <div class="mt-4 flex items-center gap-2">
          <div class="flex-1 h-2.5 rounded-full bg-gray-100 overflow-hidden">
            <div class="h-full rounded-full bg-primary transition-all" :style="{ width: detail.progress + '%' }"></div>
          </div>
          <span class="text-xs text-text-secondary w-10 text-right">{{ detail.progress }}%</span>
        </div>
      </section>

      <!-- 7 days grid -->
      <section class="mt-6">
        <h3 class="text-base font-semibold text-text mb-3">每日训练</h3>
        <div class="grid grid-cols-2 gap-3">
          <button
            v-for="day in days"
            :key="day.day"
            @click="goDay(day)"
            :disabled="day.status === 'locked'"
            class="card p-4 flex flex-col items-start text-left transition-transform active:scale-[0.97] touch-target"
            :class="day.status === 'locked' ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'"
          >
            <div class="w-9 h-9 rounded-full flex items-center justify-center mb-2"
              :class="day.isQuiz
                ? (day.status === 'completed' ? 'bg-success/10 text-success' : day.status === 'available' ? 'bg-primary-soft text-primary' : 'bg-gray-100 text-text-secondary')
                : (day.status === 'completed' ? 'bg-success/10 text-success' : day.status === 'available' ? 'bg-primary-soft text-primary' : 'bg-gray-100 text-text-secondary')"
            >
              <svg v-if="day.status === 'completed'" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
              </svg>
              <svg v-else-if="day.isQuiz" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <span v-else class="text-sm font-bold">{{ day.day }}</span>
            </div>
            <span class="text-sm font-medium text-text">{{ day.title }}</span>
            <span class="text-[11px] mt-0.5"
              :class="day.status === 'completed' ? 'text-success'
                : day.status === 'available' ? 'text-primary'
                : 'text-text-secondary'"
            >
              {{ day.status === 'completed' ? '已完成' : day.status === 'available' ? '可学习' : '未解锁' }}
            </span>
          </button>
        </div>
      </section>
    </div>

    <!-- Start button -->
    <div class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-100 px-5 py-3 z-40">
      <div class="max-w-[420px] mx-auto">
        <button @click="startLearning" class="btn-primary w-full rounded-xl text-base">
          开始学习 · {{ firstAvailableDay?.title }}
        </button>
      </div>
    </div>
    </template>
  </div>
</template>
