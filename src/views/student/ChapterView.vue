<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLearningStore } from '@/stores/learning'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const learningStore = useLearningStore()
const authStore = useAuthStore()

const courseId = computed(() => route.params.courseId as string)
const chapter = computed(() => Number(route.params.chapter) || 1)

interface DayItem {
  day: number
  title: string
  status: 'locked' | 'available' | 'completed'
  isQuiz: boolean
}

interface ChapterVM {
  courseId: string
  courseTitle: string
  chapterTitle: string
  description: string
  progress: number
  dayCount: number
}

const loading = ref(false)
const error = ref('')

const chapterData = ref<ChapterVM>({
  courseId: '',
  courseTitle: '',
  chapterTitle: '',
  description: '',
  progress: 0,
  dayCount: 7,
})

const days = computed<DayItem[]>(() => {
  const total = chapterData.value.dayCount
  const completedDays = Math.floor((chapterData.value.progress / 100) * (total - 1))
  const result: DayItem[] = []
  for (let i = 1; i <= total; i++) {
    const isQuiz = i === total
    let status: DayItem['status']
    if (i <= completedDays) status = 'completed'
    else if (i === completedDays + 1) status = 'available'
    else status = 'locked'
    result.push({ day: i, title: isQuiz ? '周测 Quiz' : `Day ${i}`, status, isQuiz })
  }
  return result
})

function dayRoute(day: DayItem) {
  const base = `/student/course/${chapterData.value.courseId}/chapter/${chapter.value}/day/${day.day}`
  return day.isQuiz ? `${base}/weekly-test` : base
}

function goDay(day: DayItem) {
  if (day.status === 'locked') return
  router.push(dayRoute(day))
}

function loadChapter() {
  const course = learningStore.courses.find((c) => c.id === courseId.value)
  if (course) {
    chapterData.value = {
      courseId: course.id,
      courseTitle: course.title,
      chapterTitle: `第 ${chapter.value} 章`,
      description: course.description || '完成本单元每日训练与周末周测。',
      progress: 0,
      dayCount: 7,
    }
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
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
    loadChapter()
  }
})
</script>

<template>
  <div class="min-h-[100dvh] bg-background pb-24">
    <!-- Top bar -->
    <div class="flex items-center gap-3 px-5 pt-12 pb-4">
      <button @click="router.back()" class="w-9 h-9 rounded-full bg-white shadow-sm flex items-center justify-center touch-target">
        <svg class="w-5 h-5 text-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>
      <div class="min-w-0">
        <h1 class="text-base font-semibold text-text truncate">{{ chapterData.courseTitle }}</h1>
        <p class="text-xs text-text-secondary">章节概览</p>
      </div>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
    </div>
    <div v-else-if="error" class="px-5">
      <div class="card p-6 text-center text-sm text-danger">{{ error }}</div>
    </div>
    <template v-else>
    <!-- Hero placeholder -->
    <div class="px-5">
      <div class="relative h-40 rounded-2xl bg-gradient-to-br from-primary to-primary-dark overflow-hidden flex items-center justify-center">
        <div class="absolute inset-0 opacity-20" style="background-image:radial-gradient(circle at 20% 20%, #fff 1px, transparent 1px); background-size: 18px 18px;"></div>
        <svg class="w-16 h-16 text-white/90" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 6.25278V19.2528M12 6.25278C10.8321 5.47686 9.24649 5 7.5 5C5.75351 5 4.16789 5.47686 3 6.25278V19.2528C4.16789 18.4769 5.75351 18 7.5 18C9.24649 18 10.8321 18.4769 12 19.2528C13.1679 18.4769 14.7535 18 16.5 18C18.2465 18 19.8321 18.4769 21 19.2528V6.25278C19.8321 5.47686 18.2465 5 16.5 5C14.7535 5 13.1679 5.47686 12 6.25278Z" />
        </svg>
        <span class="absolute bottom-3 right-4 text-white/80 text-xs font-medium">Chapter {{ chapter }}</span>
      </div>
    </div>

    <div class="px-5 mt-5">
      <!-- Chapter info -->
      <section class="card p-5">
        <h2 class="text-lg font-bold text-text">{{ chapterData.chapterTitle }}</h2>
        <p class="text-sm text-text-secondary mt-2 leading-relaxed">{{ chapterData.description }}</p>

        <div class="mt-4">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-xs text-text-secondary">本章进度</span>
            <span class="text-xs font-medium text-primary">{{ chapterData.progress }}%</span>
          </div>
          <div class="h-2.5 rounded-full bg-gray-100 overflow-hidden">
            <div class="h-full rounded-full bg-primary transition-all" :style="{ width: chapterData.progress + '%' }"></div>
          </div>
        </div>
      </section>

      <!-- Day list -->
      <section class="mt-6">
        <h3 class="text-base font-semibold text-text mb-3">训练日程</h3>
        <ul class="space-y-2.5">
          <li
            v-for="day in days"
            :key="day.day"
            @click="goDay(day)"
            class="card px-4 py-3.5 flex items-center gap-3 transition-transform active:scale-[0.98]"
            :class="day.status === 'locked' ? 'opacity-50' : 'cursor-pointer'"
          >
            <div class="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
              :class="day.status === 'completed' ? 'bg-success/10 text-success'
                : day.status === 'available' ? 'bg-primary-soft text-primary'
                : 'bg-gray-100 text-text-secondary'"
            >
              <svg v-if="day.status === 'completed'" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
              </svg>
              <svg v-else-if="day.isQuiz" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <span v-else class="text-sm font-bold">{{ day.day }}</span>
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium text-text">{{ day.title }}</p>
              <p class="text-[11px]"
                :class="day.status === 'completed' ? 'text-success' : day.status === 'available' ? 'text-primary' : 'text-text-secondary'"
              >
                {{ day.isQuiz ? '综合周测' : '跟读与听力训练' }} ·
                {{ day.status === 'completed' ? '已完成' : day.status === 'available' ? '可学习' : '未解锁' }}
              </p>
            </div>
            <svg class="w-5 h-5 text-text-secondary" :class="day.status === 'locked' ? 'opacity-40' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
            </svg>
          </li>
        </ul>
      </section>
    </div>
    </template>
  </div>
</template>
