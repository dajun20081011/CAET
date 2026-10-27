<template>
  <main class="teacher-app">
    <section v-if="section === 'home'" class="teacher-page teacher-home">
      <header class="dynamic-greeting">
        <h1>亲爱的{{ teacherName }}，{{ daypartGreeting }}</h1>
        <p>{{ todayLabel }} · 今天的教学任务已经为您整理好了</p>
      </header>

      <section class="today-work" aria-labelledby="today-work-title">
        <header><h2 id="today-work-title">今日工作</h2><button type="button" @click="go('evaluations')">进入评价 →</button></header>
        <div class="today-metrics">
          <article><span>待评价</span><strong>{{ pendingCount }}</strong></article>
          <article><span>复训跟进</span><strong>{{ retrainingCount }}</strong></article>
          <article><span>今日已完成</span><strong>{{ dashboardMetric('today_completed') }}</strong></article>
        </div>
        <p>优先处理低分、复训重新提交和临近截止任务</p>
      </section>

      <section class="home-card priority-card" aria-labelledby="priority-title">
        <header><h2 id="priority-title">优先处理</h2><button type="button" @click="go('evaluations')">查看全部</button></header>
        <div v-if="priorities.length" class="priority-list">
          <button v-for="item in priorities" :key="keyOf(item)" type="button" @click="openFromHome(item)">
            <span class="priority-copy"><strong>{{ item.learner_name }} · {{ item.content_title || item.task_title }}</strong><small>{{ priorityMeta(item) }}</small></span>
            <span class="priority-action"><b :class="item.priority">{{ priorityBadge(item) }}</b><em>开始评价 →</em></span>
          </button>
        </div>
        <p v-else class="home-empty">当前没有优先任务</p>
      </section>

      <section class="home-card weekly-card" aria-labelledby="weekly-title">
        <h2 id="weekly-title">本周工作</h2>
        <div class="weekly-metrics">
          <article><span>已评价</span><strong>{{ weeklyCompletedLabel }}</strong></article>
          <article><span>待评价</span><strong class="orange">{{ pendingCount }}</strong></article>
          <article><span>复训完成</span><strong class="green">{{ dashboardMetric('week_retraining_completed') }}</strong></article>
        </div>
        <div class="weekly-progress" role="progressbar" aria-label="本周工作完成率" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="weeklyRate"><i :style="{ width: `${weeklyRate}%` }" /></div>
        <p>本周完成率 {{ weeklyRate }}%</p>
      </section>
    </section>

    <section v-else-if="section === 'evaluations'" class="teacher-page evaluations" :class="{ 'workspace-open':detailOpen }">
      <section v-if="submitted" class="submitted">
        <button class="back" @click="returnToQueue">‹ 训练评价</button><h1>评价已提交</h1><p>{{ submittedLabel }}</p>
        <div class="submitted-card"><span>✓</span><h2>评价已提交</h2><p>教员点评与音频评价已同步至学员端</p><div class="submitted-summary"><b v-if="submittedHasText">文字评价 <em>已同步</em></b><b v-if="submittedHasAudio">语音评价 <em>已同步</em></b></div><button @click="returnToQueue">返回待评价列表 →</button></div>
      </section>

      <InstructorReviewWorkspace v-else-if="detailOpen && detail && !detailLoading && !detailError" :detail="detail" :audio-src="audioUrl" :audio-loading="audioLoading" :saving="saving" @back="closeWorkspace" @open-learner="openCurrentLearner" @load-audio="loadAudio" @submit="publishReview" />
      <section v-else-if="detailOpen && detailLoading" class="state loading"><i/><i/><i/><p>正在加载评价证据…</p></section>
      <section v-else-if="detailOpen && detailError" class="state error"><b>!</b><h2>评价详情加载失败</h2><p>{{ detailError }}</p><button @click="retryDetail">重新加载</button></section>

      <template v-else>
        <TeacherHeader title="训练评价" subtitle="选任务 · 看学员 · 评价 · 提交" />
        <section v-if="loading && !queue.length" class="state loading"><i/><i/><i/><p>正在加载评价任务…</p></section>
        <section v-else-if="queueError && !queue.length" class="state error"><b>!</b><h2>暂时无法加载</h2><p>请检查网络后重试</p><button @click="initialize">重新加载</button></section>
        <section v-else-if="!evaluationItems.length" class="state empty"><b>✓</b><h2>暂时没有待评价任务</h2><p>新的学员训练提交后会显示在这里</p></section>
        <section v-else class="card evaluation-list">
          <div class="filters"><button v-for="item in filters" :key="item.key" :class="{ active:filter === item.key }" @click="filter=item.key">{{ item.label }} {{ item.count }}</button></div>
          <article v-for="item in evaluationItems" :key="keyOf(item)" class="evaluation-item" :class="{ active:isSelected(item) }"><strong>{{ item.learner_name }} · {{ item.content_title || item.task_title }}</strong><span>AI 已完成 · {{ statusOf(item) }}</span><footer><button type="button" @click="openLearnerFromQueue(item)">查看学员详情</button><button type="button" @click="loadDetail(item,true)">开始评价 →</button></footer></article>
        </section>
      </template>
    </section>

    <section v-else-if="section === 'students'" class="teacher-page learner-page">
      <template v-if="!selectedLearner">
        <TeacherHeader title="我的学员" :subtitle="`当前负责 ${learners.length} 名学员`" />
        <input v-model.trim="search" class="search" type="search" inputmode="search" placeholder="搜索姓名 / 工号" aria-label="搜索姓名或工号" />
        <DetailState v-if="learnersLoading && !learners.length" tone="loading" title="正在加载学员名单" />
        <DetailState v-else-if="learnersError && !learners.length" tone="error" title="学员名单加载失败" action-label="重新加载" @action="loadLearners" />
        <section v-else class="student-list">
          <button v-for="learner in visibleLearners" :key="learner.learner_id" @click="openLearner(learner)">
            <span class="student-identity"><strong>{{ learner.learner_name }}</strong><small>{{ learner.external_ref || '未设置工号' }} · {{ learner.class_name || '未分班' }}</small></span>
            <span>提交 {{ learner.submitted_count }} · 待评价 {{ learner.pending_review_count }}</span>
            <b :class="{ warn:learner.retraining_count }">{{ learner.retraining_count ? `${learner.retraining_count} 项需复训 · 查看 →` : '查看提交内容 →' }}</b>
          </button>
          <DetailState v-if="!visibleLearners.length" tone="empty" :title="learners.length ? '没有匹配的学员' : '暂未分配学员'" />
        </section>
      </template>
      <template v-else>
        <button class="learner-back" type="button" @click="closeLearner">‹ 返回我的学员</button>
        <header class="learner-detail-heading"><div><h1>{{ selectedLearner.learner_name }}</h1><p>{{ selectedLearner.external_ref || '未设置工号' }} · {{ selectedLearner.class_name || '未分班' }}</p></div><span>{{ selectedLearner.submitted_count }} 次提交</span></header>
        <section class="learner-stat-grid"><article><span>待评价</span><strong>{{ selectedLearner.pending_review_count }}</strong></article><article><span>已完成</span><strong>{{ selectedLearner.published_review_count }}</strong></article><article><span>需复训</span><strong>{{ selectedLearner.retraining_count }}</strong></article></section>
        <DetailState v-if="submissionsLoading" tone="loading" title="正在加载提交内容" />
        <DetailState v-else-if="submissionsError" tone="error" title="提交内容加载失败" action-label="重新加载" @action="reloadLearnerSubmissions" />
        <section v-else-if="learnerSubmissions.length" class="submission-list">
          <button v-for="item in learnerSubmissions" :key="keyOf(item)" type="button" :disabled="item.ai_status !== 'completed'" @click="openLearnerSubmission(item)">
            <span><small>{{ item.review_type === 'practice' ? '练习' : '考试' }} · {{ formatDate(item.submitted_at) }}</small><strong>{{ item.content_title || item.task_title }}</strong><small>{{ item.task_title }}</small></span>
            <b :class="{ warn:item.priority === 'retraining' || item.review_status !== 'published' }">{{ submissionStatus(item) }}</b>
          </button>
        </section>
        <DetailState v-else tone="empty" title="该学员尚未提交训练内容" />
      </template>
    </section>

    <section v-else-if="section === 'profile'" class="teacher-page teacher-profile">
      <header class="profile-greeting">
        <span>我的</span>
        <h1>亲爱的{{ teacherName }}，您辛苦了</h1>
        <p>每一次认真反馈，都在帮助学员不断进步</p>
      </header>

      <p v-if="dashboardError" class="dashboard-notice" role="status">工作数据暂时无法完整读取，未取到的历史统计以“—”显示。<button type="button" @click="loadDashboard">重试</button></p>

      <section class="teacher-profile-card work-overview" aria-labelledby="work-overview-title">
        <header><h2 id="work-overview-title">工作概况</h2><button type="button" @click="openPublished">工作记录 →</button></header>
        <div class="overview-grid">
          <article><span>累计评价</span><strong class="blue">{{ dashboardMetric('total_evaluations') }}</strong><small>次</small></article>
          <article><span>本月评价</span><strong>{{ dashboardMetric('month_evaluations') }}</strong><small>次</small></article>
          <article><span>累计辅导</span><strong>{{ dashboardMetric('total_mentored') }}</strong><small>人</small></article>
          <article><span>当前带教</span><strong class="orange">{{ currentMentoring }}</strong><small>人</small></article>
        </div>
        <p class="week-note">本周已完成 {{ dashboardMetric('week_completed') }} 次评价</p>
      </section>

      <section class="teacher-profile-card mentoring-progress" aria-labelledby="mentoring-title">
        <header><h2 id="mentoring-title">带教进展</h2><button type="button" @click="go('students')">查看全部 →</button></header>
        <div class="mentoring-counts"><article><span>已通过考核</span><strong class="green">{{ dashboardMetric('passed_mentoring') }} 人</strong></article><article><span>辅导中</span><strong class="orange">{{ activeMentoring }} 人</strong></article></div>
        <p class="mentoring-summary">已有 {{ dashboardMetric('passed_mentoring') }} 位学员完成考核，{{ activeMentoring }} 位学员仍在辅导中</p>
        <div class="recent-passed">
          <h3>最近通过</h3>
          <template v-if="dashboard?.recent_passed.length">
            <p v-for="item in dashboard.recent_passed" :key="item.learner_id"><strong>{{ item.learner_name }}</strong><span>{{ formatPassedDate(item.passed_at) }}通过</span></p>
          </template>
          <p v-else class="recent-empty">暂无已通过记录</p>
        </div>
      </section>

      <p class="thanks-note">感谢您的耐心指导与认真评价</p>
    </section>

    <nav v-if="!detailOpen && !submitted" class="teacher-nav" aria-label="教员端主导航"><button v-for="item in nav" :key="item.key" :class="{ active:section === item.key }" :aria-current="section === item.key ? 'page' : undefined" @click="go(item.key)">{{ item.label }}</button></nav>
  </main>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onBeforeUnmount, onMounted, ref, watch, type PropType } from 'vue'
