<template>
  <main class="pronunciation-page">
    <header class="pronunciation-header">
      <button type="button" aria-label="返回测评详情" @click="goBack">‹</button>
      <h1>{{ stage === 'complete' ? '专项训练完成' : '专项发音训练' }}</h1>
      <span v-if="stage !== 'complete'">{{ progressText }}</span>
    </header>

    <PageState v-if="loading" tone="loading" title="正在生成专项训练" />
    <PageState v-else-if="fatalError || !attempt" tone="error" title="专项训练无法读取"
      :message="fatalError || '该测评记录不存在。'" action-label="重试" @action="loadTraining" />

    <template v-else>
      <section v-if="stage === 'complete'" class="pronunciation-complete">
        <div class="complete-check"><img :src="checkIcon" alt="" /></div>
        <h2>本次专项训练完成</h2>
        <p>问题词已经逐一完成跟读与纠音</p>
        <div class="complete-summary">
          <div><strong>{{ masteredCount }}</strong><span>已掌握</span></div>
          <div><strong>{{ needsPracticeCount }}</strong><span>需加强</span></div>
        </div>
        <div class="complete-list">
          <article v-for="item in queue" :key="item.engine.id">
            <div><strong>{{ item.engine.word }}</strong><small>{{ item.engine.ipa }}</small></div>
            <span :class="{ warning: !item.result || item.result.verdict === 'needs_practice' }">
              {{ !item.result ? '未练习' : item.result.verdict === 'needs_practice' ? '需加强' : '已掌握' }}
            </span>
          </article>
        </div>
        <button type="button" class="pronunciation-primary" @click="retest">完成训练，重新测评</button>
        <button type="button" class="pronunciation-secondary" @click="backToDetail">返回测评详情</button>
      </section>

      <section v-else-if="currentItem" class="pronunciation-session">
        <div class="pronunciation-word-hero">
          <h2>{{ currentItem.engine.word }}</h2>
          <p>{{ currentItem.engine.ipa }}</p>
          <div class="pronunciation-divider" />
          <template v-if="stage === 'result' && currentResult">
            <strong :class="resultMastered ? 'success' : 'warning'">{{ currentResult.score }}</strong>
            <span :class="resultMastered ? 'success' : 'warning'">{{ resultMastered ? '已掌握' : '需要再练' }}</span>
          </template>
          <span v-else :class="{ recording: stage === 'recording' }">{{ heroStatus }}</span>
        </div>

        <button v-if="stage !== 'analyzing'" type="button" class="pronunciation-audio standard"
          :disabled="standardLoading" @click="playStandard(1)">
          <i><img :src="playBlueIcon" alt="" /></i>
          <strong>{{ standardLoading ? '正在加载标准发音' : '标准发音' }}</strong>
        </button>
        <button v-if="stage === 'result'" type="button" class="pronunciation-audio mine"
          :disabled="!recordingUrl" @click="playMine">
          <i><img :src="playDarkIcon" alt="" /></i><strong>我的发音</strong>
        </button>

        <div v-if="stage === 'ready'" class="pronunciation-speed">
          <button type="button" @click="playStandard(1)">标准速度</button>
          <button type="button" @click="playStandard(0.68)">慢速示范</button>
        </div>
        <div v-if="stage === 'ready'" class="pronunciation-recorder">
          <p>先听标准发音，再完整读出这个单词。</p>
          <button type="button" aria-label="开始跟读" @click="startRecording"><img :src="recorderReadyIcon" alt="" /></button>
          <strong>开始跟读</strong>
        </div>
        <div v-else-if="stage === 'recording'" class="pronunciation-recorder recording">
          <b>{{ recordingClock }}</b>
          <button type="button" aria-label="停止录音" @click="stopRecording"><i /></button>
          <strong>正在跟读</strong>
        </div>
        <div v-else-if="stage === 'analyzing'" class="pronunciation-analysis" aria-live="polite">
          <h3>AI 正在分析发音</h3><p>正在分析音素、替换和完整度</p><div><span /></div>
        </div>

        <template v-else-if="stage === 'result' && currentResult">
          <div v-if="resultMastered" class="pronunciation-success-card">
            <strong>✓ 本词已掌握</strong>
            <p>{{ allMastered ? '3 秒后自动显示训练结果' : '3 秒后自动进入下一个问题词' }}</p>
          </div>
          <div v-else class="pronunciation-feedback-card">
            <strong>{{ feedbackTitle }}</strong><p>{{ feedbackBody }}</p>
          </div>
          <button v-if="resultMastered" type="button" class="pronunciation-primary" @click="continueTraining">
            {{ allMastered ? '查看训练结果' : '下一个单词' }}
          </button>
          <template v-else>
            <button type="button" class="pronunciation-primary" @click="retryWord">再读一次</button>
            <button type="button" class="pronunciation-secondary" @click="continueTraining">下一个单词</button>
            <button type="button" class="pronunciation-link" @click="playStandard(0.68)">听慢速示范</button>
            <button type="button" class="pronunciation-link muted" @click="finishTraining">结束训练并查看结果</button>
          </template>
        </template>
        <p v-if="sessionError" class="pronunciation-error" role="alert">{{ sessionError }}</p>
      </section>
    </template>
    <audio ref="recordingAudio" class="visually-hidden" :src="recordingUrl" />
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageState from '@/components/PageState.vue'
import { cabinlingoApi, type LearnerAttempt, type WordDetail } from '@/api'
import { learnerError } from '@/domain/learnerPresentation'
import { pronunciationApi, type PronunciationAssessment, type PronunciationWord } from '@/api/pronunciation'
import checkIcon from '@/assets/pronunciation/check.svg'
import playBlueIcon from '@/assets/pronunciation/play-blue.svg'
import playDarkIcon from '@/assets/pronunciation/play-dark.svg'
import recorderReadyIcon from '@/assets/pronunciation/recorder-ready.svg'

