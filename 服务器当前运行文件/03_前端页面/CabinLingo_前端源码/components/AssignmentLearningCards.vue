<template>
  <section v-if="cards.length || error" class="lesson-card">
    <h2>课程学习卡片</h2>
    <div class="version-tabs"><button v-for="card in cards" :key="card.id" :class="{active:selected?.id===card.id}" @click="open(card)">{{ card.title }}</button></div>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <LearningCardViewer v-if="viewer && selected" :src="viewer" :title="selected.title" @refresh="open(selected)" />
  </section>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import { cabinlingoApi } from '@/api'
import LearningCardViewer from './LearningCardViewer.vue'
const props = defineProps<{ assignmentId: string }>()
type Card = { id: string; title: string; learning_card_id: string }
const cards = ref<Card[]>([]); const selected = ref<Card | null>(null); const viewer = ref(''); const error = ref('')
let requestNo = 0
async function open(card: Card) {
  const request = ++requestNo; selected.value = card; viewer.value = ''; error.value = ''
  try { const result = await cabinlingoApi.learnerLearningCard(card.id, props.assignmentId); if(request===requestNo) viewer.value=result.viewer_url }
  catch { if(request===requestNo) error.value='课程卡片加载失败，请重新选择篇目。' }
}
watch(() => props.assignmentId, async (id) => {
  const request=++requestNo; cards.value=[]; selected.value=null; viewer.value=''; error.value=''
  if(!id) return
  try { const result=await cabinlingoApi.assignmentLearningCards(id); if(request!==requestNo)return; cards.value=result; if(result[0])await open(result[0]) }
  catch { if(request===requestNo)error.value='无法读取当前任务的课程卡片。' }
}, { immediate:true })
</script>