import { isAxiosError } from 'axios'
import { useRoute, useRouter } from 'vue-router'
import InstructorReviewWorkspace from '@/components/InstructorReviewWorkspace.vue'
import { cabinlingoApi, type InstructorDashboard, type InstructorLearner, type InstructorQueueItem, type InstructorReviewDetail, type InstructorReviewPayload } from '@/api'
import { useSessionStore } from '@/stores/session'

type Section = 'home' | 'evaluations' | 'students' | 'profile'
type Filter = 'pending' | 'retraining' | 'published'
type ReviewSubmitEvent = { payload: InstructorReviewPayload; audioBlob: Blob | null; audioDurationMs: number; hasText: boolean; hasAudio: boolean }
type DashboardMetricKey = Exclude<keyof InstructorDashboard, 'recent_passed'>

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const queue = ref<InstructorQueueItem[]>([])
const learners = ref<InstructorLearner[]>([])
const dashboard = ref<InstructorDashboard | null>(null)
const selected = ref<InstructorQueueItem | null>(null)
const detail = ref<InstructorReviewDetail | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const saving = ref(false)
const queueError = ref('')
const dashboardError = ref('')
const detailError = ref('')
const detailOpen = ref(false)
const submitted = ref(false)
const submittedLabel = ref('')
const submittedHasText = ref(false)
const submittedHasAudio = ref(false)
const learnersLoading = ref(false)
const learnersError = ref('')
const selectedLearner = ref<InstructorLearner | null>(null)
const learnerSubmissions = ref<InstructorQueueItem[]>([])
const submissionsLoading = ref(false)
const submissionsError = ref('')
const filter = ref<Filter>('pending')
const search = ref('')
const studentFilter = ref('')
const audioUrl = ref('')
const audioLoading = ref(false)

