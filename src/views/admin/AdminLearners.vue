<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'

const router = useRouter()
const adminStore = useAdminStore()

const search = ref('')
const groupFilter = ref('')

const loading = ref(false)
const error = ref('')

const learners = computed(() =>
  adminStore.learners.map((l: any) => ({
    ...l,
    completion_rate: Math.round(l.avg_progress || 0),
    total_hours: Math.round((l.total_seconds || 0) / 360 * 10) / 10,
    last_active: formatDate(l.updated_at || l.created_at),
  }))
)

const groups = computed(() => {
  const map = new Map<string, string>()
  for (const l of learners.value) {
    const g = l.group_id || ''
    if (g && !map.has(g)) map.set(g, shortId(g))
  }
  return [...map.entries()].map(([id, name]) => ({ id, name }))
})

function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) + '…' : id
}
function getGroupName(g: string | null): string {
  if (!g) return '未分组'
  const found = groups.value.find((x) => x.id === g)
  return found ? found.name : '未分组'
}
function formatDate(s?: string): string {
  if (!s) return ''
  const d = new Date(s)
  if (isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const filtered = computed(() => {
  return learners.value.filter((l) => {
    if (groupFilter.value && l.group_id !== groupFilter.value) return false
    if (search.value) {
      const q = search.value.toLowerCase()
      return (
        (l.display_name || '').toLowerCase().includes(q) ||
        (l.employee_no || '').toLowerCase().includes(q) ||
        getGroupName(l.group_id).toLowerCase().includes(q)
      )
    }
    return true
  })
})

function rateBarClass(rate: number) {
  if (rate >= 80) return 'bg-success'
  if (rate >= 50) return 'bg-warning'
  return 'bg-danger'
}

function viewDetail(id: string) {
  router.push(`/admin/learners/${id}`)
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    await adminStore.loadLearners()
  } catch (e: any) {
    error.value = e?.message || '学员加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-5">
    <!-- Toolbar -->
    <div class="card p-4 flex flex-col sm:flex-row gap-3">
      <div class="relative flex-1">
        <svg class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
        <input
          v-model="search" type="text" placeholder="搜索姓名 / 工号 / 分组"
          class="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/40"
        />
      </div>
      <select v-model="groupFilter" class="px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white text-text focus:outline-none focus:ring-2 focus:ring-primary/40">
        <option value="">全部分组</option>
        <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
      </select>
    </div>

    <div v-if="loading" class="card p-10 flex items-center justify-center py-10">
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
                <th class="py-3 px-4 font-medium">姓名</th>
                <th class="py-3 px-4 font-medium">工号</th>
                <th class="py-3 px-4 font-medium">分组</th>
                <th class="py-3 px-4 font-medium w-36">总体完成率</th>
                <th class="py-3 px-4 font-medium">累计学习时长</th>
                <th class="py-3 px-4 font-medium">最近学习</th>
                <th class="py-3 px-4 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="l in filtered" :key="l.id"
                class="border-b border-gray-50 hover:bg-gray-50/60 transition-colors"
              >
                <td class="py-3 px-4">
                  <div class="flex items-center gap-3">
                    <div class="w-8 h-8 rounded-full bg-primary-soft text-primary flex items-center justify-center text-sm font-medium shrink-0">
                      {{ (l.display_name || '?')[0] }}
                    </div>
                    <span class="font-medium text-text">{{ l.display_name }}</span>
                  </div>
                </td>
                <td class="py-3 px-4 text-text-secondary">{{ l.employee_no }}</td>
                <td class="py-3 px-4">
                  <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs">{{ getGroupName(l.group_id) }}</span>
                </td>
                <td class="py-3 px-4">
                  <div class="flex items-center gap-2">
                    <div class="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div class="h-full rounded-full" :class="rateBarClass(l.completion_rate)" :style="{ width: l.completion_rate + '%' }"></div>
                    </div>
                    <span class="text-xs text-text-secondary w-8 text-right">{{ l.completion_rate }}%</span>
                  </div>
                </td>
                <td class="py-3 px-4 text-text-secondary">{{ l.total_hours }} h</td>
                <td class="py-3 px-4 text-text-secondary">{{ l.last_active }}</td>
                <td class="py-3 px-4">
                  <button @click="viewDetail(l.id)" class="text-primary hover:underline">详情</button>
                </td>
              </tr>
              <tr v-if="!filtered.length">
                <td colspan="7" class="py-10 text-center text-text-secondary">未找到匹配的学员</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
