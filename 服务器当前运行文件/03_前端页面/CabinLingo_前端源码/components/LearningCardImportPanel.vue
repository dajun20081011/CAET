<template>
  <section class="learning-card-panel panel">
    <div class="learning-card-panel__heading">
      <div><p class="panel-kicker">LEARNING CARD</p><h2>学习卡片</h2><p>导入制作完成的高保真 HTML 课程包，预览后直接加入现有课程。</p></div>
      <button class="primary-button primary-button--compact" type="button" @click="openImport">+ 导入学习卡片</button>
    </div>
    <p v-if="notice" class="learning-card-notice" :class="{error:noticeError}" role="status">{{ notice }}</p>
    <div v-if="loading" class="learning-card-empty">正在加载学习卡片…</div>
    <div v-else-if="cards.length" class="learning-card-list">
      <article v-for="card in cards" :key="card.id">
        <span class="learning-card-icon">卡</span>
        <div><strong>{{ card.title }}</strong><small>{{ card.category }} · {{ languageLabel(card) }}<template v-if="durationLabel(card)"> · 建议 {{ durationLabel(card) }}</template></small></div>
        <span class="state-pill" :class="card.status">{{ card.status === 'active' ? '可用' : '已归档' }}</span>
        <div class="learning-card-actions"><button type="button" @click="preview(card)">预览</button><button v-if="card.status === 'active'" type="button" @click="openCourse(card)">加入课程</button><button v-if="card.status === 'active'" class="danger" type="button" @click="archive(card)">归档</button></div>
      </article>
    </div>
    <div v-else class="learning-card-empty">还没有学习卡片。导入 ZIP 后可直接预览并加入课程。</div>

    <Teleport to="body">
      <div v-if="dialog" class="learning-card-backdrop" @click.self="close">
        <section class="learning-card-modal" :class="{'learning-card-modal--preview':dialog==='preview'}" role="dialog" aria-modal="true">
          <header><div><h2>{{ dialogTitle }}</h2><p>{{ dialogSubtitle }}</p></div><button type="button" aria-label="关闭" @click="close">×</button></header>
          <template v-if="dialog === 'import'">
            <button class="learning-card-dropzone" type="button" @click="fileInput?.click()"><strong>{{ selectedFile?.name || '选择 Learning Card ZIP' }}</strong><small>仅支持 CabinLingo Learning Card Package V1，最大 50 MB</small></button>
            <input ref="fileInput" class="sr-only" type="file" accept="application/zip,.zip" @change="selectFile">
            <p v-if="dialogError" class="learning-card-error">{{ dialogError }}</p>
            <footer><button type="button" @click="close">取消</button><button class="primary" type="button" :disabled="!selectedFile || submitting" @click="importCard">{{ submitting ? '正在校验并导入…' : '导入' }}</button></footer>
          </template>
          <template v-else-if="dialog === 'success' && activeCard">
            <div class="learning-card-success"><span>✓</span><div><strong>学习卡片导入成功</strong><h3>{{ activeCard.title }}</h3><p>{{ activeCard.category }} · {{ languageLabel(activeCard) }}<template v-if="durationLabel(activeCard)"> · 建议 {{ durationLabel(activeCard) }}</template></p></div></div>
            <footer><button type="button" @click="preview(activeCard)">预览</button><button class="primary" type="button" @click="openCourse(activeCard)">加入课程</button></footer>
          </template>
          <template v-else-if="dialog === 'course' && activeCard">
            <div v-if="courses.length" class="learning-card-course-list"><label v-for="course in courses" :key="course.id" :class="{selected:selectedCourseId===course.id}"><input v-model="selectedCourseId" type="radio" :value="course.id"><span><strong>{{ course.title }}</strong><small>{{ course.description || course.code }}</small></span></label></div><div v-else class="learning-card-empty">请先创建课程，再加入学习卡片。</div>
            <p v-if="dialogError" class="learning-card-error">{{ dialogError }}</p>
            <footer><button type="button" @click="close">取消</button><button class="primary" type="button" :disabled="!selectedCourseId || submitting" @click="addToCourse">{{ submitting ? '正在加入…' : '确认加入' }}</button></footer>
          </template>
          <template v-else-if="dialog === 'preview' && activeCard">
            <LearningCardViewer v-if="viewerUrl" :src="viewerUrl" :title="activeCard.title" @refresh="preview(activeCard)" />
            <div v-else class="learning-card-empty">正在生成安全预览…</div>
          </template>
        </section>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { cabinlingoApi, type Course, type LearningCard } from '@/api'
import LearningCardViewer from '@/components/LearningCardViewer.vue'

