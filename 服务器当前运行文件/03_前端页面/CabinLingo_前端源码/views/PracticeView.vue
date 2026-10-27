<template>
  <main class="app-shell page-shell practice-page" :class="{ 'is-assessing':assessmentVisible, 'is-complete':submitStage==='success' }">
    <MobileDetailHeader :title="selected?.title || workspace?.task_title || '课程练习'" @back="leavePractice" />

    <PageState v-if="loading" tone="loading" title="正在加载课程与训练记录" />
    <PageState v-else-if="!workspace" tone="error" title="课程无法读取" :message="errorMessage || '内容不存在'" action-label="重试" secondary-action-label="返回任务" @action="initializeWorkspace" @secondary-action="leavePractice" />

    <template v-else>
      <div v-if="workspace.contents.length > 1" class="content-switcher" aria-label="训练篇目">
        <button v-for="item in workspace.contents" :key="item.id" :disabled="submitting || recording || paused" :class="{ active:selected?.id === item.id, done:item.completed }" @click="selectContent(item)">
          <b>{{ contentLabel(item) }}</b><small>第 {{ item.sequence_no }} 篇</small>
        </button>
      </div>

      <PageState v-if="!selected" tone="empty" title="暂无训练内容" message="该任务尚未包含可学习内容。" />
      <template v-else>
        <PdfPageViewer v-if="selected.document_url" :bytes="documentBytes" :page-number="selected.document_page_no || 1" :page-count="selected.document_page_count" />
        <section v-if="selected.assets?.length" class="course-media">
          <div class="course-media__heading"><strong>课程音视频</strong></div>
          <article v-for="asset in selected.assets" :key="asset.id" class="course-media__item">
            <div><span>{{ asset.mime_type.startsWith('video/') ? '视频' : '音频' }}</span><strong>{{ asset.original_filename }}</strong></div>
            <video v-if="asset.mime_type.startsWith('video/') && mediaPreviews[asset.id]" controls playsinline :src="mediaPreviews[asset.id]" />
            <audio v-else-if="mediaPreviews[asset.id]" controls :src="mediaPreviews[asset.id]" />
            <small v-else>媒体载入中…</small>
          </article>
        </section>

        <div class="practice-stage">
          <section class="lesson-card">
            <article v-if="selected.content_type === 'broadcast' && selected.reference_text" class="reference-copy" aria-label="标准广播词">
              <p v-for="(paragraph,index) in referenceParagraphs" :key="index">{{ paragraph }}</p>
            </article>
            <LearningCardViewer v-else-if="selected.learning_card_id && learningCardViewer" :src="learningCardViewer.viewer_url" :title="selected.title" @ready="cardReady = true" @refresh="loadContentResources(selected)" />
            <div v-else-if="selected.learning_card_id" class="learning-card-waiting">正在生成学习卡片安全访问地址…</div>
            <iframe v-else class="lesson-preview" sandbox="" title="课程内容" :srcdoc="selected.sanitized_html" />

            <section v-if="selected.interactions?.length" class="interactive-card">
              <div class="interactive-heading"><div><span>AI 互动练习</span><strong>完成互动，再提交录音</strong></div><small>{{ selected.completed_interactions }}/{{ selected.required_interactions }}</small></div>
              <article v-for="interaction in selected.interactions" :key="interaction.id" class="interactive-item">
                <div class="interactive-item__title"><span>{{ interaction.interaction_type === 'fill_blank' ? '填空' : interaction.interaction_type === 'hotspot' ? '点击' : '选择' }}</span><strong>{{ interaction.title }}</strong><i v-if="interaction.completed">已完成</i></div>
                <p>{{ interaction.prompt }}</p>
                <div v-if="interaction.interaction_type !== 'fill_blank'" class="interaction-options"><button v-for="option in interaction.options" :key="option" type="button" :disabled="interactionPending === interaction.id" :class="{ chosen:interactionFeedback[interaction.id]?.is_correct && interactionFeedback[interaction.id]?.feedback && option === interactionFeedback[interaction.id]?.answer }" @click="submitInteraction(interaction,option)">{{ option }}</button></div>
                <form v-else class="interaction-fill" @submit.prevent="submitInteraction(interaction,interactionInputs[interaction.id] || '')"><input v-model="interactionInputs[interaction.id]" type="text" placeholder="输入你的答案" :disabled="interactionPending === interaction.id"><button class="outline-button outline-button--small" :disabled="interactionPending === interaction.id">{{ interactionPending === interaction.id ? '提交中…' : '提交答案' }}</button></form>
                <p v-if="interactionFeedback[interaction.id]" class="interaction-feedback" :class="{ correct:interactionFeedback[interaction.id].is_correct }">{{ interactionFeedback[interaction.id].feedback }}</p>
              </article>
            </section>
          </section>

          <section v-if="selected.learning_card_id" class="record-card-live">
            <button class="primary-button" :disabled="!cardReady || markingRead || selected.completed" @click="markRead">{{ selected.completed ? '已读' : markingRead ? '正在保存…' : '标记已读' }}</button>
          </section>
          <section v-else class="record-card-live">
            <div v-if="!audioBlob || recording || paused" class="record-control">
              <button v-if="!audioBlob || recording || paused" class="record-main" :class="{ active:recording, paused }" type="button" :disabled="submitting" :aria-label="recording ? '完成录音' : paused ? '继续录音' : '开始录音'" @click="toggleRecording"><span aria-hidden="true" /></button>
              <span v-else class="record-complete-icon" aria-hidden="true">✓</span>
              <div class="record-state"><strong>{{ recording ? '正在录音' : paused ? '录音已暂停' : audioBlob ? '录音已完成' : '开始录音' }}</strong><small v-if="recording || paused || audioBlob">{{ formatDuration(recording || paused ? elapsedMs : durationMs) }}</small></div>
            </div>
            <audio ref="audioPlayer" class="record-preview" :src="audioPreview" @play="previewing=true" @pause="previewing=false" @ended="previewing=false" />
            <div v-if="recording || paused" class="record-actions record-actions--active"><button class="outline-button" type="button" :disabled="submitting" @click="finishRecordingNow">完成录音</button></div>
            <div v-if="audioBlob && !recording && !paused && !assessmentVisible" class="recorded-actions" aria-label="录音完成操作">
              <div class="recorded-action recorded-action--complete" role="status"><span><img :src="recordingCheck" alt=""></span><strong>完成录音</strong></div>
              <button class="recorded-action recorded-action--submit" type="button" :disabled="submitting" @click="submitPractice"><span><img :src="recordingSubmit" alt=""></span><strong>提交</strong></button>
            </div>
          </section>
        </div>

        <section v-if="result || historyLoading" class="result-card">
          <div v-if="historyLoading" class="history-loading">正在读取历史训练结果…</div>
          <template v-else-if="result">
            <header class="result-title"><h2>AI 测评结果</h2><span>第 {{ attemptOrdinal(result) }} 次</span></header>
            <div v-if="attemptHistory.length > 1" class="attempt-tabs" role="tablist" aria-label="训练次数">
              <button v-for="(attempt,index) in attemptHistory" :key="attempt.attempt_id" type="button" role="tab" :aria-selected="attempt.attempt_id === result.attempt_id" :class="{ active:attempt.attempt_id === result.attempt_id }" @click="selectAttempt(attempt)"><span>第 {{ index + 1 }} 次</span><strong>{{ attemptScore(attempt) ?? '—' }}</strong><small>{{ formatAttemptDate(attempt.created_at) }}</small></button>
            </div>

            <section class="assessment-overview" aria-label="本次测评">
              <article class="overall-score"><strong>{{ result.overall_score ?? '—' }}</strong><span>{{ overallAssessment }}</span></article>
              <div class="score-grid"><article v-for="entry in primaryScores" :key="entry.key"><span>{{ entry.label }}</span><strong>{{ entry.value ?? '—' }}</strong></article></div>
              <div class="result-meta"><span v-if="result.speed !== null">语速 <strong>{{ result.speed }}</strong></span><span v-if="result.duration_seconds !== null">评测时长 <strong>{{ formatAssessmentDuration(result.duration_seconds) }}</strong></span></div>
            </section>

            <section class="issue-summary" aria-labelledby="issue-summary-title">
              <header><h3 id="issue-summary-title">问题汇总</h3><small>{{ feedbackItems.length }} 项</small></header>
              <div class="issue-summary-grid"><article v-for="item in issueSummary" :key="item.key" :class="{ active:item.count > 0 }"><span>{{ item.label }}</span><strong>{{ item.count }}</strong></article></div>
            </section>

            <section class="analysis-disclosure">
              <button class="analysis-toggle" type="button" :aria-expanded="detailedAnalysisOpen" aria-controls="detailed-analysis" @click="toggleDetailedAnalysis"><span><strong>详细分析</strong><small>逐词发音 · 问题清单 · 录音定位</small></span><i aria-hidden="true">⌄</i></button>
              <section v-if="detailedAnalysisOpen" id="detailed-analysis" class="feedback-copy">
                <section v-if="evidenceAudioUrl" class="feedback-audio" aria-label="本次测评录音"><button type="button" :class="{ playing:evidencePlaying }" @click="toggleEvidencePlayback"><span>{{ evidencePlaying ? 'Ⅱ' : '▶' }}</span><b>{{ evidencePlaying ? '暂停播放' : '我的录音' }}</b></button><div><strong>本次测评录音</strong><small>{{ formatAudioClock(evidenceCurrentSeconds) }} / {{ formatAudioClock(evidenceDurationSeconds) }}</small><input type="range" min="0" :max="Math.max(evidenceDurationSeconds,0)" step="0.1" :value="evidenceCurrentSeconds" aria-label="录音进度" @input="changeEvidencePosition"></div></section>
                <div class="feedback-legend"><span><i class="good" />优秀 ≥85</span><span><i class="medium" />注意 70–84</span><span><i class="low" />改进 &lt;70</span><span><i class="problem" />错漏读</span></div>
                <div v-if="!granularScoreAvailable" class="granular-score-notice"><div><strong>本次记录没有逐字 / 逐词得分</strong><span>可使用现有录音重新分析，无需重新录音。</span></div><button type="button" :disabled="reanalyzing" @click="reanalyzeCurrentAttempt">{{ reanalyzing ? '正在重新分析…' : '重新分析现有录音' }}</button></div>
                <div class="annotated-script feedback-script" aria-label="AI 发音标注文本"><template v-for="segment in scriptSegments" :key="segment.key"><button v-if="segment.isWord" type="button" class="script-word" :class="wordClass(segment)" :title="wordTitle(segment)" @click="selectEvidence(segment,$event)"><i v-if="segment.issues.length">{{ shortIssueLabel(segment.issues[0]?.type) }}</i><b>{{ segment.text }}</b><small>{{ segment.detail ? wordScore(segment.detail) ?? '—' : '—' }}</small></button><span v-else>{{ segment.text }}</span></template></div>
                <nav class="feedback-filters" aria-label="问题筛选"><button v-for="filter in feedbackFilters" :key="filter.key" type="button" :class="{ active:issueFilter === filter.key }" :aria-pressed="issueFilter === filter.key" @click="issueFilter=filter.key">{{ filter.label }} <strong>{{ filter.count }}</strong></button></nav>
                <section class="feedback-list"><h3>问题清单</h3><button v-for="item in visibleFeedbackItems" :key="item.key" type="button" :class="{ 'is-selected':feedbackIsSelected(item) }" :aria-pressed="feedbackIsSelected(item)" @click="openFeedback(item,$event)"><span :class="item.category">{{ categoryLabel(item.category) }}</span><div><strong>{{ item.label }}</strong><p>{{ compactFeedbackMessage(item) }}</p></div><small v-if="typeof item.startMs === 'number'">{{ formatEvidenceTime(item.startMs) }} ▶</small></button><button v-if="filteredFeedbackItems.length > 4" type="button" class="feedback-expand" @click="showAllFeedback = !showAllFeedback">{{ showAllFeedback ? '收起问题清单' : `展开全部 ${filteredFeedbackItems.length} 项问题` }}</button><div v-if="!filteredFeedbackItems.length" class="result-empty">此分类没有发现问题。</div></section>
                <audio ref="evidenceAudioPlayer" class="record-preview" :src="evidenceAudioUrl" @play="evidencePlaying=true" @pause="evidencePlaying=false" @ended="evidencePlaying=false" @timeupdate="syncEvidenceProgress" @loadedmetadata="syncEvidenceProgress" />
              </section>
            </section>

            <div v-if="canRetrain" class="result-actions"><p>教员建议针对本次问题再次练习</p><button class="primary-button" type="button" @click="retry">再练一遍</button></div>
          </template>
        </section>
      </template>
    </template>

    <section v-if="selected && assessmentVisible" class="figma-submit-state" :class="{ 'is-failed':submitStage==='failed' }" aria-live="polite">
      <article class="figma-submit-script"><p v-for="(paragraph,index) in referenceParagraphs" :key="index">{{ paragraph }}</p></article>
      <template v-if="submitStage==='success'">
        <button class="figma-completed-cta" type="button" :disabled="!result" @click="openCurrentResult">查看详情 <img :src="chevronRightWhite" alt=""></button>
      </template>
      <template v-else>
        <div class="figma-assessing-card">
          <img v-if="submitStage!=='failed'" class="figma-loading-dots" :src="aiLoadingDots" alt="">
          <span v-else class="figma-error-badge" aria-hidden="true">!</span>
          <strong>{{ submitStage==='failed' ? '测评暂未完成' : 'AI 测评中' }}</strong>
          <p>{{ submitStage==='failed' ? assessmentError : '正在分析发音、流利度与完整度' }}</p>
          <button v-if="submitStage==='failed'" type="button" :disabled="submitting" @click="retryAssessment">{{ submitting ? '正在查询…' : pendingSubmission ? '重新查询' : '重试提交' }}</button>
        </div>
      </template>
    </section>

    <p v-if="errorMessage" class="form-error">{{ errorMessage }}</p>

    <div v-if="selectedEvidence" class="word-detail-layer" :class="{ 'is-sheet':wordDetailIsSheet }">
      <button class="word-detail-backdrop" type="button" aria-label="关闭字词详情" @click="closeEvidence" />
      <section class="word-detail-card" role="dialog" aria-modal="true" aria-labelledby="word-detail-title" :style="wordDetailStyle">
        <button class="word-detail-close" type="button" aria-label="关闭" @click="closeEvidence">×</button>
        <h3 id="word-detail-title">{{ selectedEvidence.text }}</h3>
        <p class="word-phonetic" :class="{ muted:!selectedEvidencePhonetic }">{{ selectedEvidencePhonetic || '音标数据未返回' }}</p>
        <p class="word-score-line"><strong>{{ selectedEvidence.detail ? wordScore(selectedEvidence.detail) ?? '—' : '—' }}</strong><span>{{ selectedEvidenceStatus }}</span></p>
        <div class="word-audio-actions"><button type="button" @click="speakStandardPronunciation">▶ 标准发音</button><button type="button" :disabled="!evidenceAudioUrl || typeof selectedEvidenceStart() !== 'number'" @click="playSelectedEvidence">▶ 我的发音</button></div>
        <p class="word-problem">{{ selectedEvidenceMessage }}</p>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import PageState from '@/components/PageState.vue'