type Stage = 'ready' | 'recording' | 'analyzing' | 'result' | 'complete'
interface TrainingItem { detail: WordDetail; engine: PronunciationWord; originalScore: number | null; result: PronunciationAssessment | null }

const route = useRoute()
const router = useRouter()
const attempt = ref<LearnerAttempt | null>(null)
const queue = ref<TrainingItem[]>([])
const unsupportedWords = ref<string[]>([])
const stage = ref<Stage>('ready')
const activeIndex = ref(0)
const loading = ref(true)
const fatalError = ref('')
const sessionError = ref('')
const recordingElapsed = ref(0)
const recordingUrl = ref('')
const recordingAudio = ref<HTMLAudioElement | null>(null)
const standardLoading = ref(false)
let standardAudio: HTMLAudioElement | null = null
let standardAudioUrl = ''
let recorder: MediaRecorder | null = null
let recordingStream: MediaStream | null = null
let recordingChunks: BlobPart[] = []
let recordingStartedAt = 0
let recordingTimer: number | undefined
let autoAdvanceTimer: number | undefined
let discardRecording = false

const currentItem = computed(() => queue.value[activeIndex.value] || null)
const currentResult = computed(() => currentItem.value?.result || null)
const resultMastered = computed(() => !!currentResult.value && currentResult.value.verdict !== 'needs_practice')
const masteredCount = computed(() => queue.value.filter(item => item.result && item.result.verdict !== 'needs_practice').length)
const needsPracticeCount = computed(() => queue.value.filter(item => !item.result || item.result.verdict === 'needs_practice').length)
const attemptedCount = computed(() => queue.value.filter(item => item.result).length)
const allMastered = computed(() => !!queue.value.length && queue.value.every(item => item.result?.verdict !== 'needs_practice' && item.result))
const progressText = computed(() => `${attemptedCount.value} / ${queue.value.length}`)
const heroStatus = computed(() => stage.value === 'recording' ? '正在录音，请完整读出单词' : stage.value === 'analyzing' ? '录音完成' : '听一遍，再完整跟读')
const recordingClock = computed(() => `00:${String(Math.max(0, Math.ceil(recordingElapsed.value / 1000))).padStart(2, '0')}`)
const feedbackTitle = computed(() => currentResult.value?.feedback[0]?.title || '部分音素还不够稳定')
const feedbackBody = computed(() => {
  const feedback = currentResult.value?.feedback[0]
  return feedback ? [feedback.message, feedback.tip].filter(Boolean).join(' ') : '先听标准发音，再按音节慢速读一遍。'
})

