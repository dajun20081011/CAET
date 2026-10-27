<template>
  <article class="review-workspace">
    <header class="review-heading">
      <div><button type="button" class="review-back" aria-label="返回评价列表" @click="emit('back')">‹</button><h1>训练评价</h1></div>
      <p>{{ detail.learner_name }} · {{ detail.content_title || detail.task_title }} · {{ attemptLabel }}</p>
      <button type="button" class="learner-link" @click="emit('open-learner')">学员详情 →</button>
    </header>

    <AudioEvidencePlayer ref="learnerPlayer" variant="instructor" title="本次训练录音" meta="学员原始录音 · 可拖动进度与调速" :src="audioSrc" :loading="audioLoading" :known-duration-seconds="knownDuration" @load="emit('load-audio')" @error="audioError = '录音暂时无法播放，请稍后重试。'" />
    <p v-if="audioError" class="inline-alert">{{ audioError }}</p>

    <section class="review-accordion" :class="{ open: asrOpen }">
      <button type="button" class="review-accordion__summary" :aria-expanded="asrOpen" @click="asrOpen = !asrOpen">
        <span><strong>语音文本识别</strong><small>{{ asrDifferenceCount }} 处识别差异</small></span><b>{{ asrOpen ? '⌃' : '⌄' }}</b>
      </button>
      <div v-if="asrOpen" class="review-accordion__content asr-content">
        <section><h2>原文本</h2><p>{{ detail.reference_text || '本次任务未保存原文，请结合录音评价。' }}</p></section>
        <section><h2>识别结果</h2><p class="asr-tokens"><template v-if="asrTokens.length"><span v-for="(token,index) in asrTokens" :key="`${token.text}-${index}`" :class="{ mismatch:token.mismatch }">{{ token.text }}</span></template><template v-else>本次未保存语音识别文本，请结合录音评价。</template></p></section>
        <p class="asr-note">红色词语 = 识别结果与原文本不一致</p>
      </div>
    </section>

    <section class="review-accordion" :class="{ open: aiOpen }">
      <button type="button" class="review-accordion__summary" :aria-expanded="aiOpen" @click="aiOpen = !aiOpen">
        <span><strong>AI测评详情</strong><small>总分 {{ totalScore ?? '—' }} · {{ issueCount }} 个重点问题</small></span><b>{{ aiOpen ? '⌃' : '⌄' }}</b>
      </button>
      <div v-if="aiOpen" class="review-accordion__content ai-content">
        <p>逐词发音评分 · 单词在上，分数在下</p>
        <div v-if="scoredWords.length" class="word-flow">
          <button v-for="(word,index) in scoredWords" :key="`${word.word}-${index}`" type="button" :class="wordLevel(word)" @click="playWord(word.start_ms)"><strong>{{ word.word }}</strong><small>{{ wordScore(word) ?? '—' }}</small></button>
        </div>
        <p v-else class="inline-empty">本次测评只返回句级结果，暂无逐词评分。</p>
      </div>
    </section>

    <section class="feedback-card">
      <header><h2>教员评价</h2><p>选择评价方式，学员原文与识别文本保持可见</p></header>
      <textarea v-model="comment" :placeholder="commentPlaceholder" aria-label="教员文字评价" />
      <div class="feedback-methods">
        <button type="button" :class="{ active:method === 'stt', recording:speechActive }" :disabled="saving || recordingActive" @click="toggleSpeech">{{ speechActive ? '停止转写' : '语音转文字' }}</button>
        <button type="button" :class="{ active:method === 'audio', recording:recordingActive }" :disabled="saving || speechActive" @click="toggleRecording">{{ recordingActive ? '停止录音' : '录制音频评价' }}</button>
      </div>

      <div v-if="speechActive" class="feedback-status feedback-status--recording"><b />正在语音转文字 {{ formatTimer(speechSeconds) }}<span>点击“停止转写”结束</span></div>
      <div v-else-if="method === 'stt' && speechReady" class="feedback-status">转写完成，可继续编辑文字后提交</div>

      <div v-if="recordingActive" class="feedback-status feedback-status--recording"><b />正在录制音频评价 {{ formatTimer(recordSeconds) }}<span>点击“停止录音”结束</span></div>
      <div v-else-if="feedbackAudioUrl" class="feedback-status feedback-audio-ready">
        <button type="button" :aria-label="feedbackPlaying ? '暂停音频评价' : '试听音频评价'" @click="toggleFeedbackPreview">{{ feedbackPlaying ? 'Ⅱ' : '▶' }}</button>
        <span>语音评价 {{ formatTimer(Math.max(1, Math.round(feedbackDurationMs / 1000))) }}</span>
        <button type="button" @click="deleteFeedbackAudio">删除</button><button type="button" @click="startRecording">重新录制</button>
        <audio ref="feedbackPreview" :src="feedbackAudioUrl" @play="feedbackPlaying = true" @pause="feedbackPlaying = false" @ended="feedbackPlaying = false" />
      </div>
      <p v-if="feedbackError" class="feedback-error">{{ feedbackError }}</p>
    </section>

    <footer class="review-actions">
      <button type="button" class="decision-pass" :class="{ active:decision === 'pass' }" :disabled="saving" @click="decision = 'pass'">通过</button>
      <button type="button" class="decision-retrain" :class="{ active:decision === 'retraining' }" :disabled="saving" @click="decision = 'retraining'">重练</button>
      <button type="button" class="review-submit" :disabled="!canSubmit || saving" @click="submitReview">{{ saving ? '提交中…' : '提交' }}</button>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AudioEvidencePlayer from '@/components/AudioEvidencePlayer.vue'
