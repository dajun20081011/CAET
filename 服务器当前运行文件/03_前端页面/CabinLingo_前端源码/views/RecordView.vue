<template>
  <main class="app-shell page-shell figma-assessment-list">
    <p class="figma-status-time">9:41</p>
    <nav class="figma-assessment-tabs" aria-label="测评筛选">
      <button type="button" :class="{active:filter==='all'}" @click="setFilter('all')">全部</button>
      <button type="button" :class="{active:filter==='improve'}" @click="setFilter('improve')">有待改进</button>
      <button type="button" :class="{active:filter==='feedback'}" @click="setFilter('feedback')">教员评价</button>
    </nav>
    <PageState v-if="loading" tone="loading" title="正在加载测评记录" />
    <PageState v-else-if="errorMessage" tone="error" title="测评记录加载失败" :message="errorMessage" action-label="重试" @action="loadRecords" />
    <template v-else>
      <header class="figma-assessment-heading"><h1>{{ heading }}</h1><span>共 {{ groups.length }} 周</span></header>
      <section class="figma-week-list">
        <button v-for="group in visibleGroups" :key="group.assignmentId" type="button" @click="openWeek(group)">
          <strong>{{ group.title }}</strong><span class="status" :class="group.statusClass">{{ group.status }}</span>
          <small>{{ group.dateLabel }}</small>
          <div><b>篇目 {{ group.completed }} / {{ group.total }}</b><b>平均分 {{ group.average ?? '—' }}</b><b>{{ filter==='improve' ? `${group.improveCount} 个篇目需要重点改进` : `教员已评价 ${group.reviewed} 个篇目` }}</b></div>
          <i><em :style="{width:`${group.progress}%`} "/></i><u>查看本周测评　›</u>
        </button>
        <div v-if="!visibleGroups.length" class="figma-assessment-empty">当前筛选下暂无测评记录</div>
      </section>
    </template>
    <BottomNav />
  </main>
</template>

