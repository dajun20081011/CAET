<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useLearningStore } from '@/stores/learning'
import { useAuthStore } from '@/stores/auth'
import type { AssignmentStatus } from '@/types/database'

const router = useRouter()
const learningStore = useLearningStore()
const authStore = useAuthStore()

const quote = 'Practice makes progress.'
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
})
const userName = computed(() => authStore.user?.display_name || '同学')

interface TaskCard {
  id: string
  taskId: string
  courseId: string
  title: string
  courseTitle: string
  chapterInfo: string
  progress: number
  status: AssignmentStatus
  dueAt: string
}

const tasks = ref<TaskCard[]>([])
const loading = ref(false)
const error = ref('')

const stats = computed(() => {
  const completed = tasks.value.filter((t) => t.status === 'completed').length
  return [
    { key: 'time', label: '学习时长', value: '12.5', unit: '小时', color: 'text-primary' },
    { key: 'courses', label: '完成课程', value: String(completed || 3), unit: '门', color: 'text-success' },
    { key: 'accuracy', label: '正确率', value: '86', unit: '%', color: 'text-info' },
    { key: 'streak', label: '连续天数', value: '7', unit: '天', color: 'text-warning' },
  ]
})

function statusMeta(status: AssignmentStatus) {
  switch (status) {
    case 'completed':
      return { label: '已完成', cls: 'bg-success/10 text-success' }
    case 'in_progress':
      return { label: '进行中', cls: 'bg-warning/10 text-warning' }
    case 'overdue':
      return { label: '已逾期', cls: 'bg-danger/10 text-danger' }
    default:
      return { label: '未开始', cls: 'bg-gray-100 text-text-secondary' }
  }
}

function formatDue(dueAt: string): string {
  const due = new Date(dueAt)
  const now = new Date()
  const diff = Math.ceil((due.getTime() - now.setHours(0, 0, 0, 0)) / 86400000)
  if (diff < 0) return '已逾期'
  if (diff === 0) return '今天截止'
  if (diff === 1) return '明天截止'
  return `${diff}天后截止`
}

function buildTasks() {
  const storeTasks = learningStore.myTasks
  tasks.value = storeTasks.map((t) => {
    const assign = learningStore.assignments.find((a) => a.task_id === t.id)
    const course = learningStore.courses.find((c) => c.id === t.course_id)
    return {
      id: assign?.id || t.id,
      taskId: t.id,
      courseId: t.course_id,
      title: t.title,
      courseTitle: course?.title || '课程',
      chapterInfo: `第 ${t.chapter_from}-${t.chapter_to} 章 · 第 ${t.day_from}-${t.day_to} 天`,
      progress: assign?.progress_percent || 0,
      status: (assign?.status || 'not_started') as AssignmentStatus,
      dueAt: t.due_at,
    }
  })
}

function goDetail(task: TaskCard) {
  router.push(`/student/tasks/${task.taskId}`)
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
    buildTasks()
  }
})
</script>

<template>
  <div class="min-h-[100dvh] bg-background pb-24">
    <!-- Header -->
    <header class="bg-primary px-5 pt-12 pb-6 rounded-b-3xl">
      <div class="flex items-center justify-between">
        <div>
          <p class="text-white/70 text-sm">{{ greeting }}，</p>
          <h1 class="text-white text-xl font-bold">{{ userName }}</h1>
        </div>
        <div class="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center text-white font-semibold">
          {{ userName.charAt(0) }}
        </div>
      </div>
      <div class="mt-4 bg-white/15 rounded-xl px-4 py-3">
        <p class="text-white/90 text-sm italic">"{{ quote }}"</p>
      </div>
    </header>

    <div class="px-5 -mt-3">
      <!-- Stats -->
      <section class="grid grid-cols-2 gap-3">
        <div v-for="s in stats" :key="s.key" class="card p-4 flex flex-col">
          <span class="text-text-secondary text-xs">{{ s.label }}</span>
          <div class="mt-1 flex items-baseline gap-1">
            <span class="text-2xl font-bold" :class="s.color">{{ s.value }}</span>
            <span class="text-xs text-text-secondary">{{ s.unit }}</span>
          </div>
        </div>
      </section>

      <!-- This week tasks -->
      <section class="mt-7">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-base font-semibold text-text">本周任务</h2>
          <span class="text-xs text-text-secondary">{{ tasks.length }} 项</span>
        </div>

        <div v-if="loading" class="flex items-center justify-center py-10">
          <div class="w-7 h-7 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
        </div>
        <div v-else-if="error" class="card p-6 text-center text-sm text-danger">{{ error }}</div>
        <div v-else-if="tasks.length === 0" class="card p-8 text-center text-text-secondary text-sm">
          暂无任务，好好放松一下吧～
        </div>

        <ul class="space-y-3">
          <li
            v-for="task in tasks"
            :key="task.id"
            @click="goDetail(task)"
            class="card p-4 active:scale-[0.98] transition-transform cursor-pointer"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="text-xs text-primary font-medium">{{ task.courseTitle }}</p>
                <h3 class="text-text font-semibold mt-0.5 truncate">{{ task.title }}</h3>
              </div>
              <span
                class="shrink-0 text-[11px] px-2 py-1 rounded-full font-medium"
                :class="statusMeta(task.status).cls"
              >
                {{ statusMeta(task.status).label }}
              </span>
            </div>

            <p class="text-xs text-text-secondary mt-2">{{ task.chapterInfo }}</p>

            <!-- Progress -->
            <div class="mt-3 flex items-center gap-2">
              <div class="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
                <div
                  class="h-full rounded-full bg-primary transition-all"
                  :style="{ width: task.progress + '%' }"
                ></div>
              </div>
              <span class="text-[11px] text-text-secondary w-9 text-right">{{ task.progress }}%</span>
            </div>

            <div class="mt-2 flex items-center gap-1 text-[11px] text-text-secondary">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{{ formatDue(task.dueAt) }}</span>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
