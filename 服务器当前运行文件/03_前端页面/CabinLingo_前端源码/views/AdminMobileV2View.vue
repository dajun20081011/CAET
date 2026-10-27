<template>
  <main class="m-app">
    <section v-if="isHome" class="m-page home-page has-tabbar">
      <header class="home-header">
        <h1>您好，{{ managerName }}</h1>
        <button type="button" @click="logout">退出登录</button>
      </header>

      <div class="home-filters">
        <label><span class="sr-only">统计周期</span><select v-model="weekMode"><option value="current">{{ weekLabel }}</option><option value="previous">上周</option></select></label>
        <label><span class="sr-only">训练计划</span><select v-model="selectedPlanId" @change="syncPlanQuery"><option value="all">全部训练计划</option><option v-for="task in activeTasks" :key="task.id" :value="task.id">{{ task.title }}{{ task.week_no ? ` · 第${task.week_no}周` : '' }}</option></select></label>
      </div>

      <LoadingCard v-if="store.loading && !store.loaded" />
      <template v-else>
        <section class="summary-card">
          <header><h2>任务完成情况</h2><span>{{ homeStats.total }} 人{{ selectedPlanId === 'all' ? '次' : '' }} · 长期有效</span></header>
          <div class="completion-ring" :style="ringStyle"><div><strong>{{ homeStats.rate }}%</strong><small>完成率</small></div></div>
          <div class="metric-grid">
            <button class="success" type="button" @click="openStatus('completed')"><span>已完成</span><strong>{{ homeStats.completed }}</strong></button>
            <button class="warning" type="button" @click="openStatus('pending')"><span>待评价</span><strong>{{ homeStats.pending }}</strong></button>
            <button class="danger" type="button" @click="openStatus('incomplete')"><span>未完成</span><strong>{{ homeStats.incomplete }}</strong></button>
          </div>
        </section>

        <section class="trend-card">
          <header><h2>近4周完成趋势</h2><span>↑ {{ trendDelta }}% 较上周</span></header>
          <div class="trend-plot">
            <svg viewBox="0 0 300 54" preserveAspectRatio="none" aria-hidden="true"><polyline :points="trendPoints" /></svg>
            <div v-for="(item,index) in trend" :key="item.label" class="trend-point" :style="trendPointStyle(item.rate,index)"><b>{{ item.rate }}%</b><i /></div>
          </div>
          <div class="trend-labels"><span v-for="item in trend" :key="item.label">{{ item.label }}</span></div>
        </section>

        <button class="track-entry" type="button" @click="go('/admin/mobile/weekly')"><span><strong>周训练轨迹</strong><small>跨任务查看学员每周训练</small></span><b>›</b></button>
      </template>
      <BottomTabs active="home" @home="go('/admin/mobile/home')" @learners="go('/admin/mobile/learners')" />
    </section>

    <section v-else-if="isStatusList" class="m-page">
      <PageHeader :title="statusTitle" @back="go('/admin/mobile/home')" />
      <SearchField v-model="search" placeholder="搜索学员 / 训练任务" />
      <section class="person-card status-person-card">
        <button v-for="learner in statusLearners" :key="learner.learner_id" type="button" @click="openLearner(learner.learner_id)">
          <Avatar :name="learner.display_name" />
          <span class="person-copy"><strong>{{ learner.display_name }} · {{ learner.completed_items }}/{{ learner.total_items }}</strong><small v-if="mobileView === 'pending'">任务进度&nbsp; {{ learner.completed_items }} / {{ learner.total_items }}</small><i v-if="mobileView !== 'completed'" class="mini-progress"><em :style="{ width: `${learner.progress_percent}%` }" /></i><small v-if="mobileView === 'completed'" class="green">已评价</small></span>
          <StatusPill v-if="mobileView === 'pending'" status="pending" label="待评价" />
          <b class="chevron">›</b>
        </button>
        <EmptyState v-if="!statusLearners.length" text="当前筛选条件下没有学员" />
      </section>
    </section>

    <section v-else-if="isWeekly" class="m-page has-tabbar">
      <h1 class="standalone-title">周训练轨迹</h1>
      <SearchField v-model="search" placeholder="搜索姓名 / 工号" />
      <div class="chip-row">
        <select v-model="groupFilter"><option value="all">全部组</option><option v-for="name in classNames" :key="name" :value="name">{{ name }}</option></select>
        <select v-model="trackStatus"><option value="all">全部状态</option><option value="completed">已完成</option><option value="pending">待评价</option><option value="incomplete">未完成</option></select>
        <select v-model="trackWeeks"><option value="6">全部周次</option><option value="3">近3周</option></select>
      </div>
      <section class="track-card">
        <h2>学员周训练轨迹</h2>
        <div class="legend"><span><i class="success" />已完成</span><span><i class="warning" />待评价</span><span><i class="danger" />未完成</span><span><i class="neutral" />未分配</span></div>
        <div class="track-scroll">
          <div class="track-grid" :style="trackGridStyle">
            <div class="track-head">学员</div><div v-for="task in visibleTrackTasks" :key="task.id" class="track-head">{{ weekName(task) }}</div>
            <template v-for="row in trackRows" :key="row.id">
              <button class="track-name" type="button" @click="openLearner(row.id)">{{ row.name }}</button>
              <button v-for="cell in row.cells" :key="cell.task.id" type="button" class="track-cell" :class="cell.status" @click="openLearnerTask(row.id,cell.task.id)"><b>{{ cell.symbol }}</b><small>{{ cell.label }}</small></button>
            </template>
          </div>
        </div>
        <EmptyState v-if="!trackRows.length" text="暂无周训练轨迹" />
      </section>
      <BottomTabs active="weekly" @home="go('/admin/mobile/home')" @learners="go('/admin/mobile/learners')" />
    </section>

    <section v-else-if="isLearners" class="m-page has-tabbar">
      <h1 class="standalone-title">学员</h1>
      <SearchField v-model="search" placeholder="搜索姓名 / 工号" />
      <div class="chip-row learner-chips"><select v-model="groupFilter"><option value="all">全部组</option><option v-for="name in classNames" :key="name" :value="name">{{ name }}</option></select><select v-model="learnerStatusFilter"><option value="all">全部状态</option><option value="completed">已完成</option><option value="pending">待评价</option><option value="incomplete">未完成</option></select><button type="button">筛选</button></div>
      <section class="person-card learners-card">
        <button v-for="row in learnerRows" :key="row.id" type="button" @click="openLearner(row.id)"><Avatar :name="row.name" /><span class="person-copy"><strong>{{ row.name }}</strong><small>{{ row.completed }}/{{ row.total }}</small></span><StatusPill :status="row.status" :label="statusLabel(row.status)" /></button>
        <EmptyState v-if="!learnerRows.length" text="当前筛选条件下没有学员" />
      </section>
      <BottomTabs active="learners" @home="go('/admin/mobile/home')" @learners="go('/admin/mobile/learners')" />
    </section>

    <section v-else-if="isLearnerDetail" class="m-page">
      <PageHeader title="学员任务详情" @back="go('/admin/mobile/learners')" />
      <select v-model="selectedPlanId" class="wide-select" @change="syncPlanQuery"><option value="all">{{ weekLabel }} · 全部计划</option><option v-for="task in activeTasks" :key="task.id" :value="task.id">{{ task.title }}</option></select>
      <LoadingCard v-if="selectedLearnerLoading" />
      <template v-else-if="selectedLearner">
        <section class="learner-hero">
          <Avatar :name="selectedLearner.display_name" />
          <div><strong>{{ selectedLearner.display_name }}</strong><small>{{ selectedLearner.external_ref || '未设置工号' }}{{ selectedLearnerClass ? ` · ${selectedLearnerClass}` : '' }}</small></div>
          <StatusPill :status="selectedLearnerSummary.status" :label="statusLabel(selectedLearnerSummary.status)" />
          <div class="hero-progress"><b>{{ selectedLearnerSummary.completed }} / {{ selectedLearnerSummary.total }}</b><small>训练计划</small></div><span><strong>AI均分 {{ selectedLearnerAverage }}</strong><small>连续达标 {{ selectedLearnerStreak }} 周</small></span>
        </section>
        <section class="week-list-card"><h2>周任务进度</h2><button v-for="task in selectedLearnerTasks" :key="task.assignment_id" type="button" @click="openLearnerTask(selectedLearner.id,task.task_id)"><strong>{{ task.week_no ? `第${cnNumber(task.week_no)}周` : task.title }}</strong><StatusPill :status="learnerTaskStatus(task)" :label="taskStatusLabel(task)" /><b>›</b></button><EmptyState v-if="!selectedLearnerTasks.length" text="当前范围没有训练计划" /></section>
      </template>
      <ErrorState v-else-if="selectedLearnerError" :text="selectedLearnerError" @retry="loadSelectedLearner(true)" />
    </section>

    <section v-else-if="isWeekDetail" class="m-page">
      <PageHeader :title="weekDetailTitle" :subtitle="weekDetailSubtitle" @back="openLearner(String(route.params.learnerId))" />
      <section class="week-summary"><small>{{ weekDetailTitle }}完成情况</small><strong>{{ weekBroadcastStats.completed }} / {{ weekBroadcastStats.total }}</strong><span>待教员评价 {{ weekBroadcastStats.pending }} 项</span></section>
      <LoadingCard v-if="selectedBroadcastLoading" />
      <section v-else class="task-list">
        <button v-for="item in weekBroadcasts" :key="item.content_item_id" type="button" :disabled="!item.latest_attempt_id" @click="openAttempt(item)"><strong>{{ item.content_title }}</strong><b>›</b><span>音频 {{ attemptDuration(item) }}</span><span class="blue">测评 {{ scoreText(item.latest_score) }}</span><span :class="item.review_status === 'published' ? 'green' : 'warning-text'">{{ reviewLabel(item) }}</span><small>点击查看音频、测评详情与教员评价</small><p v-if="attemptReviewText(item)" class="review-preview"><b>教员评价</b>{{ attemptReviewText(item) }}</p></button>
        <EmptyState v-if="!weekBroadcasts.length" text="本周暂无训练任务" />
      </section>
    </section>

    <section v-else-if="isAttemptDetail" class="m-page">
      <PageHeader title="训练任务详情" :subtitle="attemptSubtitle" @back="goBackToWeek" />
      <LoadingCard v-if="attemptLoading" />
      <ErrorState v-else-if="attemptError" :text="attemptError" @retry="loadAttempt" />
      <template v-else-if="attemptDetail">
        <AudioEvidencePlayer class="attempt-audio" title="学员录音" :meta="attemptDetail.content_title || '训练任务录音'" :src="audioUrl" :loading="audioLoading" variant="instructor" :known-duration-seconds="attemptDetail.duration_seconds" @load="loadAudio" @error="audioError" />
        <section class="assessment-card"><h2>测评详情</h2><div class="score-overview"><strong>{{ attemptDetail.overall_score ?? '—' }}</strong><span v-for="score in scoreItems" :key="score.label"><small>{{ score.label }}</small><b :class="score.tone">{{ score.value }}</b></span></div><h3>问题汇总</h3><div class="issue-pills"><span class="danger">发音问题 {{ issueCount('pronunciation') }}</span><span class="warning">停顿问题 {{ issueCount('pause') }}</span><span class="success">其余正常</span></div><div class="transcript" :class="{ collapsed: !aiExpanded }"><div v-if="attemptDetail.word_details.length" class="word-score-flow"><span v-for="(word,index) in attemptDetail.word_details" :key="`${word.word}-${index}`" :class="wordTone(word.overall)"><b>{{ word.word }}</b><small>{{ Math.round(word.overall ?? 0) || '—' }}</small></span></div><p v-else>{{ attemptDetail.reference_text || '暂无广播词原文' }}</p><ul><li v-for="(issue,index) in attemptDetail.ai_issues" :key="index"><b>{{ issue.word || issue.dimension || issue.type || '问题' }}</b><span>{{ issue.message || issue.training_advice || '请结合录音复核' }}</span></li></ul></div><button class="expand-button" type="button" @click="aiExpanded=!aiExpanded">{{ aiExpanded ? '收起完整测评详情⌃' : '展开完整测评详情⌄' }}</button></section>
        <section class="teacher-card"><h2>教员评价</h2><template v-if="attemptDetail.review"><strong class="blue">评分 {{ attemptDetail.review.final_score ?? '—' }}</strong><p>{{ attemptDetail.review.correction_advice || attemptDetail.review.summary || '教员已完成评价，暂无文字评语。' }}</p><small class="green">教员已完成评价</small></template><template v-else-if="attemptReviewItem"><label>评分<input v-model.number="reviewScore" type="number" min="0" max="100"></label><label>评价<textarea v-model="reviewText" rows="3" placeholder="填写评价与改进建议" /></label><button type="button" :disabled="reviewSaving" @click="publishReview">{{ reviewSaving ? '提交中…' : '提交教员评价' }}</button><p v-if="reviewError" class="form-error">{{ reviewError }}</p></template><p v-else>当前任务尚未进入教员评价队列。</p></section>
      </template>
    </section>

    <p v-if="store.error" class="global-error">{{ store.error }} <button type="button" @click="store.refreshAfterMutation">重试</button></p>
  </main>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { cabinlingoApi, type AdminLearnerBroadcastItem, type InstructorReviewDetail, type InstructorReviewPayload, type LearnerTask, type TaskListItem, type TaskRosterLearner, type UserSummary } from '@/api'
