<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAdminStore } from '@/stores/admin'
import { getToken } from '@/lib/api'
import { eventLabel, eventColor } from '@/lib/eventMeta'

const adminStore = useAdminStore()

// Filters
const filterLearner = ref('')
const filterType = ref('')
const filterFrom = ref('')
const filterTo = ref('')

const loading = ref(false)
const error = ref('')

interface EventRow {
  id: string | number
  learner_name: string
  employee_no: string
  event_type: string
  course_content: string
  detail: string
  time: string
}

function normalizeEvent(e: any): EventRow {
  const rawTime = e.client_timestamp || e.created_at || e.time || ''
  const time = String(rawTime).replace('T', ' ').slice(0, 16)
  let detail = ''
  if (typeof e.event_value === 'string') detail = e.event_value
  else if (e.detail) detail = String(e.detail)
  else if (e.event_value) detail = JSON.stringify(e.event_value)
  return {
    id: e.id,
    learner_name: e.display_name || e.learner_name || e.employee_no || '未知学员',
    employee_no: e.employee_no || '',
    event_type: e.event_type || '',
    course_content: e.course_title || e.content || e.course_content || '',
    detail,
    time,
  }
}

const learnerOptions = computed(() =>
  (adminStore.learners || []).map((l: any) => ({
    id: l.id,
    name: l.display_name || l.employee_no || l.id,
  }))
)

const typeOptions = [
  'answer_submit',
  'weekly_test_submit',
  'recording_complete',
  'recording_start',
  'audio_standard_play',
  'audio_slow_play',
  'speech_transcription',
  'copy',
  'eudic_lookup',
  'favorite_word',
  'learning_heartbeat',
]

// Visible count
const visibleCount = ref(10)

const filtered = computed<EventRow[]>(() => {
  const rows = (adminStore.events || []).map(normalizeEvent)
  return rows.filter((e) => {
    if (filterLearner.value && e.learner_name !== filterLearner.value) return false
    if (filterType.value && e.event_type !== filterType.value) return false
    if (filterFrom.value && e.time < filterFrom.value) return false
    if (filterTo.value && e.time > filterTo.value + ' 23:59') return false
    return true
  })
})

const visibleEvents = computed(() => filtered.value.slice(0, visibleCount.value))
const hasMore = computed(() => visibleCount.value < filtered.value.length)

function loadMore() {
  visibleCount.value += 10
}
function resetFilters() {
  filterLearner.value = ''
  filterType.value = ''
  filterFrom.value = ''
  filterTo.value = ''
  visibleCount.value = 10
}

// Badge color classes
const badgeClass: Record<string, string> = {
  primary: 'bg-primary-soft text-primary',
  success: 'bg-green-50 text-green-700',
  info: 'bg-blue-50 text-blue-700',
  warning: 'bg-amber-50 text-amber-700',
  gray: 'bg-gray-100 text-gray-600',
}
function badgeOf(type: string) {
  return badgeClass[eventColor(type)] || badgeClass.gray
}

async function exportCsv() {
  try {
    const url = adminStore.exportCSV('events')
    const token = getToken()
    const res = await fetch(url, {
      headers: token ? { Authorization: 'Bearer ' + token } : {},
    })
    if (!res.ok) throw new Error('导出失败')
    const blob = await res.blob()
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = 'learning_events.csv'
    a.click()
    URL.revokeObjectURL(blobUrl)
    return
  } catch {
    /* 服务端导出不可用时，回退到客户端导出当前筛选结果 */
  }
  const headers = ['时间', '学员', '工号', '事件类型', '课程内容', '详情']
  const rows = filtered.value.map((e) => [e.time, e.learner_name, e.employee_no, eventLabel(e.event_type), e.course_content, e.detail])
  const csv = [headers, ...rows]
    .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'learning_events.csv'
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([adminStore.loadEvents(), adminStore.loadLearners()])
  } catch (e: any) {
    error.value = e?.message || '加载事件失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-5">
    <!-- Loading -->
    <div v-if="loading" class="card p-10 flex items-center justify-center text-text-secondary">
      <svg class="w-5 h-5 animate-spin mr-2" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" /></svg>
      加载中…
    </div>

    <!-- Error -->
    <div v-else-if="error" class="card p-6 text-center text-danger">{{ error }}</div>

    <template v-else>
      <!-- Toolbar -->
      <div class="card p-4 flex flex-col lg:flex-row gap-3">
        <select v-model="filterLearner" class="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white text-text focus:outline-none focus:ring-2 focus:ring-primary/40">
          <option value="">全部学员</option>
          <option v-for="l in learnerOptions" :key="l.id" :value="l.name">{{ l.name }}</option>
        </select>
        <select v-model="filterType" class="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white text-text focus:outline-none focus:ring-2 focus:ring-primary/40">
          <option value="">全部事件类型</option>
          <option v-for="t in typeOptions" :key="t" :value="t">{{ eventLabel(t) }}</option>
        </select>
        <div class="flex items-center gap-2 text-sm text-text-secondary">
          <input type="date" v-model="filterFrom" class="px-3 py-2 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/40" />
          <span>至</span>
          <input type="date" v-model="filterTo" class="px-3 py-2 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/40" />
        </div>
        <div class="flex items-center gap-2 lg:ml-auto">
          <button @click="resetFilters" class="px-3 py-2 text-sm rounded-lg border border-gray-200 text-text-secondary hover:bg-gray-50 transition-colors">重置</button>
          <button @click="exportCsv" class="btn-primary px-4 py-2 text-sm flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
            导出 CSV
          </button>
        </div>
      </div>

      <!-- Table -->
      <div class="card overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-text-secondary border-b border-gray-100 bg-gray-50/60">
                <th class="py-3 px-4 font-medium">时间</th>
                <th class="py-3 px-4 font-medium">学员</th>
                <th class="py-3 px-4 font-medium">事件类型</th>
                <th class="py-3 px-4 font-medium">课程 / 内容</th>
                <th class="py-3 px-4 font-medium">详情</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in visibleEvents" :key="e.id" class="border-b border-gray-50 hover:bg-gray-50/60 transition-colors">
                <td class="py-3 px-4 text-text-secondary whitespace-nowrap">{{ e.time }}</td>
                <td class="py-3 px-4">
                  <div class="font-medium text-primary">{{ e.learner_name }}</div>
                  <div class="text-xs text-text-secondary">{{ e.employee_no }}</div>
                </td>
                <td class="py-3 px-4">
                  <span class="px-2 py-0.5 rounded-full text-xs" :class="badgeOf(e.event_type)">{{ eventLabel(e.event_type) }}</span>
                </td>
                <td class="py-3 px-4 text-text">{{ e.course_content }}</td>
                <td class="py-3 px-4 text-text-secondary">{{ e.detail }}</td>
              </tr>
              <tr v-if="!visibleEvents.length">
                <td colspan="5" class="py-10 text-center text-text-secondary">暂无事件数据</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Load more -->
        <div class="flex items-center justify-between px-4 py-3 border-t border-gray-100 text-sm text-text-secondary">
          <span>显示 {{ visibleEvents.length }} / {{ filtered.length }} 条</span>
          <button v-if="hasMore" @click="loadMore" class="px-4 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors">加载更多</button>
        </div>
      </div>
    </template>
  </div>
</template>