const TeacherHeader = defineComponent({
  props: { title: { type: String, required: true }, subtitle: { type: String, required: true } },
  setup(props) {
    return () => h('header', { class: 'teacher-header' }, [
      h('div', [h('h1', props.title), h('p', props.subtitle)]),
      h('button', { onClick: logout, 'aria-label': '退出登录' }, '退出'),
    ])
  },
})
const DetailState = defineComponent({
  emits: ['action'],
  props: {
    tone: { type: String as PropType<'loading' | 'empty' | 'error'>, default: 'empty' },
    title: { type: String, required: true },
    actionLabel: { type: String, default: '' },
  },
  setup(props, { emit }) {
    return () => h('section', { class: ['detail-state', props.tone] }, [
      h('b', props.tone === 'loading' ? '…' : props.tone === 'error' ? '!' : '✓'),
      h('h2', props.title),
      props.actionLabel ? h('button', { onClick: () => emit('action') }, props.actionLabel) : null,
    ])
  },
})

const nav: Array<{ key: Section; label: string }> = [
  { key: 'home', label: '首页' },
  { key: 'evaluations', label: '评价' },
  { key: 'students', label: '学员' },
  { key: 'profile', label: '我的' },
]
const section = computed<Section>(() => ['evaluations', 'students', 'profile'].includes(String(route.params.section)) ? String(route.params.section) as Section : 'home')
const pending = computed(() => queue.value.filter(item => item.review_status !== 'published' && item.priority !== 'retraining'))
const retraining = computed(() => queue.value.filter(item => item.review_status !== 'published' && item.priority === 'retraining'))
const published = computed(() => queue.value.filter(item => item.review_status === 'published'))
const priorities = computed(() => [...retraining.value, ...pending.value].slice(0, 2))
const teacherName = computed(() => {
  let value = session.displayName.trim().replace(/\s+/g, '')
  const departmentMarker = '客舱服务部'
  const departmentIndex = value.lastIndexOf(departmentMarker)
  if (departmentIndex >= 0) value = value.slice(departmentIndex + departmentMarker.length)
  value = value.replace(/^[·•,，:：\-—_]+|(?:老师|教员|教师)$/g, '')
  if (!value) return '老师'
  const compoundSurnames = ['欧阳', '司马', '上官', '诸葛', '东方', '皇甫', '尉迟', '公孙', '慕容', '司徒', '司空', '夏侯']
  const surname = compoundSurnames.find(item => value.startsWith(item)) || Array.from(value)[0]
  return `${surname}老师`
})
const daypartGreeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 5) return '夜深了'
  if (hour < 12) return '早上好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})
const todayLabel = computed(() => {
  const now = new Date()
  return `${now.getMonth() + 1}月${now.getDate()}日`
})
const pendingCount = computed(() => dashboard.value?.pending_reviews ?? pending.value.length)
const retrainingCount = computed(() => dashboard.value?.retraining_followups ?? retraining.value.length)
const currentMentoring = computed(() => dashboard.value?.current_mentoring ?? learners.value.length)
const activeMentoring = computed(() => dashboard.value?.active_mentoring ?? currentMentoring.value)
const weeklyCompletedLabel = computed(() => dashboard.value ? `${dashboard.value.week_completed} / ${dashboard.value.week_total}` : '— / —')
const weeklyRate = computed(() => {
  const total = dashboard.value?.week_total || 0
  return total ? Math.min(100, Math.round((dashboard.value?.week_completed || 0) / total * 100)) : 0
})
const filters = computed(() => [
  { key: 'pending' as const, label: '待评价', count: pending.value.length },
  { key: 'retraining' as const, label: '需复训', count: retraining.value.length },
  { key: 'published' as const, label: '已完成', count: published.value.length },
])
const evaluationItems = computed(() => {
  let items = filter.value === 'pending' ? pending.value : filter.value === 'retraining' ? retraining.value : published.value
  if (studentFilter.value) items = items.filter(item => item.learner_id === studentFilter.value)
  return items
})
const visibleLearners = computed(() => {
  const query = search.value.toLowerCase()
  return learners.value.filter(item => !query || item.learner_name.toLowerCase().includes(query) || (item.external_ref || '').toLowerCase().includes(query))
})
const recording = computed(() => detail.value?.recordings[0] || null)

watch(section, value => {
  submitted.value = false
  closeWorkspace()
  if (value !== 'students') closeLearner()
})
onMounted(initialize)
onBeforeUnmount(revokeAudio)