import { confirmedIssues } from '@/domain/learnerPresentation'
import type { InstructorReviewDetail, InstructorReviewPayload, WordDetail } from '@/api'

type Decision = 'pass' | 'retraining'
type Method = 'stt' | 'audio' | null
type RecognitionAlternative = { transcript?: string; confidence?: number }
type RecognitionResult = { readonly length: number; [index: number]: RecognitionAlternative | undefined; isFinal?: boolean }
type RecognitionEvent = { resultIndex?: number; results: ArrayLike<RecognitionResult> }
type Recognition = { lang: string; continuous: boolean; interimResults: boolean; maxAlternatives?: number; onresult: ((event: RecognitionEvent) => void) | null; onerror: ((event: { error?: string }) => void) | null; onend: (() => void) | null; start(): void; stop(): void; abort(): void }
type RecognitionCtor = new () => Recognition
type SubmitEvent = { payload: InstructorReviewPayload; audioBlob: Blob | null; audioDurationMs: number; hasText: boolean; hasAudio: boolean }

const props = defineProps<{ detail: InstructorReviewDetail; audioSrc: string; audioLoading: boolean; saving: boolean }>()
const emit = defineEmits<{ back: []; 'open-learner': []; 'load-audio': []; submit: [event: SubmitEvent] }>()
const learnerPlayer = ref<InstanceType<typeof AudioEvidencePlayer> | null>(null)
const asrOpen = ref(true), aiOpen = ref(false), decision = ref<Decision>('pass'), method = ref<Method>(null), comment = ref(''), audioError = ref('')
const speechActive = ref(false), speechReady = ref(false), speechSeconds = ref(0), feedbackError = ref('')
const recordingActive = ref(false), recordSeconds = ref(0), feedbackAudioBlob = ref<Blob | null>(null), feedbackAudioUrl = ref(''), feedbackDurationMs = ref(0), feedbackPlaying = ref(false), feedbackPreview = ref<HTMLAudioElement | null>(null)
let recognizer: Recognition | null = null, speechTimer = 0, recordTimer = 0, mediaRecorder: MediaRecorder | null = null, mediaStream: MediaStream | null = null, recordStartedAt = 0, recordingMime = 'audio/webm', chunks: BlobPart[] = []