function normalize(value: string) { return value.toLowerCase().replace(/[^a-z0-9]/g, '') }
function detailScore(detail: WordDetail) {
  const values = [detail.pronunciation, detail.overall, detail.expected_tone ? detail.tone : undefined]
    .filter((value): value is number => typeof value === 'number')
  return values.length ? Math.round(Math.min(...values)) : null
}
function cleanupStandardAudio() {
  standardAudio?.pause(); standardAudio = null
  if (standardAudioUrl) URL.revokeObjectURL(standardAudioUrl)
  standardAudioUrl = ''
}
async function playStandard(rate = 1) {
  if (!currentItem.value || !attempt.value || standardLoading.value) return
  cleanupStandardAudio(); standardLoading.value = true; sessionError.value = ''
  try {
    const blob = await cabinlingoApi.learnerStandardPronunciation({
      attempt_id: attempt.value.attempt_id,
      text: currentItem.value.engine.word,
      reference_index: currentItem.value.detail.reference_index ?? null,
    })
    standardAudioUrl = URL.createObjectURL(blob)
    standardAudio = new Audio(standardAudioUrl); standardAudio.playbackRate = rate
    await standardAudio.play()
  } catch {
    if ('speechSynthesis' in window) {
      const utterance = new SpeechSynthesisUtterance(currentItem.value.engine.word)
      utterance.lang = 'en-US'; utterance.rate = rate
      window.speechSynthesis.cancel(); window.speechSynthesis.speak(utterance)
    } else sessionError.value = '标准发音暂时无法播放，请稍后重试。'
  } finally { standardLoading.value = false }
}
function clearRecordingTimer() { if (recordingTimer !== undefined) window.clearInterval(recordingTimer); recordingTimer = undefined }
function clearAutoAdvance() { if (autoAdvanceTimer !== undefined) window.clearTimeout(autoAdvanceTimer); autoAdvanceTimer = undefined }
function scheduleAutoAdvance() {
  clearAutoAdvance()
  if (resultMastered.value) autoAdvanceTimer = window.setTimeout(continueTraining, 3000)
}
function stopTracks() { recordingStream?.getTracks().forEach(track => track.stop()); recordingStream = null }
function clearRecordingUrl() {
  recordingAudio.value?.pause()
  if (recordingUrl.value) URL.revokeObjectURL(recordingUrl.value)
  recordingUrl.value = ''
}
async function startRecording() {
  sessionError.value = ''
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    sessionError.value = '当前浏览器不支持录音，请使用最新版 Safari、Chrome 或 Edge。'; return
  }
  clearRecordingUrl()
  try {
    recordingStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
    recordingChunks = []; discardRecording = false
    const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(type => MediaRecorder.isTypeSupported(type))
    recorder = mimeType ? new MediaRecorder(recordingStream, { mimeType }) : new MediaRecorder(recordingStream)
    recorder.ondataavailable = event => { if (event.data.size) recordingChunks.push(event.data) }
    recorder.onstop = () => void finishRecording()
    recorder.start(200); recordingStartedAt = performance.now(); recordingElapsed.value = 0; stage.value = 'recording'
    recordingTimer = window.setInterval(() => {
      recordingElapsed.value = performance.now() - recordingStartedAt
      if (recordingElapsed.value >= 5000) stopRecording()
    }, 100)
  } catch (error) {
    stopTracks()
    sessionError.value = error instanceof DOMException && error.name === 'NotAllowedError' ? '麦克风权限未开启，请允许后重新跟读。' : '录音启动失败，请重试。'
  }
}
function stopRecording() { if (recorder?.state === 'recording') recorder.stop() }
async function finishRecording() {
  clearRecordingTimer(); stopTracks()
  const mimeType = recorder?.mimeType || 'audio/webm'; recorder = null
  if (discardRecording) return
  if (!recordingChunks.length || !currentItem.value) { stage.value = 'ready'; sessionError.value = '没有录到声音，请重新跟读。'; return }
  const blob = new Blob(recordingChunks, { type: mimeType }); recordingUrl.value = URL.createObjectURL(blob); stage.value = 'analyzing'
  try {
    currentItem.value.result = await pronunciationApi.assess(currentItem.value.engine.id, blob)
    stage.value = 'result'
    scheduleAutoAdvance()
  } catch { stage.value = 'ready'; sessionError.value = 'AI 发音分析失败，请确认网络后重新录音。' }
}
async function playMine() {
  if (!recordingAudio.value || !recordingUrl.value) return
  recordingAudio.value.currentTime = 0
  try { await recordingAudio.value.play() } catch { sessionError.value = '本次跟读录音暂时无法播放。' }
}
function retryWord() { clearAutoAdvance(); clearRecordingUrl(); sessionError.value = ''; stage.value = 'ready' }
function continueTraining() {
  clearAutoAdvance()
  clearRecordingUrl(); sessionError.value = ''
  const length = queue.value.length
  if (!length || allMastered.value) { stage.value = 'complete'; return }
  const order = Array.from({ length }, (_, offset) => (activeIndex.value + offset + 1) % length)
  const nextIndex = order.find(index => !queue.value[index].result)
    ?? order.find(index => queue.value[index].result?.verdict === 'needs_practice')
  if (nextIndex === undefined) { stage.value = 'complete'; return }
  activeIndex.value = nextIndex; stage.value = 'ready'
}
function finishTraining() { clearAutoAdvance(); clearRecordingUrl(); sessionError.value = ''; stage.value = 'complete' }
function goBack() { backToDetail() }
function backToDetail() { void router.replace(`/student/results/${String(route.params.attemptId)}`) }
function retest() {
  if (!attempt.value?.content_item_id) { backToDetail(); return }
  void router.push({ path: '/student/practice', query: { assignment: attempt.value.assignment_id, content: attempt.value.content_item_id, correction: attempt.value.attempt_id } })
}
async function loadTraining() {
  loading.value = true; fatalError.value = ''
  try {
    const loadedAttempt = await cabinlingoApi.learnerAttempt(String(route.params.attemptId))
    attempt.value = loadedAttempt
    const problemDetails = (loadedAttempt.word_details || []).filter(detail => detail.word.trim() && (detailScore(detail) ?? 100) < 90)
    const words = problemDetails.length ? await pronunciationApi.resolveWords(problemDetails.map(detail => detail.word)) : []
    const byWord = new Map(words.map(word => [normalize(word.word), word]))
    const unsupported: string[] = []
    queue.value = problemDetails.flatMap(detail => {
      const engine = byWord.get(normalize(detail.word))
      if (!engine) { unsupported.push(detail.word); return [] }
      return [{ detail, engine, originalScore: detailScore(detail), result: null }]
    })
    unsupportedWords.value = [...new Set(unsupported)]
    activeIndex.value = 0
    if (!queue.value.length) fatalError.value = unsupportedWords.value.length ? '当前问题单词暂不支持专项训练。' : '本次测评没有需要纠正的问题单词。'
    else stage.value = 'ready'
  } catch (error) { fatalError.value = learnerError(error) }
  finally { loading.value = false }
}