import AudioEvidencePlayer from '@/components/AudioEvidencePlayer.vue'
import { useAdminMobileStore } from '@/stores/adminMobile'
import { useSessionStore } from '@/stores/session'

type ViewName = 'home'|'completed'|'pending'|'incomplete'|'weekly'|'learners'|'learner'|'week'|'attempt'
type StatusName = 'completed'|'pending'|'incomplete'|'neutral'

const route = useRoute()
const router = useRouter()
const store = useAdminMobileStore()
const session = useSessionStore()
const search = ref('')
const weekMode = ref('current')
const selectedPlanId = ref(String(route.query.plan || 'all'))
const groupFilter = ref('all')
const trackStatus = ref('all')
const trackWeeks = ref('6')
const learnerStatusFilter = ref('all')
const attemptDetail = ref<InstructorReviewDetail|null>(null)
const weekAttemptDetails = ref<Record<string,InstructorReviewDetail>>({})
const attemptLoading = ref(false)
const attemptError = ref('')
const audioUrl = ref('')
const audioLoading = ref(false)
const aiExpanded = ref(false)
const reviewScore = ref<number|null>(null)
const reviewText = ref('')
const reviewSaving = ref(false)
const reviewError = ref('')

const PageHeader = defineComponent({ props:{ title:{type:String,required:true}, subtitle:{type:String,default:''} }, emits:['back'], setup:(p,{emit})=>()=>h('header',{class:'page-header'},[h('button',{type:'button','aria-label':'返回',onClick:()=>emit('back')},'‹'),h('div',[h('h1',p.title),p.subtitle?h('p',p.subtitle):null])]) })
const Avatar = defineComponent({ props:{name:{type:String,required:true}}, setup:p=>()=>h('i',{class:'avatar'},p.name.trim().slice(0,1)||'员') })
const StatusPill = defineComponent({ props:{status:{type:String,required:true},label:{type:String,required:true}},setup:p=>()=>h('em',{class:['status-pill',p.status]},p.label) })
const SearchField = defineComponent({ props:{modelValue:{type:String,required:true},placeholder:{type:String,required:true}},emits:['update:modelValue'],setup:(p,{emit})=>()=>h('label',{class:'search-field'},[h('span','⌕'),h('input',{value:p.modelValue,placeholder:p.placeholder,onInput:(e:Event)=>emit('update:modelValue',(e.target as HTMLInputElement).value)})]) })
const EmptyState = defineComponent({props:{text:{type:String,required:true}},setup:p=>()=>h('div',{class:'empty-state'},p.text)})
const ErrorState = defineComponent({props:{text:{type:String,required:true}},emits:['retry'],setup:(p,{emit})=>()=>h('div',{class:'error-state'},[h('p',p.text),h('button',{type:'button',onClick:()=>emit('retry')},'重新加载')])})
const LoadingCard = defineComponent({setup:()=>()=>h('div',{class:'loading-card'},[h('i'),h('i'),h('i')])})
const BottomTabs = defineComponent({props:{active:{type:String,required:true}},emits:['home','learners'],setup:(p,{emit})=>()=>h('nav',{class:'bottom-tabs'},[h('button',{class:p.active==='home'?'active':'',onClick:()=>emit('home')},[h('b','⌂'),h('span','首页')]),h('button',{class:p.active==='learners'?'active':'',onClick:()=>emit('learners')},[h('b','◎'),h('span','学员')])])})

