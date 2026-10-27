<template>
  <section class="task-panel" :class="{ 'task-panel--compact': compact }">
    <template v-if="!compact">
      <div class="task-panel__heading">
        <div>
          <p class="page-kicker">TASK OPERATIONS</p>
          <h2>任务发布与进度</h2>
          <p>草稿仅管理员可见；发布后学员可学习；删除后管理端和学员端均不再显示。</p>
        </div>
        <div class="task-panel__create">
          <button type="button" class="outline-button" @click="$emit('create', 'practice')">+ 新建练习</button>
          <button type="button" class="primary-button primary-button--compact" @click="$emit('create', 'exam')">+ 新建考试</button>
        </div>
      </div>

      <div class="task-summary" aria-label="任务状态统计">
        <button v-for="item in summaryItems" :key="item.value" type="button" :class="{ active: statusFilter === item.value }" @click="statusFilter = item.value">
          <strong>{{ item.count }}</strong><span>{{ item.label }}</span>
        </button>
      </div>

      <div class="task-filters" role="search">
        <label class="search-field"><span class="sr-only">搜索任务</span><input v-model.trim="query" type="search" placeholder="搜索任务名称"></label>
        <label><span class="sr-only">任务类型</span><select v-model="typeFilter"><option value="all">全部类型</option><option value="practice">练习任务</option><option value="exam">考试任务</option></select></label>
        <label><span class="sr-only">内容来源</span><select v-model="sourceFilter"><option value="all">全部来源</option><option value="course">课程版本</option><option value="broadcast">广播词库</option><option value="legacy">历史广播词</option></select></label>
        <button v-if="hasFilters" type="button" class="filter-reset" @click="resetFilters">清除筛选</button>
      </div>
    </template>

    <div v-if="visibleTasks.length" class="task-list">
      <article v-for="task in visibleTasks" :key="task.id" class="task-card">
        <div class="task-card__identity">
          <span class="task-type" :class="task.task_type">{{ task.task_type === 'practice' ? '练习' : '考试' }}</span>
          <div><strong>{{ task.week_no ? `第 ${task.week_no} 周 · ` : '' }}{{ task.title }}</strong><small>{{ sourceLabel(task) }}<template v-if="task.unlock_after_task_id"> · 完成前置任务后解锁</template></small></div>
        </div>
        <div class="task-card__status">
          <span class="state-pill" :class="normalizedStatus(task.status)">{{ statusLabel(task.status) }}</span>
          <small>{{ task.due_at ? `截止 ${formatDate(task.due_at)}` : '未设置截止时间' }}</small>
        </div>
        <div class="task-card__progress">
          <div><span>完成进度</span><strong>{{ task.completed_count }} / {{ task.assignment_count }}</strong></div>
          <i aria-hidden="true"><b :style="{ width: `${completionPercent(task)}%` }"></b></i>
          <small>{{ task.assignment_count ? `${completionPercent(task)}%` : '尚未分配学员' }}</small>
        </div>
        <div class="task-card__actions">
          <button v-if="task.status === 'draft'" type="button" class="primary-action" @click="$emit('status', task, 'publish')">发布任务</button>
          <button v-else-if="task.status !== 'closed'" type="button" class="danger-action" @click="$emit('status', task, 'close')">关闭任务</button>
          <span v-else>已结束</span>
          <button type="button" class="delete-action" @click="$emit('delete', task)">删除任务</button>
        </div>
      </article>
    </div>
    <div v-else class="task-empty">
      <strong>{{ tasks.length ? '没有符合筛选条件的任务' : '还没有任务' }}</strong>
      <p>{{ tasks.length ? '调整筛选条件后再查看。' : '先创建练习或考试，保存为草稿后再发布给学员。' }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { BroadcastScript, Course, CourseVersion, TaskListItem } from '@/api'

const props = withDefaults(defineProps<{ tasks: TaskListItem[]; courses?: Course[]; courseVersions?: CourseVersion[]; broadcastScripts?: BroadcastScript[]; compact?: boolean }>(), { courses: () => [], courseVersions: () => [], broadcastScripts: () => [], compact: false })
defineEmits<{ create: [type: 'practice' | 'exam']; status: [task: TaskListItem, action: 'publish' | 'close']; delete: [task: TaskListItem] }>()

type StatusFilter = 'all' | 'active' | 'draft' | 'closed'
const query = ref('')
const typeFilter = ref<'all' | 'practice' | 'exam'>('all')
const sourceFilter = ref<'all' | 'course' | 'broadcast' | 'legacy'>('all')
const statusFilter = ref<StatusFilter>('all')

const summaryItems = computed(() => [
  { label: '全部任务', value: 'all' as StatusFilter, count: props.tasks.length },
  { label: '进行中', value: 'active' as StatusFilter, count: props.tasks.filter(task => ['published', 'open'].includes(task.status)).length },
  { label: '待发布', value: 'draft' as StatusFilter, count: props.tasks.filter(task => task.status === 'draft').length },
  { label: '已关闭', value: 'closed' as StatusFilter, count: props.tasks.filter(task => task.status === 'closed').length },
])
const visibleTasks = computed(() => props.tasks.filter(task => {
  if (query.value && !task.title.toLowerCase().includes(query.value.toLowerCase())) return false
  if (typeFilter.value !== 'all' && task.task_type !== typeFilter.value) return false
  if (statusFilter.value !== 'all' && normalizedStatus(task.status) !== statusFilter.value) return false
  if (sourceFilter.value !== 'all' && sourceType(task) !== sourceFilter.value) return false
  return true
}))
const hasFilters = computed(() => Boolean(query.value || typeFilter.value !== 'all' || sourceFilter.value !== 'all' || statusFilter.value !== 'all'))

function normalizedStatus(status: string): StatusFilter { return status === 'draft' ? 'draft' : status === 'closed' ? 'closed' : 'active' }
function statusLabel(status: string) { return status === 'draft' ? '待发布' : status === 'closed' ? '已关闭' : '进行中' }
function sourceType(task: TaskListItem): 'course' | 'broadcast' | 'legacy' { return task.broadcast_script_count > 0 || task.broadcast_script_id ? 'broadcast' : task.course_version_id ? 'course' : 'legacy' }
function sourceLabel(task: TaskListItem) {
  if (task.broadcast_script_count > 1) return `广播词组合 · ${task.broadcast_script_count} 篇`
  if (task.broadcast_script_id) return props.broadcastScripts.find(item => item.id === task.broadcast_script_id)?.title || '广播词库内容'
  if (task.course_version_id) {
    const version = props.courseVersions.find(item => item.id === task.course_version_id)
    const course = version ? props.courses.find(item => item.id === version.course_id) : null
    return version ? `${course?.title || '课程'} · ${version.version_label}` : '课程版本'
  }
  return '历史广播词'
}
function completionPercent(task: TaskListItem) { return task.assignment_count ? Math.min(100, Math.round(task.completed_count / task.assignment_count * 100)) : 0 }
function formatDate(value: string) { return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }
function resetFilters() { query.value = ''; typeFilter.value = 'all'; sourceFilter.value = 'all'; statusFilter.value = 'all' }
</script>

<style scoped>
.task-panel{min-width:0;padding:24px;border:1px solid #e5edf8;border-radius:18px;background:#fff;box-shadow:var(--shadow-card)}.task-panel__heading{display:flex;align-items:flex-start;justify-content:space-between;gap:24px}.page-kicker{margin:0 0 6px;color:var(--blue);font-size:10px;font-weight:800;letter-spacing:.14em}.task-panel__heading h2{margin:0;color:var(--ink);font-size:19px}.task-panel__heading p{margin:6px 0 0;color:var(--muted);font-size:12px;line-height:1.6}.task-panel__create{display:flex;gap:10px;flex:none}.task-panel__create button{min-height:44px}.task-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:22px 0 16px}.task-summary button{display:flex;align-items:center;gap:10px;min-height:64px;padding:13px 16px;border:1px solid var(--line);border-radius:13px;color:var(--ink-secondary);background:var(--surface-soft);text-align:left}.task-summary button.active{border-color:#8ebaff;background:var(--blue-soft);box-shadow:0 0 0 2px #dceaff}.task-summary strong{color:var(--ink);font-size:23px}.task-summary span{font-size:12px}.task-filters{display:grid;grid-template-columns:minmax(220px,1fr) 160px 160px auto;gap:10px;margin-bottom:10px}.task-filters input,.task-filters select{width:100%;min-height:44px;padding:0 12px;border:1px solid var(--line);border-radius:10px;color:var(--ink);background:#fff}.filter-reset{min-height:44px;padding:0 13px;border-radius:10px;color:var(--blue);background:var(--blue-soft)}.task-list{display:grid}.task-card{display:grid;grid-template-columns:minmax(260px,1.45fr) minmax(150px,.7fr) minmax(200px,.85fr) 210px;align-items:center;gap:20px;padding:18px 4px;border-top:1px solid var(--line)}.task-card__identity{display:flex;align-items:center;gap:13px;min-width:0}.task-card__identity>div{min-width:0}.task-card__identity strong,.task-card__identity small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.task-card__identity strong{font-size:14px}.task-card__identity small{margin-top:5px;color:var(--muted);font-size:11px}.task-type{display:grid;place-items:center;flex:none;width:46px;height:38px;border-radius:10px;color:var(--blue);background:var(--blue-soft);font-size:11px;font-weight:700}.task-type.exam{color:var(--green);background:var(--green-soft)}.task-card__status{display:grid;justify-items:start;gap:7px}.task-card__status small{color:var(--muted);font-size:10px}.state-pill{padding:6px 9px;border-radius:999px;font-size:10px;font-weight:700}.state-pill.active{color:var(--green);background:var(--green-soft)}.state-pill.draft{color:var(--amber);background:var(--amber-soft)}.state-pill.closed{color:var(--muted);background:#edf2f8}.task-card__progress>div{display:flex;justify-content:space-between;gap:12px;font-size:11px}.task-card__progress>div span{color:var(--muted)}.task-card__progress>div strong{color:var(--ink)}.task-card__progress i{display:block;height:7px;margin:8px 0 5px;overflow:hidden;border-radius:99px;background:#edf2f8}.task-card__progress i b{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--blue),#5a9cff)}.task-card__progress small{color:var(--muted);font-size:10px}.task-card__actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}.task-card__actions button{min-width:92px;min-height:40px;padding:0 12px;border-radius:9px;font-size:11px;font-weight:700}.primary-action{color:#fff;background:var(--blue)}.danger-action{color:var(--red);border:1px solid #f3c4cc;background:#fff}.delete-action{color:#fff;background:#d94a60}.task-card__actions span{color:var(--muted);font-size:11px}.task-empty{padding:60px 20px;text-align:center}.task-empty strong{color:var(--ink)}.task-empty p{margin:7px 0 0;color:var(--muted);font-size:12px}.task-panel--compact{padding:0;border:0;border-radius:0;box-shadow:none}.task-panel--compact .task-card{grid-template-columns:minmax(240px,1.4fr) minmax(140px,.7fr) minmax(180px,.8fr) 210px}.task-panel--compact .task-empty{padding:36px 16px}
@media(max-width:1100px){.task-card,.task-panel--compact .task-card{grid-template-columns:minmax(240px,1.3fr) minmax(170px,.8fr) 210px}.task-card__status{display:none}.task-filters{grid-template-columns:1fr 150px 150px}.filter-reset{grid-column:1/-1;justify-self:end}}
@media(max-width:760px){.task-panel{padding:18px}.task-panel__heading{flex-direction:column}.task-panel__create{width:100%}.task-panel__create button{flex:1}.task-summary{grid-template-columns:repeat(2,1fr)}.task-filters{grid-template-columns:1fr}.filter-reset{grid-column:auto;justify-self:stretch}.task-card,.task-panel--compact .task-card{grid-template-columns:1fr;gap:13px;padding:18px 0}.task-card__status{display:flex;align-items:center;justify-content:space-between}.task-card__actions{justify-content:stretch}.task-card__actions button{width:100%;min-height:44px}}
</style>
