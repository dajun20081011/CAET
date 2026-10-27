<template>
  <main class="app-shell page-shell figma-tasks">
    <p class="figma-status-time">9:41</p>
    <nav class="figma-task-tabs" aria-label="任务类型">
      <button type="button" :class="{ active:typeFilter==='practice' }" @click="typeFilter='practice'">练习任务</button>
      <button type="button" :class="{ active:typeFilter==='exam' }" @click="typeFilter='exam'">考试任务</button>
    </nav>
    <PageState v-if="loading" tone="loading" title="正在加载任务" />
    <PageState v-else-if="errorMessage" tone="error" title="任务加载失败" :message="errorMessage" action-label="重试" @action="loadTasks" />
    <section v-else class="figma-task-list" aria-live="polite">
      <button v-for="task in visibleTasks" :key="task.assignment_id" type="button" :disabled="task.locked || Boolean(openingAssignmentId)" :class="{ opening:openingAssignmentId===task.assignment_id }" :aria-busy="openingAssignmentId===task.assignment_id" @click="open(task)">
        <strong>{{ task.title }}</strong>
        <span class="figma-task-status" :class="statusClass(task)">{{ openingAssignmentId===task.assignment_id ? '正在打开' : statusLabel(task) }}</span>
        <small>完成进度</small><b>{{ task.completed_items }} / {{ task.total_items }}</b>
        <i><em :style="{width:`${progress(task)}%`} "/></i>
      </button>
      <div v-if="!visibleTasks.length" class="figma-task-empty">当前没有{{ typeFilter==='practice' ? '练习' : '考试' }}任务</div>
    </section>
    <BottomNav />
  </main>
</template>

<script setup lang="ts">
import { computed,onMounted,ref } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import BottomNav from '@/components/BottomNav.vue'
import PageState from '@/components/PageState.vue'
import { cabinlingoApi,type LearnerTask } from '@/api'
import { learnerError } from '@/domain/learnerPresentation'
const route=useRoute();const router=useRouter();const loading=ref(true);const errorMessage=ref('');const tasks=ref<LearnerTask[]>([]);const typeFilter=ref<'practice'|'exam'>(route.query.type==='exam'?'exam':'practice');const openingAssignmentId=ref('')
const visibleTasks=computed(()=>tasks.value.filter(task=>task.task_type===typeFilter.value).sort((a,b)=>Number(completed(a))-Number(completed(b))))
function progress(task:LearnerTask){return Math.min(100,Math.max(0,Number(task.progress_percent)||0))}
function completed(task:LearnerTask){return task.status==='completed'||progress(task)>=100}
function statusLabel(task:LearnerTask){if(task.locked)return'未解锁';if(completed(task))return'已完成';if(task.status==='in_progress'||progress(task)>0)return'进行中';return'待完成'}
function statusClass(task:LearnerTask){return completed(task)?'done':statusLabel(task)==='进行中'?'active':'pending'}
async function open(task:LearnerTask){
  if(task.locked||openingAssignmentId.value)return
  openingAssignmentId.value=task.assignment_id
  try{
    if(task.task_type==='exam')await router.push({path:'/student/exam',query:{assignment:task.assignment_id,task:task.task_id}})
    else await router.push({path:`/student/tasks/${task.assignment_id}`,query:{task:task.task_id,content:task.next_content_item_id||undefined}})
  }catch(error){errorMessage.value=learnerError(error)}finally{openingAssignmentId.value=''}
}
async function loadTasks(){loading.value=true;errorMessage.value='';try{tasks.value=(await cabinlingoApi.learnerTasks()).filter(task=>task.status!=='deleted')}catch(error){errorMessage.value=learnerError(error)}finally{loading.value=false}}
onMounted(loadTasks)
</script>

<style scoped>
.figma-tasks{position:relative;width:100%;max-width:390px;min-height:844px;padding:0 20px 100px;background:#f6f8fb;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;overflow:hidden}.figma-status-time{position:absolute;left:24px;top:0;margin:0;color:#0e131c;font-size:12px;font-weight:500}.figma-task-tabs{position:absolute;left:20px;top:54px;display:grid;grid-template-columns:1fr 1fr;width:350px;height:56px;padding:3px;border:1px solid #e0e5f0;border-radius:22px;background:#fff}.figma-task-tabs button{height:48px;min-height:48px;border-radius:18px;color:#616e80;background:#fff;font-size:14px;font-weight:500}.figma-task-tabs button.active{color:#0a63eb;background:#ebf4ff}.figma-task-list{position:absolute;left:20px;right:20px;top:125px;display:grid;gap:18px;max-height:610px;overflow-y:auto;padding-bottom:8px}.figma-task-list>button{position:relative;width:350px;height:128px;padding:0;border:1px solid #e0e5f0;border-radius:18px;color:#0e131c;background:#fff;text-align:left;overflow:hidden}.figma-task-list>button>strong{position:absolute;left:15px;top:13px;width:230px;font-size:14px;line-height:20px}.figma-task-status{position:absolute;right:18px;top:11px;display:grid;place-items:center;width:78px;height:24px;border-radius:12px;font-size:10px}.figma-task-status.active{color:#0a63eb;background:#ebf4ff}.figma-task-status.pending{color:#f58c14;background:#fff5e3}.figma-task-status.done{color:#1a9e63;background:#e8faf0}.figma-task-list small{position:absolute;left:15px;top:49px;color:#616e80;font-size:10px}.figma-task-list b{position:absolute;right:18px;top:49px;font-size:10px;font-weight:500}.figma-task-list i{position:absolute;left:15px;top:71px;width:318px;height:6px;border-radius:3px;background:#e8edf5;overflow:hidden}.figma-task-list em{display:block;height:100%;border-radius:3px;background:#0a63eb}.figma-task-empty{display:grid;place-items:center;width:350px;height:128px;border:1px solid #e0e5f0;border-radius:18px;color:#616e80;background:#fff;font-size:13px}
.figma-task-list>button.opening{border-color:#9ac3ff;background:#f6faff}.figma-task-list>button:disabled:not(.opening){cursor:not-allowed}.figma-task-list>button.opening .figma-task-status{color:#0a63eb;background:#ebf4ff}
@media(min-width:700px){.figma-tasks{max-width:834px;min-height:1194px;padding-inline:40px}.figma-task-tabs{left:40px;width:754px}.figma-task-list{left:40px;right:40px;grid-template-columns:1fr 1fr}.figma-task-list>button,.figma-task-empty{width:100%}}
</style>