const attemptLabel = computed(() => props.detail.review_type === 'practice' ? '本次训练' : '考试录音')
const knownDuration = computed(() => Math.max((props.detail.recordings[0]?.duration_ms || 0) / 1000, props.detail.duration_seconds || 0))
const totalScore = computed(() => props.detail.overall_score ?? score(['overall', 'total', 'score']))
const issueCount = computed(() => confirmedIssues(props.detail.ai_issues).length)
const scoredWords = computed(() => props.detail.word_details.filter(word => word.word && word.char_type !== 1 && word.detail_level !== 'sentence'))
const asrDifferenceCount = computed(() => props.detail.alignment.filter(item => item.type !== 'matched').length || fallbackDifferenceCount())
const asrTokens = computed(() => {
  if (props.detail.alignment.length) return props.detail.alignment.filter(item => item.recognized || item.reference).map(item => ({ text: item.recognized || item.reference || '', mismatch: item.type !== 'matched' }))
  const recognized = tokenize(props.detail.recognized_text || '')
  const reference = tokenize(props.detail.reference_text || '')
  return recognized.map((text, index) => ({ text, mismatch: normalize(text) !== normalize(reference[index] || '') }))
})
const canSubmit = computed(() => !speechActive.value && !recordingActive.value && Boolean(comment.value.trim() || feedbackAudioBlob.value))
const commentPlaceholder = computed(() => recordingActive.value ? '正在录制音频评价…' : method.value === 'audio' ? '音频评价可独立使用，无需填写文字点评。' : speechActive.value ? '正在识别教员语音…' : '语音转文字完成后，可在这里查看并编辑点评内容…')

watch(() => props.detail.target_id, () => resetForDetail(), { immediate: true })
function resetForDetail() { stopSpeech(true); stopRecording(true); deleteFeedbackAudio(); asrOpen.value = true; aiOpen.value = false; decision.value = props.detail.review?.required_retraining ? 'retraining' : 'pass'; comment.value = props.detail.review?.correction_advice || props.detail.review?.summary || ''; method.value = comment.value ? 'stt' : null; speechReady.value = Boolean(comment.value); feedbackError.value = ''; audioError.value = '' }
function score(keys: string[]) { for (const key of keys) { const value = props.detail.ai_scores[key]; if (typeof value === 'number') return value } return null }
function normalize(value: string) { return value.toLowerCase().replace(/[^a-z0-9\u3400-\u9fff]/g, '') }
function tokenize(value: string) { return value.trim().split(/\s+/).filter(Boolean) }
function fallbackDifferenceCount() { const left = tokenize(props.detail.reference_text); const right = tokenize(props.detail.recognized_text || ''); return Math.max(left.length, right.length) - left.filter((token, index) => normalize(token) === normalize(right[index] || '')).length }
function wordScore(word: WordDetail) { const values = [word.pronunciation, word.overall, word.expected_tone ? word.tone : undefined].filter((value): value is number => typeof value === 'number'); return values.length ? Math.round(Math.min(...values)) : null }
function wordLevel(word: WordDetail) { const value = wordScore(word); return { normal: value === null || value >= 85, medium: value !== null && value >= 70 && value < 85, low: value !== null && value < 70 } }
async function playWord(milliseconds: number) { await learnerPlayer.value?.seekAndPlay(milliseconds) }
function formatTimer(seconds: number) { const safe = Math.max(0, Math.floor(seconds || 0)); return `${Math.floor(safe / 60).toString().padStart(2, '0')}:${(safe % 60).toString().padStart(2, '0')}` }