async function initialize() {
  loading.value = true
  queueError.value = ''
  await Promise.all([loadQueue(), loadLearners(), loadDashboard()])
  loading.value = false
}
async function loadQueue() {
  try { queue.value = canonicalQueue(await cabinlingoApi.instructorQueue()) }
  catch (error) { queueError.value = errorText(error, '评价任务') }
}
async function loadLearners() {
  learnersLoading.value = true
  learnersError.value = ''
  try { learners.value = await cabinlingoApi.instructorLearners() }
  catch (error) { learnersError.value = errorText(error, '学员名单') }
  finally { learnersLoading.value = false }
}
async function loadDashboard() {
  dashboardError.value = ''
  try { dashboard.value = await cabinlingoApi.instructorDashboard() }
  catch (error) { dashboard.value = null; dashboardError.value = errorText(error, '工作数据') }
}
async function loadDetail(item: InstructorQueueItem, open: boolean) {
  selected.value = item
  detailLoading.value = true
  detailError.value = ''
  revokeAudio()
  if (open) detailOpen.value = true
  try { detail.value = await cabinlingoApi.instructorReview(item.review_type, item.target_id) }
  catch (error) { detail.value = null; detailError.value = errorText(error, '评价详情') }
  finally { detailLoading.value = false }
}
function retryDetail() { if (selected.value) void loadDetail(selected.value, true) }
function closeWorkspace() { detailOpen.value = false; detailError.value = ''; revokeAudio() }
function keyOf(item: InstructorQueueItem) { return `${item.review_type}:${item.target_id}` }
function isSelected(item: InstructorQueueItem) { return selected.value?.target_id === item.target_id && selected.value?.review_type === item.review_type }
function statusOf(item: InstructorQueueItem) { return item.review_status === 'published' ? '已完成' : item.priority === 'retraining' ? '需要复训' : '待教员评价' }
function canonicalQueue(items: InstructorQueueItem[]) {
  const latest = new Map<string, InstructorQueueItem>()
  for (const item of items) {
    if (item.ai_status !== 'completed') continue
    const key = [item.review_type, item.learner_id, item.assignment_id, item.content_title || item.task_title].join(':')
    const current = latest.get(key)
    if (!current || new Date(item.submitted_at).getTime() > new Date(current.submitted_at).getTime()) latest.set(key, item)
  }
  return [...latest.values()]
}
function dashboardMetric(key: DashboardMetricKey) { return dashboard.value?.[key] ?? '—' }
function priorityBadge(item: InstructorQueueItem) { return item.priority === 'retraining' ? '复训' : item.priority === 'overdue' ? '临近截止' : '待评价' }
function priorityMeta(item: InstructorQueueItem) { return `${item.review_type === 'practice' ? '训练' : '考核'} · ${formatDate(item.submitted_at)}提交` }
function go(value: Section) { if (section.value !== value) void router.push(`/instructor/${value}`) }
function openFromHome(item: InstructorQueueItem) { filter.value = item.priority === 'retraining' ? 'retraining' : 'pending'; void router.push('/instructor/evaluations').then(() => loadDetail(item, true)) }
function openPublished() { filter.value = 'published'; void router.push('/instructor/evaluations') }
async function openLearnerFromQueue(item: InstructorQueueItem) {
  const learner = learners.value.find(candidate => candidate.learner_id === item.learner_id)
  if (learner) await router.push('/instructor/students').then(() => openLearner(learner))
  else await router.push('/instructor/students')
}
async function openCurrentLearner() { if (selected.value) await openLearnerFromQueue(selected.value) }
async function openLearner(learner: InstructorLearner) {
  selectedLearner.value = learner
  learnerSubmissions.value = []
  submissionsLoading.value = true
  submissionsError.value = ''
  try { learnerSubmissions.value = await cabinlingoApi.instructorLearnerSubmissions(learner.learner_id) }
  catch (error) { submissionsError.value = errorText(error, '学员提交记录') }
  finally { submissionsLoading.value = false }
}
function reloadLearnerSubmissions() { if (selectedLearner.value) void openLearner(selectedLearner.value) }
function closeLearner() { selectedLearner.value = null; learnerSubmissions.value = []; submissionsError.value = '' }
function openLearnerSubmission(item: InstructorQueueItem) {
  if (item.ai_status !== 'completed') return
  studentFilter.value = item.learner_id
  filter.value = item.review_status === 'published' ? 'published' : item.priority === 'retraining' ? 'retraining' : 'pending'
  if (!queue.value.some(candidate => keyOf(candidate) === keyOf(item))) queue.value = [item, ...queue.value]
  void router.push('/instructor/evaluations').then(() => loadDetail(item, true))
}
function submissionStatus(item: InstructorQueueItem) { if (item.ai_status !== 'completed') return 'AI 分析中'; return statusOf(item) }
function returnToQueue() { submitted.value = false; closeWorkspace(); filter.value = 'pending'; void Promise.all([loadQueue(), loadDashboard()]) }
function logout() { session.signOut(); void router.replace('/login') }
function formatDate(value: string) { try { return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) } catch { return value } }
function formatPassedDate(value: string) { try { const date = new Date(value); return `${date.getMonth() + 1}月${date.getDate()}日` } catch { return value } }
async function loadAudio() {
  if (!recording.value || audioLoading.value) return
  audioLoading.value = true
  try { audioUrl.value = URL.createObjectURL(await cabinlingoApi.protectedAudio(recording.value.audio_url)) }
  catch { detailError.value = '学员录音暂时无法读取，评分内容仍可查看。' }
  finally { audioLoading.value = false }
}
function revokeAudio() { if (audioUrl.value) URL.revokeObjectURL(audioUrl.value); audioUrl.value = '' }
async function publishReview(event: ReviewSubmitEvent) {
  if (!detail.value || saving.value) return
  saving.value = true
  detailError.value = ''
  try {
    let payload = event.payload
    if (event.audioBlob) {
      const uploaded = await cabinlingoApi.uploadInstructorFeedbackAudio(detail.value.review_type, detail.value.target_id, event.audioBlob, event.audioDurationMs)
      payload = { ...payload, evidence: { ...payload.evidence, feedback_audio: uploaded } }
    }
    await cabinlingoApi.publishInstructorReview(detail.value.review_type, detail.value.target_id, payload)
    submittedLabel.value = `${detail.value.learner_name} · ${detail.value.content_title || detail.value.task_title}`
    submittedHasText.value = event.hasText
    submittedHasAudio.value = event.hasAudio
    submitted.value = true
    detailOpen.value = false
    const item = queue.value.find(isSelected)
    if (item) item.review_status = 'published'
  } catch (error) { detailError.value = errorText(error, '评价提交') }
  finally { saving.value = false }
}
function errorText(error: unknown, subject: string) {
  if (isAxiosError(error)) {
    if (error.response?.status === 401) return '登录已失效，请重新登录。'
    if (error.response?.status === 403) return `当前账号无权访问${subject}。`
    if (error.response?.status === 413) return '录音文件过大，请缩短录制后重试。'
    if (error.response?.status === 415) return '当前录音格式不受支持，请更换浏览器重试。'
    if (!error.response) return `${subject}网络连接失败，请检查网络后重试。`
  }
  return `${subject}失败，请稍后重试。`
}
</script>

