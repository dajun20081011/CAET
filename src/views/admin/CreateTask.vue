<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import { api } from '@/lib/api'

const adminStore = useAdminStore()
const router = useRouter()

const steps = ['选择课程', '章节范围', '设置日期', '选择学员', '确认发布']
const step = ref(1)

const loading = ref(false)
const loadError = ref('')

const courses = ref<any[]>([] as any[])
const learners = ref<any[]>([])
const groups = computed(() => {
  const ids = Array.from(
    new Set(learners.value.map((l: any) => l.group_id).filter(Boolean)),
  ) as string[]
  return ids.map((id) => ({ id, name: groupName(id) }))
})

function groupName(id: string) {
  return '分组 ' + id
}

const form = reactive({
  courseId: '',
  chapterFrom: 1,
  chapterTo: 2,
  dayFrom: 1,
  dayTo: 3,
  startAt: '',
  dueAt: '',
  learnerTab: 'all' as 'all' | 'group' | 'specified',
  selectedGroups: [] as string[],
  selectedLearners: [] as string[],
  instructorId: '' as string,
})

const selectedCourse = computed(() => courses.value.find((c) => c.id === form.courseId))

const courseTypeMeta: Record<string, { label: string; cls: string }> = {
  broadcast: { label: '广播词', cls: 'bg-primary-soft text-primary' },
  caet2: { label: 'CAET2', cls: 'bg-info/10 text-info' },
  caet3: { label: 'CAET3', cls: 'bg-warning/10 text-warning' },
}
function courseTypeOf(t: string) {
  return courseTypeMeta[t] || { label: t, cls: 'bg-gray-100 text-text-secondary' }
}

// 教员候选（供创建时指派）
const instructors = ref<any[]>([])

const selectedLearnerIds = computed<string[]>(() => {
  if (form.learnerTab === 'all') return learners.value.map((l) => l.id)
  if (form.learnerTab === 'group') {
    return learners.value
      .filter((l) => form.selectedGroups.includes(l.group_id || ''))
      .map((l) => l.id)
  }
  return form.selectedLearners
})

const selectedLearnerObjs = computed(() =>
  learners.value.filter((l) => selectedLearnerIds.value.includes(l.id)),
)

// Validation
const canProceed = computed(() => {
  if (step.value === 1) return !!form.courseId
  if (step.value === 2)
    return (
      form.chapterFrom > 0 &&
      form.chapterTo >= form.chapterFrom &&
      form.dayFrom > 0 &&
      form.dayTo >= form.dayFrom
    )
  if (step.value === 3) return !!form.startAt && !!form.dueAt
  if (step.value === 4) return selectedLearnerIds.value.length > 0
  return true
})

function next() {
  if (step.value < 5 && canProceed.value) step.value++
}
function prev() {
  if (step.value > 1) step.value--
}

// keep group/learner selections sane when switching tabs
watch(
  () => form.learnerTab,
  () => {
    form.selectedGroups = []
    form.selectedLearners = []
  },
)

const submitting = ref(false)
const success = ref(false)
const errorMsg = ref('')

async function submit() {
  if (!canProceed.value) return
  submitting.value = true
  errorMsg.value = ''
  const taskPayload = {
    title: `${selectedCourse.value?.title} 章节 ${form.chapterFrom}-${form.chapterTo} 任务`,
    course_id: form.courseId,
    chapter_from: form.chapterFrom,
    chapter_to: form.chapterTo,
    day_from: form.dayFrom,
    day_to: form.dayTo,
    start_at: new Date(form.startAt).toISOString(),
    due_at: new Date(form.dueAt).toISOString(),
    completion_rule: {},
    status: 'active',
    created_by: 'admin',
    instructor_id: form.instructorId || null,
  }
  const result = await adminStore.createTask(taskPayload, selectedLearnerIds.value)
  submitting.value = false
  if (result.success) {
    success.value = true
    setTimeout(() => router.push('/admin/tasks'), 1400)
  } else {
    errorMsg.value = result.error || '发布失败'
  }
}