function recognitionCtor(): RecognitionCtor | null { if (typeof window === 'undefined') return null; const target = window as Window & { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }; return target.SpeechRecognition || target.webkitSpeechRecognition || null }
function toggleSpeech() { if (speechActive.value) stopSpeech(false); else startSpeech() }
function startSpeech() {
  feedbackError.value = ''; method.value = 'stt'; const Ctor = recognitionCtor()
  if (!Ctor) { feedbackError.value = '当前浏览器不支持语音转文字，请改用键盘输入或录制音频评价。'; return }
  const recognition = new Ctor(); recognizer = recognition; recognition.lang = 'zh-CN'; recognition.continuous = true; recognition.interimResults = true; recognition.maxAlternatives = 3
  const base = comment.value.trim(); let finalText = '', interimText = ''
  recognition.onresult = event => { interimText = ''; for (let i = event.resultIndex ?? 0; i < event.results.length; i++) { const result = event.results[i]; if (!result) continue; const text = bestSpeech(result); if (result.isFinal) finalText = appendSpeech(finalText, text); else interimText = appendSpeech(interimText, text) } const transcript = normalizeTeacherSpeech(`${finalText}${finalText && interimText ? '，' : ''}${interimText}`); comment.value = [base, transcript].filter(Boolean).join(base && transcript ? '\n' : '') }
  recognition.onerror = event => { feedbackError.value = event.error === 'not-allowed' ? '麦克风权限未开启，请允许后重试。' : event.error === 'no-speech' ? '没有检测到清晰语音，请靠近麦克风后重试。' : '语音识别暂时不可用，请使用键盘输入。' }
  recognition.onend = () => { speechActive.value = false; recognizer = null; window.clearInterval(speechTimer); speechReady.value = Boolean(comment.value.trim()) }
  try { recognition.start(); speechActive.value = true; speechReady.value = false; speechSeconds.value = 0; speechTimer = window.setInterval(() => speechSeconds.value += 1, 1000) } catch { feedbackError.value = '语音转文字启动失败，请稍后重试。' }
}
function stopSpeech(silent: boolean) { if (recognizer) { if (silent) recognizer.onend = null; try { silent ? recognizer.abort() : recognizer.stop() } catch {} recognizer = null } window.clearInterval(speechTimer); speechActive.value = false; if (!silent) speechReady.value = Boolean(comment.value.trim()) }
function bestSpeech(result: RecognitionResult) { let best = '', confidence = -1; for (let i = 0; i < Math.max(1, result.length); i++) { const item = result[i], text = item?.transcript?.trim() || '', scoreValue = typeof item?.confidence === 'number' ? item.confidence : 0; if (text && scoreValue >= confidence) { best = text; confidence = scoreValue } } return best }
function appendSpeech(current: string, next: string) { const clean = next.trim(); if (!clean || current.endsWith(clean)) return current; if (clean.startsWith(current)) return clean; return `${current}${current ? '，' : ''}${clean}` }
function normalizeTeacherSpeech(value: string) { const replacements: Record<string, string> = { '停联': '停连', '复讯': '复训', '复信': '复训', '重因': '重音', '与速': '语速', '语宿': '语速' }; let text = value.trim().replace(/\s+/g, '').replace(/[，,]{2,}/g, '，'); for (const [from, to] of Object.entries(replacements)) text = text.split(from).join(to); return text.replace(/^[，。！？]+|[，]+$/g, '') }

