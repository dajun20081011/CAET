<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useLearningStore } from '@/stores/learning'
import { eventLabel, eventColor } from '@/lib/eventMeta'

const router = useRouter()
const learningStore = useLearningStore()

const loading = ref(false)
const error = ref('')

interface RecentItem {
  name: string
  date: string
  duration: string
  progress: number
}

interface EventStat {
  key: string
  label: string
  count: number
  color: string
}

const colorClass: Record<string, string> = {
  primary: 'text-primary',
  success: 'text-success',
  info: 'text-info',
  warning: 'text-warning',
  gray: 'text-text-secondary',
}

const weekStats = computed(() => {
  const stats = learningStore.record?.stats || {}
  const hours = Math.round((stats_value(stats.total_effective_seconds) / 360) * 10) / 10
  return {
    duration: String(hours),
    sentences: stats.completed_contents || 0,
    readings: stats.total_events || 0,
    accuracy: stats.task_completion_rate || 0,
  }
})
function stats_value(v: any): number {
  const n = Number(v)
  return isNaN(n) ? 0 : n
}

const recent = computed<RecentItem[]>(() => {
  const list = learningStore.record?.recent_content || []
  return list.map((c: any) => ({
    name: `${c.chapter_title || '课程'}${c.day_no ? ' · Day ' + c.day_no : ''}`,
    date: formatDateTime(c.updated_at),
    duration: `${Math.max(1, Math.round((c.effective_seconds || 0) / 60))} 分钟`,
    progress: c.completed ? 100 : 0,
  }))
})

const eventStats = computed<EventStat[]>(() => {
  const list = learningStore.record?.event_distribution || []
  return list.map((e: any) => ({
    key: e.event_type,
    label: eventLabel(e.event_type),
    count: e.count || 0,
    color: colorClass[eventColor(e.event_type)] || 'text-text-secondary',
  }))
})

// 7 天学习日历（来自后端最近 7 天事件统计）
const weekDays = computed(() => {
  const cal = learningStore.record?.calendar_7d || []
  const labels = ['日', '一', '二', '三', '四', '五', '六']
  const today = new Date()
  return cal.map((d: any) => {
    const dt = d.date ? new Date(d.date) : null
    return {
      label: dt ? labels[dt.getDay()] : '',
      studied: (d.count || 0) > 0,
      isToday: dt ? dt.toDateString() === today.toDateString() : false,
    }
  })
})

const hasData = computed(() => !!learningStore.record)

function formatDateTime(s?: string): string {
  if (!s) return ''
  const d = new Date(s)
  if (isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    await learningStore.loadRecord()
  } catch (e: any) {
    error.value = e?.message || '学习记录加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="min-h-[100dvh] bg-background pb-24">
    <!-- Header -->
    <header class="bg-primary px-5 pt-12 pb-6 rounded-b-3xl">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-white text-xl font-bold">学习记录</h1>
          <p class="text-white/70 text-sm mt-0.5">坚持，是最好的捷径</p>
        </div>
        <button @click="router.push('/student/tasks')" class="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center touch-target">
          <svg class="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        </button>
      </div>
    </header>

    <div v-if="loading" class="px-5 mt-10 flex items-center justify-center py-20">
      <div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
    </div>
    <div v-else-if="error" class="px-5 mt-10">
      <div class="card p-6 text-center text-sm text-danger">{{ error }}</div>
    </div>
    <div v-else-if="!hasData" class="px-5 mt-10">
      <div class="card p-8 text-center text-text-secondary text-sm">暂无学习记录</div>
    </div>
    <template v-else>
      <div class="px-5 -mt-3 space-y-5">
        <!-- 学习日历 -->
        <section class="card p-5">
          <h2 class="text-sm font-semibold text-text mb-3">学习日历</h2>
          <div class="grid grid-cols-7 gap-2">
            <div v-for="d in weekDays" :key="d.label" class="flex flex-col items-center gap-1.5">
              <span class="text-[11px] text-text-secondary">周{{ d.label }}</span>
              <div
                class="w-9 h-9 rounded-full flex items-center justify-center"
                :class="d.studied ? 'bg-primary text-white' : 'bg-gray-100 text-text-secondary'"
                :style="d.isToday ? 'box-shadow:0 0 0 2px #7C3AED33' : ''"
              >
                <svg v-if="d.studied" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
                </svg>
                <span v-else class="text-xs">·</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 本周学习数据 -->
        <section>
          <h2 class="text-sm font-semibold text-text mb-3">本周学习数据</h2>
          <div class="grid grid-cols-2 gap-3">
            <div class="card p-4">
              <p class="text-xs text-text-secondary">学习时长</p>
              <p class="text-2xl font-bold text-primary mt-1">{{ weekStats.duration }}<span class="text-sm font-normal text-text-secondary ml-1">小时</span></p>
            </div>
            <div class="card p-4">
              <p class="text-xs text-text-secondary">学习句数</p>
              <p class="text-2xl font-bold text-info mt-1">{{ weekStats.sentences }}<span class="text-sm font-normal text-text-secondary ml-1">句</span></p>
            </div>
            <div class="card p-4">
              <p class="text-xs text-text-secondary">跟读练习</p>
              <p class="text-2xl font-bold text-success mt-1">{{ weekStats.readings }}<span class="text-sm font-normal text-text-secondary ml-1">次</span></p>
            </div>
            <div class="card p-4">
              <p class="text-xs text-text-secondary">正确率</p>
              <p class="text-2xl font-bold text-warning mt-1">{{ weekStats.accuracy }}<span class="text-sm font-normal text-text-secondary ml-1">%</span></p>
            </div>
          </div>
        </section>

        <!-- 最近学习 -->
        <section>
          <h2 class="text-sm font-semibold text-text mb-3">最近学习</h2>
          <ul class="space-y-2.5">
            <li
              v-for="(item, i) in recent"
              :key="i"
              class="card px-4 py-3 flex items-center gap-3"
            >
              <div class="w-10 h-10 rounded-full bg-primary-soft text-primary flex items-center justify-center shrink-0">
                <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.25278V19.2528M12 6.25278C10.8321 5.47686 9.24649 5 7.5 5C5.75351 5 4.16789 5.47686 3 6.25278V19.2528C4.16789 18.4769 5.75351 18 7.5 18C9.24649 18 10.8321 18.4769 12 19.2528C13.1679 18.4769 14.7535 18 16.5 18C18.2465 18 19.8321 18.4769 21 19.2528V6.25278C19.8321 5.47686 18.2465 5 16.5 5C14.7535 5 13.1679 5.47686 12 6.25278Z" />
                </svg>
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-text truncate">{{ item.name }}</p>
                <p class="text-[11px] text-text-secondary mt-0.5">{{ item.date }} · {{ item.duration }}</p>
              </div>
              <div class="flex items-center gap-2 w-20">
                <div class="flex-1 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                  <div class="h-full rounded-full bg-primary" :style="{ width: item.progress + '%' }"></div>
                </div>
                <span class="text-[11px] text-text-secondary w-7 text-right">{{ item.progress }}%</span>
              </div>
            </li>
          </ul>
        </section>

        <!-- 学习事件统计 -->
        <section class="pb-2">
          <h2 class="text-sm font-semibold text-text mb-3">学习事件统计</h2>
          <div class="card p-4">
            <div class="grid grid-cols-2 gap-3">
              <div v-for="s in eventStats" :key="s.key" class="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2.5">
                <span class="text-xs text-text-secondary">{{ s.label }}</span>
                <span class="text-base font-bold" :class="s.color">{{ s.count }}</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>