const props = defineProps<{ courses: Course[] }>()
const emit = defineEmits<{ added: [courseId: string] }>()
type Dialog = 'import' | 'success' | 'course' | 'preview' | null
const cards = ref<LearningCard[]>([]); const loading = ref(true); const submitting = ref(false); const dialog = ref<Dialog>(null); const activeCard = ref<LearningCard | null>(null); const selectedFile = ref<File | null>(null); const selectedCourseId = ref(''); const viewerUrl = ref(''); const dialogError = ref(''); const notice = ref(''); const noticeError = ref(false); const fileInput = ref<HTMLInputElement | null>(null)
const dialogTitle = computed(() => dialog.value === 'import' ? '导入学习卡片' : dialog.value === 'success' ? '导入完成' : dialog.value === 'course' ? '加入课程' : activeCard.value?.title || '学习卡片预览')
const dialogSubtitle = computed(() => dialog.value === 'import' ? '系统会校验课程包结构与安全性' : dialog.value === 'course' ? '选择一门现有课程即可，系统自动处理课程草稿' : dialog.value === 'preview' ? '此处与学员端使用同一安全查看器' : '')
function languageLabel(card: LearningCard){const values=Array.isArray(card.metadata.languages)?card.metadata.languages:[];return values.length?values.map(value=>String(value).toLowerCase().startsWith('zh')?'中文':String(value).toLowerCase().startsWith('en')?'English':String(value)).join(' / '):'课程精讲'}
function durationLabel(card: LearningCard){const seconds=Number(card.metadata.estimatedDuration||0);return seconds>0?`${seconds}s`:''}
async function load(){loading.value=true;try{cards.value=await cabinlingoApi.learningCards()}catch{notice.value='学习卡片加载失败，请检查服务、权限及数据库版本。';noticeError.value=true}finally{loading.value=false}}
function openImport(){selectedFile.value=null;dialogError.value='';dialog.value='import'}
function selectFile(event:Event){const file=(event.target as HTMLInputElement).files?.[0]||null;dialogError.value='';if(file&&!file.name.toLowerCase().endsWith('.zip')){dialogError.value='请选择 .zip 学习卡片课程包';selectedFile.value=null;return}if(file&&file.size>50*1024*1024){dialogError.value='课程包文件不能超过 50 MB';selectedFile.value=null;return}selectedFile.value=file}
async function importCard(){if(!selectedFile.value)return;submitting.value=true;dialogError.value='';try{activeCard.value=await cabinlingoApi.importLearningCard(selectedFile.value);await load();dialog.value='success'}catch(error:any){dialogError.value=error?.response?.data?.detail||'导入失败，请检查课程包结构和安全内容'}finally{submitting.value=false}}
async function preview(card:LearningCard){activeCard.value=card;viewerUrl.value='';dialog.value='preview';try{viewerUrl.value=(await cabinlingoApi.previewLearningCard(card.id)).viewer_url}catch{notice.value='预览地址生成失败，请稍后重试。';noticeError.value=true;close()}}
function openCourse(card:LearningCard){activeCard.value=card;selectedCourseId.value=props.courses[0]?.id||'';dialogError.value='';dialog.value='course'}
async function addToCourse(){if(!activeCard.value||!selectedCourseId.value)return;submitting.value=true;dialogError.value='';try{const result=await cabinlingoApi.addLearningCardToCourse(activeCard.value.id,selectedCourseId.value);notice.value=`“${activeCard.value.title}”已加入“${result.course_title}”草稿，发布课程版本后即可创建任务。`;noticeError.value=false;emit('added',selectedCourseId.value);close()}catch(error:any){dialogError.value=error?.response?.data?.detail||'加入课程失败，请稍后重试'}finally{submitting.value=false}}
async function archive(card:LearningCard){if(!window.confirm(`归档“${card.title}”？已加入课程的历史内容仍会保留。`))return;try{await cabinlingoApi.archiveLearningCard(card.id);notice.value='学习卡片已归档，历史课程引用保持可用。';noticeError.value=false;await load()}catch{notice.value='归档失败，请稍后重试。';noticeError.value=true}}
function close(){dialog.value=null;viewerUrl.value='';dialogError.value='';submitting.value=false}
onMounted(load)
</script>