function toggleRecording() { if (recordingActive.value) stopRecording(false); else void startRecording() }
async function startRecording() {
  feedbackError.value = ''; method.value = 'audio'
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { feedbackError.value = '当前浏览器不支持录制音频评价。'; return }
  try {
    deleteFeedbackAudio(); mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true }); const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].find(value => MediaRecorder.isTypeSupported(value)) || ''
    mediaRecorder = new MediaRecorder(mediaStream, mime ? { mimeType: mime } : undefined); recordingMime = mediaRecorder.mimeType || mime || 'audio/webm'; chunks = []; mediaRecorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }; mediaRecorder.onstop = finishRecording; mediaRecorder.start(250); recordStartedAt = Date.now(); recordSeconds.value = 0; recordingActive.value = true; recordTimer = window.setInterval(() => recordSeconds.value = Math.max(0, Math.floor((Date.now() - recordStartedAt) / 1000)), 1000)
  } catch { releaseStream(); feedbackError.value = '无法使用麦克风，请检查权限后重试。' }
}
function stopRecording(silent: boolean) { window.clearInterval(recordTimer); recordingActive.value = false; if (mediaRecorder && mediaRecorder.state !== 'inactive') { if (silent) mediaRecorder.onstop = null; try { mediaRecorder.stop() } catch {} } mediaRecorder = null; if (silent) { chunks = []; releaseStream() } }
function finishRecording() { const blob = new Blob(chunks, { type: recordingMime }); feedbackDurationMs.value = Math.max(Date.now() - recordStartedAt, 1000); chunks = []; mediaRecorder = null; releaseStream(); if (!blob.size) { feedbackError.value = '没有录到有效音频，请重新录制。'; return } feedbackAudioBlob.value = blob; feedbackAudioUrl.value = URL.createObjectURL(blob) }
function releaseStream() { mediaStream?.getTracks().forEach(track => track.stop()); mediaStream = null }
async function toggleFeedbackPreview() { if (!feedbackPreview.value) return; if (feedbackPreview.value.paused) { try { await feedbackPreview.value.play() } catch { feedbackError.value = '音频评价暂时无法试听。' } } else feedbackPreview.value.pause() }
function deleteFeedbackAudio() { feedbackPreview.value?.pause(); feedbackPlaying.value = false; if (feedbackAudioUrl.value) URL.revokeObjectURL(feedbackAudioUrl.value); feedbackAudioUrl.value = ''; feedbackAudioBlob.value = null; feedbackDurationMs.value = 0 }
function submitReview() { if (!canSubmit.value || props.saving) return; stopSpeech(true); stopRecording(false); emit('submit', { payload: { completeness_score: score(['completeness']), pronunciation_score: score(['pronunciation']), fluency_score: score(['fluency']), expression_score: score(['expression']), final_score: totalScore.value, evidence: { ai_status: props.detail.ai_status, issue_count: issueCount.value, feedback_mode: feedbackAudioBlob.value && comment.value.trim() ? 'text_and_audio' : feedbackAudioBlob.value ? 'audio' : 'text' }, summary: decision.value === 'retraining' ? '教员复训要求' : '教员评价', correction_advice: comment.value.trim(), required_retraining: decision.value === 'retraining', remediation_due_at: null }, audioBlob: feedbackAudioBlob.value, audioDurationMs: feedbackDurationMs.value, hasText: Boolean(comment.value.trim()), hasAudio: Boolean(feedbackAudioBlob.value) }) }
onBeforeUnmount(() => { stopSpeech(true); stopRecording(true); deleteFeedbackAudio() })
</script>