const mobileView = computed<ViewName>(()=>{
  if(route.name==='admin-mobile-learner') return 'learner'
  if(route.name==='admin-mobile-week') return 'week'
  if(route.name==='admin-mobile-attempt') return 'attempt'
  if(String(route.path).startsWith('/admin/mobile/')) return String(route.params.view||'home') as ViewName
  const section=String(route.params.section||'dashboard')
  return section==='users'?'learners':'home'
})
const isHome=computed(()=>mobileView.value==='home')
const isStatusList=computed(()=>['completed','pending','incomplete'].includes(mobileView.value))
const isWeekly=computed(()=>mobileView.value==='weekly')
const isLearners=computed(()=>mobileView.value==='learners')
const isLearnerDetail=computed(()=>mobileView.value==='learner')
const isWeekDetail=computed(()=>mobileView.value==='week')
const isAttemptDetail=computed(()=>mobileView.value==='attempt')
const managerName=computed(()=>session.user?.display_name||'经理')
const activeTasks=computed(()=>[...store.activeTasks].sort((a,b)=>(a.week_no??99)-(b.week_no??99)))
const selectedTask=computed(()=>activeTasks.value.find(t=>t.id===selectedPlanId.value)||null)
const selectedRoster=computed(()=>selectedTask.value?store.taskRosters[`${selectedTask.value.task_type}:${selectedTask.value.id}`]||null:null)
const weekLabel=computed(()=>{const now=new Date();const day=now.getDay()||7;const start=new Date(now);start.setDate(now.getDate()-day+1);const end=new Date(start);end.setDate(start.getDate()+6);return `本周 · ${start.getMonth()+1}/${start.getDate()}—${end.getMonth()+1}/${end.getDate()}`})
const allRosters=computed(()=>activeTasks.value.map(t=>store.taskRosters[`${t.task_type}:${t.id}`]).filter(Boolean))
const homeStats=computed(()=>{
  const rosters=selectedRoster.value?[selectedRoster.value]:allRosters.value
  const statuses=rosters.flatMap(r=>r.learners.map(aggregateItemStatus))
  const total=statuses.length,completed=statuses.filter(x=>x==='completed').length,pending=statuses.filter(x=>x==='pending').length,incomplete=statuses.filter(x=>x==='incomplete').length
  return{total,completed,pending,incomplete,rate:total?Math.round(completed/total*100):0}
})
const ringStyle=computed(()=>({background:`conic-gradient(#1769e0 ${homeStats.value.rate*3.6}deg,#e8eef7 0deg)`}))
const trend=computed(()=>{const tasks=activeTasks.value.slice(-4);const vals=tasks.map((t,i)=>{const r=store.taskRosters[`${t.task_type}:${t.id}`];return{label:i===tasks.length-1?'本周':`第${i+1}周`,rate:r?.total_count?Math.round(r.passed_count/r.total_count*100):0}});while(vals.length<4)vals.unshift({label:`第${vals.length+1}周`,rate:0});return vals})
const trendDelta=computed(()=>Math.max(0,trend.value[3].rate-trend.value[2].rate))
const trendPoints=computed(()=>trend.value.map((v,i)=>`${i*100},${50-v.rate*.45}`).join(' '))
const statusTitle=computed(()=>({completed:'已完成',pending:'待评价',incomplete:'未完成'} as Record<string,string>)[mobileView.value]||'状态')
const statusLearners=computed(()=>{const wanted=mobileView.value as StatusName;const items=selectedRoster.value?.learners||[];const q=search.value.trim().toLowerCase();return items.filter(x=>aggregateItemStatus(x)===wanted&&(!q||`${x.display_name} ${x.external_ref||''}`.toLowerCase().includes(q)))})
const visibleTrackTasks=computed(()=>activeTasks.value.slice(0,Number(trackWeeks.value)))
const classNames=computed(()=>Array.from(new Set(allRosters.value.flatMap(r=>r.learners.map(l=>l.class_name).filter((x):x is string=>Boolean(x))))))
const allLearnerMap=computed(()=>{const map=new Map<string,{id:string;name:string;external:string;className:string;items:TaskRosterLearner[]}>();allRosters.value.forEach(r=>r.learners.forEach(x=>{const row=map.get(x.learner_id)||{id:x.learner_id,name:x.display_name,external:x.external_ref||'',className:x.class_name||'',items:[]};row.items.push(x);map.set(x.learner_id,row)}));return map})
const trackRows=computed(()=>Array.from(allLearnerMap.value.values()).filter(row=>{const q=search.value.trim().toLowerCase();if(q&&!`${row.name} ${row.external}`.toLowerCase().includes(q))return false;if(groupFilter.value!=='all'&&row.className!==groupFilter.value)return false;if(trackStatus.value!=='all'&&!row.items.some(x=>aggregateItemStatus(x)===trackStatus.value))return false;return true}).map(row=>({id:row.id,name:row.name,cells:visibleTrackTasks.value.map(task=>{const r=store.taskRosters[`${task.task_type}:${task.id}`]?.learners.find(x=>x.learner_id===row.id);const status=r?aggregateItemStatus(r):'neutral';return{task,status,symbol:status==='completed'?'✓':status==='pending'?'•':status==='incomplete'?'!':'—',label:r?(task.title.slice(0,2)||weekName(task)):'未分配'}})})))
const trackGridStyle=computed(()=>({gridTemplateColumns:`60px repeat(${Math.max(visibleTrackTasks.value.length,1)},minmax(0,1fr))`}))
const learnerRows=computed(()=>Array.from(allLearnerMap.value.values()).map(row=>{const total=row.items.reduce((n,x)=>n+x.total_items,0),completed=row.items.reduce((n,x)=>n+x.completed_items,0),itemStatuses=row.items.map(aggregateItemStatus);let status:StatusName=itemStatuses.some(x=>x==='pending')?'pending':itemStatuses.length>0&&itemStatuses.every(x=>x==='completed')?'completed':'incomplete';return{...row,total,completed,status}}).filter(row=>{const q=search.value.trim().toLowerCase();return(!q||`${row.name} ${row.external}`.toLowerCase().includes(q))&&(groupFilter.value==='all'||row.className===groupFilter.value)&&(learnerStatusFilter.value==='all'||row.status===learnerStatusFilter.value)}))
const selectedLearner=computed<UserSummary|null>(()=>{const id=String(route.params.learnerId||'');return store.learnerUsers.find(u=>u.id===id)||null})
const selectedLearnerTasks=computed(()=>{if(!selectedLearner.value)return[];const items=store.learnerTasksByUser[selectedLearner.value.id]||[];return selectedPlanId.value==='all'?items:items.filter(t=>t.task_id===selectedPlanId.value)})
const selectedLearnerLoading=computed(()=>Boolean(selectedLearner.value&&store.learnerTasksLoading[selectedLearner.value.id]))
const selectedLearnerError=computed(()=>selectedLearner.value?store.learnerTasksError[selectedLearner.value.id]||'':'未找到学员')
const selectedLearnerBroadcasts=computed(()=>selectedLearner.value?store.learnerBroadcastsByUser[selectedLearner.value.id]||[]:[])
const selectedBroadcastLoading=computed(()=>Boolean(selectedLearner.value&&store.learnerBroadcastsLoading[selectedLearner.value.id]))
const selectedLearnerClass=computed(()=>allLearnerMap.value.get(selectedLearner.value?.id||'')?.className||'')
const selectedLearnerSummary=computed(()=>{const total=selectedLearnerTasks.value.reduce((n,t)=>n+t.total_items,0),completed=selectedLearnerTasks.value.reduce((n,t)=>n+t.completed_items,0);const status:StatusName=selectedLearnerBroadcasts.value.some(x=>['pending_review','draft'].includes(x.review_status))?'pending':total>0&&completed>=total?'completed':'incomplete';return{total,completed,status}})
const selectedLearnerAverage=computed(()=>{const scores=selectedLearnerBroadcasts.value.map(x=>x.latest_score).filter((x):x is number=>typeof x==='number');return scores.length?(scores.reduce((a,b)=>a+b,0)/scores.length).toFixed(1):'—'})
const selectedLearnerStreak=computed(()=>selectedLearnerTasks.value.filter(t=>t.progress_percent>=100).length)
const weekTask=computed(()=>activeTasks.value.find(t=>t.id===String(route.params.taskId||''))||store.tasks.find(t=>t.id===String(route.params.taskId||''))||null)
const weekBroadcasts=computed(()=>selectedLearnerBroadcasts.value.filter(x=>x.task_id===String(route.params.taskId||'')))
const weekBroadcastStats=computed(()=>({total:weekBroadcasts.value.length,completed:weekBroadcasts.value.filter(x=>x.progress_status==='completed').length,pending:weekBroadcasts.value.filter(x=>['pending_review','draft'].includes(x.review_status)).length}))
const weekDetailTitle=computed(()=>weekTask.value?.week_no?`第${cnNumber(weekTask.value.week_no)}周训练`:weekTask.value?.title||'周任务详情')
const weekDetailSubtitle=computed(()=>`${selectedLearner.value?.display_name||'学员'} · ${selectedLearnerClass.value||'未分组'}`)
const attemptReviewItem=computed(()=>store.reviews.find(x=>x.learnerId===String(route.params.learnerId||'')&&x.targetId===String(route.params.attemptId||''))||null)
const attemptSubtitle=computed(()=>`${selectedLearner.value?.display_name||'学员'} · ${weekDetailTitle.value} · ${attemptDetail.value?.content_title||'训练任务'}`)
const scoreItems=computed(()=>{const s=attemptDetail.value?.ai_scores||{};return[{label:'发音',value:s.pronunciation??'—',tone:'orange'},{label:'停连',value:s.completeness??'—',tone:'green'},{label:'流利度',value:s.fluency??'—',tone:'green'}]})
onMounted(async()=>{await store.refresh();ensurePlan();await loadSelectedLearner();if(isWeekDetail.value)await loadWeekAttemptDetails();if(isAttemptDetail.value)await loadAttempt()})
watch(()=>route.fullPath,async()=>{search.value='';ensurePlan();await loadSelectedLearner();if(isWeekDetail.value)await loadWeekAttemptDetails();if(isAttemptDetail.value)await loadAttempt()})
onBeforeUnmount(()=>revokeAudio())