<style scoped>
.learning-card-panel{margin-bottom:18px}.learning-card-panel__heading{display:flex;align-items:flex-start;justify-content:space-between;gap:22px}.panel-kicker{margin:0 0 5px;color:#1769ef;font-size:10px;font-weight:800;letter-spacing:.15em}.learning-card-panel h2{margin:0;color:#102f63;font-size:20px}.learning-card-panel__heading p:last-child{margin:6px 0 0;color:#7b8da9;font-size:12px}.learning-card-list{display:grid;margin-top:18px;border-top:1px solid #e2eaf5}.learning-card-list article{display:grid;grid-template-columns:42px minmax(0,1fr) auto auto;align-items:center;gap:13px;padding:15px 4px;border-bottom:1px solid #e7edf6}.learning-card-icon{display:grid;place-items:center;width:40px;height:40px;border-radius:12px;color:#fff;background:linear-gradient(135deg,#1769ef,#5a9cff);font-weight:800}.learning-card-list strong,.learning-card-list small{display:block}.learning-card-list small{margin-top:5px;color:#8190a9;font-size:11px}.state-pill{padding:5px 8px;border-radius:99px;color:#237d61;background:#eaf9f3;font-size:10px}.state-pill.archived{color:#71809a;background:#eef2f7}.learning-card-actions{display:flex;gap:7px}.learning-card-actions button{min-height:38px;padding:0 11px;border:1px solid #cbdcf5;border-radius:9px;color:#1769ef;background:#fff}.learning-card-actions .danger{color:#bd5362;border-color:#f0c4ca}.learning-card-empty{padding:28px;text-align:center;color:#8090aa}.learning-card-notice,.learning-card-error{margin:14px 0 0;padding:10px 12px;border-radius:10px;color:#267b60;background:#eaf9f3;font-size:12px}.learning-card-notice.error,.learning-card-error{color:#a44450;background:#fff0f2}.learning-card-backdrop{position:fixed;inset:0;z-index:80;display:grid;place-items:center;padding:20px;background:#071d496e}.learning-card-modal{width:min(600px,100%);max-height:92vh;overflow:auto;padding:24px;border-radius:20px;background:#fff;box-shadow:0 28px 80px #071d4950}.learning-card-modal--preview{width:min(1180px,96vw)}.learning-card-modal>header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:18px}.learning-card-modal h2{margin:0;color:#102f63}.learning-card-modal header p{margin:5px 0 0;color:#8190a9;font-size:12px}.learning-card-modal header>button{width:36px;height:36px;border-radius:50%;color:#6e7f9b;background:#eef3f9;font-size:22px}.learning-card-dropzone{display:grid;place-items:center;gap:7px;width:100%;min-height:160px;padding:24px;border:1px dashed #8db8f7;border-radius:16px;color:#1769ef;background:#f5f9ff}.learning-card-dropzone small{color:#8090aa}.learning-card-modal footer{display:flex;justify-content:flex-end;gap:9px;margin-top:20px}.learning-card-modal footer button{min-width:96px;min-height:44px;padding:0 16px;border:1px solid #cbdcf5;border-radius:10px;color:#1769ef;background:#fff}.learning-card-modal footer .primary{color:#fff;border-color:#1769ef;background:#1769ef}.learning-card-modal footer button:disabled{opacity:.45}.learning-card-success{display:flex;align-items:flex-start;gap:15px;padding:20px;border-radius:16px;background:#f1fbf6}.learning-card-success>span{display:grid;place-items:center;width:42px;height:42px;border-radius:50%;color:#fff;background:#2bad7f;font-size:22px}.learning-card-success h3{margin:8px 0 4px;color:#102f63}.learning-card-success p{margin:0;color:#71809b}.learning-card-course-list{display:grid;gap:9px;max-height:360px;overflow:auto}.learning-card-course-list label{display:flex;align-items:center;gap:12px;padding:13px;border:1px solid #dde7f4;border-radius:12px}.learning-card-course-list label.selected{border-color:#74a9f8;background:#f2f7ff}.learning-card-course-list strong,.learning-card-course-list small{display:block}.learning-card-course-list small{margin-top:4px;color:#8493aa}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}@media(max-width:760px){.learning-card-panel{padding:18px}.learning-card-panel__heading{flex-direction:column}.learning-card-panel__heading button{width:100%;min-height:44px}.learning-card-list article{grid-template-columns:42px 1fr}.learning-card-list article>.state-pill{justify-self:start}.learning-card-actions{grid-column:1/-1}.learning-card-actions button{flex:1;min-height:44px}.learning-card-backdrop{align-items:end;padding:0}.learning-card-modal{width:100%;max-height:94vh;padding:20px 16px calc(20px + env(safe-area-inset-bottom));border-radius:22px 22px 0 0}.learning-card-modal--preview{width:100%}.learning-card-modal footer{position:sticky;bottom:0;margin:18px -16px -20px;padding:12px 16px calc(12px + env(safe-area-inset-bottom));background:#fff}.learning-card-modal footer button{flex:1}}
</style>
