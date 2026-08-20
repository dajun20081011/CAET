<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'

const route = useRoute()
const router = useRouter()

const adminStore = useAdminStore()
const learnerId = computed(() => route.params.learnerId as string)

const loading = computed(() => adminStore.loadingDetail)
const detail = computed(() => adminStore.learnerDetail)

const profile = computed<any | null>(() => detail.value?.profile || null)
const notFound = computed(() => !loading.value && !profile.value)

const learner = computed(() => {
  const p = profile.value
  if (!p) return null
  const totalSeconds = p.total_seconds ?? 0
  return {
    display_name: p.display_name || '未知学员',
    employee_no: p.employee_no || '—',
    group_id: p.group_id ?? null,
    group_name: p.group_name || '',
    completion_rate: Math.round(p.avg_progress ?? p.completion_rate ?? 0),
    total_hours: p.total_hours ?? Math.round((totalSeconds / 360) * 10) / 10,
    active_days: p.active_days ?? 0,
  }
})

function groupName(id: string | null, fallbackName?: string) {
  if (fallbackName) return fallbackName
  return id ? '分组 ' + id : '未分组'
}

const taskProgress = computed(() => {
  const list = detail.value?.assignments || []
  return list.map((a: any) => ({
    title: a.title || a.task_title || '未命名任务',
    rate: Math.round(a.progress_percent ?? a.rate ?? 0),
  }))
})

// 学习时长趋势 (7 天，可能为 number[] 或 [{date,hours}] )
const weeklyHours = computed<number[]>(() => {
  const trend = detail.value?.duration_trend
  if (!Array.isArray(trend) || !trend.length) return []
  if (typeof trend[0] === 'number') return trend as number[]
  return trend.map((d: any) => Number(d.hours ?? d.value ?? 0))
})

const lineW = 560
const lineH = 140
const linePadY = 14
const linePoints = computed(() => {
  const vals = weeklyHours.value
  if (!vals.length) return []
  const max = Math.max(...vals, 1)
  const range = max || 1
  const stepX = lineW / (vals.length - 1)
  return vals.map((v, i) => ({
    x: i * stepX,
    y: lineH - linePadY - (v / range) * (lineH - linePadY * 2),
    v,
  }))
})
const linePath = computed(() => linePoints.value.map((p) => `${p.x},${p.y}`).join(' '))
const lineArea = computed(() => {
  const pts = linePoints.value
  if (!pts.length) return ''
  return `0,${lineH} ${pts.map((p) => `${p.x},${p.y}`).join(' ')} ${lineW},${lineH}`
})

function rateBarClass(rate: number) {
  if (rate >= 80) return 'bg-success'
  if (rate >= 50) return 'bg-warning'
  return 'bg-danger'
}

const events = computed(() => {
  const list = detail.value?.events || []
  return list.map((e: any) => {
    const rawTime = e.client_timestamp || e.created_at || e.time || ''
    return {
      type: e.event_type || e.type || '',
      content: e.content || e.event_value?.content || e.detail || e.course_title || '',
      time: String(rawTime).replace('T', ' ').slice(0, 16),
    }
  })
})

const eventMeta: Record<string, { label: string; cls: string }> = {
  answer_submit: { label: '答题提交', cls: 'bg-primary-soft text-primary' },
  weekly_test_submit: { label: '周测提交', cls: 'bg-green-50 text-green-700' },
  recording_complete: { label: '录音完成', cls: 'bg-blue-50 text-blue-700' },
  recording_start: { label: '开始录音', cls: 'bg-blue-50 text-blue-700' },
  audio_standard_play: { label: '标准音', cls: 'bg-gray-100 text-gray-600' },
  audio_slow_play: { label: '慢速音', cls: 'bg-gray-100 text-gray-600' },
  speech_transcription: { label: '语音转写', cls: 'bg-blue-50 text-blue-700' },
  copy: { label: '复制', cls: 'bg-gray-100 text-gray-600' },
  eudic_lookup: { label: '查词', cls: 'bg-amber-50 text-amber-700' },
  favorite_word: { label: '收藏', cls: 'bg-green-50 text-green-700' },
  learning_heartbeat: { label: '学习心跳', cls: 'bg-gray-100 text-gray-600' },
}
function evMeta(t: string) {
  return eventMeta[t] || eventMeta.learning_heartbeat
}

function back() {
  router.push('/admin/learners')
}