function ensurePlan(){const q=String(route.query.plan||'');if(q&&activeTasks.value.some(t=>t.id===q))selectedPlanId.value=q;else if(selectedPlanId.value!=='all'&&!activeTasks.value.some(t=>t.id===selectedPlanId.value))selectedPlanId.value='all'}
function go(path:string,query:Record<string,string>={}){void router.push({path,query:{...query,...(selectedPlanId.value!=='all'?{plan:selectedPlanId.value}:{})}})}
function syncPlanQuery(){void router.replace({query:{...route.query,...(selectedPlanId.value==='all'?{plan:undefined}:{plan:selectedPlanId.value})}})}
function openStatus(view:'completed'|'pending'|'incomplete'){if(selectedPlanId.value==='all'&&activeTasks.value[0])selectedPlanId.value=activeTasks.value[0].id;go(`/admin/mobile/${view}`)}
function openLearner(id:string){go(`/admin/mobile/learner/${encodeURIComponent(id)}`)}
function openLearnerTask(learnerId:string,taskId:string){go(`/admin/mobile/learner/${encodeURIComponent(learnerId)}/task/${encodeURIComponent(taskId)}`)}
function openAttempt(item:AdminLearnerBroadcastItem){if(item.latest_attempt_id)go(`/admin/mobile/learner/${encodeURIComponent(String(route.params.learnerId))}/attempt/${encodeURIComponent(item.latest_attempt_id)}`,{task:item.task_id})}
function goBackToWeek(){const learner=String(route.params.learnerId||''),task=String(route.query.task||attemptDetail.value?.task_id||'');task?openLearnerTask(learner,task):openLearner(learner)}
function logout(){session.signOut();void router.replace('/login')}
async function loadSelectedLearner(force=false){if(!selectedLearner.value)return;await Promise.all([store.loadLearnerTasks(selectedLearner.value.id,force),store.loadLearnerBroadcasts(selectedLearner.value.id,force)])}
async function loadWeekAttemptDetails(){const learnerId=String(route.params.learnerId||'');const entries=await Promise.all(weekBroadcasts.value.filter(x=>x.latest_attempt_id).map(async item=>{try{return[item.latest_attempt_id!,await cabinlingoApi.adminLearnerAttemptDetail(learnerId,item.latest_attempt_id!)] as const}catch{return null}}));weekAttemptDetails.value=Object.fromEntries(entries.filter((x):x is readonly [string,InstructorReviewDetail]=>Boolean(x)))}
async function loadAttempt(){const learnerId=String(route.params.learnerId||''),attemptId=String(route.params.attemptId||'');if(!learnerId||!attemptId)return;attemptLoading.value=true;attemptError.value='';attemptDetail.value=null;revokeAudio();try{attemptDetail.value=await cabinlingoApi.adminLearnerAttemptDetail(learnerId,attemptId);reviewScore.value=attemptDetail.value.review?.final_score??attemptDetail.value.overall_score;reviewText.value=attemptDetail.value.review?.correction_advice||''}catch{attemptError.value='训练音频与测评详情读取失败，请稍后重试。'}finally{attemptLoading.value=false}}
async function loadAudio(){const source=attemptDetail.value?.recording_url||attemptDetail.value?.recordings[0]?.audio_url;if(!source){attemptError.value='该任务没有可播放的录音。';return}audioLoading.value=true;try{audioUrl.value=URL.createObjectURL(await cabinlingoApi.protectedAudio(source))}catch{attemptError.value='录音加载失败，请检查网络后重试。'}finally{audioLoading.value=false}}
function audioError(){attemptError.value='录音播放失败，请检查网络后重试。'}
function revokeAudio(){if(audioUrl.value)URL.revokeObjectURL(audioUrl.value);audioUrl.value='';audioLoading.value=false}
async function publishReview(){if(!attemptReviewItem.value||!attemptDetail.value||reviewSaving.value)return;reviewSaving.value=true;reviewError.value='';const scores=attemptDetail.value.ai_scores;const payload:InstructorReviewPayload={completeness_score:scores.completeness??null,pronunciation_score:scores.pronunciation??null,fluency_score:scores.fluency??null,expression_score:scores.expression??null,final_score:reviewScore.value,evidence:{source:'mobile-admin'},summary:reviewText.value,correction_advice:reviewText.value,required_retraining:false};try{await cabinlingoApi.publishInstructorReview(attemptReviewItem.value.reviewType!,attemptReviewItem.value.targetId!,payload);await store.refreshAfterMutation();await loadAttempt()}catch{reviewError.value='教员评价提交失败，请检查权限或网络后重试。'}finally{reviewSaving.value=false}}
function aggregateItemStatus(x:TaskRosterLearner):StatusName{if(x.pending_review||x.final_status==='pending_review')return'pending';if(x.final_status==='passed'||x.progress_status==='completed'||(x.total_items>0&&x.completed_items>=x.total_items))return'completed';return'incomplete'}
function statusLabel(s:StatusName){return s==='completed'?'已完成':s==='pending'?'待评价':s==='incomplete'?'未完成':'未分配'}
function learnerTaskStatus(t:LearnerTask):StatusName{if(selectedLearnerBroadcasts.value.some(x=>x.task_id===t.task_id&&['pending_review','draft'].includes(x.review_status)))return'pending';if(t.progress_percent>=100)return'completed';return'incomplete'}
function taskStatusLabel(t:LearnerTask){if(t.locked)return'未到周';return statusLabel(learnerTaskStatus(t))}
function weekName(t:TaskListItem){return t.week_no?`第${t.week_no}周`:t.title.slice(0,3)}
function cnNumber(n:number){return(['零','一','二','三','四','五','六','七','八','九','十'][n]||String(n))}
function trendPointStyle(rate:number,index:number){return{left:`calc(${index*33.333}% - 3px)`,top:`${Math.max(1,50-rate*.45)}px`}}
function reviewLabel(item:AdminLearnerBroadcastItem){return item.review_status==='published'?'教员 已评价':['pending_review','draft'].includes(item.review_status)?'教员 待评价':'尚未评价'}
function scoreText(value:number|null){return typeof value==='number'?value.toFixed(1):'—'}
function attemptDuration(item:AdminLearnerBroadcastItem){return formatSeconds(weekAttemptDetails.value[item.latest_attempt_id||'']?.duration_seconds||0)}
function attemptReviewText(item:AdminLearnerBroadcastItem){const review=weekAttemptDetails.value[item.latest_attempt_id||'']?.review;return review?.correction_advice||review?.summary||''}
function issueCount(kind:string){return attemptDetail.value?.ai_issues.filter(x=>`${x.dimension||''} ${x.type||''}`.toLowerCase().includes(kind)).length||0}
function formatSeconds(value:number){const n=Math.max(0,Math.round(value));return`${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`}
function wordTone(score:number|undefined){return score===undefined?'':score<85?'bad':score<92?'warn':'good'}
</script>

