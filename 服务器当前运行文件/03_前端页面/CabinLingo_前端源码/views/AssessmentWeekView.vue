<template>
  <main class="app-shell figma-week-detail">
    <MobileDetailHeader :title="weekTitle" @back="router.back()" />
    <PageState v-if="loading" tone="loading" title="正在加载本周测评" />
    <PageState v-else-if="errorMessage || !workspace" tone="error" title="本周测评无法读取" :message="errorMessage || '任务不存在'" action-label="返回测评" @action="router.replace('/student/results')" />
    <template v-else>
      <p class="figma-week-meta">{{ task?.due_at ? `截止 ${formatDate(task.due_at)} · ` : '' }}已完成 {{ task?.completed_items || 0 }} / {{ task?.total_items || workspace.contents.length }}</p>
      <section class="figma-week-summary"><div><span>周平均分</span><strong>{{ average ?? '—' }}</strong></div><div><span>有待改进</span><strong>{{ improveCount }}</strong></div><div><span>教员已评价</span><strong>{{ reviewed }} / {{ workspace.contents.length }}</strong></div><p>点击篇目查看教员评价与历次测评；历史结果不会被新测试覆盖。</p></section>
      <h2>本周篇目</h2>
      <section class="figma-week-items">
        <button v-for="item in contentRows" :key="item.id" type="button" @click="openItem(item)">
          <strong>{{ item.title }}</strong><b>{{ item.score ?? '—' }}{{ item.score != null ? ' 分' : '' }}</b><small>第 {{ item.attemptCount }} 次测试 · {{ item.issueText }}</small><span :class="item.reviewed?'reviewed':''">{{ item.reviewed?'教员已评价':'暂无教员评价' }}</span><u>查看测评详情　›</u>
        </button>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed,onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import MobileDetailHeader from '@/components/MobileDetailHeader.vue'
import PageState from '@/components/PageState.vue'
import { cabinlingoApi,type LearnerAttempt,type LearnerTask,type PracticeWorkspace,type TeacherFeedback } from '@/api'
import { confirmedIssues,learnerError } from '@/domain/learnerPresentation'
const route=useRoute();const router=useRouter();const assignmentId=String(route.params.assignmentId);const task=ref<LearnerTask|null>(null);const workspace=ref<PracticeWorkspace|null>(null);const attempts=ref<LearnerAttempt[]>([]);const feedback=ref<TeacherFeedback[]>([]);const loading=ref(true);const errorMessage=ref('')
const weekTitle=computed(()=>task.value?.week_no?`第${['一','二','三','四','五','六','七','八'][task.value.week_no-1]||task.value.week_no}周${task.value.title.replace(/^第?\s*\d+\s*周[·\s]*/,'')}`:task.value?.title||workspace.value?.task_title||'周任务')
const relatedAttempts=computed(()=>attempts.value.filter(item=>item.assignment_id===assignmentId));const scored=computed(()=>relatedAttempts.value.map(item=>item.overall_score).filter((value):value is number=>typeof value==='number'));const average=computed(()=>scored.value.length?Math.round(scored.value.reduce((sum,value)=>sum+value,0)/scored.value.length):null);const improveCount=computed(()=>new Set(relatedAttempts.value.filter(item=>(item.overall_score??100)<90).map(item=>item.content_item_id)).size);const reviewed=computed(()=>{const ids=new Set(relatedAttempts.value.map(item=>item.attempt_id));return feedback.value.filter(item=>item.practice_attempt_id&&ids.has(item.practice_attempt_id)).length})
const contentRows=computed(()=>(workspace.value?.contents||[]).map(content=>{const rows=relatedAttempts.value.filter(item=>item.content_item_id===content.id).sort((a,b)=>a.attempt_no-b.attempt_no);const latest=rows[rows.length-1];const review=latest&&feedback.value.some(item=>item.practice_attempt_id===latest.attempt_id);const issues=latest?confirmedIssues(latest.issues):[];return{id:content.id,title:content.title||content.chapter_title,score:latest?.overall_score??null,attemptCount:rows.length,issueText:issues.length?`发音 ${issues.length}`:'表现良好',reviewed:review,attemptId:latest?.attempt_id||null}}))
function formatDate(value:string){return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit'}).format(new Date(value))}
function openItem(item:{id:string;attemptId:string|null}){if(item.attemptId){void router.push(`/student/results/${item.attemptId}`);return}void router.push({path:'/student/practice',query:{assignment:assignmentId,content:item.id}})}
async function load(){loading.value=true;errorMessage.value='';try{const[tasks,data,a,f]=await Promise.all([cabinlingoApi.learnerTasks(),cabinlingoApi.practiceWorkspace(assignmentId),cabinlingoApi.learnerAttempts(),cabinlingoApi.learnerFeedback()]);task.value=tasks.find(item=>item.assignment_id===assignmentId)||null;workspace.value=data;attempts.value=a;feedback.value=f}catch(error){errorMessage.value=learnerError(error)}finally{loading.value=false}}
onMounted(load)
</script>

<style scoped>
.figma-week-detail{width:100%;max-width:390px;min-height:844px;margin:auto;padding:24px 20px 40px;background:#f6f8fb;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}.figma-week-detail>.mobile-detail-header{width:390px;margin-left:-20px}.figma-week-meta{margin:12px 0 38px;color:#75849b;font-size:11px}.figma-week-summary{display:grid;grid-template-columns:repeat(3,1fr);width:350px;height:110px;padding:14px 16px;border:1px solid #e0e5f0;border-radius:18px;background:#fff}.figma-week-summary div span,.figma-week-summary div strong{display:block}.figma-week-summary div span{color:#75849b;font-size:10px}.figma-week-summary div strong{margin-top:8px;font-size:28px}.figma-week-summary div:nth-child(2) strong{color:#f58c14}.figma-week-summary div:nth-child(3) strong{color:#7653ee}.figma-week-summary p{grid-column:1/-1;margin:4px 0 0;color:#75849b;font-size:9px}.figma-week-detail>h2{margin:26px 0 20px;font-size:15px}.figma-week-items{display:grid;gap:10px}.figma-week-items button{position:relative;width:350px;height:92px;padding:0 14px;border:1px solid #e0e5f0;border-radius:16px;color:#0e131c;background:#fff;text-align:left}.figma-week-items button>strong{position:absolute;left:14px;top:12px;font-size:14px}.figma-week-items button>b{position:absolute;right:16px;top:12px;font-size:14px}.figma-week-items button>small{position:absolute;left:14px;top:39px;color:#75849b;font-size:10px}.figma-week-items button>span{position:absolute;right:16px;top:34px;display:grid;place-items:center;width:108px;height:24px;border-radius:12px;color:#75849b;background:#e8edf5;font-size:10px}.figma-week-items button>span.reviewed{color:#7653ee;background:#f2eaff}.figma-week-items button>u{position:absolute;left:14px;top:66px;color:#0a63eb;font-size:11px;font-weight:600;text-decoration:none}
@media(min-width:700px){.figma-week-detail{max-width:834px;min-height:1194px;padding-inline:40px}.figma-week-detail>.mobile-detail-header{width:100%;margin:0}.figma-week-summary{width:100%}.figma-week-items{grid-template-columns:1fr 1fr}.figma-week-items button{width:100%}}
</style>
