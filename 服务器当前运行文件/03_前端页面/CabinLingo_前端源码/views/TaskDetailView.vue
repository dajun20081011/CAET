<template>
  <main class="app-shell task-detail-page">
    <MobileDetailHeader :title="task?.title || workspace?.task_title || '任务详情'" @back="router.replace('/student/tasks')" />
    <PageState v-if="loading" tone="loading" title="正在加载任务" />
    <PageState v-else-if="!workspace" tone="error" title="任务无法读取" :message="errorMessage || '任务不存在'" action-label="重试" secondary-action-label="返回任务" @action="load" @secondary-action="router.replace('/student/tasks')" />
    <template v-else>
      <h2>训练篇目</h2>
      <section class="task-content-list">
        <button v-for="item in workspace.contents" :key="item.id" type="button" :disabled="Boolean(openingContentId)" :class="{ opening:openingContentId===item.id }" @click="openContent(item)">
          <strong>{{ item.title || item.chapter_title }}</strong>
          <span :class="item.completed ? 'done' : item.attempt_count > 0 ? 'active' : 'pending'">{{ item.completed ? '已完成' : item.attempt_count > 0 ? '进行中' : '待完成' }}</span>
          <small>{{ item.completed ? '查看测评记录' : '开始 / 继续' }}</small>
        </button>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { ref,watch } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import MobileDetailHeader from '@/components/MobileDetailHeader.vue'
import PageState from '@/components/PageState.vue'
import { cabinlingoApi,type LearnerContent,type LearnerTask,type PracticeWorkspace } from '@/api'
import { learnerError } from '@/domain/learnerPresentation'
const route=useRoute();const router=useRouter();const loading=ref(true);const errorMessage=ref('');const task=ref<LearnerTask|null>(null);const workspace=ref<PracticeWorkspace|null>(null);const openingContentId=ref('');let loadRequest=0
async function openContent(item:LearnerContent){
  if(!workspace.value||openingContentId.value)return
  openingContentId.value=item.id
  try{
    if(item.completed&&item.latest_attempt_id)await router.push(`/student/results/${item.latest_attempt_id}`)
    else await router.push({path:'/student/practice',query:{assignment:workspace.value.assignment_id,task:workspace.value.task_id,content:item.id}})
  }catch(error){errorMessage.value=learnerError(error)}finally{openingContentId.value=''}
}
async function load(){
  const request=++loadRequest;const assignment=String(route.params.assignmentId||'')
  loading.value=true;errorMessage.value='';task.value=null;workspace.value=null
  if(!assignment){errorMessage.value='缺少任务参数';loading.value=false;return}
  try{
    const data=await cabinlingoApi.practiceWorkspace(assignment)
    if(request!==loadRequest)return
    workspace.value=data;loading.value=false
    void cabinlingoApi.learnerTasks().then(rows=>{if(request===loadRequest)task.value=rows.find(row=>row.assignment_id===assignment)||null}).catch(()=>{})
  }catch(error){
    if(request!==loadRequest)return
    try{
      const rows=await cabinlingoApi.learnerTasks();const matched=rows.find(row=>row.assignment_id===assignment)
      if(request!==loadRequest)return
      if(matched?.task_type==='exam'){await router.replace({path:'/student/exam',query:{assignment:matched.assignment_id,task:matched.task_id}});return}
    }catch{/* 保留原始课程读取错误 */}
    if(request===loadRequest){errorMessage.value=learnerError(error);loading.value=false}
  }
}
watch(()=>route.params.assignmentId,()=>{void load()},{immediate:true})
</script>

<style scoped>
.task-detail-page{width:100%;max-width:390px;min-height:844px;margin:auto;padding:24px 20px 40px;background:#f6f8fb;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}.task-detail-page>.mobile-detail-header{margin:0 -20px;width:390px}.task-detail-page>h2{margin:28px 14px 18px;color:#0e131c;font-size:16px}.task-content-list{display:grid;gap:18px}.task-content-list button{position:relative;width:350px;height:64px;padding:0 14px;border:1px solid #e0e5f0;border-radius:16px;color:#0e131c;background:#fff;text-align:left}.task-content-list button.opening{border-color:#9ac3ff;background:#f6faff}.task-content-list strong{position:absolute;left:14px;top:10px;width:225px;font-size:13px}.task-content-list span{position:absolute;right:16px;top:8px;display:grid;place-items:center;width:82px;height:24px;border-radius:12px;font-size:10px}.task-content-list span.pending{color:#f58c14;background:#fff5e3}.task-content-list span.active{color:#0a63eb;background:#ebf4ff}.task-content-list span.done{color:#1a9e63;background:#e8faf0}.task-content-list small{position:absolute;left:14px;top:36px;color:#0a63eb;font-size:11px}.task-content-list button:has(span.done) small{color:#616e80}
@media(min-width:700px){.task-detail-page{max-width:834px;min-height:1194px;padding-inline:40px}.task-detail-page>.mobile-detail-header{margin:0;width:100%}.task-content-list{grid-template-columns:1fr 1fr}.task-content-list button{width:100%}}
</style>