<style scoped>
.m-app{--blue:#1769e0;--ink:#171b24;--muted:#667085;--faint:#98a2b3;--line:#dce3ec;--bg:#f4f7fb;min-height:100dvh;color:var(--ink);background:var(--bg);font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif}.m-app *{box-sizing:border-box}.m-app button,.m-app input,.m-app select,.m-app textarea{font:inherit}.m-app button{border:0;cursor:pointer}.m-page{width:min(100%,430px);min-height:100dvh;margin:auto;padding:20px 20px 40px}.m-page.has-tabbar{padding-bottom:108px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.home-header{display:flex;align-items:center;justify-content:space-between}.home-header h1,.standalone-title{margin:0;font-size:24px;line-height:1.3}.home-header button{min-width:88px;height:40px;border:1px solid #ef4444;border-radius:22px;color:#dc2626;background:#fff5f5;font-size:12px}.home-filters{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:36px}.home-filters select,.wide-select{width:100%;height:52px;padding:0 12px;border:1px solid var(--line);border-radius:14px;color:#40506a;background:#eef2f6;font-size:12px}.summary-card,.trend-card,.track-card,.person-card,.week-list-card,.audio-card,.assessment-card,.teacher-card{border:1px solid var(--line);border-radius:18px;background:#fff;box-shadow:0 3px 10px #0000000f}.summary-card{margin-top:24px;padding:14px 15px 16px}.summary-card>header,.trend-card>header{display:flex;align-items:center;justify-content:space-between}.summary-card h2,.trend-card h2,.track-card h2,.week-list-card h2,.audio-card h2,.assessment-card h2,.teacher-card h2{margin:0;font-size:14px}.summary-card>header span{color:var(--faint);font-size:10px}.completion-ring{display:grid;width:112px;height:112px;margin:20px auto 16px;padding:12px;border-radius:50%;place-items:center}.completion-ring>div{display:grid;width:88px;height:88px;border-radius:50%;background:#fff;place-items:center;text-align:center}.completion-ring strong{align-self:end;font-size:29px}.completion-ring small{align-self:start;color:var(--faint);font-size:9px}.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.metric-grid button{display:grid;height:54px;padding:8px 10px;border-radius:12px;background:#f8fafc;text-align:left}.metric-grid span{color:var(--muted);font-size:9px}.metric-grid strong{font-size:18px}.success strong,.green{color:#159447!important}.warning strong,.warning-text{color:#c27a0c!important}.danger strong{color:#d92d20!important}.trend-card{margin-top:16px;padding:12px 15px 10px}.trend-card header span{color:#16833b;font-size:9px}.trend-plot{position:relative;height:58px;margin-top:6px}.trend-plot svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}.trend-plot polyline{fill:none;stroke:var(--blue);stroke-width:2}.trend-point{position:absolute;width:8px;height:8px}.trend-point i{display:block;width:7px;height:7px;border-radius:50%;background:var(--blue)}.trend-point b{position:absolute;bottom:9px;left:-13px;width:34px;color:#475467;font-size:8px;text-align:center}.trend-labels{display:grid;grid-template-columns:repeat(4,1fr);color:var(--faint);font-size:8px;text-align:center}.track-entry{display:flex;align-items:center;justify-content:space-between;width:100%;height:68px;margin-top:16px;padding:0 16px;border:1px solid #c9d9f5;border-radius:16px;color:#1858c9;background:#f7faff;text-align:left}.track-entry strong,.track-entry small{display:block}.track-entry strong{font-size:13px}.track-entry small{margin-top:7px;color:var(--muted);font-size:10px}.track-entry>b{font-size:24px}.page-header{display:flex;align-items:flex-start;gap:8px;margin-bottom:32px}.page-header>button{width:22px;height:40px;padding:0;color:var(--blue);background:transparent;font-size:32px;line-height:1}.page-header h1{margin:1px 0 0;font-size:24px}.page-header p{margin:5px 0 0;color:var(--faint);font-size:11px}.search-field{display:flex;align-items:center;gap:8px;height:44px;margin-bottom:20px;padding:0 14px;border:1px solid #e6ebf2;border-radius:13px;color:var(--faint);background:#f0f3f7}.search-field input{min-width:0;flex:1;border:0;outline:0;color:var(--ink);background:transparent;font-size:11px}.person-card{overflow:hidden;padding:0 12px}.person-card>button{display:flex;align-items:center;gap:12px;width:100%;min-height:76px;padding:10px 0;border-bottom:1px solid var(--line);background:#fff;text-align:left}.person-card>button:last-of-type{border-bottom:0}.avatar{display:grid;flex:0 0 42px;width:42px;height:42px;border-radius:50%;color:var(--blue);background:#eef4ff;font-size:13px;font-style:normal;font-weight:700;place-items:center}.person-copy{min-width:0;flex:1}.person-copy strong,.person-copy small{display:block}.person-copy strong{font-size:13px}.person-copy small{margin-top:6px;color:var(--faint);font-size:10px}.mini-progress{display:block;width:120px;height:4px;margin-top:8px;border-radius:4px;background:#e4ebf5}.mini-progress em{display:block;height:100%;border-radius:inherit;background:var(--blue)}.status-pill{min-width:72px;padding:7px 10px;border-radius:999px;font-size:10px;font-style:normal;text-align:center}.status-pill.completed{color:#159447;background:#e8f8ee}.status-pill.pending{color:#b66d00;background:#fff3df}.status-pill.incomplete{color:#d92d20;background:#fff0f1}.status-pill.neutral{color:#8b929e;background:#f2f4f7}.chevron{color:#a7b1c2}.standalone-title{margin-bottom:28px}.chip-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:-4px 0 16px}.chip-row select,.chip-row button{height:36px;padding:0 10px;border:1px solid var(--line);border-radius:18px;color:#475467;background:#fff;font-size:10px}.track-card{padding:15px 13px;box-shadow:none}.legend{display:flex;gap:18px;margin:14px 0 20px;color:var(--muted);font-size:8px}.legend span{white-space:nowrap}.legend i{display:inline-block;width:7px;height:7px;margin-right:4px;border-radius:50%}.legend i.success{background:#299b52}.legend i.warning{background:#c77a00}.legend i.danger{background:#d92d20}.legend i.neutral{background:#a6b0c0}.track-scroll{overflow-x:auto}.track-grid{display:grid;gap:8px;min-width:max-content;align-items:stretch}.track-head{align-self:center;color:var(--muted);font-size:9px;text-align:center}.track-head:first-child{text-align:left}.track-name{min-height:56px;color:#344054;background:transparent;font-size:11px;font-weight:700;text-align:left}.track-cell{display:grid;width:54px;height:56px;border-radius:10px;place-items:center}.track-cell b{font-size:13px}.track-cell small{font-size:7px}.track-cell.completed{color:#178b45;background:#eef9f1}.track-cell.pending{color:#b66d00;background:#fff7e9}.track-cell.incomplete{color:#d92d20;background:#fff0f1}.track-cell.neutral{color:#98a2b3;background:#f4f6f8}.bottom-tabs{position:fixed;z-index:20;right:0;bottom:0;left:0;display:grid;grid-template-columns:1fr 1fr;width:min(100%,430px);height:74px;margin:auto;padding-bottom:env(safe-area-inset-bottom);border:1px solid var(--line);background:#fff}.bottom-tabs button{display:grid;color:#8c94a2;background:#fff;place-items:center}.bottom-tabs button.active{color:var(--blue)}.bottom-tabs b,.bottom-tabs span{display:block}.bottom-tabs b{align-self:end;font-size:15px}.bottom-tabs span{align-self:start;font-size:10px}.learner-chips{grid-template-columns:1fr 1fr 1fr}.learner-hero{display:grid;grid-template-columns:52px 1fr auto;align-items:center;margin:20px 0;padding:18px;border-radius:18px;background:#fff}.learner-hero .avatar{width:48px;height:48px}.learner-hero>div strong,.learner-hero>div small{display:block}.learner-hero>div strong{font-size:18px}.learner-hero>div small{margin-top:6px;color:var(--muted);font-size:11px}.learner-hero>b{margin-top:20px;color:var(--blue);font-size:28px}.learner-hero>p{align-self:end;margin:0 0 4px;color:var(--muted);font-size:10px}.learner-hero>span{margin-top:20px}.learner-hero>span strong,.learner-hero>span small{display:block;font-size:10px}.learner-hero>span small{margin-top:7px;color:var(--muted)}.wide-select{margin-bottom:0;background:#fff}.week-list-card{padding:16px}.week-list-card>button{display:grid;grid-template-columns:1fr auto 16px;align-items:center;width:100%;height:48px;margin-top:9px;padding:0 12px;border:1px solid #e6eaf0;border-radius:12px;background:#fafbfc;text-align:left}.week-list-card>button>strong{font-size:13px}.week-list-card>button>b{color:#a7b1c2}.week-summary{display:grid;grid-template-columns:1fr auto;margin-bottom:16px;padding:16px;border-radius:18px;color:#fff;background:#245fcb}.week-summary small{font-size:10px}.week-summary strong{grid-row:2;font-size:26px}.week-summary span{grid-row:2;grid-column:2;align-self:center;font-size:11px}.task-list{display:grid;gap:12px}.task-list>button{display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:8px;min-height:94px;padding:14px;border:1px solid var(--line);border-radius:16px;background:#fff;box-shadow:0 3px 9px #0000000c;text-align:left}.task-list>button>strong{grid-column:1/4;font-size:13px}.task-list>button>b{color:#a7b1c2}.task-list>button>span{color:var(--muted);font-size:10px}.task-list>button>small{grid-column:1/-1;color:var(--faint);font-size:9px}.blue{color:var(--blue)!important}.audio-card,.assessment-card,.teacher-card{margin-bottom:12px;padding:16px;box-shadow:none}.audio-player{display:flex;align-items:center;gap:14px;margin-top:18px}.audio-player>button{flex:0 0 44px;width:44px;height:44px;border-radius:50%;color:#fff;background:var(--blue)}.audio-player>div{flex:1}.audio-player i{display:block;height:5px;border-radius:5px;background:#e3eaf4}.audio-player em{display:block;height:100%;border-radius:inherit;background:var(--blue)}.audio-player small{display:block;margin-top:7px;color:var(--faint);font-size:10px}.load-audio{margin-top:10px;color:var(--blue);background:transparent;font-size:10px}.score-overview{display:flex;align-items:end;gap:20px;margin:26px 20px}.score-overview>strong{margin-right:auto;font-size:36px}.score-overview span{text-align:center}.score-overview small,.score-overview b{display:block}.score-overview small{color:var(--muted);font-size:9px}.score-overview b{margin-top:6px;font-size:18px}.orange{color:#f97316}.score-overview .green{color:#13965b}.assessment-card h3{margin:18px 32px 10px;font-size:12px}.issue-pills{display:flex;gap:8px;margin:0 32px}.issue-pills span{padding:6px 10px;border-radius:14px;font-size:8px}.issue-pills .danger{color:#ef4444;background:#fff0f0}.issue-pills .warning{color:#d97706;background:#fff6e9}.issue-pills .success{color:#179252;background:#ebf9f0}.transcript{max-height:280px;margin:34px 32px 0;overflow:hidden}.transcript.collapsed{max-height:150px}.transcript p{font-size:13px;line-height:2.2;white-space:pre-wrap}.transcript ul{padding-left:16px}.transcript li{margin:8px 0;color:var(--muted);font-size:10px}.transcript li b,.transcript li span{display:block}.expand-button{display:block;margin:10px 16px 0 auto;color:var(--blue);background:transparent;font-size:10px}.teacher-card>strong{display:block;margin:18px 0 12px}.teacher-card p{color:var(--muted);font-size:11px;line-height:1.7}.teacher-card>small{font-size:10px}.teacher-card label{display:grid;gap:6px;margin-top:12px;font-size:11px}.teacher-card input,.teacher-card textarea{width:100%;padding:10px;border:1px solid var(--line);border-radius:10px;resize:none}.teacher-card>button{width:100%;height:44px;margin-top:14px;border-radius:12px;color:#fff;background:var(--blue);font-weight:700}.teacher-card>button:disabled{opacity:.55}.form-error{color:#c2412d!important}.loading-card{display:grid;gap:12px;margin-top:20px}.loading-card i{height:76px;border-radius:16px;background:linear-gradient(90deg,#edf1f6,#f8fafc,#edf1f6);background-size:200% 100%;animation:shimmer 1.3s linear infinite}.empty-state,.error-state{padding:36px 16px;color:var(--faint);font-size:11px;text-align:center}.error-state button{height:38px;padding:0 16px;border-radius:10px;color:#fff;background:var(--blue)}.global-error{position:fixed;z-index:50;right:16px;bottom:88px;left:16px;max-width:398px;margin:auto;padding:12px;border-radius:12px;color:#a33e30;background:#fff0ed;font-size:11px}.global-error button{float:right;color:var(--blue);background:transparent}@keyframes shimmer{to{background-position:-200% 0}}@media(max-width:360px){.m-page{padding-right:14px;padding-left:14px}.legend{gap:9px}.score-overview{margin-right:4px;margin-left:4px;gap:12px}.issue-pills,.transcript{margin-right:4px;margin-left:4px}}
.learner-hero>b{white-space:nowrap}
:deep(.page-header>button){width:22px;height:32px;padding:0;border:0;color:var(--blue);background:transparent;font-size:27px;line-height:1}
:deep(.page-header h1){margin:1px 0 0;font-size:22px;line-height:1.25}
:deep(.page-header p){margin:4px 0 0;color:var(--faint);font-size:10px;line-height:1.35}
:deep(.search-field input){min-width:0;flex:1;height:40px;padding:0;border:0;outline:0;color:var(--ink);background:transparent;font-size:11px;box-shadow:none}
:deep(.bottom-tabs button){display:grid;border:0;color:#94969e;background:#fff;place-items:center}
:deep(.bottom-tabs button.active){color:var(--blue)}
:deep(.bottom-tabs b),:deep(.bottom-tabs span){display:block;font-weight:500}
:deep(.bottom-tabs b){align-self:end;font-size:14px}
:deep(.bottom-tabs span){align-self:start;font-size:10px}
:deep(.week-list-card>button){font-size:13px}
.word-score-flow{display:flex;flex-wrap:wrap;align-items:flex-start;gap:7px 5px;line-height:1.15}.word-score-flow span{display:grid;gap:2px}.word-score-flow b{font-size:12px;font-weight:500}.word-score-flow small{color:#667085;font-size:6px}.word-score-flow .bad b{color:#ff4d3d}.word-score-flow .warn b{color:#ff7a00}.word-score-flow .good b{color:#171b24}
.track-grid{width:100%;min-width:0;gap:6px 4px}.track-cell{width:auto;min-width:0}.learner-hero{grid-template-columns:72px 1fr auto}.learner-hero>.hero-progress{grid-row:2;grid-column:1/3;display:flex;align-items:end;gap:14px;margin-top:20px}.learner-hero>.hero-progress b{color:var(--blue);font-size:26px;white-space:nowrap}.learner-hero>.hero-progress small{margin-bottom:4px;color:var(--muted);font-size:10px}.learner-hero>span{grid-row:2;grid-column:3}
.attempt-audio{width:calc(100% + 8px);margin:0 -4px 12px}
.assessment-card{width:calc(100% + 8px);margin-right:-4px;margin-left:-4px;padding:20px;border-radius:28px}.assessment-card>h2{font-size:16px}.score-overview{min-height:76px;margin:18px 0 8px;gap:24px}.score-overview>strong{font-size:44px;line-height:48px}.score-overview small{font-size:10px}.score-overview b{font-size:23px}.assessment-card h3{margin:18px 0 12px;font-size:16px}.issue-pills{margin:0;gap:8px}.issue-pills span{height:28px;padding:0 14px;border-radius:14px;font-size:10px;line-height:28px}.transcript{height:476px;max-height:476px;margin:24px 0 0;padding:20px 18px;border-radius:28px;background:#f8fafc;overflow-x:hidden;overflow-y:auto;overscroll-behavior:contain;touch-action:pan-y;-webkit-overflow-scrolling:touch;scrollbar-gutter:stable}.transcript.collapsed{height:164px;max-height:164px;overflow:hidden}.word-score-flow{align-content:flex-start;gap:5px 7px}.word-score-flow span{min-height:40px}.word-score-flow b{font-size:16px;line-height:21px}.word-score-flow small{font-size:9px}.transcript p{font-size:16px;line-height:1.7}.transcript li{font-size:12px;line-height:1.6}.expand-button{margin:12px 0 0 auto;font-size:12px}.review-preview{grid-column:1/-1;margin:2px 0 0;padding:9px 10px;border-radius:10px;color:#60708a;background:#f5f8fd;font-size:10px;line-height:1.5}.review-preview b{display:block;margin-bottom:3px;color:#171f2e;font-size:10px}.teacher-card{width:calc(100% + 8px);margin-right:-4px;margin-left:-4px;padding:14px;border-radius:18px}.teacher-card h2{font-size:18px}.teacher-card p{padding:14px;border-radius:16px;background:#f5f8fd;font-size:13px;line-height:1.65}
</style>