<style scoped>
.teacher-app{--bg:#f6f9fc;--blue:#1459d1;--ink:#121a29;--muted:#616e80;--line:#e0e8f2;--orange:#f28c1f;--green:#14a166;--red:#e83847;min-height:100dvh;padding-bottom:calc(104px + env(safe-area-inset-bottom));color:var(--ink);background:var(--bg)}button,input,textarea{font:inherit}.teacher-page{width:min(100%,834px);min-height:100dvh;margin:auto;padding:26px 20px 80px}.teacher-header{display:flex;justify-content:space-between;margin-bottom:28px;padding:0 4px}.teacher-header h1{margin:0;font-size:30px}.teacher-header p{margin:2px 0;color:var(--muted);font-size:15px}.teacher-header button,.back,.mobile-back{min-width:44px;min-height:44px;color:var(--muted);background:transparent}.card{border-radius:24px;background:#fff;box-shadow:0 10px 30px #0d1a3308}.today-hero{position:relative;min-height:180px;padding:22px;border-radius:28px;color:#fff;background:var(--blue);box-shadow:0 18px 34px #1459d126}.today-hero span,.today-hero strong,.today-hero b{display:block}.today-hero strong{font-size:49px}.today-hero b{font-size:17px}.today-hero button{position:absolute;right:20px;bottom:20px;min-height:44px;color:#fff;background:transparent}.home-grid{display:grid;gap:20px;margin-top:20px}.weekly,.priority{padding:20px}.weekly h2,.priority h2{margin:0 0 16px;font-size:19px}.weekly>strong,.weekly>b{display:block}.weekly>strong{font-size:27px}.weekly>b{margin-top:10px;color:var(--blue);font-size:20px}.priority>button{display:grid;width:100%;min-height:58px;padding:8px 0;text-align:left;background:transparent}.priority span{color:var(--muted)}.warn{color:var(--orange)!important}
.teacher-home,.teacher-profile{width:min(100%,390px);padding:24px 20px calc(132px + env(safe-area-inset-bottom))}.dynamic-greeting{display:grid;gap:6px;margin:0 4px 21px}.dynamic-greeting h1,.dynamic-greeting p{overflow-wrap:anywhere;margin:0}.dynamic-greeting h1{font-size:30px;line-height:1.2}.dynamic-greeting p{color:var(--muted);font-size:14px;line-height:17px}.today-work{min-height:180px;padding:18px 20px;border-radius:26px;color:#fff;background:var(--blue);overflow:hidden}.today-work header,.home-card>header,.teacher-profile-card>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.today-work h2,.home-card h2,.teacher-profile-card h2{margin:0}.today-work h2{font-size:16px}.today-work button,.home-card header button,.teacher-profile-card header button{min-height:32px;padding:0;border:0;color:inherit;background:transparent;font-size:12px;font-weight:700}.today-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));margin-top:10px}.today-metrics article{min-width:0}.today-metrics span,.today-metrics strong{display:block}.today-metrics span{color:#e0edff;font-size:12px}.today-metrics strong{margin-top:4px;font-size:28px;line-height:1.2}.today-metrics article:first-child strong{font-size:34px}.today-work>p{margin:34px 0 0;color:#e0edff;font-size:12px;line-height:1.25}.home-card{margin-top:16px;border-radius:24px;background:#fff}.priority-card{min-height:228px;padding:16px 18px 6px}.priority-card h2{font-size:19px}.priority-card header button{color:var(--blue)}.priority-list{margin-top:4px}.priority-list>button{display:grid;grid-template-columns:minmax(0,1fr) 88px;align-items:start;gap:10px;width:100%;min-height:86px;padding:10px 0;border:0;border-bottom:1px solid var(--line);text-align:left;background:transparent}.priority-list>button:last-child{border-bottom:0}.priority-copy{min-width:0}.priority-copy strong,.priority-copy small{display:block;overflow-wrap:anywhere}.priority-copy strong{font-size:15px;line-height:1.35}.priority-copy small{margin-top:5px;color:var(--muted);font-size:11px;line-height:1.4}.priority-action{display:grid;justify-items:end;gap:17px}.priority-action b{min-width:80px;padding:5px 8px;border-radius:12px;color:var(--blue);background:#e5f2ff;font-size:11px;font-weight:700;text-align:center}.priority-action b.retraining{color:var(--orange);background:#fff5e3}.priority-action b.overdue{color:var(--red);background:#fff0f2}.priority-action em{color:var(--blue);font-size:12px;font-style:normal;font-weight:700;white-space:nowrap}.home-empty{display:grid;place-items:center;min-height:150px;margin:0;color:var(--muted);font-size:13px}.weekly-card{min-height:150px;padding:16px 18px}.weekly-card h2{font-size:18px}.weekly-metrics{display:grid;grid-template-columns:1.2fr 1fr .82fr;margin-top:6px}.weekly-metrics span,.weekly-metrics strong{display:block}.weekly-metrics span{color:var(--muted);font-size:12px}.weekly-metrics strong{margin-top:2px;font-size:24px;white-space:nowrap}.weekly-metrics .orange,.overview-grid .orange,.mentoring-counts .orange{color:var(--orange)}.weekly-metrics .green,.mentoring-counts .green{color:var(--green)}.weekly-progress{height:8px;margin-top:10px;border-radius:4px;background:#ebf0f7;overflow:hidden}.weekly-progress i{display:block;height:100%;border-radius:inherit;background:var(--blue)}.weekly-card>p{margin:4px 0 0;color:var(--muted);font-size:11px;text-align:right}
.profile-greeting{margin:0 4px 22px}.profile-greeting span{display:block;color:var(--blue);font-size:13px;font-weight:700}.profile-greeting h1,.profile-greeting p{overflow-wrap:anywhere;margin:0}.profile-greeting h1{margin-top:7px;font-size:25px;line-height:1.2}.profile-greeting p{margin-top:6px;color:var(--muted);font-size:13px;line-height:16px}.dashboard-notice{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:-12px 0 10px;padding:9px 12px;border-radius:12px;color:#9a5b0b;background:#fff5e3;font-size:11px;line-height:1.4}.dashboard-notice button{flex:none;border:0;color:var(--blue);background:transparent;font-weight:700}.teacher-profile-card{border-radius:22px;background:#fff}.work-overview{min-height:220px;padding:16px 18px 8px}.teacher-profile-card h2{font-size:18px}.teacher-profile-card header button{color:var(--blue)}.overview-grid{display:grid;grid-template-columns:1fr 1fr;row-gap:18px;margin-top:16px}.overview-grid article{display:grid;grid-template-columns:auto 1fr;align-items:end}.overview-grid span{grid-column:1/-1;color:var(--muted);font-size:11px}.overview-grid strong{margin-top:3px;font-size:25px;line-height:30px}.overview-grid strong.blue{color:var(--blue)}.overview-grid small{align-self:end;margin:0 0 3px 4px;color:var(--muted);font-size:11px}.week-note{margin:7px 0 0;padding:5px 12px;border-radius:12px;color:var(--blue);background:#e5f2ff;font-size:11px;font-weight:700}.mentoring-progress{min-height:310px;margin-top:10px;padding:16px 18px 10px}.mentoring-counts{display:grid;grid-template-columns:114px 1fr;margin-top:16px}.mentoring-counts span,.mentoring-counts strong{display:block}.mentoring-counts span{color:var(--muted);font-size:11px}.mentoring-counts strong{margin-top:3px;font-size:24px}.mentoring-summary{overflow-wrap:anywhere;margin:6px 0 0;color:var(--muted);font-size:12px;line-height:1.5}.recent-passed{margin-top:13px;padding-top:13px;border-top:1px solid var(--line)}.recent-passed h3{margin:0 0 7px;font-size:13px}.recent-passed p{display:grid;grid-template-columns:76px 1fr;min-height:34px;align-items:center;margin:0;font-size:13px}.recent-passed p strong{overflow-wrap:anywhere}.recent-passed p span{color:var(--muted);font-size:11px}.recent-passed p.recent-empty{display:block;padding:12px 0;color:var(--muted);font-size:12px}.thanks-note{overflow-wrap:anywhere;margin:12px 0 0;padding:11px 18px;border-radius:16px;color:var(--ink);background:#fcf7eb;font-size:12px;font-weight:700;line-height:16px}
.teacher-header :deep(h1){margin:0;font-size:30px}.teacher-header :deep(p){margin:2px 0;color:var(--muted);font-size:15px}.teacher-header :deep(button){min-width:44px;min-height:44px;border-radius:18px;color:var(--muted);background:#fff;font-size:12px}
.assigned-overview{margin-top:20px;padding:20px}.assigned-overview>header{display:flex;align-items:center;justify-content:space-between;gap:14px}.assigned-overview h2,.assigned-overview p{margin:0}.assigned-overview h2{font-size:19px}.assigned-overview header p{margin-top:4px;color:var(--muted);font-size:12px}.assigned-overview>header>button{min-height:44px;color:var(--blue);background:transparent;font-weight:700;white-space:nowrap}.assigned-overview .detail-state{min-height:180px}.assigned-list{display:grid;gap:10px;margin-top:16px}.assigned-list>button{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:12px;min-height:76px;padding:12px 14px;border-radius:16px;text-align:left;background:var(--bg);touch-action:manipulation}.assigned-list span,.assigned-list strong,.assigned-list small{display:block;min-width:0}.assigned-list strong,.assigned-list small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.assigned-list strong{font-size:15px}.assigned-list small{margin-top:4px;color:var(--muted);font-size:11px}.assigned-list b{color:var(--green);font-size:12px;white-space:nowrap}.assigned-list b.idle{color:var(--muted)}
.teacher-nav{position:fixed;z-index:50;left:50%;bottom:calc(18px + env(safe-area-inset-bottom));display:grid;grid-template-columns:repeat(4,1fr);width:min(358px,calc(100% - 32px));min-height:72px;padding:6px;border-radius:28px;background:#fffffff5;box-shadow:0 12px 30px #0d1a331c;transform:translateX(-50%);backdrop-filter:blur(16px)}.teacher-nav button{min-height:50px;border-radius:22px;color:#6b7585;background:transparent;font-size:12px}.teacher-nav button.active{color:var(--blue);background:#e5f2ff;font-weight:700;box-shadow:0 4px 12px #1459d11a}
.evaluations.workspace-open{width:100%;max-width:none;padding:0}.evaluation-layout{display:grid;gap:18px}.evaluation-list{padding:4px 0;background:transparent;box-shadow:none}.filters{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;overflow:auto;margin-bottom:20px;padding:4px;border-radius:18px;background:#fff}.filters button{min-height:40px;padding:0 10px;border:0;border-radius:14px;color:var(--ink);background:transparent;white-space:nowrap}.filters button.active{color:var(--ink);background:#e8f2ff;font-weight:700}.evaluation-item{display:grid;width:100%;min-height:122px;padding:16px 18px;border-radius:22px;text-align:left;background:#fff}.evaluation-item+.evaluation-item{margin-top:18px}.evaluation-item strong{font-size:17px}.evaluation-item>span{margin-top:8px;color:var(--orange)}.evaluation-item footer{display:flex;justify-content:space-between;gap:12px;margin-top:14px}.evaluation-item footer button{min-height:36px;padding:0;border:0;color:var(--blue);background:transparent;font-size:13px;font-weight:700}.evaluation-item.active{box-shadow:inset 0 0 0 2px #1459d12e}.evaluation-pane{display:none;padding:20px}.detail-open .evaluation-list{display:none}.detail-open .evaluation-pane{display:block}.compact-heading h2{margin:8px 0 4px;font-size:24px}.compact-heading span{color:var(--muted)}.evaluation-pane .audio-evidence-player{margin-top:18px}.compact-score{display:block;margin:20px 0;color:var(--orange);font-size:22px}.compact-issues p{color:var(--orange)}.detail-link{min-height:44px;color:var(--blue);background:transparent;font-weight:700}
.reading-evidence{margin-top:18px;padding:16px;border:1px solid var(--line);border-radius:20px;background:#f8fbff}.reading-evidence>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.reading-evidence h3,.reading-evidence h4,.reading-evidence header p{margin:0}.reading-evidence h3{font-size:17px}.reading-evidence header p{margin-top:4px;color:var(--muted);font-size:12px}.reading-evidence header>span{flex:none;padding:5px 9px;border-radius:999px;color:var(--blue);background:#e8f2ff;font-size:11px;font-weight:700}.reading-evidence>div{display:grid;gap:10px;margin-top:14px}.reading-evidence article{min-width:0;padding:14px;border:1px solid var(--line);border-radius:14px;background:#fff}.reading-evidence h4{color:var(--blue);font-size:13px}.reading-evidence article p{margin:8px 0 0;color:#324863;font-size:14px;line-height:1.75;white-space:pre-wrap;overflow-wrap:anywhere}.assessment-reading{margin-top:16px}
.feedback-form{margin-top:24px;padding:16px;border-radius:24px;background:#fff;box-shadow:0 10px 30px #0d1a3308}.feedback-form header{display:grid;grid-template-columns:1fr auto 44px;align-items:center;gap:8px}.feedback-form h2{margin:0;font-size:16px}.feedback-form header span{color:var(--muted);font-size:11px}.feedback-form header button{width:44px;height:44px;border-radius:22px;background:#e8f2ff}.feedback-form textarea{width:100%;min-height:92px;margin-top:8px;padding:12px;border:0;border-radius:16px;background:var(--bg);resize:vertical;outline:none}.feedback-form textarea:focus{box-shadow:0 0 0 3px #1459d126}.form-message{color:var(--muted);font-size:12px}.feedback-form footer{display:grid;grid-template-columns:1fr 1.25fr;gap:8px;margin-top:12px}.feedback-form footer button{min-height:44px;border-radius:16px;font-weight:700}.feedback-form .pass{color:#1a9e61;background:#ebfaf2}.feedback-form .retrain{color:#eb7a14;background:#fff5e5}.feedback-form footer button.active{box-shadow:inset 0 0 0 2px currentColor}.feedback-form .submit{grid-column:1/-1;color:#fff;background:var(--blue)}.feedback-form .submit:disabled{opacity:.48}
.feedback-form :deep(header){display:grid;grid-template-columns:1fr auto 44px;align-items:center;gap:8px}.feedback-form :deep(h2){margin:0;font-size:16px}.feedback-form :deep(header span){color:var(--muted);font-size:11px}.feedback-form :deep(header button){width:44px;height:44px;border-radius:22px;background:#e8f2ff}.feedback-form :deep(textarea){width:100%;min-height:92px;margin-top:8px;padding:12px;border:0;border-radius:16px;background:var(--bg);resize:vertical;outline:none}.feedback-form :deep(textarea:focus){box-shadow:0 0 0 3px #1459d126}.feedback-form :deep(.form-message){color:var(--muted);font-size:12px}.feedback-form :deep(footer){display:grid;grid-template-columns:1fr 1.25fr;gap:8px;margin-top:12px}.feedback-form :deep(footer button){min-height:44px;border-radius:16px;font-weight:700}.feedback-form :deep(.pass){color:#1a9e61;background:#ebfaf2}.feedback-form :deep(.retrain){color:#eb7a14;background:#fff5e5}.feedback-form :deep(footer button.active){box-shadow:inset 0 0 0 2px currentColor}.feedback-form :deep(.submit){grid-column:1/-1;color:#fff;background:var(--blue)}.feedback-form :deep(.submit:disabled){opacity:.48}
.state{min-height:340px;display:grid;align-content:center;gap:26px;padding:40px 24px;border-radius:28px;text-align:center;background:#fff}.state>i{height:52px;border-radius:16px;background:#edf0f5;animation:pulse 1.4s ease-in-out infinite}.state>i:nth-child(2){animation-delay:.12s}.state>i:nth-child(3){animation-delay:.24s}.state p{color:var(--muted)}.state b,.detail-state b{display:grid;place-items:center;width:100px;height:100px;margin:auto;border-radius:50%;color:var(--blue);background:#e8f2ff;font-size:42px}.state button,.detail-state button{min-height:54px;border:0;border-radius:18px;color:#fff;background:var(--blue)}.state.error b{color:var(--red);background:#ffedf0}.detail-state{min-height:280px;display:grid;place-items:center;align-content:center;gap:18px;text-align:center}.detail-state b{width:72px;height:72px;font-size:28px}.detail-state h2{margin:0}.submitted>h1{margin:18px 4px 4px;font-size:28px}.submitted>p{margin:0 4px;color:var(--muted)}.submitted-card{min-height:386px;display:grid;place-items:center;align-content:center;gap:18px;margin-top:42px;padding:28px 16px;border-radius:28px;background:#fff}.submitted-card>span{display:grid;place-items:center;width:100px;height:100px;border-radius:50%;color:var(--green);background:#e8f2ff;font-size:42px}.submitted-card h2,.submitted-card p{margin:0}.submitted-card button{min-height:44px;border:0;color:var(--blue);background:transparent;font-weight:700}.submitted-summary{display:grid;gap:12px;width:100%;margin-top:2px;padding:14px;border:1px solid var(--line);border-radius:14px}.submitted-summary b{display:flex;justify-content:space-between;font-size:13px}.submitted-summary em{color:var(--green);font-style:normal}
.detail-state :deep(b){display:grid;place-items:center;width:72px;height:72px;margin:auto;border-radius:50%;color:var(--blue);background:#e8f2ff;font-size:28px}.detail-state :deep(h2){margin:0}.detail-state :deep(button){min-width:160px;min-height:54px;border-radius:18px;color:#fff;background:var(--blue)}
.assessment-detail>header{margin:6px 4px 20px}.assessment-detail>header h1{margin:0}.assessment-detail>header p{color:var(--muted)}.assessment-summary{display:grid;grid-template-columns:80px repeat(2,1fr);gap:16px;align-items:center;padding:22px}.assessment-summary>div{grid-row:1/3}.assessment-summary>div strong,.assessment-summary>div span,.assessment-summary article span,.assessment-summary article strong{display:block}.assessment-summary>div strong{color:var(--blue);font-size:46px}.assessment-summary article span{color:var(--muted);font-size:12px}.assessment-summary article strong{color:var(--blue);font-size:20px}.assessment-summary>p{grid-column:1/-1;color:var(--muted)}.issue-summary,.assessment-audio,.word-analysis{margin-top:16px;padding:18px}.issue-summary span{display:inline-block;margin-right:18px;color:var(--muted)}.issue-summary span.active{color:var(--orange);font-weight:700}.word-analysis>p{color:var(--muted)}.word-analysis>div{display:flex;flex-wrap:wrap;gap:8px}.word-analysis>div>button{min-width:62px;min-height:58px;display:grid;padding:7px;border:1px solid var(--line);border-radius:12px;text-align:left;background:#fff}.word-analysis button span{font-size:12px}.word-analysis button.good{border-color:#14a1664a}.word-analysis button.good span,.word-popover strong.good{color:var(--green)}.word-analysis button.medium{border-color:#f28c1f4a}.word-analysis button.medium span,.word-popover strong.medium{color:var(--orange)}.word-analysis button.low{border-color:#e838474a}.word-analysis button.low span,.word-popover strong.low{color:var(--red)}
.word-layer{position:fixed;z-index:100;inset:0;background:#0d1a3347}.word-popover{position:absolute;left:50%;bottom:0;width:min(390px,100%);padding:20px 20px calc(22px + env(safe-area-inset-bottom));border-radius:24px 24px 0 0;background:#fff;transform:translateX(-50%);outline:none}.word-popover>button{position:absolute;right:16px;top:14px;width:44px;height:44px;border-radius:50%;background:#f1f5fa}.word-popover>strong{font-size:22px}.word-popover>div{display:grid;grid-template-columns:1fr 1fr;gap:10px}.word-popover>div button{min-height:44px;border-radius:14px;color:var(--blue);background:#e8f2ff}.search{width:100%;min-height:50px;padding:0 18px;border:0;border-radius:18px;background:#fff}.student-list{display:grid;gap:14px;margin-top:20px}.student-list>button{display:grid;gap:8px;min-height:112px;padding:16px 18px;border-radius:22px;text-align:left;background:#fff;box-shadow:0 10px 30px #0d1a3308;touch-action:manipulation}.student-list strong{font-size:18px}.student-list span{color:var(--muted)}.student-list b{color:var(--blue)}.student-identity strong,.student-identity small{display:block}.student-identity small{margin-top:4px;color:var(--muted);font-size:12px}.learner-back{min-height:44px;padding:0 4px;color:var(--blue);background:transparent;font-weight:700}.learner-detail-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:12px 4px 20px}.learner-detail-heading h1,.learner-detail-heading p{margin:0}.learner-detail-heading p{margin-top:4px;color:var(--muted)}.learner-detail-heading>span{color:var(--blue);font-weight:700}.learner-stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:18px}.learner-stat-grid article{padding:14px;border-radius:18px;background:#fff;box-shadow:0 8px 24px #0d1a3308}.learner-stat-grid span,.learner-stat-grid strong{display:block}.learner-stat-grid span{color:var(--muted);font-size:11px}.learner-stat-grid strong{margin-top:4px;color:var(--blue);font-size:24px}.submission-list{display:grid;gap:12px}.submission-list>button{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:14px;min-height:96px;padding:15px 17px;border-radius:20px;text-align:left;background:#fff;box-shadow:0 10px 30px #0d1a3308;touch-action:manipulation}.submission-list>button:disabled{cursor:not-allowed;opacity:.65}.submission-list span{min-width:0}.submission-list strong,.submission-list small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.submission-list strong{margin:4px 0;font-size:16px}.submission-list small{color:var(--muted);font-size:11px}.submission-list b{color:var(--green);font-size:12px;white-space:nowrap}
@media(min-width:700px){.teacher-app{padding-bottom:118px}.teacher-page{padding:38px 32px 80px}.teacher-home,.teacher-profile{padding:24px 20px calc(132px + env(safe-area-inset-bottom))}.today-hero{min-height:206px;padding:26px 28px}.home-grid{grid-template-columns:1fr 1fr}.weekly{min-height:230px}.priority{min-height:320px}.assigned-list{grid-template-columns:repeat(2,minmax(0,1fr))}.teacher-nav{width:min(802px,calc(100% - 32px))}.evaluation-layout{grid-template-columns:300px minmax(0,1fr)}.evaluation-list{display:block!important}.evaluation-pane{display:block;min-height:760px}.mobile-back{display:none}.detail-open .evaluation-list{display:block}.reading-evidence>div{grid-template-columns:repeat(2,minmax(0,1fr))}.assessment-summary{grid-template-columns:96px repeat(4,1fr);min-height:188px}.assessment-summary>div{grid-row:auto}.feedback-form footer{grid-template-columns:88px 112px minmax(118px,1fr)}.feedback-form .submit{grid-column:auto}.feedback-form :deep(footer){grid-template-columns:88px 112px minmax(118px,1fr)}.feedback-form :deep(.submit){grid-column:auto}.word-popover{left:auto;right:calc(50% - 370px);bottom:auto;top:50%;width:292px;border-radius:22px;transform:translateY(-50%)}.student-list>button{grid-template-columns:minmax(0,1fr) auto auto;align-items:center}.student-list>button>span:not(.student-identity),.student-list>button>b{justify-self:end}}
@keyframes pulse{50%{opacity:.45}}@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
