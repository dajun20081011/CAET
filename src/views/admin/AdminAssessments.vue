<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/lib/api'

const router = useRouter()

const loading = ref(false)
const error = ref('')
const items = ref<any[]>([])

const statusFilter = ref('')
const typeFilter = ref('')
const users = ref<any[]>([])  // 教员候选

const typeMeta: Record<string, { label: string; cls: string }> = {
  broadcast_recording: { label: '广播词录音', cls: 'bg-primary-soft text-primary' },
  english_qa: { label: '英文问答', cls: 'bg-warning/10 text-warning' },
  zh_to_en: { label: '中译英', cls: 'bg-success/10 text-success' },
}
function typeOf(t: string) {
  return typeMeta[t] || { label: t, cls: 'bg-gray-100 text-text-secondary' }
}

const statusMeta: Record<string, { label: string; type: string }> = {
  submitted: { label: '待评分', type: 'warning' },
  graded: { label: '已评分', type: 'success' },
  resubmit: { label: '需重提交', type: 'danger' },
}
function statusOf(s: string) {
  return statusMeta[s] || { label: s, type: 'info' }
}

function fmt(s: string | null) {
  if (!s) return '—'
  try { return new Date(s).toLocaleString('zh-CN', { hour12: false }) }
  catch { return s }
}

const filtered = computed(() =>
  items.value.filter((a) => {
    if (statusFilter.value && a.status !== statusFilter.value) return false
    if (typeFilter.value && a.assessment_type !== typeFilter.value) return false
    return true
  }),
)

const showAssign = ref(false)
const assignTarget = ref<any | null>(null)
const assignInstructorId = ref('')
const instructors = computed(() =>
  users.value.filter((u) => u.role === 'instructor' || u.role === 'admin'),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [pending, list] = await Promise.all([
      api.assessments.pending(),
      api.users.list(),
    ])
    items.value = pending || []
    users.value = list || []
  } catch (e: any) {
    error.value = e?.message || '加载失败'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

function openAssign(row: any) {
  assignTarget.value = row
  assignInstructorId.value = row.instructor_id || ''
  showAssign.value = true
}
async function doAssign() {
  if (!assignTarget.value || !assignInstructorId.value) {
    ElMessage.warning('请选择教员')
    return
  }
  try {
    await api.assessments.setInstructor(assignTarget.value.assignment_id, assignInstructorId.value)
    ElMessage.success('已指派')
    showAssign.value = false
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '指派失败')
  }
}

function goGrade(row: any) {
  router.push(`/instructor/assessments/${row.id}`)
}

onMounted(load)
</script>

<template>
  <div class="space-y-5">
    <div class="rounded-xl bg-white border border-gray-100 p-5 flex items-center justify-between">
      <div>
        <h2 class="text-base font-semibold text-text">测评管理</h2>
        <p class="text-xs text-text-secondary mt-1">查看/指派/跳转评分</p>
      </div>
      <button @click="load" class="px-4 py-2 rounded-lg border border-gray-200 text-sm hover:bg-gray-50 transition-colors">
        <el-icon class="mr-1"><Refresh /></el-icon>
        刷新
      </button>
    </div>

    <div class="rounded-xl bg-white border border-gray-100 p-4 flex flex-col md:flex-row md:items-center gap-3">
      <label class="text-sm text-text-secondary">测评类型</label>
      <el-select v-model="typeFilter" placeholder="全部类型" clearable style="width: 180px">
        <el-option label="广播词录音" value="broadcast_recording" />
        <el-option label="英文问答" value="english_qa" />
        <el-option label="中译英" value="zh_to_en" />
      </el-select>
      <label class="text-sm text-text-secondary md:ml-4">状态</label>
      <el-select v-model="statusFilter" placeholder="全部状态" clearable style="width: 160px">
        <el-option label="待评分" value="submitted" />
        <el-option label="已评分" value="graded" />
        <el-option label="需重提交" value="resubmit" />
      </el-select>
      <span class="text-xs text-text-secondary md:ml-auto">共 {{ filtered.length }} 条</span>
    </div>

    <div v-loading="loading" class="rounded-xl bg-white border border-gray-100 overflow-hidden">
      <el-table :data="filtered" stripe empty-text="暂无测评">
        <el-table-column label="学员" min-width="140">
          <template #default="{ row }">
            <span class="font-medium text-text">{{ row.learner_name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="任务 / 课程" min-width="220">
          <template #default="{ row }">
            <p class="text-text">{{ row.task_title || '—' }}</p>
            <p class="text-xs text-text-secondary">{{ row.course_title || '' }}</p>
          </template>
        </el-table-column>
        <el-table-column label="测评类型" width="130">
          <template #default="{ row }">
            <span class="px-2 py-0.5 rounded text-xs" :class="typeOf(row.assessment_type).cls">
              {{ typeOf(row.assessment_type).label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusOf(row.status).type as any" size="small" effect="plain">
              {{ statusOf(row.status).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="评分" width="100">
          <template #default="{ row }">
            <span v-if="row.score !== null && row.score !== undefined" :class="row.score >= 80 ? 'text-success' : row.score >= 60 ? 'text-warning' : 'text-danger'">
              {{ row.score }}
            </span>
            <span v-else class="text-text-secondary">—</span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status !== 'graded'" link type="primary" @click="goGrade(row)">去评分</el-button>
            <el-button link type="primary" @click="openAssign(row)">指派教员</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Assign dialog -->
    <el-dialog v-model="showAssign" title="指派教员" width="420">
      <p class="text-sm text-text-secondary mb-3">
        为 <span class="font-medium text-text">{{ assignTarget?.learner_name }}</span> 的
        「{{ assignTarget?.task_title }}」指派评分教员
      </p>
      <el-select v-model="assignInstructorId" placeholder="选择教员或管理员" filterable class="w-full">
        <el-option
          v-for="u in instructors"
          :key="u.id"
          :label="`${u.display_name || u.email}（${u.role}）`"
          :value="u.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="showAssign = false">取消</el-button>
        <el-button type="primary" :disabled="!assignInstructorId" @click="doAssign">指派</el-button>
      </template>
    </el-dialog>

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
.w-full { width: 100%; }
</style>