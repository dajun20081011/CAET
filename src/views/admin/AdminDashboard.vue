<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'

const adminStore = useAdminStore()
const router = useRouter()

const loading = ref(false)
const error = ref('')

const tasks = computed(() => adminStore.tasks)

const metrics = computed(() => {
  const d = adminStore.dashboard
  if (!d) return { totalLearners: 0, completionRate: 0, totalHours: 0, avgHours: 0, taskCompleted: 0 }
  const people = d.learning_people_count || 0
  const totalHours = Math.round((d.total_effective_seconds || 0) / 360) / 10
  const avgSeconds = d.avg_seconds_per_person || 0
  return {
    totalLearners: people,
    completionRate: Math.round((d.overall_completion_rate || 0) * 10) / 10,
    totalHours,
    avgHours: Math.round((avgSeconds / 360) * 10) / 10,
    taskCompleted: d.task_completion_count || 0,
  }
})

const topContent = computed(() =>
  (adminStore.dashboard?.content_completion_top5 || []).map((c: any) => ({
    content: c.title || '',
    rate: Math.round((c.completion_rate || 0) * 10) / 10,
    course_title: c.chapter_no ? `第 ${c.chapter_no} 章` : '',
  }))
)

// Donut chart — 总体完成率
const donutRate = computed(() => metrics.value.completionRate)
const donutRadius = 54
const donutCircumference = 2 * Math.PI * donutRadius
const donutDash = computed(() => (donutRate.value / 100) * donutCircumference)

const taskDistribution = computed(() => adminStore.taskDistribution)

// Line chart — 每日活跃趋势
const lineValues = computed(() =>
  (adminStore.dashboard?.daily_active_trend || []).map((d: any) => d.active || 0)
)
const lineLabels = computed(() =>
  (adminStore.dashboard?.daily_active_trend || []).map((d: any) => formatDate(d.date))
)
const lineW = 560
const lineH = 160
const linePadY = 16