import MobileDetailHeader from '@/components/MobileDetailHeader.vue'
import recordingCheck from '@/assets/figma/recording-check.svg'
import recordingSubmit from '@/assets/figma/recording-submit.svg'
import aiLoadingDots from '@/assets/figma/ai-loading-dots.svg'
import chevronRightWhite from '@/assets/figma/chevron-right-white.svg'
import { learnerError, confirmedIssues } from '@/domain/learnerPresentation'
import PdfPageViewer from '@/components/PdfPageViewer.vue'
import LearningCardViewer from '@/components/LearningCardViewer.vue'
import { computed,onBeforeUnmount,onMounted,reactive,ref,watch } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { cabinlingoApi,type InteractionAnswer,type LearnerAttempt,type LearnerContent,type LearnerInteraction,type LearnerIssue,type PracticeWorkspace,type WordDetail } from '@/api'

interface ScriptSegment { key:string; text:string; isWord:boolean; index?:number; detail?:WordDetail; issues:LearnerIssue[] }
type IssueCategory='omission'|'insertion'|'repetition'|'substitution'|'pronunciation'|'pause'|'other'
type IssueFilter='all'|IssueCategory
interface FeedbackItem { key:string; category:IssueCategory; label:string; message:string; startMs?:number; issue?:LearnerIssue; detail?:WordDetail }
interface PendingPracticeSubmission { assignmentId:string; contentId:string; recordingId:string; attemptId?:string; requestedAt:number }