<script setup lang="ts">
import { computed,onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import BottomNav from '@/components/BottomNav.vue'
import PageState from '@/components/PageState.vue'
import { cabinlingoApi,type LearnerAttempt,type LearnerTask,type TeacherFeedback } from '@/api'
import { learnerError } from '@/domain/learnerPresentation'
type Filter='all'|'improve'|'feedback'
interface WeekGroup{assignmentId:string;title:string;dateLabel:string;completed:number;total:number;average:number|null;reviewed:number;improveCount:number;progress:number;status:string;statusClass:string}
const route=useRoute();const router=useRouter();const attempts=ref<LearnerAttempt[]>([]);const feedback=ref<TeacherFeedback[]>([]);const tasks=ref<LearnerTask[]>([]);const loading=ref(true);const errorMessage=ref('')
const routeFilter=computed<Filter>(()=>route.meta.recordTab==='feedback'?'feedback':route.query.filter==='improve'?'improve':'all');const filter=ref<Filter>(routeFilter.value)
const groups=computed<WeekGroup[]>(()=>tasks.value.filter(task=>task.task_type==='practice').map((task,index)=>{const rows=attempts.value.filter(item=>item.assignment_id===task.assignment_id);const scores=rows.map(item=>item.overall_score).filter((score):score is number=>typeof score==='number');const ids=new Set(rows.map(item=>item.attempt_id));const reviewed=feedback.value.filter(item=>item.practice_attempt_id&&ids.has(item.practice_attempt_id)).length;const improveCount=new Set(rows.filter(item=>(item.overall_score??100)<90).map(item=>item.content_item_id)).size;const done=task.status==='completed'||task.progress_percent>=100;return{assignmentId:task.assignment_id,title:task.week_no?`第${chineseWeek(task.week_no)}周${task.title.replace(/^第?\s*\d+\s*周[·\s]*/,'')}`:task.title||`第${chineseWeek(index+1)}周广播词训练`,dateLabel:task.due_at?`截止 ${formatDate(task.due_at)}`:'长期有效',completed:task.completed_items,total:task.total_items,average:scores.length?Math.round(scores.reduce((sum,value)=>sum+value,0)/scores.length):null,reviewed,improveCount,progress:task.progress_percent,status:done?'已完成':task.progress_percent>0?'进行中':'未开始',statusClass:done?'done':task.progress_percent>0?'active':'pending'}}))
const visibleGroups=computed(()=>groups.value.filter(group=>filter.value==='all'||filter.value==='improve'&&group.improveCount>0||filter.value==='feedback'&&group.reviewed>0))
const heading=computed(()=>filter.value==='improve'?'有待改进的周任务':filter.value==='feedback'?'已有教员评价的周任务':'每周任务')
function chineseWeek(value:number){return['一','二','三','四','五','六','七','八','九','十'][value-1]||String(value)}
function formatDate(value:string){return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit'}).format(new Date(value))}
function setFilter(value:Filter){filter.value=value;const path=value==='feedback'?'/student/feedback':'/student/results';void router.replace({path,query:value==='improve'?{filter:'improve'}:{}})}
function openWeek(group:WeekGroup){void router.push(`/student/results/week/${group.assignmentId}`)}
async function loadRecords(){loading.value=true;errorMessage.value='';try{const[a,f,t]=await Promise.all([cabinlingoApi.learnerAttempts(),cabinlingoApi.learnerFeedback(),cabinlingoApi.learnerTasks()]);attempts.value=a;feedback.value=f;tasks.value=t.filter(item=>item.status!=='deleted')}catch(error){errorMessage.value=learnerError(error)}finally{loading.value=false}}
onMounted(loadRecords)
</script>

<style scoped>
.figma-assessment-list{position:relative;width:100%;max-width:390px;min-height:844px;padding:0 20px 100px;background:#f6f8fb;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;overflow:hidden}.figma-status-time{position:absolute;left:24px;top:0;margin:0;color:#0e131c;font-size:12px;font-weight:500}.figma-assessment-tabs{position:absolute;left:20px;top:54px;display:grid;grid-template-columns:106px 112px 112px;gap:6px;width:350px;height:56px;padding:3px;border:1px solid #e0e5f0;border-radius:22px;background:#fff}.figma-assessment-tabs button{height:48px;min-height:48px;border-radius:18px;color:#616e80;background:#fff;font-size:14px;font-weight:500}.figma-assessment-tabs button.active{color:#0a63eb;background:#ebf4ff;font-weight:600}.figma-assessment-heading{position:absolute;left:20px;right:20px;top:120px;display:flex;align-items:center;justify-content:space-between}.figma-assessment-heading h1{margin:0;color:#0e131c;font-size:14px}.figma-assessment-heading span{color:#616e80;font-size:10px}.figma-week-list{position:absolute;left:20px;right:20px;top:154px;display:grid;gap:16px;max-height:592px;overflow-y:auto;padding-bottom:8px}.figma-week-list>button{position:relative;width:350px;height:150px;padding:0;border:1px solid #e0e5f0;border-radius:18px;color:#0e131c;background:#fff;text-align:left}.figma-week-list>button>strong{position:absolute;left:15px;top:13px;font-size:15px}.figma-week-list .status{position:absolute;right:18px;top:11px;display:grid;place-items:center;width:80px;height:24px;border-radius:12px;font-size:10px}.figma-week-list .status.done{color:#1a9e63;background:#e8faf0}.figma-week-list .status.active{color:#0a63eb;background:#ebf4ff}.figma-week-list .status.pending{color:#616e80;background:#e8edf5}.figma-week-list>button>small{position:absolute;left:15px;top:41px;color:#75849b;font-size:10px}.figma-week-list>button>div{position:absolute;left:15px;right:15px;top:69px;display:grid;grid-template-columns:88px 88px 1fr;gap:8px}.figma-week-list>button>div b{font-size:11px;font-weight:500}.figma-week-list>button>i{position:absolute;left:15px;top:97px;width:318px;height:6px;border-radius:3px;background:#e8edf5;overflow:hidden}.figma-week-list>button>i em{display:block;height:100%;border-radius:3px;background:#0a63eb}.figma-week-list>button>u{position:absolute;left:15px;top:118px;color:#0a63eb;font-size:11px;font-weight:600;text-decoration:none}.figma-assessment-empty{display:grid;place-items:center;width:350px;height:150px;border:1px solid #e0e5f0;border-radius:18px;color:#616e80;background:#fff;font-size:13px}
@media(min-width:700px){.figma-assessment-list{max-width:834px;min-height:1194px;padding-inline:40px}.figma-assessment-tabs{left:40px;width:754px;grid-template-columns:repeat(3,1fr)}.figma-assessment-heading{left:40px;right:40px}.figma-week-list{left:40px;right:40px;grid-template-columns:1fr 1fr}.figma-week-list>button,.figma-assessment-empty{width:100%}}
</style>