onMounted(loadTraining)
onBeforeUnmount(() => {
  discardRecording = true
  if (recorder?.state === 'recording') recorder.stop()
  clearRecordingTimer(); clearAutoAdvance(); stopTracks(); clearRecordingUrl(); cleanupStandardAudio(); window.speechSynthesis?.cancel()
})
</script>

<style scoped>
.pronunciation-page{width:100%;max-width:390px;min-height:100dvh;margin:auto;padding:18px 16px calc(34px + env(safe-area-inset-bottom));color:#0d1421;background:#f6f8fb;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}.pronunciation-header{display:grid;grid-template-columns:26px 1fr 72px;align-items:center;height:48px}.pronunciation-header button{width:26px;height:40px;padding:0;color:#0d1421;background:transparent;font-size:28px;font-weight:600;text-align:left}.pronunciation-header h1{margin:0 0 0 12px;font-size:17px;line-height:22px}.pronunciation-header>span{color:#6b788f;font-size:12px;text-align:right}.pronunciation-queue{padding-top:26px}.pronunciation-queue>h2{margin:0;font-size:24px;line-height:32px}.pronunciation-queue>p{margin:8px 0 20px;color:#6b788f;font-size:12px;line-height:18px}.pronunciation-queue-card{display:grid;gap:14px;padding:14px;border-radius:20px;background:#fff}.pronunciation-queue-card article{display:flex;align-items:center;justify-content:space-between;min-height:66px;padding:10px 14px;border:1px solid #e0e8f2;border-radius:14px;background:#fbfcff}.pronunciation-queue-card article:first-child{border-color:transparent}.pronunciation-queue-card strong,.pronunciation-queue-card small{display:block}.pronunciation-queue-card strong{font-size:16px;line-height:20px}.pronunciation-queue-card small{margin-top:6px;color:#6b788f;font-size:11px}.pronunciation-queue-card span{min-width:74px;padding:8px 10px;border-radius:15px;color:#6b788f;background:#f5f7fc;font-size:11px;font-weight:600;text-align:center}.pronunciation-queue-card .needs-practice span{color:#eb8714;background:#fff5e0}.pronunciation-queue-card .mastered span{color:#1aa361;background:#e8faf0}.pronunciation-method{margin-top:18px;padding:16px;border-radius:18px;background:#ebf2ff}.pronunciation-method strong{color:#1a6bf5;font-size:14px}.pronunciation-method p{margin:16px 0 0;color:#0d1421;font-size:12px;line-height:20px}.pronunciation-note{padding:0 4px;color:#eb8714!important;line-height:18px!important}.pronunciation-primary,.pronunciation-secondary{width:100%;height:54px;border-radius:16px;font-size:14px;font-weight:600}.pronunciation-primary{color:#fff;background:#1a6bf5}.pronunciation-primary:disabled{opacity:.5}.pronunciation-secondary{margin-top:12px;color:#0d1421;background:#f7faff}.queue-start{margin-top:62px}.pronunciation-session{padding-top:30px}.pronunciation-word-hero{display:grid;justify-items:center;height:178px;padding:22px 32px 10px;border-radius:20px;background:#fff}.pronunciation-word-hero h2{margin:0;font-size:30px;line-height:38px}.pronunciation-word-hero p{margin:0;color:#5e45bf;font-size:14px;line-height:20px}.pronunciation-divider{width:100%;height:1px;background:#e0e8f2}.pronunciation-word-hero>strong{font-size:38px;line-height:40px}.pronunciation-word-hero>span{font-size:13px;font-weight:600}.pronunciation-word-hero .success{color:#1aa361}.pronunciation-word-hero .warning{color:#eb8714}.pronunciation-word-hero .recording{color:#eb3333}.pronunciation-audio{display:flex;align-items:center;width:100%;height:52px;margin-top:16px;padding:0 14px;border-radius:16px;text-align:left}.pronunciation-audio.standard{color:#1a6bf5;background:#ebf2ff}.pronunciation-audio.mine{color:#0d1421;border:1px solid #e0e8f2;background:#fafbff}.pronunciation-audio i{display:grid;place-items:center;width:32px;height:32px;margin-right:12px;border-radius:16px;background:#1a6bf5}.pronunciation-audio.mine i{border:1px solid #e0e8f2;background:#fff}.pronunciation-audio strong{font-size:13px}.pronunciation-speed{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px}.pronunciation-speed button{height:40px;border-radius:12px;color:#6b788f;border:1px solid #e0e8f2;background:#f7faff;font-size:12px;font-weight:600}.pronunciation-speed button:first-child{color:#1a6bf5;border-color:transparent;background:#ebf2ff}.pronunciation-recorder{display:grid;justify-items:center;margin-top:28px}.pronunciation-recorder p{margin:0 0 34px;color:#6b788f;font-size:12px}.pronunciation-recorder>button{display:grid;padding:0;background:transparent;place-items:center}.pronunciation-recorder>strong{margin-top:12px;color:#1aa361;font-size:14px}.pronunciation-recorder.recording{margin-top:78px}.pronunciation-recorder.recording b{margin-bottom:22px;font-size:20px}.pronunciation-recorder.recording button{width:72px;height:72px;border-radius:36px;background:#eb3333}.pronunciation-recorder.recording button i{width:20px;height:20px;border-radius:4px;background:#fff}.pronunciation-recorder.recording strong{color:#eb3333}.pronunciation-analysis{height:184px;margin-top:40px;padding:34px 36px;border-radius:20px;background:#fff;text-align:center}.pronunciation-analysis h3{margin:0;font-size:18px;line-height:24px}.pronunciation-analysis p{margin:14px 0 30px;color:#6b788f;font-size:12px}.pronunciation-analysis>div{height:5px;border-radius:3px;background:#e0e8f5;overflow:hidden}.pronunciation-analysis span{display:block;width:62%;height:100%;border-radius:3px;background:#1a6bf5;animation:analysis 1.1s ease-in-out infinite alternate}.pronunciation-feedback-card,.pronunciation-success-card{margin:16px 0 28px;padding:18px 16px;border-radius:18px}.pronunciation-feedback-card{min-height:166px;color:#0d1421;background:#fff5e0}.pronunciation-feedback-card strong{color:#eb8714;font-size:14px;line-height:20px}.pronunciation-feedback-card p{margin:20px 0 0;font-size:12px;line-height:21px}.pronunciation-success-card{min-height:132px;padding-top:26px;background:#e8faf0;text-align:center}.pronunciation-success-card strong{color:#1aa361;font-size:16px}.pronunciation-success-card p{margin:22px 0 0;font-size:12px}.pronunciation-error{margin:14px 0 0;padding:10px 12px;border-radius:12px;color:#c73737;background:#fff0f1;font-size:12px}.pronunciation-complete{padding-top:40px;text-align:center}.complete-check{display:grid;width:72px;height:72px;margin:0 auto 18px;border-radius:36px;background:#1aa361;place-items:center}.pronunciation-complete>h2{margin:0;font-size:22px;line-height:30px}.pronunciation-complete>p{margin:8px 0 30px;color:#6b788f;font-size:12px}.complete-summary{display:grid;grid-template-columns:1fr 1fr;height:122px;border-radius:20px;background:#fff}.complete-summary div{display:grid;align-content:center;gap:6px}.complete-summary strong{color:#1aa361;font-size:30px}.complete-summary div:last-child strong{color:#0d1421}.complete-summary span{color:#6b788f;font-size:12px}.complete-list{display:grid;margin:20px 0 40px;padding:4px 16px;border-radius:20px;background:#fff;text-align:left}.complete-list article{display:flex;align-items:center;justify-content:space-between;min-height:54px}.complete-list strong,.complete-list small{display:block}.complete-list strong{font-size:14px}.complete-list small{margin-top:4px;color:#6b788f;font-size:10px}.complete-list span{color:#1aa361;font-size:11px;font-weight:600}.complete-list span.warning{color:#eb8714}.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}@keyframes analysis{from{transform:translateX(-20%)}to{transform:translateX(70%)}}@media(min-width:700px){.pronunciation-page{max-width:834px;padding-inline:40px}.pronunciation-header{grid-template-columns:34px 1fr 80px}.pronunciation-queue-card{grid-template-columns:1fr 1fr}.pronunciation-session,.pronunciation-queue,.pronunciation-complete{max-width:520px;margin:auto}}
.pronunciation-link{display:block;margin:14px auto 0;padding:8px;color:#1a6bf5;background:transparent;font-size:12px;font-weight:600}
.pronunciation-link.muted{margin-top:2px;color:#6b788f;font-weight:500}
</style>