onMounted(async () => {
  await adminStore.loadLearnerDetail(learnerId.value)
})
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-5">
    <!-- Back -->
    <button @click="back" class="inline-flex items-center gap-1.5 text-sm text-text-secondary hover:text-text">
      <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" /></svg>
      返回学员列表
    </button>

    <!-- Loading -->
    <div v-if="loading" class="card p-10 flex items-center justify-center text-text-secondary">
      <svg class="w-5 h-5 animate-spin mr-2" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" /></svg>
      加载中…
    </div>

    <!-- Not found -->
    <div v-else-if="notFound" class="card p-10 text-center text-text-secondary">未找到该学员</div>

    <template v-else-if="learner">
      <!-- Header -->
      <div class="card p-6">
        <div class="flex items-center gap-5">
          <div class="w-16 h-16 rounded-full bg-primary-soft text-primary flex items-center justify-center text-2xl font-semibold shrink-0">
            {{ (learner.display_name || '?')[0] }}
          </div>
          <div class="flex-1">
            <div class="flex items-center gap-3">
              <h2 class="text-xl font-semibold text-text">{{ learner.display_name }}</h2>
              <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs">{{ groupName(learner.group_id, learner.group_name) }}</span>
            </div>
            <div class="text-sm text-text-secondary mt-1">工号 {{ learner.employee_no }}</div>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-4 mt-6">
          <div class="text-center p-3 rounded-lg bg-gray-50">
            <div class="text-2xl font-semibold text-primary">{{ learner.completion_rate }}%</div>
            <div class="text-xs text-text-secondary mt-1">总体完成率</div>
          </div>
          <div class="text-center p-3 rounded-lg bg-gray-50">
            <div class="text-2xl font-semibold text-text">{{ learner.total_hours }}<span class="text-base font-normal text-text-secondary">h</span></div>
            <div class="text-xs text-text-secondary mt-1">累计学习时长</div>
          </div>
          <div class="text-center p-3 rounded-lg bg-gray-50">
            <div class="text-2xl font-semibold text-text">{{ learner.active_days }}</div>
            <div class="text-xs text-text-secondary mt-1">活跃天数</div>
          </div>
        </div>
      </div>

      <!-- Task progress -->
      <div class="card p-6">
        <h3 class="text-base font-semibold text-text mb-4">最近任务进度</h3>
        <div class="space-y-4">
          <div v-for="(p, i) in taskProgress" :key="i">
            <div class="flex items-center justify-between text-sm mb-1.5">
              <span class="text-text font-medium">{{ p.title }}</span>
              <span class="text-text-secondary">{{ p.rate }}%</span>
            </div>
            <div class="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div class="h-full rounded-full transition-all" :class="rateBarClass(p.rate)" :style="{ width: p.rate + '%' }"></div>
            </div>
          </div>
          <div v-if="!taskProgress.length" class="text-sm text-text-secondary">暂无任务进度</div>
        </div>
      </div>

      <!-- Study trend -->
      <div class="card p-6">
        <h3 class="text-base font-semibold text-text mb-4">学习时长趋势（近 7 天）</h3>
        <svg :viewBox="`0 0 ${lineW} ${lineH}`" class="w-full h-36" preserveAspectRatio="none">
          <polygon :points="lineArea" fill="#7C3AED" fill-opacity="0.08" />
          <polyline :points="linePath" fill="none" stroke="#7C3AED" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" />
          <circle v-for="(p, i) in linePoints" :key="i" :cx="p.x" :cy="p.y" r="3.5" fill="#fff" stroke="#7C3AED" stroke-width="2" vector-effect="non-scaling-stroke" />
        </svg>
        <div class="flex justify-between mt-2 text-xs text-text-secondary">
          <span v-for="(_p, i) in linePoints" :key="i">D{{ i + 1 }}</span>
        </div>
        <div class="flex justify-between mt-1 text-xs font-medium text-text">
          <span v-for="(p, i) in linePoints" :key="i">{{ p.v }}h</span>
        </div>
      </div>

      <!-- Events -->
      <div class="card p-6">
        <h3 class="text-base font-semibold text-text mb-4">学习事件明细</h3>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-text-secondary border-b border-gray-100">
                <th class="py-3 pr-4 font-medium">类型</th>
                <th class="py-3 pr-4 font-medium">内容</th>
                <th class="py-3 font-medium">时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(e, i) in events" :key="i" class="border-b border-gray-50 hover:bg-gray-50/60 transition-colors">
                <td class="py-3 pr-4">
                  <span class="px-2 py-0.5 rounded-full text-xs" :class="evMeta(e.type).cls">{{ evMeta(e.type).label }}</span>
                </td>
                <td class="py-3 pr-4 text-text">{{ e.content }}</td>
                <td class="py-3 text-text-secondary">{{ e.time }}</td>
              </tr>
              <tr v-if="!events.length">
                <td colspan="3" class="py-8 text-center text-text-secondary">暂无学习事件</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