const route=useRoute(); const router=useRouter(); const assignmentId=computed(()=>String(route.query.assignment||'')); const workspace=ref<PracticeWorkspace|null>(null); const selected=ref<LearnerContent|null>(null); const loading=ref(true); const recording=ref(false); const paused=ref(false); const previewing=ref(false); const audioBlob=ref<Blob|null>(null); const audioPreview=ref(''); const audioPlayer=ref<HTMLAudioElement|null>(null); const durationMs=ref(0); const elapsedMs=ref(0); const submitting=ref(false); const submitStage=ref<'idle'|'recorded'|'uploading'|'analyzing'|'success'|'failed'>('idle'); const assessmentError=ref(''); const pendingSubmission=ref<PendingPracticeSubmission|null>(null); const reanalyzing=ref(false); const errorMessage=ref(''); const result=ref<LearnerAttempt|null>(null); const attemptHistory=ref<LearnerAttempt[]>([]); const historyLoading=ref(false); const issueFilter=ref<IssueFilter>('all'); const evidenceAudioUrl=ref(''); const evidenceAudioPlayer=ref<HTMLAudioElement|null>(null); const evidencePlaying=ref(false); const evidenceCurrentSeconds=ref(0); const evidenceDurationSeconds=ref(0); const correctionOf=ref<string|null>(String(route.query.correction||'')||null); const browserTranscript=ref(''); const selectedEvidence=ref<ScriptSegment|null>(null); const detailedAnalysisOpen=ref(false); const wordDetailIsSheet=ref(false); const wordDetailAnchor=ref({left:0,top:0,bottom:0,width:0}); let mediaRecorder:MediaRecorder|null=null; let stream:MediaStream|null=null; let chunks:BlobPart[]=[]; let accumulatedMs=0; let activeStartedAt=0; let ticker:number|undefined; let stopResolver:(()=>void)|null=null; let discardRecording=false; let speechRecognition:CabinSpeechRecognition|null=null; let speechShouldRun=false; let speechRestartTimer:number|undefined; let historyRequest=0; let evidenceAudioRequest=0; let assessmentRequest=0; let workspaceRequest=0
const interactionInputs=reactive<Record<string,string>>({}); const interactionFeedback=reactive<Record<string,InteractionAnswer>>({}); const interactionPending=ref('')
const assessmentVisible=computed(()=>['uploading','analyzing','failed','success'].includes(submitStage.value))
const referenceParagraphs=computed(()=>selected.value?.reference_text.split(/\r?\n+/).map(item=>item.trim()).filter(Boolean)||[])
const primaryScores=computed(()=>[
  {key:'fluency',label:'流畅度',value:result.value?.score_summary?.fluency},
  {key:'expression',label:'表达与韵律',value:result.value?.score_summary?.expression},
  {key:'completeness',label:'完整度',value:result.value?.score_summary?.completeness},
  {key:'pronunciation',label:'发音',value:result.value?.score_summary?.pronunciation},
])
const scriptSegments=computed<ScriptSegment[]>(()=>buildScriptSegments(selected.value?.reference_text||'',result.value))
const feedbackItems=computed<FeedbackItem[]>(()=>buildFeedbackItems(result.value))
const issueSummary=computed(()=>[
  {key:'pronunciation',label:'发音',count:feedbackItems.value.filter(item=>item.category==='pronunciation').length},
  {key:'omission',label:'漏读',count:feedbackItems.value.filter(item=>item.category==='omission').length},
  {key:'insertion',label:'增读',count:feedbackItems.value.filter(item=>item.category==='insertion').length},
  {key:'repetition',label:'回读',count:feedbackItems.value.filter(item=>item.category==='repetition').length},
  {key:'substitution',label:'错读',count:feedbackItems.value.filter(item=>item.category==='substitution').length},
  {key:'pause',label:'停顿',count:feedbackItems.value.filter(item=>item.category==='pause').length},
])
const overallAssessment=computed(()=>{const score=result.value?.overall_score;if(score===null||score===undefined)return '等待评分';if(score>=90)return '表现优秀';if(score>=75)return '整体良好';if(score>=60)return '继续加油';return '需要改进'})
const canRetrain=computed(()=>result.value?.teacher_feedback?.required_retraining===true)
const selectedEvidencePhonetic=computed(()=>{
  const detail=selectedEvidence.value?.detail
  if(!detail)return ''
  const pinyin=detail.expected_pinyin||detail.pinyin
  if(pinyin)return pinyin
  const phonemes=(detail.phonemes||[]).map(item=>item.phoneme||item.phone||'').filter(Boolean)
  return phonemes.length?`/${phonemes.join(' ')}/`:''
})
const selectedEvidenceStatus=computed(()=>{const detail=selectedEvidence.value?.detail;const score=detail?wordScore(detail):null;if(score===null)return selectedEvidence.value?.issues.length?'需要改进':'查看详情';if(score>=85)return '优秀';if(score>=70)return '需要注意';return '需要改进'})
const selectedEvidenceMessage=computed(()=>selectedEvidence.value?.issues[0]?.training_advice||selectedEvidence.value?.issues[0]?.message||(selectedEvidenceStatus.value==='优秀'?'发音清晰，继续保持。':selectedEvidenceStatus.value==='需要注意'?'发音基本准确，注意音素稳定性。':'请对照标准发音，重点练习该词。'))
const wordDetailStyle=computed<Record<string,string>>(()=>{
  if(wordDetailIsSheet.value)return {} as Record<string,string>
  const width=Math.min(340,Math.max(window.innerWidth-32,260));const left=Math.min(Math.max(wordDetailAnchor.value.left+wordDetailAnchor.value.width/2-width/2,16),window.innerWidth-width-16);const above=wordDetailAnchor.value.top>280;const top=above?Math.max(16,wordDetailAnchor.value.top-12):Math.min(window.innerHeight-260,wordDetailAnchor.value.bottom+12)
  return{width:`${width}px`,left:`${left}px`,top:`${top}px`,transform:above?'translateY(-100%)':'none'}
})
const feedbackFilters=computed(()=>{
  const definitions:Array<{key:IssueFilter;label:string}>=[{key:'all',label:'全部'},{key:'omission',label:'漏读'},{key:'insertion',label:'增读'},{key:'repetition',label:'回读'},{key:'substitution',label:'错读'},{key:'pronunciation',label:'发音问题'},{key:'pause',label:'停顿问题'},{key:'other',label:'其他'}]
  return definitions.map(item=>({...item,count:item.key==='all'?feedbackItems.value.length:feedbackItems.value.filter(issue=>issue.category===item.key).length})).filter(item=>item.key!=='other'||item.count>0)
})
const filteredFeedbackItems=computed(()=>issueFilter.value==='all'?feedbackItems.value:feedbackItems.value.filter(item=>item.category===issueFilter.value))
const showAllFeedback=ref(false)
const visibleFeedbackItems=computed(()=>showAllFeedback.value?filteredFeedbackItems.value:filteredFeedbackItems.value.slice(0,4))
watch([issueFilter,result],()=>{showAllFeedback.value=false})
watch(result,()=>{detailedAnalysisOpen.value=false;selectedEvidence.value=null})
const granularScoreAvailable=computed(()=>scriptSegments.value.some(segment=>segment.detail&&wordScore(segment.detail)!==null))
const cardReady=ref(false); const markingRead=ref(false); let resourceRequest=0
const documentBytes=ref<Uint8Array|null>(null); const learningCardViewer=ref<{viewer_url:string}|null>(null); const mediaPreviews=reactive<Record<string,string>>({}); const resourceUrls=new Set<string>()
function clearContentResources(){resourceUrls.forEach(url=>URL.revokeObjectURL(url));resourceUrls.clear();documentBytes.value=null;learningCardViewer.value=null;Object.keys(mediaPreviews).forEach(key=>delete mediaPreviews[key])}
async function loadContentResources(item:LearnerContent){const request=++resourceRequest;cardReady.value=false;clearContentResources();if(item.learning_card_id){try{const viewer=await cabinlingoApi.learnerLearningCard(item.id,assignmentId.value);if(request===resourceRequest)learningCardViewer.value=viewer}catch{errorMessage.value='学习卡片载入失败，请刷新任务后重试'}return}if(item.document_url){try{documentBytes.value=await cabinlingoApi.courseDocumentPdf(item.id)}catch{errorMessage.value='PDF 课件载入失败，请稍后重试'}}for(const asset of item.assets||[]){try{const blob=await cabinlingoApi.protectedMedia(asset.url);const url=URL.createObjectURL(blob);resourceUrls.add(url);mediaPreviews[asset.id]=url}catch{errorMessage.value='课程音视频载入失败，请稍后重试'}}}
watch(selected,(item)=>{if(item)void loadContentResources(item)},{immediate:true})
async function markRead(){if(!selected.value?.learning_card_id||!cardReady.value)return;const contentId=selected.value.id;markingRead.value=true;try{await cabinlingoApi.markLearningCardRead(contentId,assignmentId.value);const updated=await cabinlingoApi.practiceWorkspace(assignmentId.value);workspace.value=updated;if(selected.value?.id===contentId){const item=updated.contents.find(item=>item.id===contentId);if(item)Object.assign(selected.value,item)}}catch{errorMessage.value='阅读记录保存失败，请确认任务仍开放。'}finally{markingRead.value=false}}
function mimeType(){for(const value of ['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus']){if(MediaRecorder.isTypeSupported(value))return value}return ''}
function stopTicker(){if(ticker){window.clearInterval(ticker);ticker=undefined}}
function startTicker(){stopTicker();ticker=window.setInterval(()=>{elapsedMs.value=accumulatedMs+Math.max(Date.now()-activeStartedAt,0)},200)}
function refreshAudioBlob(type=mediaRecorder?.mimeType||'audio/webm'){if(!chunks.length)return;const blob=new Blob(chunks,{type});if(!blob.size)return;if(audioPreview.value)URL.revokeObjectURL(audioPreview.value);durationMs.value=elapsedMs.value;audioBlob.value=blob;audioPreview.value=URL.createObjectURL(blob)}
function clearSpeechRestart(){if(speechRestartTimer){window.clearTimeout(speechRestartTimer);speechRestartTimer=undefined}}
function startBrowserSpeech(){
  const Constructor=window.SpeechRecognition||window.webkitSpeechRecognition
  if(!Constructor)return
  clearSpeechRestart(); speechShouldRun=true
  try{
    speechRecognition?.abort()
    const recognition=new Constructor()
    recognition.continuous=true; recognition.interimResults=false; recognition.maxAlternatives=1
    recognition.lang=/[\u3400-\u9fff]/.test(selected.value?.reference_text||'')?'zh-CN':'en-US'
    recognition.onresult=(event)=>{let finalText='';for(let index=event.resultIndex;index<event.results.length;index+=1){const item=event.results[index];if(item?.isFinal&&item[0]?.transcript)finalText+=`${item[0].transcript} `}if(finalText)browserTranscript.value=`${browserTranscript.value} ${finalText}`.replace(/\s+/g,' ').trim()}
    recognition.onerror=(event)=>{if(['not-allowed','service-not-allowed','audio-capture'].includes(event.error))speechShouldRun=false}
    recognition.onend=()=>{if(speechRecognition===recognition)speechRecognition=null;if(speechShouldRun&&recording.value){speechRestartTimer=window.setTimeout(startBrowserSpeech,180)}}
    speechRecognition=recognition; recognition.start()
  }catch{speechRecognition=null}
}
function stopBrowserSpeech(abort=false){speechShouldRun=false;clearSpeechRestart();const recognition=speechRecognition;speechRecognition=null;if(!recognition)return;try{if(abort)recognition.abort();else recognition.stop()}catch{/* 浏览器转写失败不得阻断录音 */}}
async function startRecording(){errorMessage.value='';assessmentError.value='';submitStage.value='idle';if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){errorMessage.value='当前浏览器不支持录音，请使用最新版 Safari、Chrome 或 Edge';return}try{clearAudioState();stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});chunks=[];accumulatedMs=0;elapsedMs.value=0;const preferred=mimeType();mediaRecorder=new MediaRecorder(stream,preferred?{mimeType:preferred}:undefined);mediaRecorder.ondataavailable=(event)=>{if(event.data.size)chunks.push(event.data);if(paused.value)refreshAudioBlob(mediaRecorder?.mimeType)};mediaRecorder.onstop=finishRecording;mediaRecorder.start(250);activeStartedAt=Date.now();recording.value=true;paused.value=false;startTicker();startBrowserSpeech()}catch{errorMessage.value='无法使用麦克风，请在浏览器地址栏允许麦克风权限'}}
function toggleRecording(){if(submitting.value)return;if(recording.value)void finishRecordingNow();else void startRecording()}
function finalizeRecording(){if(!mediaRecorder||mediaRecorder.state==='inactive')return Promise.resolve();if(recording.value){accumulatedMs+=Math.max(Date.now()-activeStartedAt,0);elapsedMs.value=accumulatedMs}recording.value=false;paused.value=false;stopTicker();stopBrowserSpeech();return new Promise<void>((resolve)=>{stopResolver=resolve;try{mediaRecorder?.stop()}catch{stopResolver=null;resolve()}})}
function finishRecording(){recording.value=false;paused.value=false;stopTicker();stopBrowserSpeech();durationMs.value=elapsedMs.value;if(!discardRecording){refreshAudioBlob(mediaRecorder?.mimeType);if(audioBlob.value)submitStage.value='recorded'}stream?.getTracks().forEach(track=>track.stop());stream=null;mediaRecorder=null;const resolve=stopResolver;stopResolver=null;resolve?.()}
async function finishRecordingNow(){if(submitting.value)return;await finalizeRecording()}
function resetEvidenceProgress(){evidencePlaying.value=false;evidenceCurrentSeconds.value=0;evidenceDurationSeconds.value=0}
function clearEvidenceAudio(){evidenceAudioRequest+=1;evidenceAudioPlayer.value?.pause();if(evidenceAudioUrl.value)URL.revokeObjectURL(evidenceAudioUrl.value);evidenceAudioUrl.value='';resetEvidenceProgress()}
async function loadAttemptAudio(attempt:LearnerAttempt){const request=++evidenceAudioRequest;evidenceAudioPlayer.value?.pause();if(evidenceAudioUrl.value)URL.revokeObjectURL(evidenceAudioUrl.value);evidenceAudioUrl.value='';resetEvidenceProgress();if(!attempt.recording_url)return;try{const blob=await cabinlingoApi.protectedAudio(attempt.recording_url);if(request!==evidenceAudioRequest)return; evidenceAudioUrl.value=URL.createObjectURL(blob)}catch{if(request===evidenceAudioRequest)errorMessage.value='该次训练录音暂时无法读取，评分内容仍可查看。'}}
function selectAttempt(attempt:LearnerAttempt){result.value=attempt;selectedEvidence.value=null;issueFilter.value='all';correctionOf.value=attempt.attempt_id;void loadAttemptAudio(attempt)}
async function loadAttemptHistory(contentId:string,preferredAttemptId?:string){const request=++historyRequest;const requestedAssignment=assignmentId.value;historyLoading.value=true;try{const all=await cabinlingoApi.learnerAttempts();if(request!==historyRequest||requestedAssignment!==assignmentId.value)return;attemptHistory.value=all.filter(item=>item.assignment_id===requestedAssignment&&item.content_item_id===contentId).sort((a,b)=>a.attempt_no-b.attempt_no);const preferred=attemptHistory.value.find(item=>item.attempt_id===preferredAttemptId);const latest=attemptHistory.value[attemptHistory.value.length-1];if(preferred||latest)selectAttempt(preferred||latest!);else{result.value=null;selectedEvidence.value=null;clearEvidenceAudio()}}catch{if(request===historyRequest)errorMessage.value='历史训练结果读取失败，请稍后刷新。'}finally{if(request===historyRequest)historyLoading.value=false}}
async function loadWorkspace(preferred?:string,requestedAssignment=assignmentId.value){const data=await cabinlingoApi.practiceWorkspace(requestedAssignment);if(requestedAssignment!==assignmentId.value)return false;workspace.value=data;const target=preferred||String(route.query.content||'')||data.contents.find(item=>!item.completed)?.id||data.contents[0]?.id;selected.value=data.contents.find(item=>item.id===target)||data.contents[0]||null;return true}
function selectContent(item:LearnerContent){if(submitting.value||recording.value||paused.value)return;historyRequest+=1;assessmentRequest+=1;selected.value=item;result.value=null;attemptHistory.value=[];selectedEvidence.value=null;issueFilter.value='all';correctionOf.value=item.latest_attempt_id;pendingSubmission.value=readPending(item.id);submitStage.value=pendingSubmission.value?'failed':'idle';assessmentError.value=pendingSubmission.value?'发现一笔未确认的提交，点击重新查询可继续恢复。':'';clearAudio();clearEvidenceAudio();void loadAttemptHistory(item.id,item.latest_attempt_id||undefined)}
function contentLabel(item:LearnerContent){const title=item.title.trim();return /^第\s*\d+\s*段$/.test(title)?item.chapter_title||'广播词内容':title||item.chapter_title||'广播词内容'}
async function submitInteraction(interaction:LearnerInteraction,answer:string){if(!selected.value||!answer.trim()){errorMessage.value='请先选择或填写答案';return} interactionPending.value=interaction.id; errorMessage.value=''; try{const feedback=await cabinlingoApi.submitInteractionAnswer(interaction.id,{assignment_id:assignmentId.value,content_item_id:selected.value.id,answer}); interactionFeedback[interaction.id]=feedback; if(feedback.completed&&!interaction.completed){interaction.completed=true; selected.value.completed_interactions+=interaction.required?1:0; selected.value.completed=selected.value.attempt_count>=((workspace.value?.minimum_attempts)||1)&&selected.value.completed_interactions>=selected.value.required_interactions; if(workspace.value)workspace.value.progress_percent=Math.round(workspace.value.contents.filter(item=>item.completed).length/Math.max(workspace.value.contents.length,1)*100)}}catch{errorMessage.value='互动提交失败，请稍后再试'}finally{interactionPending.value=''}}
function pendingKey(contentId:string){return`cabinlingo:practice-pending:${assignmentId.value}:${contentId}`}
function savePending(value:PendingPracticeSubmission){pendingSubmission.value=value;try{window.localStorage.setItem(pendingKey(value.contentId),JSON.stringify(value))}catch{/* 本地状态不可用时仍以当前内存状态防重 */}}
function clearPending(contentId:string){pendingSubmission.value=null;try{window.localStorage.removeItem(pendingKey(contentId))}catch{/* ignore */}}
function readPending(contentId:string){try{const raw=window.localStorage.getItem(pendingKey(contentId));if(!raw)return null;const value=JSON.parse(raw) as PendingPracticeSubmission;if(value.assignmentId!==assignmentId.value||value.contentId!==contentId||!value.recordingId)return null;return value}catch{return null}}
function normalizedAiStatus(attempt:LearnerAttempt){return String(attempt.ai_status||'').trim().toLowerCase()}
function assessmentHasResult(attempt:LearnerAttempt){const scores=Object.values(attempt.score_summary||{}).some(value=>typeof value==='number');return normalizedAiStatus(attempt)==='completed'&&(typeof attempt.overall_score==='number'||scores||(attempt.word_details||[]).length>0)}
function assessmentIsPending(attempt:LearnerAttempt){return['','pending','queued','processing','in_progress','running','assessing'].includes(normalizedAiStatus(attempt))}
function assessmentIsFailed(attempt:LearnerAttempt){return['failed','error','cancelled','canceled','timeout'].includes(normalizedAiStatus(attempt))}
function waitForPoll(milliseconds:number){return new Promise<void>(resolve=>window.setTimeout(resolve,milliseconds))}
async function completeAssessment(attempt:LearnerAttempt,contentId:string){result.value=attempt;correctionOf.value=attempt.attempt_id;submitStage.value='success';assessmentError.value='';clearPending(contentId);await Promise.allSettled([loadWorkspace(contentId),loadAttemptHistory(contentId,attempt.attempt_id)])}
async function resolveAssessmentAttempt(attempt:LearnerAttempt,contentId:string){
  const request=++assessmentRequest
  let current=attempt
  const deadline=Date.now()+180000
  while(request===assessmentRequest){
    if(assessmentHasResult(current)){await completeAssessment(current,contentId);return}
    if(assessmentIsFailed(current)||(!assessmentIsPending(current)&&normalizedAiStatus(current)!=='completed'))throw new Error(`AI 测评返回状态：${current.ai_status||'unknown'}`)
    if(normalizedAiStatus(current)==='completed')throw new Error('AI 测评已结束，但本次结果尚不可用')
    if(Date.now()>=deadline)throw new Error('AI 测评仍在处理中，请稍后重新查询')
    await waitForPoll(1600)
    try{current=await cabinlingoApi.learnerAttempt(current.attempt_id)}catch(error){if(Date.now()>=deadline)throw error}
  }
}
async function findPendingAttempt(value:PendingPracticeSubmission,timeoutMs=0){
  const deadline=Date.now()+timeoutMs
  do{
    const rows=await cabinlingoApi.learnerAttempts()
    const match=rows.find(item=>item.assignment_id===value.assignmentId&&item.content_item_id===value.contentId&&Boolean(item.recording_url?.endsWith(`/${value.recordingId}`)))
    if(match)return match
    if(Date.now()>=deadline)return null
    await waitForPoll(1600)
  }while(true)
}
async function resumePendingAssessment(value:PendingPracticeSubmission,queryWindowMs=0){
  submitStage.value='analyzing';assessmentError.value='';savePending(value)
  const attempt=value.attemptId?await cabinlingoApi.learnerAttempt(value.attemptId):await findPendingAttempt(value,queryWindowMs)
  if(!attempt)throw new Error('提交状态尚未确认；系统已阻止重复创建，请稍后重新查询')
  if(!value.attemptId){value={...value,attemptId:attempt.attempt_id};savePending(value)}
  await resolveAssessmentAttempt(attempt,value.contentId)
}
async function retryAssessment(){
  if(submitting.value)return
  if(!pendingSubmission.value){await submitPractice();return}
  submitting.value=true
  try{await resumePendingAssessment(pendingSubmission.value,30000)}catch(error){submitStage.value='failed';assessmentError.value=learnerError(error)}finally{submitting.value=false}
}
function openCurrentResult(){if(result.value)void router.push(`/student/results/${result.value.attempt_id}`)}
async function submitPractice(){
  if(submitting.value||recording.value||!selected.value||!audioBlob.value)return
  if(pendingSubmission.value){await retryAssessment();return}
  submitting.value=true
  if(paused.value)await finalizeRecording()
  if(!audioBlob.value){submitting.value=false;return}
  const contentId=selected.value.id
  let requestPending:PendingPracticeSubmission|null=null
  errorMessage.value='';assessmentError.value='';selectedEvidence.value=null;submitStage.value='uploading'
  try{
    const currentAssignment=assignmentId.value
    const uploaded=await cabinlingoApi.uploadAudio({assignment_id:currentAssignment,purpose:'practice',content_item_id:contentId,blob:audioBlob.value,duration_ms:durationMs.value})
    let pending:PendingPracticeSubmission={assignmentId:currentAssignment,contentId,recordingId:uploaded.recording_id,requestedAt:Date.now()}
    requestPending=pending;savePending(pending);submitStage.value='analyzing'
    const submitted=await cabinlingoApi.submitCoursePractice({assignment_id:currentAssignment,content_item_id:contentId,recording_id:uploaded.recording_id,correction_of_attempt_id:correctionOf.value,recognized_text:browserTranscript.value||null})
    pending={...pending,attemptId:submitted.attempt_id};requestPending=pending;savePending(pending)
    await resolveAssessmentAttempt(submitted,contentId)
  }catch(error){
    if(requestPending){
      const pending=requestPending
      try{const found=await findPendingAttempt(pending);if(found){const recovered:PendingPracticeSubmission={assignmentId:pending.assignmentId,contentId:pending.contentId,recordingId:pending.recordingId,requestedAt:pending.requestedAt,attemptId:found.attempt_id};savePending(recovered);await resolveAssessmentAttempt(found,contentId);return}}catch{/* 统一进入可重试错误态 */}
    }
    submitStage.value='failed';assessmentError.value=`${learnerError(error)} 本地录音与提交标识均已保留。`
  }finally{submitting.value=false}
}
async function reanalyzeCurrentAttempt(){if(!result.value||reanalyzing.value)return;const attemptId=result.value.attempt_id;reanalyzing.value=true;errorMessage.value='';selectedEvidence.value=null;try{const updated=await cabinlingoApi.reanalyzeLearnerAttempt(attemptId);result.value=updated;const index=attemptHistory.value.findIndex(item=>item.attempt_id===attemptId);if(index>=0)attemptHistory.value.splice(index,1,updated);await loadAttemptAudio(updated)}catch{errorMessage.value='现有录音重新分析失败，原测评结果已保留，请稍后重试。'}finally{reanalyzing.value=false}}
function retry(){if(!canRetrain.value)return;if(result.value)correctionOf.value=result.value.attempt_id;selectedEvidence.value=null;clearAudio();document.querySelector('.record-card-live')?.scrollIntoView({behavior:'smooth',block:'center'})}
function clearAudioState(){audioPlayer.value?.pause();previewing.value=false;if(audioPreview.value)URL.revokeObjectURL(audioPreview.value);audioPreview.value='';audioBlob.value=null;browserTranscript.value='';durationMs.value=0;elapsedMs.value=0;accumulatedMs=0}
function clearAudio(){stopBrowserSpeech(true);if(mediaRecorder&&mediaRecorder.state!=='inactive'){discardRecording=true;void finalizeRecording().finally(()=>{discardRecording=false})}else{stream?.getTracks().forEach(track=>track.stop());stream=null}recording.value=false;paused.value=false;stopTicker();clearAudioState()} function formatDuration(ms:number){const seconds=Math.round(ms/1000);return `${Math.floor(seconds/60).toString().padStart(2,'0')}:${(seconds%60).toString().padStart(2,'0')}`} function formatAssessmentDuration(seconds:number){const value=Number.isInteger(seconds)?seconds.toFixed(0):seconds.toFixed(3).replace(/0+$/,'').replace(/\.$/,'');return `${value}s`}
function normalizeWord(value:string){return value.toLowerCase().replace(/’/g,"'").replace(/[^a-z0-9'\u3400-\u9fff]/g,'')}
function isGranularDetail(detail:WordDetail){if(detail.detail_level)return detail.detail_level==='word';const value=detail.word.trim();if(!value)return false;const chinese=[...value].filter(char=>/[\u3400-\u9fff]/.test(char));return chinese.length?chinese.length===1:!/[\s.!?,;:]/.test(value)}
function buildScriptSegments(referenceText:string,attempt:LearnerAttempt|null):ScriptSegment[]{
  if(!referenceText)return []
  const details=(attempt?.word_details||[]).filter(item=>item.word&&item.char_type!==1&&isGranularDetail(item))
  const issues=confirmedIssues(attempt?.issues); const segments:ScriptSegment[]=[]; const tokenPattern=/[A-Za-z]+(?:['’][A-Za-z]+)?|\d+(?:[.:]\d+)?|[\u3400-\u9fff]/g
  let cursor=0; let tokenIndex=0; let detailCursor=0; let match:RegExpExecArray|null
  while((match=tokenPattern.exec(referenceText))!==null){
    if(match.index>cursor)segments.push({key:`text-${cursor}`,text:referenceText.slice(cursor,match.index),isWord:false,issues:[]})
    const token=match[0]; const normalized=normalizeWord(token); let detail=details.find(item=>item.reference_index===tokenIndex)
    const found=detail?-1:details.findIndex((item,index)=>index>=detailCursor&&normalizeWord(item.word)===normalized)
    if(found>=0){detail=details[found];detailCursor=found+1}
    const related=issues.filter(issue=>issue.reference_index===tokenIndex||(Boolean(issue.word)&&normalizeWord(String(issue.word))===normalized)||(detail&&typeof issue.start_ms==='number'&&issue.start_ms===detail.start_ms))
    segments.push({key:`word-${tokenIndex}-${match.index}`,text:token,isWord:true,index:tokenIndex,detail,issues:related})
    cursor=match.index+token.length; tokenIndex+=1
  }
  if(cursor<referenceText.length)segments.push({key:`text-${cursor}`,text:referenceText.slice(cursor),isWord:false,issues:[]})
  return segments
}
function detailText(detail:WordDetail,key:'expected_pinyin'|'expected_tone'|'detected_tone'){const value=(detail as unknown as Record<string,unknown>)[key];return typeof value==='string'?value:''}
function wordScore(detail:WordDetail){const scores=[detail.pronunciation,detail.overall,detailText(detail,'expected_tone')?detail.tone:undefined].filter((value):value is number=>typeof value==='number');return scores.length?Math.min(...scores):null}
function wordClass(segment:ScriptSegment){const score=segment.detail?wordScore(segment.detail):null;return {problem:segment.issues.length>0,low:score!==null&&score<70,medium:score!==null&&score>=70&&score<85,good:score!==null&&score>=85,selected:selectedEvidence.value?.key===segment.key}}
function wordTitle(segment:ScriptSegment){const parts=segment.issues.map(issue=>issueLabel(issue.type));const score=segment.detail?wordScore(segment.detail):null;if(score!==null)parts.unshift(`单词得分 ${score}`);if(segment.detail)parts.push(`点击试听 ${formatEvidenceTime(segment.detail.start_ms)}`);return parts.join(' · ')||'点击查看该词反馈'}
function issueLabel(type?:string){return ({word_omitted:'漏读',omission:'漏读',word_inserted:'增读',insertion:'增读',word_repeated:'回读',repetition:'回读',word_replaced:'错读',substitution:'错读',chinese_tone_error:'声调错误',long_pause:'长时间停顿',leading_silence:'开头等待过长',trailing_silence:'结尾空白过长',provider_unconfigured:'AI 能力待接入',provider_failed:'AI 服务暂不可用'} as Record<string,string>)[type||'']||type||'需要改进'}
function shortIssueLabel(type?:string){return issueLabel(type).replace('疑似','')}
function issueCategory(type?:string):IssueCategory{const value=(type||'').toLowerCase();if(['word_omitted','omission'].includes(value))return 'omission';if(['word_inserted','insertion'].includes(value))return 'insertion';if(['word_repeated','repetition'].includes(value))return 'repetition';if(['word_replaced','substitution'].includes(value))return 'substitution';if(['long_pause','leading_silence','trailing_silence'].includes(value))return 'pause';if(value.includes('pronunciation')||value.includes('phoneme')||value.includes('tone'))return 'pronunciation';return 'other'}
function categoryLabel(category:IssueCategory){return ({omission:'漏读',insertion:'增读',repetition:'回读',substitution:'错读',pronunciation:'发音',pause:'停顿',other:'提示'} as Record<IssueCategory,string>)[category]}
function buildFeedbackItems(attempt:LearnerAttempt|null):FeedbackItem[]{
  if(!attempt)return[]
  const confirmed=confirmedIssues(attempt.issues)
  const items:FeedbackItem[]=confirmed.map((issue,index)=>{
    const category=issueCategory(issue.type);const word=issue.word||issue.expected||''
    return{key:`issue-${index}-${issue.type||'other'}`,category,label:word?`${word} · ${issueLabel(issue.type)}`:issueLabel(issue.type),message:issue.message||'请根据提示再次练习。',startMs:typeof issue.start_ms==='number'?issue.start_ms:undefined,issue}
  })
  const pronunciationIssueKeys=new Set(confirmed.filter(issue=>issueCategory(issue.type)==='pronunciation').flatMap(issue=>[
    typeof issue.reference_index==='number'?`index:${issue.reference_index}`:'',
    typeof issue.start_ms==='number'?`start:${issue.start_ms}`:'',
    normalizeWord(String(issue.word||issue.expected||''))?`word:${normalizeWord(String(issue.word||issue.expected||''))}`:'',
  ]).filter(Boolean))
  attempt.word_details.forEach((detail,index)=>{
    const score=wordScore(detail);const normalized=normalizeWord(detail.word||'')
    if(score===null||score>=70||!normalized)return
    const keys=[typeof detail.reference_index==='number'?`index:${detail.reference_index}`:'',typeof detail.start_ms==='number'?`start:${detail.start_ms}`:'',`word:${normalized}`].filter(Boolean)
    if(keys.some(key=>pronunciationIssueKeys.has(key)))return
    const scoreName=typeof detail.pronunciation==='number'?'发音得分':'字词得分'
    items.push({key:`word-score-${detail.reference_index??index}-${detail.start_ms}`,category:'pronunciation',label:`${detail.word} · 发音待改进`,message:`${scoreName} ${Math.round(score)}，低于 70 分；点击可回听对应录音并针对发音再练。`,startMs:typeof detail.start_ms==='number'?detail.start_ms:undefined,detail})
  })
  return items
}
function attemptOrdinal(attempt:LearnerAttempt){const index=attemptHistory.value.findIndex(item=>item.attempt_id===attempt.attempt_id);return index>=0?index+1:attempt.attempt_no}
function attemptScore(attempt:LearnerAttempt){if(attempt.overall_score!==null)return attempt.overall_score;const values=Object.values(attempt.score_summary||{}).filter((value):value is number=>typeof value==='number');return values.length?Math.round(values.reduce((sum,value)=>sum+value,0)/values.length):null}
function formatAttemptDate(value:string){return new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}
function formatEvidenceTime(milliseconds:number){const seconds=Math.max(milliseconds,0)/1000;return `${Math.floor(seconds/60).toString().padStart(2,'0')}:${(seconds%60).toFixed(1).padStart(4,'0')}`}
async function seekEvidenceAudio(milliseconds:number){const player=evidenceAudioPlayer.value;if(!player||!evidenceAudioUrl.value)return;try{if(player.readyState===0){player.load();await new Promise<void>((resolve)=>{const done=()=>{player.removeEventListener('loadedmetadata',done);player.removeEventListener('error',done);resolve()};player.addEventListener('loadedmetadata',done,{once:true});player.addEventListener('error',done,{once:true});window.setTimeout(done,2000)})}player.currentTime=Math.max(milliseconds,0)/1000;await player.play()}catch{errorMessage.value='录音定位暂不可用，请稍后重试。'}}
function syncEvidenceProgress(){const player=evidenceAudioPlayer.value;if(!player)return;evidenceCurrentSeconds.value=Number.isFinite(player.currentTime)?player.currentTime:0;evidenceDurationSeconds.value=Number.isFinite(player.duration)?player.duration:0}
function formatAudioClock(seconds:number){const safe=Math.max(0,Math.floor(seconds||0));return `${Math.floor(safe/60).toString().padStart(2,'0')}:${(safe%60).toString().padStart(2,'0')}`}
function changeEvidencePosition(event:Event){const player=evidenceAudioPlayer.value;const value=Number((event.target as HTMLInputElement).value);if(!player||!Number.isFinite(value))return;player.currentTime=value;evidenceCurrentSeconds.value=value}
async function toggleEvidencePlayback(){const player=evidenceAudioPlayer.value;if(!player||!evidenceAudioUrl.value)return;if(!player.paused){player.pause();return}try{if(player.ended)player.currentTime=0;await player.play()}catch{errorMessage.value='录音暂时无法播放，请稍后重试。'}}
function selectedEvidenceStart(){return selectedEvidence.value?.detail?.start_ms??selectedEvidence.value?.issues.find(issue=>typeof issue.start_ms==='number')?.start_ms}
function playSelectedEvidence(){const start=selectedEvidenceStart();if(typeof start==='number')void seekEvidenceAudio(start)}
function updateWordDetailMode(){wordDetailIsSheet.value=window.innerWidth<=640}
function anchorWordDetail(event?:Event){const element=event?.currentTarget as HTMLElement|undefined;if(!element)return;const rect=element.getBoundingClientRect();wordDetailAnchor.value={left:rect.left,top:rect.top,bottom:rect.bottom,width:rect.width}}
function selectEvidence(segment:ScriptSegment,event?:Event){selectedEvidence.value=segment;updateWordDetailMode();anchorWordDetail(event)}
function openIssue(issue:LearnerIssue,event?:Event){const segment=scriptSegments.value.find(item=>item.issues.includes(issue));if(segment){selectEvidence(segment,event);return}const detail=result.value?.word_details.find(item=>typeof issue.start_ms==='number'&&item.start_ms===issue.start_ms);selectEvidence({key:`issue-evidence-${issue.type||'other'}-${issue.reference_index??issue.start_ms??0}`,text:String(issue.word||issue.expected||issue.actual||issueLabel(issue.type)),isWord:true,detail,issues:[issue]},event)}
function feedbackIsSelected(item:FeedbackItem){return !!selectedEvidence.value && (!!item.detail && selectedEvidence.value.detail===item.detail || !!item.issue && selectedEvidence.value.issues.includes(item.issue))}
function openFeedback(item:FeedbackItem,event?:Event){if(item.issue){openIssue(item.issue,event);return}if(item.detail){const segment=scriptSegments.value.find(part=>part.detail?.start_ms===item.detail?.start_ms&&normalizeWord(part.text)===normalizeWord(item.detail?.word||''));selectEvidence(segment||{key:`detail-evidence-${item.detail.start_ms}`,text:item.detail.word||'该字词',isWord:true,detail:item.detail,issues:[]},event);return}if(typeof item.startMs==='number')void seekEvidenceAudio(item.startMs)}
function compactFeedbackMessage(item:FeedbackItem){if(item.detail){const score=wordScore(item.detail);return score===null?'查看该词评分与录音位置':`得分 ${Math.round(score)} · 点击查看发音详情`}return item.issue?.training_advice||item.message}
function closeEvidence(){selectedEvidence.value=null;window.speechSynthesis?.cancel()}
function speakStandardPronunciation(){if(!selectedEvidence.value||!('speechSynthesis'in window)){errorMessage.value='当前浏览器不支持标准发音播放';return}window.speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(selectedEvidence.value.text);utterance.lang=/[\u3400-\u9fff]/.test(selectedEvidence.value.text)?'zh-CN':'en-US';utterance.rate=.82;window.speechSynthesis.speak(utterance)}
function toggleDetailedAnalysis(){detailedAnalysisOpen.value=!detailedAnalysisOpen.value;if(!detailedAnalysisOpen.value)closeEvidence()}
function handleEvidenceKey(event:KeyboardEvent){if(event.key==='Escape'&&selectedEvidence.value)closeEvidence()}
function leavePractice(){const assignment=assignmentId.value;void router.replace(assignment?`/student/tasks/${assignment}`:'/student/tasks')}
async function initializeWorkspace(){
  const request=++workspaceRequest;const requestedAssignment=assignmentId.value
  loading.value=true;errorMessage.value='';workspace.value=null;selected.value=null
  if(!requestedAssignment){errorMessage.value='缺少练习任务参数';loading.value=false;return}
  try{
    const loaded=await loadWorkspace(undefined,requestedAssignment)
    if(!loaded||request!==workspaceRequest)return
    const activeContent=selected.value as LearnerContent|null
    if(activeContent&&!activeContent.learning_card_id){await loadAttemptHistory(activeContent.id,activeContent.latest_attempt_id||undefined);if(request!==workspaceRequest)return;const pending=readPending(activeContent.id);if(pending){pendingSubmission.value=pending;try{await resumePendingAssessment(pending,5000)}catch(error){submitStage.value='failed';assessmentError.value=learnerError(error)}}}
  }catch(error){
    if(request!==workspaceRequest)return
    try{
      const rows=await cabinlingoApi.learnerTasks();const matched=rows.find(item=>item.assignment_id===requestedAssignment)
      if(request!==workspaceRequest)return
      if(matched?.task_type==='exam'){await router.replace({path:'/student/exam',query:{assignment:matched.assignment_id,task:matched.task_id}});return}
    }catch{/* 保留原始课程读取错误 */}
    if(request===workspaceRequest)errorMessage.value=learnerError(error)
  }finally{if(request===workspaceRequest)loading.value=false}
}
watch(assignmentId,(next,previous)=>{if(next===previous)return;historyRequest+=1;assessmentRequest+=1;correctionOf.value=String(route.query.correction||'')||null;pendingSubmission.value=null;result.value=null;attemptHistory.value=[];clearEvidenceAudio();clearAudio();void initializeWorkspace()})
onMounted(()=>{updateWordDetailMode();window.addEventListener('resize',updateWordDetailMode);window.addEventListener('keydown',handleEvidenceKey);void initializeWorkspace()})
onBeforeUnmount(()=>{assessmentRequest+=1;window.removeEventListener('resize',updateWordDetailMode);window.removeEventListener('keydown',handleEvidenceKey);window.speechSynthesis?.cancel();clearAudio()})
onBeforeUnmount(clearContentResources)
onBeforeUnmount(clearEvidenceAudio)
</script>

<style scoped>
.learning-card-waiting{display:grid;place-items:center;min-height:480px;margin:16px 0;border:1px dashed #b8cff0;border-radius:16px;color:#71819d;background:#f5f9ff}
.course-media{margin:16px 0;padding:14px;border:1px solid #dfe7f3;border-radius:14px;background:#f8fbff}.course-media__heading{display:flex;justify-content:space-between;gap:10px;color:#31517f;font-size:12px}.course-media__heading small{color:#71819d}.course-media__item{margin-top:10px;padding:10px;border-radius:10px;background:#fff}.course-media__item>div{display:flex;gap:8px;align-items:center;color:#405474;font-size:12px}.course-media__item>div span{padding:3px 6px;border-radius:5px;color:#2d76e8;background:#edf4ff;font-size:10px}.course-media__item audio,.course-media__item video{display:block;width:100%;max-height:320px;margin-top:9px}.course-media__item>small{display:block;margin-top:8px;color:#8998b2}.practice-page:has(.pdf-viewer) .lesson-preview{display:none}
 .practice-page{max-width:1120px}.workspace-summary,.lesson-card,.record-card-live,.result-card{padding:20px;border-radius:20px;background:#fff;box-shadow:0 8px 24px #2447810c}.workspace-summary>div:first-child{display:flex;justify-content:space-between;color:#6f809e}.workspace-summary strong{color:var(--ink)}.workspace-progress{height:7px;margin:12px 0 7px;overflow:hidden;border-radius:9px;background:#e7edf7}.workspace-progress i{display:block;height:100%;background:linear-gradient(90deg,#1768f3,#58a9ff)}.workspace-summary small{color:#8b9ab4}.content-switcher{display:flex;gap:8px;margin:16px 0;overflow:auto}.content-switcher button{min-width:145px;display:flex;flex-direction:column;gap:4px;padding:11px 13px;border:1px solid #dce5f2;border-radius:12px;background:#fff;text-align:left}.content-switcher button.active{border-color:#4b91ff;background:#f3f7ff}.content-switcher button.done{border-color:#9bdcc5}.content-switcher b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.content-switcher small{color:#8998b2}.lesson-heading,.result-title{display:flex;justify-content:space-between;align-items:start}.lesson-heading>span:first-child,.result-title span{color:#8998b2;font-size:11px}.lesson-heading h2,.result-title h2{margin:5px 0 0;color:var(--ink)}.status-dot{padding:6px 9px;border-radius:8px;color:#a36b24!important;background:#fff3e2}.status-dot.done{color:#218d67!important;background:#e9faf3}.lesson-preview{width:100%;height:280px;margin:16px 0 0;border:1px solid #dfe7f3;border-radius:14px}.annotated-script{margin-top:16px;padding:16px;border:1px solid #dfe7f3;border-radius:14px;color:#162847;background:#fff;font-size:16px;line-height:2.15;white-space:pre-wrap}.script-word{display:inline;padding:2px 1px;border:0;border-radius:4px;color:inherit;background:transparent;font:inherit;line-height:inherit;cursor:pointer}.script-word:hover,.script-word:focus-visible,.script-word.selected{outline:2px solid #5b92ee;outline-offset:1px;background:#edf5ff}.script-word.good{border-bottom:2px solid #78c9a7}.script-word.medium{border-bottom:2px solid #f1b24d;background:#fffaf0}.script-word.low,.script-word.problem{border-bottom:2px solid #ee6677;background:#fff0f2}.record-card-live{margin-top:16px}.record-state{display:flex;align-items:center;gap:13px}.record-orb{position:relative;display:grid;place-items:center;width:54px;height:54px;border-radius:50%;color:#fff;background:#337ef2;box-shadow:0 0 0 8px #337ef21a}.record-orb:before{content:"";width:18px;height:18px;border-radius:50%;background:#fff}.record-orb.recording{background:#e65468;animation:pulse 1.2s infinite}.record-orb.recording:before{border-radius:3px}.record-orb.paused{background:#f2a23a}.record-orb.paused:before{width:15px;border-radius:3px}.record-state strong,.record-state small{display:block}.record-state small{margin-top:5px;color:#8b9ab2}.record-preview{display:none}.record-actions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:18px}.record-actions button{min-height:44px}.record-toggle{padding:12px 18px;border-radius:10px;color:#fff;background:#347cef}.record-toggle.active{background:#e65468}.record-submit{width:100%;min-height:48px;margin-top:12px}.privacy-note{margin:12px 0 0;color:#9aa7bb;font-size:10px}.result-card{margin-top:16px}.result-title small{color:#8998b2}.score-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:18px 0}.score-grid article{padding:12px;border-radius:12px;background:#f4f8fd;text-align:center}.score-grid span,.score-grid strong{display:block}.score-grid span{color:#7c8ba5;font-size:10px}.score-grid strong{margin-top:5px;color:#226fe8;font-size:22px}.result-meta{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.result-meta span{padding:7px 10px;border-radius:8px;color:#667894;background:#f2f6fc;font-size:11px}.result-meta strong{margin-left:4px;color:#1f6fe8}.evidence-panel{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;margin:14px 0;padding:16px;border:1px solid #cddff8;border-radius:14px;background:#f6faff}.evidence-panel>div:first-child{min-width:0}.evidence-panel span,.evidence-panel small{color:#71819d;font-size:10px}.evidence-panel h3{margin:4px 0 0;color:#142e5e;font-size:20px}.evidence-panel dl{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,minmax(100px,1fr));gap:8px;margin:0}.evidence-panel dl div{min-width:0;padding:9px 10px;border:1px solid #e8f0fa;border-radius:9px;background:#fff}.evidence-panel dt{color:#8292ad;font-size:9px}.evidence-panel dd{margin:4px 0 0;color:#1768f3;font-size:16px;font-weight:700;overflow-wrap:anywhere}.phoneme-list{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px}.phoneme-list button{display:flex;gap:6px;padding:7px 9px;border:1px solid #cfe0f8;border-radius:8px;color:#31517f;background:#fff}.phoneme-list button span{color:#1768f3;font-weight:700}.evidence-panel p,.evidence-panel>small{grid-column:1/-1;margin:0}.evidence-panel p{color:#a6525e;font-size:11px}.issue-list{display:grid;gap:8px;margin:16px 0}.issue-list button{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;width:100%;padding:12px;border:0;border-radius:12px;color:inherit;background:#fff8ed;text-align:left;cursor:pointer}.issue-list button:hover,.issue-list button:focus-visible{outline:2px solid #f1bd75;outline-offset:1px}.issue-list>button>span{height:max-content;padding:4px 7px;border-radius:6px;color:#a76b22;background:#ffeac9;font-size:10px}.issue-list strong{font-size:12px}.issue-list p{margin:5px 0 0;color:#71819d;font-size:11px}.issue-list button>small{color:#a76b22;font-size:10px}.result-empty{padding:16px;border-radius:12px;color:#66816f;background:#effaf4}.result-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:16px}@keyframes pulse{50%{box-shadow:0 0 0 14px #e6546810}}@media(max-width:900px){.practice-page{max-width:720px}.feedback-detail-grid{grid-template-columns:1fr}.evidence-panel{position:static}}@media(max-width:640px){.lesson-preview{height:220px}.record-actions{gap:7px}.record-actions button{padding-inline:8px;font-size:12px}.score-grid{grid-template-columns:repeat(2,1fr)}.evidence-panel{grid-template-columns:1fr}.evidence-panel dl{grid-template-columns:repeat(2,minmax(0,1fr))}}
.interactive-card{margin:16px 0;padding:16px;border:1px solid #e2dcff;border-radius:16px;background:linear-gradient(180deg,#fbfaff,#f8fbff)}.interactive-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.interactive-heading span,.interactive-heading strong{display:block}.interactive-heading span{color:#7959d8;font-size:11px;font-weight:700}.interactive-heading strong{margin-top:4px;color:#152f63;font-size:15px}.interactive-heading small{color:#7a6eaa;font-size:11px}.interactive-item{margin-top:12px;padding:14px;border-radius:12px;background:#fff;box-shadow:0 5px 18px #445a8a0d}.interactive-item__title{display:flex;align-items:center;gap:8px}.interactive-item__title>span{padding:4px 7px;border-radius:6px;color:#6b4ec5;background:#eeeaff;font-size:10px}.interactive-item__title strong{font-size:13px}.interactive-item__title i{margin-left:auto;color:#22956d;font-size:11px;font-style:normal}.interactive-item>p{margin:10px 0;color:#435878;line-height:1.6}.interaction-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.interaction-options button{min-height:44px;padding:10px 12px;border:1px solid #d8e2f1;border-radius:10px;color:#31517f;background:#f9fbfe;text-align:left}.interaction-options button:hover,.interaction-options button:focus-visible{border-color:#8b71e5;color:#5f45bb;background:#f4f0ff}.interaction-fill{display:flex;gap:8px}.interaction-fill input{flex:1;min-width:0;padding:10px 12px;border:1px solid #d8e2f1;border-radius:10px}.interaction-feedback{margin:10px 0 0;padding:8px 10px;border-radius:8px;color:#a05c27;background:#fff4e7;font-size:11px}.interaction-feedback.correct{color:#237e60;background:#ebfaf3}@media(max-width:640px){.interaction-options{grid-template-columns:1fr}.interaction-fill{flex-direction:column}.interaction-fill button{width:100%}}
.history-loading{margin-top:16px;padding:18px;border-radius:14px;color:#70809b;background:#f4f8fd;text-align:center}
.attempt-tabs{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0}
.attempt-tabs button{display:grid;grid-template-columns:1fr auto;gap:3px 10px;min-height:68px;padding:12px 14px;border:1px solid #dce5f2;border-radius:13px;color:#546682;background:#fff;text-align:left;cursor:pointer}
.attempt-tabs button:hover,.attempt-tabs button:focus-visible{border-color:#8bb6f8;outline:2px solid #d7e7ff;outline-offset:1px}
.attempt-tabs button.active{border-color:#2f7cf0;color:#174e9f;background:#edf5ff;box-shadow:0 6px 18px #337ef218}
.attempt-tabs button span{align-self:center;color:inherit!important;font-size:12px;font-weight:700}.attempt-tabs button strong{grid-row:1/3;grid-column:2;align-self:center;color:#1768f3;font-size:23px}.attempt-tabs button small{grid-column:1;color:#8391a9;font-size:10px}
.feedback-copy{margin-top:16px;padding:18px;border:1px solid #cfdff7;border-radius:17px;background:linear-gradient(180deg,#f7fbff 0,#fff 45%)}
.feedback-copy__head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.feedback-copy__head span{color:#2472e5;font-size:11px;font-weight:700}.feedback-copy__head h3{margin:5px 0 3px;color:#142d5c;font-size:18px}.feedback-copy__head p{margin:0;color:#7d8ca5;font-size:11px}.feedback-copy__head>b{flex:none;padding:7px 10px;border-radius:8px;color:#1768f3;background:#eaf3ff;font-size:11px}
.feedback-legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin-top:16px;color:#697b98;font-size:10px}.feedback-legend span{display:flex;align-items:center;gap:5px}.feedback-legend i{width:9px;height:9px;border-radius:50%;background:#8bb8a7}.feedback-legend i.medium{background:#eead44}.feedback-legend i.low{background:#e85d70}.feedback-legend i.problem{background:#8356d8}
.granular-score-notice{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:12px;padding:11px 13px;border:1px solid #f1d397;border-radius:11px;color:#7b5d2b;background:#fff9ed}.granular-score-notice>div{display:grid;gap:4px}.granular-score-notice strong{font-size:11px}.granular-score-notice span{font-size:10px;line-height:1.55}.granular-score-notice>button{flex:none;min-height:36px;padding:8px 11px;border:1px solid #d79b37;border-radius:8px;color:#8b5b12;background:#fff;cursor:pointer}.granular-score-notice>button:disabled{opacity:.6;cursor:wait}
.feedback-script.annotated-script{margin-top:12px;padding:20px 18px;line-height:3.4;background:#fff;overflow-wrap:anywhere}
.feedback-script .script-word{position:relative;display:inline-flex;flex-direction:column;align-items:center;justify-content:center;min-width:31px;min-height:46px;margin:6px 2px 0;padding:6px 5px 4px;border:1px solid transparent;border-radius:8px;vertical-align:middle;line-height:1.1}
.feedback-script .script-word>b{color:#192c4b;font-size:15px;font-weight:600}.feedback-script .script-word>small{margin-top:5px;color:#8190a8;font-size:9px;line-height:1}.feedback-script .script-word>i{position:absolute;top:-12px;left:50%;z-index:1;max-width:54px;padding:3px 5px;overflow:hidden;border-radius:5px;color:#fff;background:#8356d8;font-size:8px;font-style:normal;line-height:1;white-space:nowrap;text-overflow:ellipsis;transform:translateX(-50%)}
.feedback-script .script-word.good{border-color:#b8dfcf;background:#f1faf6}.feedback-script .script-word.good>small{color:#278365}.feedback-script .script-word.medium{border-color:#f1cf92;background:#fff8eb}.feedback-script .script-word.medium>small{color:#a86b19}.feedback-script .script-word.low{border-color:#f1a6b1;background:#fff1f3}.feedback-script .script-word.low>small{color:#bd3f55}.feedback-script .script-word.problem{box-shadow:inset 0 -3px #8356d8}.feedback-script .script-word.selected{outline:3px solid #82b2f8;outline-offset:2px}
.feedback-filters{display:flex;gap:8px;margin-top:16px;padding-bottom:2px;overflow-x:auto}.feedback-filters button{flex:none;min-height:38px;padding:8px 11px;border:1px solid #d6e2f3;border-radius:999px;color:#5e708c;background:#fff;font-size:11px;cursor:pointer}.feedback-filters button strong{margin-left:4px;color:#2472e5}.feedback-filters button.active{border-color:#2f7cf0;color:#fff;background:#2f7cf0}.feedback-filters button.active strong{color:#fff}
.feedback-detail-grid{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr);gap:12px;margin-top:14px}
.feedback-list,.evidence-placeholder{padding:14px;border:1px solid #e0e8f3;border-radius:14px;background:#fff}.feedback-list>h3{margin:0 0 9px;color:#21395f;font-size:13px}.feedback-list>button{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:start;gap:10px;width:100%;min-height:54px;margin-top:7px;padding:10px;border:0;border-radius:10px;color:inherit;background:#f7f9fc;text-align:left;cursor:pointer}.feedback-list>button:hover,.feedback-list>button:focus-visible{outline:2px solid #9fc4fa;outline-offset:1px;background:#f0f6ff}.feedback-list>button>span{padding:4px 6px;border-radius:5px;color:#5d3fa6;background:#eee8ff;font-size:9px}.feedback-list>button>span.pronunciation{color:#a15b1c;background:#fff0d7}.feedback-list>button>span.pause{color:#b75527;background:#fff0e8}.feedback-list>button>span.omission,.feedback-list>button>span.substitution{color:#b43e50;background:#ffe8ec}.feedback-list>button>span.insertion,.feedback-list>button>span.repetition{color:#7851bf;background:#eee8ff}.feedback-list>button strong{color:#253b5e;font-size:11px}.feedback-list>button p{margin:4px 0 0;color:#7787a0;font-size:10px;line-height:1.45}.feedback-list>button>small{color:#2472e5;font-size:9px;white-space:nowrap}
.feedback-detail-grid .evidence-panel{position:relative;grid-template-columns:minmax(90px,.45fr) 1fr;align-content:start;margin:0}.evidence-play{position:absolute;top:12px;right:12px;min-height:36px;padding:7px 10px;border:1px solid #a9c9f6;border-radius:9px;color:#1768f3;background:#fff;cursor:pointer}.evidence-play:hover,.evidence-play:focus-visible{outline:2px solid #cfe2ff}.evidence-placeholder{display:grid;place-content:center;min-height:170px;color:#7c8da7;text-align:center}.evidence-placeholder strong{color:#365271;font-size:13px}.evidence-placeholder p{margin:6px 0 0;font-size:11px}
.confirmed-issue{grid-column:1/-1;padding:10px;border-radius:10px;background:#fff4f5}.confirmed-issue>b{color:#aa3d4f;font-size:11px}.confirmed-issue>p{margin:6px 0;color:#5f708a}.confirmed-issue>dl{display:grid;grid-template-columns:1fr 1fr!important}.confirmed-issue ul{margin:7px 0;padding-left:18px;color:#667894;font-size:10px}.confirmed-issue>small{display:block;color:#526d91!important;line-height:1.5}
.feedback-audio{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:13px;margin-top:14px;padding:13px 15px;border:1px solid #cfe0f7;border-radius:13px;background:#f5f9ff}.feedback-audio>button{display:flex;align-items:center;gap:8px;min-width:120px;min-height:42px;padding:9px 13px;border:0;border-radius:10px;color:#fff;background:#2f7cf0;cursor:pointer}.feedback-audio>button.playing{background:#e85c70}.feedback-audio>button span{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;color:#2f7cf0;background:#fff;font-size:11px}.feedback-audio>button b{font-size:12px}.feedback-audio>div{display:grid;grid-template-columns:1fr auto;gap:5px 12px;min-width:0}.feedback-audio>div strong{color:#263f65;font-size:12px}.feedback-audio>div small{color:#6f819e;font-size:10px}.feedback-audio input{grid-column:1/-1;width:100%;height:5px;accent-color:#2f7cf0;cursor:pointer}
.feedback-note{margin:12px 0 0;color:#8694aa;font-size:10px}.result-actions button{min-height:44px}
@media(max-width:720px){.feedback-copy{padding:14px}.feedback-copy__head{gap:8px}.feedback-copy__head p{line-height:1.5}.granular-score-notice{align-items:stretch;flex-direction:column}.feedback-script.annotated-script{padding:16px 10px;font-size:14px}.feedback-detail-grid{grid-template-columns:1fr}.feedback-detail-grid .evidence-panel{grid-template-columns:1fr}.attempt-tabs{display:flex;overflow-x:auto}.attempt-tabs button{flex:0 0 165px}.result-actions{display:grid;grid-template-columns:1fr 1fr}.result-actions button{width:100%}}
@media(max-width:420px){.feedback-copy__head{display:block}.feedback-copy__head>b{display:inline-block;margin-top:9px}.feedback-legend{gap:7px 11px}.feedback-script .script-word{min-width:29px;margin-inline:1px;padding-inline:4px}.feedback-list>button{grid-template-columns:auto minmax(0,1fr)}.feedback-list>button>small{grid-column:2}.feedback-audio{grid-template-columns:1fr}.feedback-audio>button{justify-content:center}.result-actions{grid-template-columns:1fr}}

/* Practice workspace: compact preparation, readable assessment, content-sized evidence. */
.practice-page.practice-page {
  --practice-muted:#52647e;
  --practice-border:#dce5f0;
  --practice-blue:#1768ed;
  max-width:1280px;
  gap:16px;
}
.practice-page > .section-header {margin-bottom:0}
.practice-page > .section-header h1 {font-size:24px;overflow-wrap:anywhere}
.practice-page > .section-header p {font-size:13px;color:var(--practice-muted)}
.practice-page :deep(.learner-brand-header) {margin-bottom:0}
.practice-page .workspace-summary {padding:14px 18px;border-radius:14px;box-shadow:none}
.workspace-summary > div:first-child {gap:12px;flex-wrap:wrap;font-size:14px}
.workspace-summary small {font-size:12px;color:var(--practice-muted)}
.workspace-progress {margin:10px 0 6px;height:5px}
.practice-page .lesson-card,.practice-page .record-card-live {border-radius:16px;padding:20px;box-shadow:0 4px 16px #24478108}
.lesson-heading {align-items:center;gap:12px}
.lesson-heading > span:first-child {font-size:14px;color:var(--practice-muted);overflow-wrap:anywhere}
.practice-page .lesson-preview {height:220px;margin-top:14px}
.practice-page .record-actions {grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.record-actions .record-toggle {grid-column:1/-1}
.record-actions button {font-size:14px;min-height:44px}
.record-state strong {font-size:17px}
.record-state small {font-size:13px;color:var(--practice-muted);line-height:1.6}
.record-orb {width:44px;height:44px;flex:none}
.record-submit {font-size:15px;min-height:48px}
.privacy-note {font-size:12px;line-height:1.6;color:var(--practice-muted)}
.practice-page .result-card {padding:24px;margin-top:4px;border-radius:18px;box-shadow:0 4px 20px #24478108}
.result-title {align-items:center;gap:16px}
.result-title h2 {font-size:24px;margin-top:4px}
.result-title span,.result-title small {font-size:13px;color:var(--practice-muted)}
.attempt-tabs {display:flex;gap:10px;overflow-x:auto;padding:4px;margin:16px -4px}
.attempt-tabs button {flex:0 0 220px;min-height:72px}
.attempt-tabs button small {font-size:12px;color:var(--practice-muted)}
.practice-page .score-grid {grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:12px 0}
.score-grid article {padding:14px 10px}
.score-grid span {font-size:13px;color:var(--practice-muted)}
.score-grid strong {font-size:26px}
.result-meta {gap:12px}
.result-meta span {font-size:13px;background:transparent;padding:4px 0;color:var(--practice-muted)}
.feedback-copy {padding:20px 0 0;border:0;border-top:1px solid var(--practice-border);border-radius:0;background:transparent}
.feedback-copy__head {align-items:center}
.feedback-copy__head span {font-size:12px}
.feedback-copy__head h3 {font-size:20px;margin:4px 0 6px}
.feedback-copy__head p {font-size:14px;line-height:1.6;color:var(--practice-muted)}
.feedback-copy__head > b {font-size:13px;white-space:nowrap}
.feedback-audio {padding:12px 14px;gap:14px;margin-top:16px}
.feedback-audio > button {min-height:44px}
.feedback-audio > button b,.feedback-audio > div strong {font-size:14px}
.feedback-audio > div small {font-size:12px;color:var(--practice-muted)}
.feedback-audio input {height:24px}
.feedback-legend {font-size:12px;color:var(--practice-muted);margin:16px 0 8px}
.feedback-script.annotated-script {padding:14px;line-height:2.5;white-space:pre-wrap}
.practice-page .feedback-script .script-word {min-width:44px;min-height:56px;margin:5px 3px;padding:6px 8px;border-width:0 0 2px;border-radius:6px}
.feedback-script .script-word > b {font-size:17px;line-height:1.4;overflow-wrap:anywhere}
.feedback-script .script-word > small {font-size:12px;margin-top:3px}
.feedback-script .script-word > i {font-size:10px}
.feedback-script .script-word.good {background:#f5faf8}
.feedback-script .script-word.good > small {color:#206349}
.feedback-script .script-word.medium > small {color:#875412}
.feedback-filters {flex-wrap:wrap;overflow:visible;gap:8px}
.feedback-filters button {min-height:44px;padding:10px 12px;font-size:13px;color:var(--practice-muted)}
.feedback-detail-grid {grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);align-items:start;gap:20px;margin-top:16px}
.feedback-list {max-height:none;overflow:visible;padding:0;border:0;background:transparent}
.feedback-list > h3 {font-size:16px;margin:0 0 12px}
.feedback-list > button {min-height:80px;padding:14px;margin-top:10px;gap:10px;border:1px solid var(--practice-border);box-shadow:none;background:#fff}
.feedback-list > button > span {font-size:12px}
.feedback-list > button strong {font-size:15px;line-height:1.5;overflow-wrap:anywhere}
.feedback-list > button p {font-size:13px;line-height:1.7;color:var(--practice-muted)}
.feedback-list > button > small {font-size:12px}
.feedback-detail-grid .evidence-panel {position:sticky;top:20px;grid-template-columns:minmax(0,1fr) auto;padding:18px;margin:0;gap:16px;background:#f5f9ff;box-shadow:none}
.feedback-detail-grid .evidence-panel .evidence-play {position:static;grid-column:2;grid-row:1;min-height:44px;padding:10px 12px;font-size:14px;white-space:nowrap}
.evidence-panel h3 {font-size:24px;overflow-wrap:anywhere}
.evidence-panel span,.evidence-panel small,.evidence-panel dt {font-size:12px;color:var(--practice-muted)}
.feedback-detail-grid .evidence-panel dl {grid-column:1/-1;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.evidence-panel dd {font-size:20px}
.evidence-panel p,.confirmed-issue ul {font-size:14px;line-height:1.7}
.confirmed-issue > b {font-size:14px}
.phoneme-list button {min-height:44px}
.evidence-placeholder {min-height:132px;padding:24px 18px;border-style:dashed;background:#f8fafc}
.evidence-placeholder strong {font-size:16px}
.evidence-placeholder p {font-size:14px;line-height:1.6;color:var(--practice-muted)}
.feedback-note {padding:14px 0;margin-top:16px;border-top:1px solid var(--practice-border);font-size:13px;color:var(--practice-muted);line-height:1.7}
.feedback-note summary {cursor:pointer;min-height:44px;display:flex;align-items:center}
.feedback-note summary::before {content:'＋';margin-right:8px}
.feedback-note[open] summary::before {content:'−'}
.result-actions {padding-top:16px;margin-top:0;border-top:1px solid var(--practice-border)}
.result-actions button {font-size:14px}
.granular-score-notice strong,.granular-score-notice span {font-size:13px}
.granular-score-notice button {min-height:44px}
@media(min-width:960px) {
  .practice-page.practice-page {grid-template-columns:minmax(0,1.55fr) minmax(280px,1fr)}
  .practice-page > .lesson-card {align-self:stretch}
}
@media(max-width:1100px) {
  .feedback-detail-grid {grid-template-columns:minmax(0,1fr)}
  .feedback-detail-grid .evidence-panel {position:static}
  .feedback-list > button {grid-template-columns:auto minmax(0,1fr) auto}
}
@media(max-width:959px) {
  .practice-page .section-header {margin:16px 0}
  .workspace-summary {margin-bottom:16px}
}
@media(max-width:600px) {
  .practice-page .result-card {padding:16px;margin-top:16px}
  .practice-page .lesson-card,.practice-page .record-card-live {padding:16px}
  .practice-page .score-grid {grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
  .feedback-copy__head {align-items:start}
  .feedback-copy__head p {font-size:13px}
  .feedback-script.annotated-script {padding:8px}
  .feedback-list > button {grid-template-columns:auto minmax(0,1fr)}
  .feedback-list > button > small {grid-column:2}
  .feedback-audio {grid-template-columns:1fr}
  .feedback-audio > button {justify-content:center}
  .feedback-detail-grid .evidence-panel {grid-template-columns:minmax(0,1fr)}
  .feedback-detail-grid .evidence-panel .evidence-play {grid-column:1;grid-row:auto;justify-self:start}
  .result-actions {flex-wrap:wrap}
  .result-actions button {flex:1}
}
.assessment-overview {display:grid;grid-template-columns:160px minmax(0,1fr);gap:16px;align-items:stretch;margin-top:16px}
.overall-score {display:flex;flex-direction:column;justify-content:center;align-items:center;padding:18px;border-radius:14px;background:#edf4ff;color:#17428c}
.overall-score > span {font-size:14px;font-weight:600}
.overall-score > strong {font-size:44px;line-height:1.3;font-variant-numeric:tabular-nums;color:var(--practice-blue)}
.overall-score > small {font-size:12px;color:var(--practice-muted)}
.practice-page .assessment-overview .score-grid {margin:0;align-items:stretch}
.assessment-overview .score-grid article {display:flex;flex-direction:column;justify-content:center;gap:8px;background:#f8fafc}
.feedback-list > button.is-selected {border-color:#1768ed;background:#eef5ff;box-shadow:inset 3px 0 #1768ed}
@media(max-width:600px) {
 .assessment-overview {grid-template-columns:100px minmax(0,1fr);gap:8px}
 .overall-score {padding:12px 8px}
 .overall-score > strong {font-size:36px}
 .assessment-overview .score-grid article {padding:10px 4px;gap:0}
 .assessment-overview .score-grid span {font-size:12px}
 .assessment-overview .score-grid strong {font-size:22px}
}

.feedback-list > .feedback-expand {display:block;min-height:44px;padding:10px;color:var(--practice-blue);border:0;background:#f0f5fc;text-align:center;font-size:14px}
@media(max-width:1100px) {.feedback-detail-grid .evidence-panel {order:-1}}

/* Learner practice + AI assessment V2. */
.practice-page.practice-page {
  display:block;
  width:100%;
  max-width:1200px;
  padding:calc(16px + env(safe-area-inset-top)) clamp(16px,3vw,34px) calc(108px + env(safe-area-inset-bottom));
  overflow:visible;
  background:var(--bg,#f7fafe);
}
.practice-topbar {display:flex;align-items:center;gap:12px;margin-bottom:20px}
.practice-topbar .back-button {flex:none;width:44px;height:44px;min-width:44px;border:1px solid #e1e9f4;box-shadow:0 4px 14px #2447810a;font-size:30px}
.practice-topbar>div{min-width:0;flex:1}.practice-topbar span{display:block;margin-bottom:2px;color:var(--v2-muted);font-size:10px}.practice-topbar h1 {margin:0;color:#102f61;font-size:clamp(20px,3vw,28px);line-height:1.35;letter-spacing:0;overflow-wrap:anywhere}.practice-progress{display:grid;place-items:center;flex:none;min-width:48px;min-height:32px;padding:4px 9px;border-radius:999px;color:var(--v2-blue);background:#e7efff;font-size:11px}
.practice-stage {display:grid;gap:16px;align-items:start}
.practice-page .lesson-card,.practice-page .record-card-live {margin:0;padding:clamp(16px,3vw,26px);border:1px solid #e1e9f3;border-radius:20px;background:#fff;box-shadow:0 8px 28px #173b6d0b}
.reference-copy {display:grid;gap:16px;margin:0}
.reference-copy p {margin:0;color:#172c4c;font-family:Inter,"SF Pro Text","Segoe UI",Arial,sans-serif;font-size:clamp(18px,2.25vw,22px);font-weight:450;line-height:1.78;letter-spacing:.005em;overflow-wrap:break-word}
.content-switcher {margin:0 0 16px;padding-bottom:4px}
.content-switcher button {min-height:52px}
.record-card-live {text-align:center}
.record-control {display:grid;justify-items:center;gap:14px}
.record-main {display:grid;place-items:center;width:92px;height:92px;min-height:92px;border:0;border-radius:50%;background:linear-gradient(145deg,#1a73f0,#1459d6);box-shadow:0 0 0 10px #1769ef14,0 16px 32px #1769ef2d;transition:transform .18s ease,box-shadow .18s ease,background-color .18s ease}
.record-main>span {width:28px;height:28px;border:5px solid #fff;border-radius:50%;box-shadow:inset 0 -9px 0 -5px #fff}
.record-main.active {background:#dc4f64;box-shadow:0 0 0 12px #dc4f6415,0 16px 32px #dc4f6428}
.record-main.active>span {width:26px;height:26px;border:0;border-radius:6px;background:#fff;box-shadow:none}
.record-main.paused {background:#d58a27}
.record-state strong {color:#19375f;font-size:17px}
.record-state small {margin-top:5px;color:#64758f;font-size:14px;font-variant-numeric:tabular-nums}
.practice-page .record-actions {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:20px}
.practice-page .record-actions--active {grid-template-columns:1fr}
.record-actions button {min-height:46px;font-size:14px}
.record-submit {min-height:52px;margin-top:14px;font-size:15px;font-weight:700}
.submit-success {margin:12px 0 0;color:#087e50;font-size:13px}
.result-card {margin-top:20px!important;padding:24px!important;border:1px solid #e1e9f3;border-radius:22px!important;background:#fff;box-shadow:0 8px 30px #173b6d0b!important}
.result-title {display:flex;align-items:center;justify-content:space-between;gap:16px}
.result-title h2 {margin:0;color:#102f61;font-size:24px}
.result-title>span {flex:none;padding:7px 11px;border-radius:999px;color:#1768ed;background:#edf4ff;font-size:12px;font-weight:700}
.assessment-overview {display:block;margin:20px 0 0}
.overall-score {padding:8px 0 18px;border:0;background:transparent}
.overall-score>strong {color:#1768ed;font-size:64px;line-height:1;font-variant-numeric:tabular-nums}
.overall-score>span {margin-top:8px;color:#314b70;font-size:16px;font-weight:700}
.practice-page .assessment-overview .score-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0}
.assessment-overview .score-grid article {padding:14px 8px;border:1px solid #e7edf5;border-radius:13px;background:#f8fafc}
.assessment-overview .score-grid span {color:#64758f;font-size:12px}
.assessment-overview .score-grid strong {margin-top:6px;color:#1768ed;font-size:24px}
.assessment-overview .result-meta {justify-content:center;gap:20px;margin:14px 0 0;color:#77879e}
.assessment-overview .result-meta span {padding:0;background:transparent;font-size:12px}
.assessment-overview .result-meta strong {color:#536681;font-weight:650}
.issue-summary {margin-top:22px;padding-top:20px;border-top:1px solid #e4ebf4}
.issue-summary>header {display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.issue-summary h3 {margin:0;color:#203b63;font-size:18px}
.issue-summary header small {color:#7a8aa1;font-size:12px}
.issue-summary-grid {display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}
.issue-summary-grid article {display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px;border:1px solid #e7edf5;border-radius:12px;color:#7c8a9f;background:#f8fafc}
.issue-summary-grid article.active {border-color:#f2c6ae;color:#a44e25;background:#fff6f0}
.issue-summary-grid span {font-size:12px}
.issue-summary-grid strong {font-size:18px;font-variant-numeric:tabular-nums}
.analysis-disclosure {margin-top:18px;border-top:1px solid #e4ebf4}
.analysis-toggle {display:flex;align-items:center;justify-content:space-between;gap:16px;width:100%;min-height:68px;padding:12px 2px;border:0;color:#203b63;background:transparent;text-align:left;cursor:pointer}
.analysis-toggle span {display:grid;gap:4px}
.analysis-toggle strong {font-size:17px}
.analysis-toggle small {color:#74849a;font-size:12px;font-weight:400}
.analysis-toggle i {color:#607694;font-size:24px;font-style:normal;transition:transform .2s ease}
.analysis-toggle[aria-expanded="true"] i {transform:rotate(180deg)}
.feedback-copy {margin:0;padding:18px 0 0;border:0;border-top:1px solid #e4ebf4;background:transparent}
.feedback-script.annotated-script {display:block;width:100%;margin-top:14px;padding:12px;line-height:2.25;white-space:pre-wrap;overflow:visible;border:1px solid #e1e9f3;border-radius:14px;background:#fff}
.practice-page .feedback-script .script-word {width:auto;min-width:0;min-height:50px;margin:6px 3px 2px;padding:6px 7px 5px;border-width:1px;border-radius:8px;line-height:1.1;white-space:nowrap}
.feedback-script .script-word>b {font-size:16px;overflow-wrap:normal}
.feedback-script .script-word>small {font-size:11px}
.feedback-script .script-word.good {border-color:#b8dfcf;background:#f1faf6}
.feedback-script .script-word.medium {border-color:#efc77d;background:#fff8e9}
.feedback-script .script-word.low {border-color:#ee9eaa;background:#fff0f2}
.feedback-filters {display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;overflow:visible}
.feedback-filters button {min-height:44px;padding:9px 12px;font-size:12px}
.feedback-list {margin-top:16px;padding:0;border:0;background:transparent}
.feedback-list>h3 {margin:0 0 10px;color:#203b63;font-size:16px}
.feedback-list>button {min-height:62px;margin-top:8px;padding:11px 12px;border:1px solid #e1e9f3;background:#fff}
.feedback-list>button strong {font-size:13px}
.feedback-list>button p {font-size:12px;line-height:1.55}
.feedback-list>.feedback-expand {border:0;background:#edf4ff}
.result-actions {display:grid;gap:10px;margin-top:20px;padding-top:18px;border-top:1px solid #e4ebf4;text-align:center}
.result-actions p {margin:0;color:#6b7c93;font-size:13px}
.result-actions .primary-button {min-height:52px;font-size:16px}
.word-detail-layer {position:fixed;inset:0;z-index:80;pointer-events:none}
.word-detail-backdrop {position:absolute;inset:0;width:100%;height:100%;border:0;background:#0b183533;pointer-events:auto;cursor:default}
.word-detail-card {position:fixed;z-index:1;padding:20px;border:1px solid #dce6f3;border-radius:17px;background:#fff;box-shadow:0 22px 60px #10264a38;pointer-events:auto}
.word-detail-close {position:absolute;right:10px;top:9px;display:grid;place-items:center;width:36px;height:36px;min-height:36px;border:0;border-radius:50%;color:#6d7e95;background:#f2f5f9;font-size:22px}
.word-detail-card h3 {margin:0;padding-right:34px;color:#173761;font-size:23px;overflow-wrap:anywhere}
.word-phonetic {margin:7px 0 0;color:#62748f;font-family:"Segoe UI",Arial,sans-serif;font-size:15px}
.word-phonetic.muted {font-size:12px}
.word-score-line {display:flex;align-items:baseline;gap:9px;margin:16px 0 0}
.word-score-line strong {color:#1768ed;font-size:30px}
.word-score-line span {color:#536781;font-size:13px;font-weight:700}
.word-audio-actions {display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}
.word-audio-actions button {min-height:44px;padding:9px;border:1px solid #bfd5f4;border-radius:10px;color:#1768ed;background:#f4f8ff;font-size:13px}
.word-audio-actions button:disabled {color:#8b98aa;background:#f4f5f7}
.word-problem {margin:14px 0 0;padding-top:13px;border-top:1px solid #e4ebf4;color:#445b79;font-size:13px;line-height:1.65}
@media(min-width:900px) {
  .practice-stage {grid-template-columns:minmax(0,1.55fr) minmax(290px,.75fr)}
  .record-card-live {position:sticky;top:20px}
}
@media(max-width:820px) {
  .practice-page.practice-page {padding-inline:16px}
  .practice-page .assessment-overview .score-grid {grid-template-columns:repeat(2,minmax(0,1fr))}
  .issue-summary-grid {grid-template-columns:repeat(3,minmax(0,1fr))}
}
@media(max-width:640px) {
  .practice-page.practice-page {padding:calc(12px + env(safe-area-inset-top)) 12px calc(104px + env(safe-area-inset-bottom))}
  .practice-topbar {margin-bottom:14px}
  .practice-topbar h1 {font-size:20px}
  .practice-page .lesson-card,.practice-page .record-card-live {padding:16px;border-radius:16px}
  .reference-copy {gap:12px}
  .reference-copy p {font-size:18px;line-height:1.72}
  .record-main {width:84px;height:84px;min-height:84px}
  .result-card {padding:0!important;border:0;border-radius:0!important;background:transparent;box-shadow:none!important}
  .result-title,.assessment-overview,.issue-summary,.analysis-disclosure {padding-left:14px;padding-right:14px;border:1px solid #e1e9f3;background:#fff}
  .result-title {padding-top:16px;padding-bottom:4px;border-bottom:0;border-radius:17px 17px 0 0}
  .result-title h2 {font-size:20px}
  .assessment-overview {margin:0;padding-top:14px;padding-bottom:18px;border-top:0;border-bottom:0}
  .overall-score {padding-top:2px}
  .overall-score>strong {font-size:56px}
  .issue-summary {margin:0;padding-top:18px;padding-bottom:18px;border-top:1px solid #e7edf5;border-bottom:0}
  .issue-summary-grid {grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
  .issue-summary-grid article {padding:10px 9px}
  .analysis-disclosure {margin:0;padding:0;border-top:1px solid #e7edf5;border-radius:0 0 17px 17px}
  .analysis-toggle {padding:12px 14px}
  .feedback-copy {width:100%;padding:14px 0 0;border-top:1px solid #e7edf5}
  .feedback-audio,.feedback-legend,.granular-score-notice,.feedback-filters,.feedback-list {margin-left:10px;margin-right:10px}
  .feedback-script.annotated-script {width:100%;padding:9px;border-left:0;border-right:0;border-radius:0}
  .practice-page .feedback-script .script-word {margin-inline:2px;padding-inline:6px}
  .feedback-list>button {grid-template-columns:auto minmax(0,1fr)}
  .feedback-list>button>small {grid-column:2}
  .result-actions {padding:16px 14px;margin-top:12px;border:1px solid #e1e9f3;border-radius:17px;background:#fff}
  .word-detail-layer.is-sheet .word-detail-backdrop {background:#0b183566}
  .word-detail-layer.is-sheet .word-detail-card {left:0!important;right:0;top:auto!important;bottom:0;width:100%!important;padding:22px 18px calc(22px + env(safe-area-inset-bottom));border-radius:22px 22px 0 0;transform:none!important}
}
@media(max-width:380px) {
  .practice-page .assessment-overview .score-grid {gap:7px}
  .assessment-overview .score-grid article {padding-inline:4px}
  .issue-summary-grid article {display:grid;justify-items:center;gap:3px;padding:9px 4px}
}

/* Figma production flow · nodes 129:250 / 129:259 / 129:272 / 498:3480 / 498:3499 */
.practice-page.practice-page{position:relative;width:100%;max-width:390px;height:844px;min-height:844px;margin:auto;padding:16px 8px 20px;border-radius:44px;background:#eef4fe;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;overflow:hidden}
.practice-page>.mobile-detail-header{width:390px;margin-left:-8px}
.practice-page>.content-switcher,.practice-page>.course-media,.practice-page>.pdf-page-viewer{display:none}
.practice-page .practice-stage{display:block;margin:20px 0 0}
.practice-page .lesson-card{width:374px;height:586px;min-height:586px;padding:14px;border:1px solid #e5ebf2;border-radius:16px;background:#fff;box-shadow:0 10px 28px rgba(13,26,61,.08);overflow:auto}
.practice-page .reference-copy{display:block;margin:0;padding:0;background:transparent}
.practice-page .reference-copy p{margin:0 0 16px;color:#12141a;font-size:22px;line-height:34px;letter-spacing:0;text-align:left}
.practice-page .reference-copy p:not(:first-child){text-indent:44px}
.practice-page .lesson-preview{width:100%;height:100%;border:0}
.practice-page .interactive-card{display:none}
.practice-page .record-card-live{position:relative;width:374px;height:150px;min-height:150px;margin:0;padding:7px 0 0;border:0;border-radius:0;background:transparent;box-shadow:none}
.practice-page .record-control{display:flex;flex-direction:column;align-items:center;gap:7px;margin:0}
.practice-page .record-main,.practice-page .record-complete-icon{display:grid;place-items:center;width:64px;height:64px;min-height:64px;border-radius:50%;color:#fff;background:#28ad73;box-shadow:none}
.practice-page .record-main>span{width:18px;height:18px;border-radius:50%;background:#fff}
.practice-page .record-main.active{background:#fa3434}
.practice-page .record-main.active>span{border-radius:4px}
.practice-page .record-complete-icon{font-size:26px;font-weight:600}
.practice-page .record-state{text-align:center}
.practice-page .record-state strong{display:block;color:#12141a;font-size:14px;line-height:20px}
.practice-page .record-main.active+.record-state strong{color:#fa3434}
.practice-page .record-state small{position:absolute;left:0;right:0;top:-12px;color:#12141a;font-size:20px;font-weight:600}
.practice-page .record-main.active{margin-top:13px}
.practice-page .record-preview,.practice-page .record-actions,.practice-page .submit-success{display:none!important}
.practice-page .record-submit{display:none}
.practice-page .record-submit:not(:disabled){position:absolute;left:26px;top:101px;display:grid;width:334px;height:44px;min-height:44px;border-radius:13px;color:#fff;background:#3b86f3;font-size:12px;box-shadow:none}
.recorded-actions{display:flex;align-items:flex-start;justify-content:flex-start;gap:40px;width:100%;padding:28px 0 0 38px}
.recorded-action{display:flex;flex-direction:column;align-items:center;gap:8px;width:120px;padding:0;border:0;color:#1a2638;background:transparent;font-family:inherit}
.recorded-action>span{display:grid;place-items:center;width:72px;height:72px;border-radius:50%;background:#21b866;box-shadow:0 6px 14px rgba(0,0,0,.12)}
.recorded-action--submit>span{background:#1769f0}.recorded-action img{width:24px;height:24px;max-width:none}.recorded-action strong{font-size:14px;line-height:20px;font-weight:600}.recorded-action--submit{cursor:pointer}.recorded-action--submit:disabled{cursor:wait;opacity:.58}
.practice-page .result-card{display:none!important}
.practice-page>.bottom-nav{display:none!important}
.practice-page>.form-error{position:absolute;left:20px;right:20px;bottom:12px;z-index:8;margin:0}
.figma-submit-state{position:absolute;inset:92px 8px 0;z-index:7;background:#eef4fe;text-align:center}
.figma-submit-script{width:374px;height:584px;padding:14px;border:1px solid #e5ebf2;border-radius:16px;background:#fff;box-shadow:0 10px 28px rgba(13,26,61,.08);overflow:auto;text-align:left}.figma-submit-script p{margin:0 0 16px;color:#12141a;font-size:22px;line-height:34px}.figma-submit-script p:not(:first-child){text-indent:44px}
.figma-assessing-card{position:absolute;left:16px;top:598px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;width:342px;min-height:122px;padding:14px 16px 12px;border-radius:20px;background:rgba(255,255,255,.82);box-shadow:0 4px 14px rgba(0,0,0,.07)}
.figma-loading-dots{width:36px;height:8px;max-width:none}.figma-assessing-card>strong{color:#1a2638;font-size:16px;line-height:22px;font-weight:400}.figma-assessing-card>p{max-width:296px;margin:0;color:#6e7d94;font-size:12px;line-height:18px}.figma-error-badge{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;color:#fff;background:#e34f5f;font-size:16px;font-weight:700}.figma-assessing-card>button{min-height:34px;padding:0 18px;border:1px solid #b6c9e8;border-radius:17px;color:#1769f0;background:#fff;font-size:12px}.figma-assessing-card>button:disabled{opacity:.55}.figma-submit-state.is-failed .figma-assessing-card{top:574px;min-height:144px;padding:10px 16px;gap:5px}
.figma-completed-cta{position:absolute;left:16px;top:615px;display:flex;align-items:center;justify-content:center;gap:8px;width:342px;height:64px;min-height:64px;border:0;border-radius:16px;color:#fff;background:#1769f0;box-shadow:0 6px 16px rgba(10,46,122,.16);font-size:15px}.figma-completed-cta img{width:18px;height:18px;max-width:none}.figma-completed-cta:disabled{opacity:.55}
@media(min-width:700px){.practice-page.practice-page{max-width:834px;height:1194px;min-height:1194px;padding-inline:40px}.practice-page>.mobile-detail-header{width:100%;margin:0}.practice-page .practice-stage{display:grid;grid-template-columns:1fr 220px;gap:20px}.practice-page .lesson-card{width:534px;height:820px}.practice-page .record-card-live{width:200px;margin-top:0}.figma-submit-state{left:40px;right:40px}.figma-submit-script{width:100%;height:820px}}
</style>
