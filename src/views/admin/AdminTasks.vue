<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'

const router = useRouter()
const adminStore = useAdminStore()

// Filters
const filterCourse = ref('')
const filterStatus = ref('')
const filterGroup = ref('')

// Pagination
const pageSize = 5
const page = ref(1)

const loading = ref(false)
const error = ref('')

const courses = computed(() => {
  const map = new Map<string, string>()
  for (const t of adminStore.tasks) {
    if (t.course_id) map.set(t.course_id, t.course_title || t.course_id)
  }
  return [...map.entries()].map(([id, title]) => ({ id, title }))
})
const groups = ref<any[]>([])
const statuses = [
  { value: 'active', label: '进行中' },
  { value: 'completed', label: '已完成' },
  { value: 'draft', label: '草稿' },
  { value: 'archived', label: '已归档' },
]

const statusMeta: Record<string, { label: string; cls: string }> = {
  active: { label: '进行中', cls: 'bg-green-50 text-green-700 border border-green-200' },
  completed: { label: '已完成', cls: 'bg-blue-50 text-blue-700 border border-blue-200' },
  draft: { label: '草稿', cls: 'bg-gray-100 text-gray-600 border border-gray-200' },
  archived: { label: '已归档', cls: 'bg-gray-100 text-gray-500 border border-gray-200' },
}
function statusOf(s: string) {
  return statusMeta[s] || statusMeta.draft
}
function rateBarClass(rate: number) {
  if (rate >= 80) return 'bg-success'
  if (rate >= 50) return 'bg-warning'
  return 'bg-danger'
}

const filtered = computed(() =>
  adminStore.tasks.filter((t: any) => {
    if (filterCourse.value && !(t.course_title || '').includes(filterCourse.value)) return false
    if (filterStatus.value && t.status !== filterStatus.value) return false
    return true
  })
)

const totalPages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))
const pagedTasks = computed(() => {
  const start = (page.value - 1) * pageSize
  return filtered.value.slice(start, start + pageSize)
})

function resetFilters() {
  filterCourse.value = ''
  filterStatus.value = ''
  filterGroup.value = ''
  page.value = 1
}
function prevPage() {
  if (page.value > 1) page.value--
}
function nextPage() {
  if (page.value < totalPages.value) page.value++
}

// Placeholder actions
function viewTask(_t: any) {
  router.push('/admin/tasks')
}
function editTask(t: any) {
  console.log('edit task', t.id)
}
function deleteTask(t: any) {
  console.log('delete task', t.id)
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    await adminStore.loadTasks()
  } catch (e: any) {
    error.value = e?.message || '任务加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-5">
    <!-- Toolbar -->
    <div class="card p-4 flex flex-col lg:flex-row lg:items-center gap-3">
      <div class="flex flex-1 flex-col sm:flex-row gap-3">
        <select v-model="filterCourse" class="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white text-text focus:outline-none focus:ring-2 focus:ring-primary/40">
          <option value="">全部课程</option>
          <option v-for="c in courses" :key="c.id" :value="c.title">{{ c.title }}</option>
        </select>
        <select v-model="filterStatus" class="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white text-text focus:outline-none focus:ring-2 focus:ring-primary/40">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s.value" :value="s.value">{{ s.label }}</option>
        </select>
        <select v-model="filterGroup" class="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white text-text focus:outline-none focus:ring-2 focus:ring-primary/40">
          <option value="">全部分组</option>
          <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
        </select>
        <button @click="resetFilters" class="px-3 py-2 text-sm rounded-lg border border-gray-200 text-text-secondary hover:bg-gray-50 transition-colors">重置</button>
      </div>
      <button @click="router.push('/admin/tasks/new')" class="btn-primary px-5 py-2.5 text-sm flex items-center justify-center gap-2">
        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" /></svg>
        新建任务
      </button>
    </div>

    <div v-if="loading" class="card p-10 flex items-center justify-center">
      <div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
    </div>
    <div v-else-if="error" class="card p-6 text-center text-sm text-danger">{{ error }}</div>
    <template v-else>
      <!-- Table -->
      <div class="card overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-text-secondary border-b border-gray-100 bg-gray-50/60">
                <th class="py-3 px-4 font-medium">任务名称</th>
                <th class="py-3 px-4 font-medium">课程</th>
                <th class="py-3 px-4 font-medium">发布日期</th>
                <th class="py-3 px-4 font-medium">截止时间</th>
                <th class="py-3 px-4 font-medium w-36">完成率</th>
                <th class="py-3 px-4 font-medium">状态</th>
                <th class="py-3 px-4 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="t in pagedTasks" :key="t.id"
                class="border-b border-gray-50 hover:bg-gray-50/60 transition-colors"
              >
                <td class="py-3 px-4 font-medium text-text">{{ t.title }}</td>
                <td class="py-3 px-4 text-text-secondary">{{ t.course_title }}</td>
                <td class="py-3 px-4 text-text-secondary">{{ t.start_at }}</td>
                <td class="py-3 px-4 text-text-secondary">{{ t.due_at }}</td>
                <td class="py-3 px-4">
                  <div class="flex items-center gap-2">
                    <div class="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div class="h-full rounded-full" :class="rateBarClass(t.rate)" :style="{ width: t.rate + '%' }"></div>
                    </div>
                    <span class="text-xs text-text-secondary w-8 text-right">{{ t.rate }}%</span>
                  </div>
                </td>
                <td class="py-3 px-4">
                  <span class="px-2 py-0.5 rounded-full text-xs" :class="statusOf(t.status).cls">{{ statusOf(t.status).label }}</span>
                </td>
                <td class="py-3 px-4">
                  <div class="flex items-center gap-3">
                    <button @click="viewTask(t)" class="text-primary hover:underline">查看</button>
                    <button @click="editTask(t)" class="text-text-secondary hover:text-text">编辑</button>
                    <button @click="deleteTask(t)" class="text-danger hover:underline">删除</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!pagedTasks.length">
                <td colspan="7" class="py-10 text-center text-text-secondary">暂无任务</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div class="flex items-center justify-between px-4 py-3 border-t border-gray-100 text-sm text-text-secondary">
          <span>共 {{ filtered.length }} 个任务</span>
          <div class="flex items-center gap-2">
            <button @click="prevPage" :disabled="page === 1" class="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed">上一页</button>
            <span class="px-2">{{ page }} / {{ totalPages }}</span>
            <button @click="nextPage" :disabled="page === totalPages" class="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed">下一页</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