function formatDate(s?: string): string {
  if (!s) return ''
  const d = new Date(s)
  if (isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const linePoints = computed(() => {
  const vals = lineValues.value
  if (vals.length < 2) return []
  const max = Math.max(...vals, 1)
  const range = max || 1
  const stepX = lineW / (vals.length - 1)
  return vals.map((v: number, i: number) => {
    const x = i * stepX
    const y = lineH - linePadY - (v / range) * (lineH - linePadY * 2)
    return { x, y, v }
  })
})

const linePath = computed(() => linePoints.value.map((p: { x: number; y: number; v: number }) => `${p.x},${p.y}`).join(' '))
const lineArea = computed(() => {
  const pts = linePoints.value
  if (!pts.length) return ''
  return `0,${lineH} ${pts.map((p: { x: number; y: number; v: number }) => `${p.x},${p.y}`).join(' ')} ${lineW},${lineH}`
})

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

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    await adminStore.loadDashboard()
    await adminStore.loadTasks()
    await adminStore.loadLearners()
  } catch (e: any) {
    error.value = e?.message || '仪表盘加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-6">
    <div v-if="loading" class="flex justify-center py-20">
      <div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
    </div>
    <div v-else-if="error" class="card p-6 text-center text-sm text-danger">{{ error }}</div>
    <template v-else>
      <!-- Metric cards -->
      <div class="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <div class="card p-5">
          <div class="text-sm text-text-secondary mb-2">学习人数</div>
          <div class="text-2xl font-semibold text-text">{{ metrics.totalLearners }}</div>
          <div class="text-xs text-text-secondary mt-1">名学员</div>
        </div>
        <div class="card p-5">
          <div class="text-sm text-text-secondary mb-2">总体完成率</div>
          <div class="text-2xl font-semibold text-primary">{{ metrics.completionRate }}%</div>
          <div class="text-xs text-text-secondary mt-1">平均任务进度</div>
        </div>
        <div class="card p-5">
          <div class="text-sm text-text-secondary mb-2">有效学习时长</div>
          <div class="text-2xl font-semibold text-text">{{ metrics.totalHours }}<span class="text-base font-normal text-text-secondary ml-1">h</span></div>
          <div class="text-xs text-text-secondary mt-1">累计有效时长</div>
        </div>
        <div class="card p-5">
          <div class="text-sm text-text-secondary mb-2">人均学习时长</div>
          <div class="text-2xl font-semibold text-text">{{ metrics.avgHours }}<span class="text-base font-normal text-text-secondary ml-1">h</span></div>
          <div class="text-xs text-text-secondary mt-1">每人平均</div>
        </div>
        <div class="card p-5">
          <div class="text-sm text-text-secondary mb-2">任务完成数</div>
          <div class="text-2xl font-semibold text-text">{{ metrics.taskCompleted }}</div>
          <div class="text-xs text-text-secondary mt-1">已结课任务</div>
        </div>
      </div>

      <!-- Charts row -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Donut -->
        <div class="card p-6">
          <h3 class="text-base font-semibold text-text mb-4">本周任务完成情况</h3>
          <div class="flex items-center gap-8">
            <div class="relative shrink-0">
              <svg width="140" height="140" viewBox="0 0 140 140" class="-rotate-90">
                <circle cx="70" cy="70" :r="donutRadius" fill="none" stroke="#EDEDED" stroke-width="14" />
                <circle
                  cx="70" cy="70" :r="donutRadius" fill="none" :stroke="'#7C3AED'" stroke-width="14"
                  stroke-linecap="round" :stroke-dasharray="`${donutDash} ${donutCircumference}`"
                />
              </svg>
              <div class="absolute inset-0 flex flex-col items-center justify-center">
                <span class="text-2xl font-semibold text-text">{{ donutRate }}%</span>
                <span class="text-xs text-text-secondary">完成率</span>
              </div>
            </div>
            <div class="space-y-3 text-sm flex-1">
              <div class="flex items-center justify-between">
                <span class="flex items-center gap-2 text-text-secondary"><span class="w-2.5 h-2.5 rounded-full bg-primary"></span>已完成</span>
                <span class="font-medium text-text">{{ taskDistribution.completed }} 个</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="flex items-center gap-2 text-text-secondary"><span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>进行中</span>
                <span class="font-medium text-text">{{ taskDistribution.active }} 个</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="flex items-center gap-2 text-text-secondary"><span class="w-2.5 h-2.5 rounded-full bg-gray-300"></span>草稿</span>
                <span class="font-medium text-text">{{ taskDistribution.draft }} 个</span>
              </div>
              <div class="border-t border-gray-100 pt-3 flex items-center justify-between">
                <span class="text-text-secondary">总计</span>
                <span class="font-semibold text-text">{{ taskDistribution.total }} 个</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Line -->
        <div class="card p-6">
          <h3 class="text-base font-semibold text-text mb-4">每日活跃趋势</h3>
          <svg :viewBox="`0 0 ${lineW} ${lineH}`" class="w-full h-40" preserveAspectRatio="none">
            <polygon :points="lineArea" fill="#7C3AED" fill-opacity="0.08" />
            <polyline
              :points="linePath" fill="none" stroke="#7C3AED" stroke-width="2.5"
              stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"
            />
            <circle
              v-for="(p, i) in linePoints" :key="i" :cx="p.x" :cy="p.y" r="3.5"
              fill="#fff" stroke="#7C3AED" stroke-width="2" vector-effect="non-scaling-stroke"
            />
          </svg>
          <div class="flex justify-between mt-2 text-xs text-text-secondary">
            <span v-for="(l, i) in lineLabels" :key="i">{{ l }}</span>
          </div>
          <div class="flex justify-between mt-1 text-xs font-medium text-text">
            <span v-for="(p, i) in linePoints" :key="i">{{ p.v }}</span>
          </div>
        </div>
      </div>

      <!-- Recent tasks + Top content -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="card p-6 lg:col-span-2">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-base font-semibold text-text">最近任务</h3>
            <button @click="router.push('/admin/tasks')" class="text-sm text-primary hover:underline">查看全部</button>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-left text-text-secondary border-b border-gray-100">
                  <th class="py-3 pr-4 font-medium">任务名称</th>
                  <th class="py-3 pr-4 font-medium">课程</th>
                  <th class="py-3 pr-4 font-medium">截止时间</th>
                  <th class="py-3 pr-4 font-medium w-32">完成率</th>
                  <th class="py-3 pr-4 font-medium">状态</th>
                  <th class="py-3 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="t in tasks.slice(0, 5)" :key="t.id"
                  class="border-b border-gray-50 hover:bg-gray-50/60 transition-colors"
                >
                  <td class="py-3 pr-4 font-medium text-text">{{ t.title }}</td>
                  <td class="py-3 pr-4 text-text-secondary">{{ 'course_title' in t ? t.course_title : '' }}</td>
                  <td class="py-3 pr-4 text-text-secondary">{{ t.due_at }}</td>
                  <td class="py-3 pr-4">
                    <div class="flex items-center gap-2">
                      <div class="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div class="h-full rounded-full" :class="rateBarClass(t.rate)" :style="{ width: t.rate + '%' }"></div>
                      </div>
                      <span class="text-xs text-text-secondary w-8 text-right">{{ t.rate }}%</span>
                    </div>
                  </td>
                  <td class="py-3 pr-4">
                    <span class="px-2 py-0.5 rounded-full text-xs" :class="statusOf(t.status).cls">{{ statusOf(t.status).label }}</span>
                  </td>
                  <td class="py-3">
                    <router-link :to="`/admin/tasks`" class="text-primary hover:underline text-sm">查看</router-link>
                  </td>
                </tr>
                <tr v-if="!tasks.length">
                  <td colspan="6" class="py-10 text-center text-text-secondary">暂无任务</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="card p-6">
          <h3 class="text-base font-semibold text-text mb-4">内容完成率 Top 5</h3>
          <div class="space-y-4">
            <div v-for="(c, i) in topContent" :key="i">
              <div class="flex items-center justify-between text-sm mb-1.5">
                <span class="text-text font-medium truncate">{{ c.content }}</span>
                <span class="text-text-secondary ml-2 shrink-0">{{ c.rate }}%</span>
              </div>
              <div class="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div class="h-full rounded-full" :class="rateBarClass(c.rate)" :style="{ width: c.rate + '%' }"></div>
              </div>
              <div class="text-xs text-text-secondary mt-1">{{ c.course_title }}</div>
            </div>
            <div v-if="!topContent.length" class="text-sm text-text-secondary">暂无内容数据</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