onMounted(async () => {
  loading.value = true
  loadError.value = ''
  try {
    const [courseList, , usersList] = await Promise.all([api.courses.list(), adminStore.loadLearners(), api.users.list()])
    courses.value = courseList || []
    learners.value = adminStore.learners || []
    instructors.value = (usersList || []).filter((u: any) => u.role === 'instructor' || u.role === 'admin')
  } catch (e: any) {
    loadError.value = e?.message || '加载课程或学员失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="max-w-3xl mx-auto space-y-5">
    <!-- Stepper -->
    <div class="card p-5">
      <div class="flex items-center">
        <template v-for="(s, i) in steps" :key="i">
          <div class="flex items-center gap-2">
            <div
              class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors"
              :class="step > i + 1 ? 'bg-primary text-white' : step === i + 1 ? 'bg-primary-soft text-primary border-2 border-primary' : 'bg-gray-100 text-gray-400'"
            >
              <svg v-if="step > i + 1" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" /></svg>
              <span v-else>{{ i + 1 }}</span>
            </div>
            <span class="text-sm hidden sm:block" :class="step >= i + 1 ? 'text-text font-medium' : 'text-text-secondary'">{{ s }}</span>
          </div>
          <div v-if="i < steps.length - 1" class="flex-1 h-px mx-3" :class="step > i + 1 ? 'bg-primary' : 'bg-gray-200'"></div>
        </template>
      </div>
    </div>

    <!-- Success banner -->
    <div v-if="success" class="card p-5 border border-green-200 bg-green-50 flex items-center gap-3">
      <svg class="w-6 h-6 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
      <div>
        <div class="font-medium text-text">任务发布成功</div>
        <div class="text-sm text-text-secondary">正在跳转到任务列表…</div>
      </div>
    </div>

    <!-- Loading -->
    <div v-else-if="loading" class="card p-10 flex items-center justify-center text-text-secondary">
      <svg class="w-5 h-5 animate-spin mr-2" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" /><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" /></svg>
      加载中…
    </div>

    <div v-else class="card p-6 space-y-5">
      <!-- Load error -->
      <div v-if="loadError" class="text-sm text-danger">{{ loadError }}</div>
      <!-- Submit error -->
      <div v-if="errorMsg" class="text-sm text-danger">{{ errorMsg }}</div>

      <!-- Step 1: course -->
      <div v-if="step === 1" class="space-y-4">
        <h3 class="text-base font-semibold text-text">选择课程</h3>
        <div class="grid sm:grid-cols-2 gap-3">
          <button
            v-for="c in courses" :key="c.id"
            @click="form.courseId = c.id"
            class="text-left p-4 rounded-lg border transition-all"
            :class="form.courseId === c.id ? 'border-primary bg-primary-soft ring-1 ring-primary' : 'border-gray-200 hover:border-gray-300'"
          >
            <div class="flex items-center gap-2">
              <span class="font-medium text-text">{{ c.title }}</span>
              <span v-if="c.course_type" class="px-1.5 py-0.5 rounded text-[10px]" :class="courseTypeOf(c.course_type).cls">
                {{ courseTypeOf(c.course_type).label }}
              </span>
            </div>
            <div class="text-xs text-text-secondary mt-1">{{ c.code }} · {{ c.description }}</div>
          </button>
        </div>
        <div v-if="!courses.length" class="text-sm text-text-secondary">暂无可分配课程</div>
      </div>

      <!-- Step 2: chapter / day range -->
      <div v-else-if="step === 2" class="space-y-4">
        <h3 class="text-base font-semibold text-text">选择章节 / Day 范围</h3>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="text-sm text-text-secondary">起始章节</label>
            <input type="number" min="1" v-model.number="form.chapterFrom" class="mt-1 w-full px-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </div>
          <div>
            <label class="text-sm text-text-secondary">结束章节</label>
            <input type="number" min="1" v-model.number="form.chapterTo" class="mt-1 w-full px-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </div>
          <div>
            <label class="text-sm text-text-secondary">起始 Day</label>
            <input type="number" min="1" v-model.number="form.dayFrom" class="mt-1 w-full px-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </div>
          <div>
            <label class="text-sm text-text-secondary">结束 Day</label>
            <input type="number" min="1" v-model.number="form.dayTo" class="mt-1 w-full px-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </div>
        </div>
        <p v-if="form.chapterTo < form.chapterFrom || form.dayTo < form.dayFrom" class="text-sm text-danger">结束值不能小于起始值。</p>
      </div>

      <!-- Step 3: dates -->
      <div v-else-if="step === 3" class="space-y-4">
        <h3 class="text-base font-semibold text-text">设置日期</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="text-sm text-text-secondary">开始时间</label>
            <input type="datetime-local" v-model="form.startAt" class="mt-1 w-full px-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </div>
          <div>
            <label class="text-sm text-text-secondary">截止时间</label>
            <input type="datetime-local" v-model="form.dueAt" class="mt-1 w-full px-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-primary/40" />
          </div>
        </div>
      </div>

      <!-- Step 4: learners -->
      <div v-else-if="step === 4" class="space-y-4">
        <h3 class="text-base font-semibold text-text">选择学员</h3>
        <div class="inline-flex rounded-lg border border-gray-200 p-1 bg-gray-50">
          <button
            v-for="tab in [{ k: 'all', t: '全部学员' }, { k: 'group', t: '按分组' }, { k: 'specified', t: '指定学员' }]"
            :key="tab.k"
            @click="form.learnerTab = tab.k as any"
            class="px-4 py-1.5 text-sm rounded-md transition-colors"
            :class="form.learnerTab === tab.k ? 'bg-white text-primary shadow-sm font-medium' : 'text-text-secondary'"
          >{{ tab.t }}</button>
        </div>

        <!-- group tab -->
        <div v-if="form.learnerTab === 'group'" class="space-y-2">
          <label
            v-for="g in groups" :key="g.id"
            class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 hover:bg-gray-50 cursor-pointer"
            :class="form.selectedGroups.includes(g.id) ? 'border-primary bg-primary-soft' : ''"
          >
            <input type="checkbox" :value="g.id" v-model="form.selectedGroups" class="w-4 h-4 accent-primary" />
            <span class="text-sm text-text">{{ g.name }}</span>
            <span class="text-xs text-text-secondary ml-auto">{{ learners.filter((l) => l.group_id === g.id).length }} 人</span>
          </label>
          <div v-if="!groups.length" class="text-sm text-text-secondary">暂无可用的分组</div>
        </div>

        <!-- specified tab -->
        <div v-else-if="form.learnerTab === 'specified'" class="space-y-2">
          <label
            v-for="l in learners" :key="l.id"
            class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 hover:bg-gray-50 cursor-pointer"
            :class="form.selectedLearners.includes(l.id) ? 'border-primary bg-primary-soft' : ''"
          >
            <input type="checkbox" :value="l.id" v-model="form.selectedLearners" class="w-4 h-4 accent-primary" />
            <span class="text-sm text-text font-medium">{{ l.display_name }}</span>
            <span class="text-xs text-text-secondary">{{ l.employee_no }}</span>
            <span class="text-xs text-text-secondary ml-auto">{{ groupName(l.group_id) }}</span>
          </label>
          <div v-if="!learners.length" class="text-sm text-text-secondary">暂无可分配的学员</div>
        </div>

        <!-- all tab summary -->
        <div v-else class="text-sm text-text-secondary p-3 rounded-lg bg-gray-50">
          将向全部 {{ learners.length }} 名学员发布该任务。
        </div>
      </div>

      <!-- Step 5: summary -->
      <div v-else-if="step === 5" class="space-y-4">
        <h3 class="text-base font-semibold text-text">发布摘要确认</h3>
        <dl class="divide-y divide-gray-100 text-sm">
          <div class="flex justify-between py-2.5">
            <dt class="text-text-secondary">课程</dt>
            <dd class="text-text font-medium">{{ selectedCourse?.title }}（{{ selectedCourse?.code }}）</dd>
          </div>
          <div class="flex justify-between py-2.5">
            <dt class="text-text-secondary">章节范围</dt>
            <dd class="text-text font-medium">第 {{ form.chapterFrom }} - {{ form.chapterTo }} 章</dd>
          </div>
          <div class="flex justify-between py-2.5">
            <dt class="text-text-secondary">Day 范围</dt>
            <dd class="text-text font-medium">Day {{ form.dayFrom }} - {{ form.dayTo }}</dd>
          </div>
          <div class="flex justify-between py-2.5">
            <dt class="text-text-secondary">开始时间</dt>
            <dd class="text-text font-medium">{{ form.startAt || '—' }}</dd>
          </div>
          <div class="flex justify-between py-2.5">
            <dt class="text-text-secondary">截止时间</dt>
            <dd class="text-text font-medium">{{ form.dueAt || '—' }}</dd>
          </div>
          <div class="flex justify-between py-2.5">
            <dt class="text-text-secondary">学员范围</dt>
            <dd class="text-text font-medium">
              {{ form.learnerTab === 'all' ? '全部学员' : form.learnerTab === 'group' ? '按分组' : '指定学员' }}
              （{{ selectedLearnerIds.length }} 人）
            </dd>
          </div>
          <div class="flex justify-between py-2.5 items-center">
            <dt class="text-text-secondary">评分教员</dt>
            <dd class="text-text font-medium">
              <el-select v-model="form.instructorId" placeholder="暂不指派（可稍后在测评管理指派）" clearable filterable style="width: 240px">
                <el-option
                  v-for="u in instructors"
                  :key="u.id"
                  :label="`${u.display_name || u.email}（${u.role}）`"
                  :value="u.id"
                />
              </el-select>
            </dd>
          </div>
        </dl>
        <div v-if="form.learnerTab !== 'all'" class="flex flex-wrap gap-2">
          <span v-for="l in selectedLearnerObjs" :key="l.id" class="px-2 py-1 rounded-full bg-primary-soft text-primary text-xs">{{ l.display_name }}</span>
        </div>
      </div>

      <!-- Footer nav -->
      <div class="flex items-center justify-between pt-2 border-t border-gray-100">
        <button @click="prev" :disabled="step === 1" class="px-4 py-2 text-sm rounded-lg border border-gray-200 text-text-secondary hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed">上一步</button>
        <button v-if="step < 5" @click="next" :disabled="!canProceed" class="btn-primary px-5 py-2 text-sm disabled:opacity-50">下一步</button>
        <button v-else @click="submit" :disabled="submitting || !canProceed" class="btn-primary px-5 py-2 text-sm disabled:opacity-50">
          {{ submitting ? '发布中…' : '确认发布' }}
        </button>
      </div>
    </div>
  </div>
</template>
