<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/lib/api'

const router = useRouter()

const loading = ref(false)
const error = ref('')
const items = ref<any[]>([])

const filterType = ref('')

const typeMeta: Record<string, { label: string; cls: string }> = {
  broadcast_recording: { label: '广播词录音', cls: 'bg-primary-soft text-primary' },
  english_qa: { label: '英文问答', cls: 'bg-warning/10 text-warning' },
  zh_to_en: { label: '中译英', cls: 'bg-success/10 text-success' },
}
function typeOf(t: string) {
  return typeMeta[t] || { label: t, cls: 'bg-gray-100 text-text-secondary' }
}

const filtered = computed(() =>
  filterType.value ? items.value.filter((a) => a.assessment_type === filterType.value) : items.value,
)

const pendingCount = computed(() => items.value.length)

function fmtTime(s: string) {
  if (!s) return '—'
  try {
    const d = new Date(s)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch { return s }
}

function goGrade(row: any) {
  router.push(`/instructor/assessments/${row.id}`)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = (await api.assessments.pending()) || []
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
  <div class="space-y-5">
    <!-- Header card -->
    <div class="rounded-xl bg-white border border-gray-100 p-5 md:p-6 flex items-center justify-between">
      <div>
        <p class="text-sm text-text-secondary">待评分测评</p>
        <p class="text-3xl font-bold text-text mt-1">{{ pendingCount }}</p>
        <p class="text-xs text-text-secondary mt-1">教员只看自己被指派的提交；管理员看全部</p>
      </div>
      <button @click="load" class="px-4 py-2 rounded-lg border border-gray-200 text-sm hover:bg-gray-50 transition-colors">
        <el-icon class="mr-1"><Refresh /></el-icon>
        刷新
      </button>
    </div>

    <!-- Filter -->
    <div class="rounded-xl bg-white border border-gray-100 p-4 flex flex-col md:flex-row md:items-center gap-3">
      <label class="text-sm text-text-secondary">测评类型</label>
      <el-select v-model="filterType" placeholder="全部类型" clearable style="width: 200px">
        <el-option label="广播词录音" value="broadcast_recording" />
        <el-option label="英文问答" value="english_qa" />
        <el-option label="中译英" value="zh_to_en" />
      </el-select>
      <span class="text-xs text-text-secondary md:ml-auto">共 {{ filtered.length }} 条</span>
    </div>

    <!-- Table -->
    <div v-loading="loading" class="rounded-xl bg-white border border-gray-100 overflow-hidden">
      <el-table :data="filtered" stripe empty-text="暂无待评分测评">
        <el-table-column label="学员" min-width="140">
          <template #default="{ row }">
            <span class="font-medium text-text">{{ row.learner_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="任务" min-width="200">
          <template #default="{ row }">
            <span class="text-text">{{ row.task_title || '—' }}</span>
            <span class="text-xs text-text-secondary block">{{ row.course_title || '' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="测评类型" width="130">
          <template #default="{ row }">
            <span class="px-2 py-0.5 rounded text-xs" :class="typeOf(row.assessment_type).cls">
              {{ typeOf(row.assessment_type).label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default>
            <el-tag size="small" type="warning" effect="plain">待评分</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="goGrade(row)">去评分</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="error" class="text-sm text-danger">{{ error }}</div>
  </div>
</template>

<style scoped>
.bg-primary-soft { background-color: #F3EDFF; }
.text-primary { color: #7C3AED; }
.text-text { color: #1F2430; }
.text-text-secondary { color: #687280; }
.text-danger { color: #EF4444; }
.text-warning { color: #F59E0B; }
.text-success { color: #22C55E; }
.bg-gray-100 { background-color: #F3F4F6; }
.border-gray-100 { border-color: #F3F4F6; }
.border-gray-200 { border-color: #E5E7EB; }
.hover\:bg-gray-50:hover { background-color: #F9FAFB; }
</style>