<style scoped>
.review-workspace{--blue:#1459d1;--ink:#121a29;--muted:#68778c;--line:#d8e2ef;--red:#ee334b;--orange:#ff7f17;position:relative;width:min(100%,390px);min-height:100dvh;margin:auto;padding:24px 16px 118px;color:var(--ink);background:#f6f9fc}.review-heading{position:relative;padding:0 8px 20px}.review-heading>div{display:flex;align-items:center;gap:5px}.review-heading h1{margin:0;font-size:30px;line-height:1.15}.review-heading p{margin:9px 0 0;color:var(--muted);font-size:14px}.review-back{display:none;width:36px;height:36px;border:0;background:transparent;color:var(--blue);font-size:28px}.learner-link{position:absolute;right:8px;top:40px;min-height:32px;border:0;color:var(--blue);background:transparent;font-size:12px;font-weight:700}.inline-alert,.feedback-error{margin:8px 4px 0;color:#c8374c;font-size:12px}.review-accordion{margin-top:16px;border:1px solid var(--line);border-radius:16px;background:#fff;overflow:hidden}.review-accordion__summary{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:58px;padding:11px 15px;border:0;text-align:left;background:#fff}.review-accordion__summary span,.review-accordion__summary strong,.review-accordion__summary small{display:block}.review-accordion__summary strong{font-size:20px}.review-accordion__summary small{margin-top:3px;color:var(--muted);font-size:12px}.review-accordion__summary>b{color:#5c6b7f;font-size:18px}.review-accordion__content{padding:0 15px 15px}.asr-content section+section{margin-top:15px}.asr-content h2{margin:0;color:#7b899d;font-size:12px;font-weight:500}.asr-content p{margin:7px 0 0;color:#5f7088;font-size:14px;line-height:1.28}.asr-content .mismatch{color:var(--red);font-weight:600}.asr-content .asr-note{margin-top:16px;font-size:11px}.asr-tokens{overflow-wrap:anywhere}.asr-tokens span+span::before{content:' '}.ai-content>p{margin:0 0 14px;color:var(--muted);font-size:12px}.word-flow{display:flex;flex-wrap:wrap;gap:15px 17px}.word-flow button{display:grid;gap:3px;min-width:0;padding:0;border:0;text-align:left;background:transparent}.word-flow strong{font-size:14px}.word-flow small{color:#687b96;font-size:10px}.word-flow .medium strong,.word-flow .medium small{color:var(--orange)}.word-flow .low strong,.word-flow .low small{color:var(--red)}.inline-empty{color:var(--muted)!important}
.feedback-card{margin-top:16px;padding:18px 16px 45px;border-radius:26px;background:#fff}.feedback-card header h2{margin:0;font-size:21px}.feedback-card header p{margin:5px 0 0;color:var(--muted);font-size:12px}.feedback-card textarea{display:block;width:100%;min-height:86px;margin-top:12px;padding:13px;border:1px solid var(--line);border-radius:14px;color:#52647d;background:#f9fbfe;resize:vertical;outline:none}.feedback-card textarea:focus{border-color:#86aff0;box-shadow:0 0 0 3px #1459d114}.feedback-methods{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:10px}.feedback-methods button{min-height:38px;border:1px solid #d5e1f0;border-radius:12px;color:#075bd9;background:#fff;font-weight:700}.feedback-methods button.active{background:#fff0f2}.feedback-methods button.recording{border-color:#ffc5cd;background:#ffecef}.feedback-status{display:flex;align-items:center;gap:6px;min-height:54px;margin-top:12px;padding:11px 13px;border-radius:12px;color:#68788e;background:#f1f4f8;font-size:12px}.feedback-status>span{margin-left:auto}.feedback-status--recording{background:#ffedf0}.feedback-status--recording b{width:9px;height:9px;border-radius:50%;background:#68798f;animation:pulse 1.2s infinite}.feedback-audio-ready{background:#e8f3ff}.feedback-audio-ready>button{min-width:26px;min-height:28px;padding:0;border:0;color:#536b88;background:transparent;font-size:11px}.feedback-audio-ready>button:first-child{font-size:15px}.feedback-audio-ready>span{margin:0 auto 0 0}.feedback-audio-ready audio{display:none}
.review-actions{position:fixed;z-index:60;left:50%;bottom:calc(20px + env(safe-area-inset-bottom));display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;width:min(358px,calc(100% - 32px));min-height:72px;padding:15px 8px;border-radius:28px;background:#fff;box-shadow:0 12px 30px #0d1a331c;transform:translateX(-50%)}.review-actions button{min-height:42px;border:0;border-radius:12px;font-weight:700}.decision-pass{color:#10a56a;background:#e6f8f1}.decision-retrain{color:#ff8c24;background:#fff3df}.review-actions .active{box-shadow:inset 0 0 0 2px currentColor}.review-submit{color:#fff;background:#165fdd}.review-submit:disabled{background:#aebbd0;box-shadow:none;cursor:not-allowed}
@keyframes pulse{50%{opacity:.35}}@media(min-width:700px){.review-workspace{width:min(100%,834px);padding-right:32px;padding-left:32px}.review-back{display:grid;place-items:center}.review-heading{padding-left:0}.review-heading>div{margin-left:-12px}.learner-link{right:0}.feedback-card{padding-right:24px;padding-left:24px}.review-actions{width:min(802px,calc(100% - 32px));grid-template-columns:102px 106px 1fr}.review-submit{justify-self:end;width:180px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
