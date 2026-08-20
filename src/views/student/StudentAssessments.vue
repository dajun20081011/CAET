<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/lib/api'

const loading = ref(false)
const error = ref('')
const items = ref<any[]>([])

const typeMeta: Record<string, { label: string; cls: string }> = {
  broadcast_recording: { label: '广播词录音', cls: 'bg-primary-soft text-primary' },
  english_qa: { label: '英文问答', cls: 'bg-warning/10 text-warning' },
  zh_to_en: { label: '中译英', cls: 'bg-success/10 text-success' },
}
function typeOf(t: string) {
  return typeMeta[t] || { label: t, cls: 'bg-gray-100 text-text-secondary' }
}

const statusMeta: Record<string, { label: string; cls: string }> = {
  submitted: { label: '已提交', cls: 'bg-info/10 text-info' },
  graded: { label: '已评分', cls: 'bg-success/10 text-success' },
  resubmit: { label: '需重提交', cls: 'bg-danger/10 text-danger' },
}
function statusOf(s: string) {
  return statusMeta[s] || { label: s, cls: 'bg-gray-100 text-text-secondary' }
}

function fmt(s: string | null) {
  if (!s) return '—'
  try { return new Date(s).toLocaleString('zh-CN', { hour12: false }) }
  catch { return s }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = (await api.assessments.my()) || []
  } catch (e: any) {
    error.value = e?.message || '加载失败'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="min-h-[100dvh] bg-background pb-20">
    <header class="bg-white border-b border-gray-100 px-5 pt-10 pb-4">
      <h1 class="text-lg font-bold text-text">我的测评</h1>
      <p class="text-xs text-text-secondary mt-0.5">提交记录与教员评分反馈</p>
    </header>

    <div class="px-5 pt-4">
      <div v-loading="loading" class="space-y-3">
        <div v-if="!loading && items.length === 0" class="card p-8 text-center text-text-secondary text-sm">
          暂无测评记录
        </div>

        <div
          v-for="row in items"
          :key="row.id"
          class="card p-4"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <p class="text-xs text-text-secondary">{{ row.course_title || '—' }} · {{ row.task_title || '—' }}</p>
              <p class="text-sm font-medium text-text mt-0.5">{{ typeOf(row.assessment_type).label }} · 第 {{ row.attempt_no }} 次</p>
            </div>
            <span class="shrink-0 text-[11px] px-2 py-1 rounded-full font-medium" :class="statusOf(row.status).cls">
              {{ statusOf(row.status).label }}
            </span>
          </div>

          <p class="text-xs text-text-secondary mt-2">提交时间：{{ fmt(row.created_at) }}</p>

          <div v-if="row.score !== null && row.score !== undefined" class="mt-3 flex items-center gap-2">
            <span class="text-xs text-text-secondary">教员评分</span>
            <span class="text-base font-bold" :class="row.score >= 80 ? 'text-success' : row.score >= 60 ? 'text-warning' : 'text-danger'">{{ row.score }}</span>
            <span class="text-xs text-text-secondary">/ 100</span>
          </div>

          <div v-if="row.feedback" class="mt-2 rounded-lg bg-gray-50 p-3">
            <p class="text-xs text-text-secondary mb-1">教员反馈</p>
            <p class="text-sm text-text leading-relaxed">{{ row.feedback }}</p>
          </div>
        </div>
      </div>

      <div v-if="error" class="text-sm text-danger mt-3">{{ error }}</div>
    </div>
  </div>
</template>

<style scoped>
.bg-background { background-color: #F8F7FC; }
.bg-gray-50 { background-color: #F9FAFB; }
.bg-primary-soft { background-color: #F3EDFF; }
.text-primary { color: #7C3AED; }
.text-text { color: #1F2430; }
.text-text-secondary { color: #687280; }
.text-danger { color: #EF4444; }
.text-warning { color: #F59E0B; }
.text-success { color: #22C55E; }
.text-info { color: #3B82F6; }
.bg-info\/10 { background-color: rgba(59, 130, 246, 0.1); }
.border-gray-100 { border-color: #F3F4F6; }
</style>