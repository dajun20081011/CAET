<template>
  <main class="app-shell figma-result-detail">
    <MobileDetailHeader title="测评详情" @back="goBack" />
    <PageState v-if="loading" tone="loading" title="正在载入训练证据" />
    <PageState
      v-else-if="errorMessage || !result"
      tone="error"
      title="结果无法读取"
      :message="errorMessage || '该训练结果不存在。'"
      action-label="重试"
      @action="loadResult"
    />

    <template v-else>
      <p class="figma-result-meta">第 {{ result.attempt_no }} 次 · {{ formatDate(result.created_at) }}</p>

      <section class="figma-result-score">
        <span>本次得分</span>
        <strong>{{ result.overall_score ?? '—' }}</strong>
        <small>/100</small>
        <div v-for="entry in visibleScores" :key="entry.key" :class="entry.key">
          <span>{{ entry.label }}</span>
          <strong>{{ entry.value ?? '—' }}</strong>
        </div>
      </section>

      <section class="figma-issue-summary">
        <h2>问题汇总</h2>
        <div>
          <span v-for="item in issueSummary" :key="item.key" :class="item.key" :title="item.hint">
            {{ item.label }} {{ item.count }}
          </span>
        </div>
      </section>

      <section v-if="teacherFeedback" class="figma-teacher-feedback">
        <header><span>评</span><h2>教员评价</h2><small>已评价</small></header>
        <h3>文本评价</h3>
        <p>{{ teacherFeedback.summary || '教员已发布评价' }}<br>{{ teacherFeedback.correction_advice }}</p>
        <button v-if="teacherFeedback.required_retraining" type="button" @click="retrain">再次练习</button>
      </section>

      <AudioEvidencePlayer
        v-if="result.recording_url"
        ref="audioPlayer"
        class="figma-audio-engine"
        title="本次训练录音"
        :src="audioUrl"
        :loading="audioLoading"
        @load="loadAudio"
        @segment-progress="handleSegmentProgress"
        @segment-end="handleSegmentEnd"
      />

      <section ref="wordFlow" class="figma-word-flow" aria-label="逐词分析">
        <p class="figma-word-hint">点击红色或橙色词语，查看发音提示</p>
        <div class="figma-word-tokens">
          <button
            v-for="(word, index) in displayWordDetails"
            :key="`${word.word}-${index}`"
            type="button"
            :class="[wordLevel(word), { selected: selectedWord === word }]"
            :data-word-index="index"
            :aria-label="`${word.word}，${wordScore(word) ?? '暂无'}分，点击查看发音提示`"
          >
            <strong>{{ word.word }}</strong>
            <small>{{ wordScore(word) ?? '—' }}</small>
          </button>
          <p v-if="!displayWordDetails.length">本次供应商未返回逐词数据。</p>
        </div>

        <section
          v-if="selectedWord"
          ref="popover"
          class="figma-word-detail"
          role="dialog"
          aria-modal="false"
          :aria-label="`${selectedLabel} 发音详情`"
          tabindex="-1"
        >
          <header>
            <h2>{{ selectedLabel }}</h2>
            <strong :class="selectedScoreTone">{{ selectedScoreText }}</strong>
            <button type="button" aria-label="关闭单词详情" @click="closeWord">×</button>
          </header>

          <p class="figma-detail-label">你刚刚读成了</p>
          <div class="figma-recognition-result">{{ selectedRecognition }}</div>

          <p class="figma-detail-label">正确读音</p>
          <div class="figma-correct-pronunciation">
            {{ standardLoading ? '正在生成正确读音…' : selectedExpected }}
          </div>

          <p class="figma-detail-label">如何读好</p>
          <ul class="figma-reading-tips">
            <li v-for="tip in readingTips" :key="tip">{{ tip }}</li>
          </ul>

          <div class="figma-current-word-actions">
            <button
              type="button"
              :class="{ active: playingSource === 'standard' }"
              :aria-pressed="playingSource === 'standard'"
              @click="speakStandard"
            >
              {{ standardButtonLabel }}
            </button>
            <button
              type="button"
              :class="{ active: playingSource === 'mine' }"
              :disabled="!result.recording_url"
              :aria-pressed="playingSource === 'mine'"
              @click="playMine"
            >
              {{ mineButtonLabel }}
            </button>
          </div>

          <div v-if="playingSource" class="figma-segment-progress" aria-hidden="true">
            <span :style="{ width: `${Math.round(playbackProgress * 100)}%` }" />
          </div>
          <p class="figma-playback-rule">{{ playbackRule }}</p>
          <p v-if="standardPlaybackError" class="figma-standard-error" role="alert">
            {{ standardPlaybackError }}
          </p>

          <button
            v-if="selectedEligibleForPractice"
            type="button"
            class="figma-add-practice"
            :class="{ added: practiceAdded }"
            disabled
          >
            ✓ 已自动纳入本次训练
          </button>
          <p v-else class="figma-no-practice">本词得分已达标，无需专项训练</p>
          <img class="figma-popover-pointer" :src="popoverPointer" alt="" />
        </section>
      </section>

      <section v-if="targetedPracticeWords.length" class="targeted-practice-entry">
        <header>
          <span>Aa</span>
          <div><h2>专项发音训练</h2><p>针对本次低分词进行逐词跟读纠音</p></div>
        </header>
        <div class="targeted-practice-list">
          <article v-for="word in targetedPracticeWords" :key="targetedPracticeKey(word)">
            <strong>{{ word.word }}</strong>
            <span>{{ wordScore(word) }} · 需练习</span>
          </article>
        </div>
        <p>已自动生成 {{ targetedPracticeWords.length }} 词专项训练</p>
      </section>
      <button v-if="targetedPracticeWords.length" type="button" class="start-targeted-practice" @click="startTargetedPractice">
        开始专项训练
      </button>
      <p v-if="targetedPracticeWords.length" class="targeted-practice-hint">
        进入后逐个单词听标准发音、跟读、查看 AI 反馈并反复纠正。
      </p>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MobileDetailHeader from '@/components/MobileDetailHeader.vue'
import AudioEvidencePlayer from '@/components/AudioEvidencePlayer.vue'
import PageState from '@/components/PageState.vue'
import { cabinlingoApi, type LearnerAttempt, type LearnerIssue, type WordDetail } from '@/api'
import { confirmedIssues, learnerError } from '@/domain/learnerPresentation'
import popoverPointer from '@/assets/pronunciation/popover-pointer.svg'

interface AttemptTeacherFeedback {
  teacher_name?: string
  summary?: string
  correction_advice?: string
  required_retraining?: boolean
}

interface AudioPlayerApi {
  seekAndPlayRange(startMilliseconds: number, endMilliseconds: number): Promise<boolean>
  stop(): void
}

interface SegmentProgress {
  currentMs: number
  durationMs: number
  progress: number
}

interface TargetedPracticeEntry {
  key: string
  attemptId: string
  referenceIndex: number | null
  word: string
  score: number | null
  addedAt: string
}

const TARGETED_PRACTICE_KEY = 'cabinlingo:targeted-practice:v1'
const route = useRoute()
const router = useRouter()
const result = ref<LearnerAttempt | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const audioUrl = ref('')
const audioLoading = ref(false)
const audioPlayer = ref<AudioPlayerApi | null>(null)
const selectedWord = ref<WordDetail | null>(null)
const popover = ref<HTMLElement | null>(null)
const wordFlow = ref<HTMLElement | null>(null)
const referenceText = ref('')
const standardPronunciation = ref('')
const englishIpa = ref('')
const standardLoading = ref(false)
const standardPlaybackLoading = ref(false)
const standardPlaybackError = ref('')
const playingSource = ref<'standard' | 'mine' | null>(null)
const playbackCurrentMs = ref(0)
const playbackDurationMs = ref(0)
const playbackProgress = ref(0)
let pronunciationRequest = 0
let playbackRequest = 0
let standardProgressTimer: number | undefined
let standardAudio: HTMLAudioElement | null = null
let standardAudioUrl = ''

const visibleScores = computed(() => {
  const scores = result.value?.score_summary || {}
  return [
    { key: 'pronunciation', label: '发音', value: scores.pronunciation },
    { key: 'fluency', label: '流利度', value: scores.fluency },
    { key: 'completeness', label: '完整度', value: scores.completeness },
  ]
})

const displayWordDetails = computed(() => (result.value?.word_details || []).filter(word => word.word.trim()))
const targetedPracticeWords = computed(() => displayWordDetails.value.filter(word => {
  const score = wordScore(word)
  return score !== null && score < 90
}))
const issues = computed(() => confirmedIssues(result.value?.issues))
const teacherFeedback = computed<AttemptTeacherFeedback | null>(() => result.value?.teacher_feedback as AttemptTeacherFeedback | null)
const pauseIssueTypes = new Set(['long_pause', 'leading_silence', 'trailing_silence'])
const nonPronunciationIssueTypes = new Set([
  'word_omitted', 'omission', 'word_inserted', 'insertion', 'word_repeated', 'repetition',
  'word_replaced', 'substitution', ...pauseIssueTypes,
])

const issueSummary = computed(() => {
  const pronunciationKeys = new Set<string>()
  for (const word of displayWordDetails.value) {
    const score = wordScore(word)
    if (score !== null && score < 70) pronunciationKeys.add(evidenceKey(word))
  }
  for (const issue of issues.value) {
    if (!nonPronunciationIssueTypes.has(issue.type || '')) pronunciationKeys.add(evidenceKey(issue))
  }
  const explicitPauses = issues.value.filter(issue => pauseIssueTypes.has(issue.type || ''))
  const inferred = explicitPauses.length ? null : inferredPauseSummary()
  const pause = explicitPauses.length || (inferred?.count ?? 0)
  const pauseHint = explicitPauses.length
    ? '来自已确认的停顿诊断'
    : inferred?.available
      ? '当前记录未返回停顿事件；根据逐词时间按 2 秒阈值推算'
      : '当前记录没有可用于停顿诊断的时间证据'
  return [
    { key: 'pronunciation', label: '发音问题', count: pronunciationKeys.size, hint: '逐词得分低于 70 分或已有确认发音问题' },
    { key: 'pause', label: '停顿问题', count: inferred && !inferred.available ? '—' : pause, hint: pauseHint },
    { key: 'normal', label: '其余正常', count: Math.max(displayWordDetails.value.length - pronunciationKeys.size, 0), hint: '逐词得分不低于 70 分' },
  ]
})

const selectedWordScore = computed(() => selectedWord.value ? wordScore(selectedWord.value) : null)
const selectedEligibleForPractice = computed(() => selectedWordScore.value !== null && selectedWordScore.value < 90)
const practiceAdded = computed(() => !!selectedWord.value && isInTargetedPractice(selectedWord.value))
const selectedWordIssues = computed<LearnerIssue[]>(() => !selectedWord.value ? [] : issues.value.filter(issue =>
  (typeof issue.reference_index === 'number' && issue.reference_index === selectedWord.value?.reference_index)
  || (issue.word && normalize(issue.word) === normalize(selectedWord.value?.word || ''))
  || (typeof issue.start_ms === 'number' && issue.start_ms === selectedWord.value?.start_ms),
))
const selectedPrimaryIssue = computed(() => selectedWordIssues.value[0] || null)
const selectedAlignment = computed(() => {
  if (!selectedWord.value) return null
  const index = selectedWord.value.reference_index
  const word = normalize(selectedWord.value.word)
  return (result.value?.alignment || []).find(item =>
    (typeof index === 'number' && item.reference_index === index)
    || (item.reference && normalize(item.reference) === word),
  ) || null
})
const selectedLabel = computed(() => String(
  selectedPrimaryIssue.value?.word
  || selectedAlignment.value?.reference
  || selectedWord.value?.word
  || '',
).trim())
const selectedIsEnglish = computed(() => /[A-Za-z]/.test(selectedLabel.value))
const selectedRecognition = computed(() => {
  const aligned = selectedAlignment.value
  if (typeof aligned?.recognized === 'string' && aligned.recognized.trim()) return aligned.recognized.trim()
  const actual = selectedPrimaryIssue.value?.actual
  if (typeof actual === 'string' && actual.trim()) return actual.trim()
  if (aligned?.type === 'omission') return '（未识别到）'
  return '未返回可定位的识别文本'
})
const selectedExpected = computed(() => {
  const expected = String(selectedPrimaryIssue.value?.expected || selectedLabel.value).trim()
  if (!expected) return '正确读音暂不可用'
  if (selectedIsEnglish.value) return englishIpa.value ? `${expected}   /${englishIpa.value}/` : expected
  return standardPronunciation.value ? `${expected}   ${standardPronunciation.value}` : expected
})
const selectedScoreText = computed(() => {
  const score = selectedWordScore.value
  if (score === null) return '暂无评分'
  return score < 70 ? `${score} · 需改进` : score < 85 ? `${score} · 需注意` : `${score} · 表现良好`
})
const selectedScoreTone = computed(() => ({ low: (selectedWordScore.value ?? 100) < 70, medium: (selectedWordScore.value ?? 100) >= 70 && (selectedWordScore.value ?? 100) < 85 }))

const readingTips = computed(() => {
  if (!selectedWord.value) return []
  if (selectedIsEnglish.value) {
    const tips: string[] = []
    if (englishIpa.value.includes('ˈ')) tips.push('重音放在带 ˈ 的音节，读得更清晰、略长')
    for (const phoneme of lowPhonemes(selectedWord.value)) {
      const guide = ipaGuides.find(([symbol]) => symbol === phoneme)?.[1]
      if (guide) tips.push(guide.replace(/^\/[^/]+\/：/, ''))
      if (tips.length >= 3) break
    }
    if (englishIpa.value.includes('eɪ') && tips.length < 3) tips.push('双元音 /eɪ/ 要完整滑动，不要拆开')
    if (tips.length < 3) tips.push('按音标分音节慢读，再连成完整单词')
    if (tips.length < 3) tips.push('结尾辅音要清楚收尾，不要吞音')
    return tips.slice(0, 3)
  }

  const labelChars = Array.from(selectedLabel.value)
  const actualChars = Array.from(selectedRecognition.value)
  const syllables = standardPronunciation.value.split(/\s+/).filter(Boolean)
  const tips: string[] = []
  const changedIndex = labelChars.findIndex((char, index) => actualChars[index] && actualChars[index] !== char)
  if (changedIndex >= 0) {
    tips.push(`“${labelChars[changedIndex]}”读 ${syllables[changedIndex] || '标准声调'}，不要读成“${actualChars[changedIndex]}”`)
  }
  if (syllables.some(value => /ng[1-5]?$/i.test(value) || /ng$/i.test(removeToneMarks(value)))) tips.push('后鼻音 -ng 要完整收尾')
  if (labelChars.length > 1) tips.push(`逐字确认声调：${labelChars.map((char, index) => `${char} ${syllables[index] || ''}`.trim()).join('、')}`)
  tips.push('词语连读自然，保持每个字清晰，不要吞音')
  return [...new Set(tips)].slice(0, 3)
})

const standardButtonLabel = computed(() => standardPlaybackLoading.value
  ? '正在准备标准音…'
  : playingSource.value === 'standard'
  ? `■ 播放中 ${formatClock(playbackCurrentMs.value)}/${formatClock(playbackDurationMs.value)}`
  : '▶ 标准音 · 当前词')
const mineButtonLabel = computed(() => playingSource.value === 'mine'
  ? `■ 播放中 ${formatClock(playbackCurrentMs.value)}/${formatClock(playbackDurationMs.value)}`
  : '▶ 我的发音 · 当前词')
const playbackRule = computed(() => playingSource.value
  ? `仅播放当前点击的 ${selectedLabel.value}，不会继续播放后续单词`
  : '播放规则：点击后仅播放当前单词 / 词语')

function isChinese(value: string) { return /[\u3400-\u9fff]/.test(value) }
function lowPhonemes(word: WordDetail) {
  return (word.phonemes || [])
    .filter(item => typeof item.pronunciation === 'number' && item.pronunciation < 70)
    .map(item => String(item.phoneme || item.phone || '').trim())
    .filter(Boolean)
}
const ipaGuides: Array<[string, string]> = [
  ['tʃ', '/tʃ/：舌尖抵住上齿龈后迅速放开并送气，像 chair 开头'], ['dʒ', '/dʒ/：口形同 /tʃ/，同时振动声带，像 job 开头'],
  ['θ', '/θ/：舌尖轻触上下齿之间，只送气，不振动声带'], ['ð', '/ð/：舌尖轻触上下齿之间，同时振动声带'],
  ['ʃ', '/ʃ/：双唇略圆，舌面靠近硬腭持续送气'], ['ʒ', '/ʒ/：口形同 /ʃ/，同时振动声带'],
  ['ŋ', '/ŋ/：舌后部抬起贴近软腭，声音从鼻腔送出，不再加 /g/'], ['æ', '/æ/：嘴张大，舌位低而靠前，声音介于“啊”和“哎”之间'],
  ['ɪ', '/ɪ/：短促放松，舌位比 /iː/ 更低，不要读成长音“衣”'], ['i', '/i/：嘴角略向两侧，舌位高而靠前，保持清晰'],
  ['ʌ', '/ʌ/：口腔放松、舌位居中偏低，短促发音'], ['ə', '/ə/：非重读弱元音，口腔放松，轻而短'],
  ['ɝ', '/ɝ/：美式卷舌元音，舌尖后卷但不要接触上腭'], ['ɚ', '/ɚ/：非重读卷舌元音，轻短并保留 /r/ 感'],
  ['ɑ', '/ɑ/：嘴张开，舌位低而靠后，声音饱满'], ['ɔ', '/ɔ/：双唇略圆，舌位靠后，不要读成汉语“哦”'],
  ['ʊ', '/ʊ/：双唇略圆，短促放松，不要拉成长音 /uː/'], ['u', '/u/：双唇收圆，舌位高而靠后，保持音长'],
  ['eɪ', '/eɪ/：从 /e/ 平滑滑向 /ɪ/，不要拆成两个音'], ['aɪ', '/aɪ/：从低元音自然滑向 /ɪ/，重音落在前半段'],
  ['aʊ', '/aʊ/：从张口的 /a/ 滑向圆唇 /ʊ/'], ['oʊ', '/oʊ/：从 /o/ 平滑滑向 /ʊ/，双唇逐渐收圆'],
  ['ɔɪ', '/ɔɪ/：从圆唇 /ɔ/ 滑向 /ɪ/'], ['r', '/r/：舌尖后卷但不接触上腭，保持美式卷舌'],
  ['ɹ', '/ɹ/：舌尖后卷但不接触上腭，保持美式卷舌'], ['l', '/l/：舌尖抵住上齿龈，气流从舌头两侧通过'],
  ['v', '/v/：下唇轻触上齿，持续送气并振动声带'], ['w', '/w/：双唇先收圆，再快速滑向后面的元音'],
]

function removeToneMarks(value: string) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

async function loadStandardPronunciation(word: WordDetail) {
  const request = ++pronunciationRequest
  standardLoading.value = true
  standardPronunciation.value = ''
  englishIpa.value = ''
  try {
    if (isChinese(selectedLabel.value)) {
      const { pinyin } = await import('pinyin-pro')
      const value = pinyin(selectedLabel.value, { toneType: 'symbol', type: 'array', toneSandhi: true, segmentit: 2 }).join(' ')
      if (request !== pronunciationRequest) return
      standardPronunciation.value = value || word.expected_pinyin || word.pinyin || '拼音未识别'
      return
    }
    const { toIPA } = await import('phonemize')
    const ipa = toIPA(selectedLabel.value.toLowerCase(), 'en-US').trim().replace(/^\/+|\/+$/g, '')
    if (request !== pronunciationRequest) return
    englishIpa.value = ipa
  } catch (error) {
    console.error('正确读音生成失败', error)
    if (request !== pronunciationRequest) return
    standardPronunciation.value = isChinese(selectedLabel.value) ? (word.expected_pinyin || word.pinyin || '拼音暂不可用') : ''
  } finally {
    if (request === pronunciationRequest) standardLoading.value = false
  }
}

function normalize(value: string) { return value.toLowerCase().replace(/[^a-z0-9\u3400-\u9fff]/g, '') }
function evidenceKey(value: WordDetail | LearnerIssue) {
  if (typeof value.reference_index === 'number') return `index:${value.reference_index}`
  if (typeof value.start_ms === 'number') return `start:${value.start_ms}`
  return `word:${normalize(String(value.word || ''))}`
}
function inferredPauseSummary() {
  const rows = displayWordDetails.value
    .filter(word => word.detail_level !== 'sentence' && word.char_type !== 1 && Number.isFinite(word.start_ms) && Number.isFinite(word.end_ms) && word.end_ms >= word.start_ms)
    .slice()
    .sort((a, b) => a.start_ms - b.start_ms || a.end_ms - b.end_ms)
  if (rows.length < 2) return { available: false, count: 0 }
  let count = rows[0].start_ms >= 2000 ? 1 : 0
  for (let index = 1; index < rows.length; index += 1) {
    if (rows[index].start_ms - rows[index - 1].end_ms >= 2000) count += 1
  }
  const totalMs = typeof result.value?.duration_seconds === 'number' ? result.value.duration_seconds * 1000 : null
  if (totalMs !== null && totalMs - rows[rows.length - 1].end_ms >= 2500) count += 1
  return { available: true, count }
}
function wordScore(word: WordDetail) {
  const values = [word.pronunciation, word.overall, word.expected_tone ? word.tone : undefined]
    .filter((value): value is number => typeof value === 'number')
  return values.length ? Math.round(Math.min(...values)) : null
}
function wordLevel(word: WordDetail) {
  const score = wordScore(word)
  return { good: score !== null && score >= 85, medium: score !== null && score >= 70 && score < 85, low: score !== null && score < 70 }
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
}
function formatClock(milliseconds: number) {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
function goBack() {
  if (window.history.length > 1) router.back()
  else void router.replace('/student/results')
}

async function loadAudio() {
  if (!result.value?.recording_url || audioLoading.value || audioUrl.value) return
  audioLoading.value = true
  try {
    audioUrl.value = URL.createObjectURL(await cabinlingoApi.protectedAudio(result.value.recording_url))
  } catch {
    errorMessage.value = '录音加载失败或无权访问。'
  } finally {
    audioLoading.value = false
  }
}

async function selectWord(word: WordDetail) {
  stopPlayback()
  standardPlaybackError.value = ''
  selectedWord.value = word
  void loadStandardPronunciation(word)
  await nextTick()
  wordFlow.value?.scrollTo({ top: 0, behavior: 'smooth' })
  window.requestAnimationFrame(() => popover.value?.focus({ preventScroll: true }))
}

function closeWord() {
  stopPlayback()
  standardPlaybackError.value = ''
  pronunciationRequest += 1
  selectedWord.value = null
  standardPronunciation.value = ''
  englishIpa.value = ''
  standardLoading.value = false
}

function handleWordClick(event: MouseEvent) {
  const target = event.target instanceof Element ? event.target.closest<HTMLButtonElement>('[data-word-index]') : null
  if (!target || !wordFlow.value?.contains(target)) return
  const index = Number(target.dataset.wordIndex)
  const word = displayWordDetails.value[index]
  if (word) void selectWord(word)
}

function bindWordClicks() {
  wordFlow.value?.removeEventListener('click', handleWordClick)
  wordFlow.value?.addEventListener('click', handleWordClick)
}

function clearStandardProgressTimer() {
  if (standardProgressTimer !== undefined) window.clearInterval(standardProgressTimer)
  standardProgressTimer = undefined
}

function resetPlaybackProgress() {
  playbackCurrentMs.value = 0
  playbackDurationMs.value = 0
  playbackProgress.value = 0
}

function stopPlayback() {
  playbackRequest += 1
  clearStandardProgressTimer()
  standardPlaybackLoading.value = false
  if (standardAudio) {
    standardAudio.pause()
    standardAudio.currentTime = 0
    standardAudio = null
  }
  if (standardAudioUrl) {
    URL.revokeObjectURL(standardAudioUrl)
    standardAudioUrl = ''
  }
  audioPlayer.value?.stop()
  playingSource.value = null
  resetPlaybackProgress()
}

async function speakStandard() {
  if (!selectedWord.value || !selectedLabel.value || !result.value) return
  if (playingSource.value === 'standard') { stopPlayback(); return }
  const word = selectedWord.value
  const label = selectedLabel.value
  stopPlayback()
  standardPlaybackError.value = ''
  const request = playbackRequest
  standardPlaybackLoading.value = true
  try {
    const blob = await cabinlingoApi.learnerStandardPronunciation({
      attempt_id: result.value.attempt_id,
      text: label,
      reference_index: word.reference_index ?? null,
    })
    if (request !== playbackRequest || selectedWord.value !== word) return
    standardAudioUrl = URL.createObjectURL(blob)
    const player = new Audio(standardAudioUrl)
    standardAudio = player
    player.onloadedmetadata = () => {
      if (request !== playbackRequest || !Number.isFinite(player.duration)) return
      playbackDurationMs.value = player.duration * 1000
    }
    player.ontimeupdate = () => {
      if (request !== playbackRequest || playingSource.value !== 'standard') return
      playbackCurrentMs.value = player.currentTime * 1000
      playbackDurationMs.value = Number.isFinite(player.duration) ? player.duration * 1000 : playbackDurationMs.value
      playbackProgress.value = playbackDurationMs.value ? playbackCurrentMs.value / playbackDurationMs.value : 0
    }
    const finish = () => {
      if (request !== playbackRequest) return
      playingSource.value = null
      resetPlaybackProgress()
    }
    player.onended = finish
    player.onerror = finish
    playingSource.value = 'standard'
    await player.play()
  } catch {
    if (request === playbackRequest && selectedWord.value === word) {
      playingSource.value = null
      resetPlaybackProgress()
      standardPlaybackError.value = '千问标准音暂时无法加载，请刷新页面后重试。'
    }
  } finally {
    if (request === playbackRequest) standardPlaybackLoading.value = false
  }
}

async function playMine() {
  if (!selectedWord.value || !result.value?.recording_url) return
  if (playingSource.value === 'mine') { stopPlayback(); return }
  const word = selectedWord.value
  const issue = selectedPrimaryIssue.value
  stopPlayback()
  if (!audioUrl.value) {
    await loadAudio()
    await nextTick()
  }
  if (selectedWord.value !== word || !audioUrl.value) return
  const start = typeof issue?.start_ms === 'number' ? issue.start_ms : word.start_ms
  const providedEnd = typeof issue?.end_ms === 'number' ? issue.end_ms : word.end_ms
  const end = Math.max(providedEnd, start + 350)
  playingSource.value = 'mine'
  playbackDurationMs.value = end - start
  const played = await audioPlayer.value?.seekAndPlayRange(start, end)
  if (!played) {
    playingSource.value = null
    resetPlaybackProgress()
  }
}

function handleSegmentProgress(payload: SegmentProgress) {
  if (playingSource.value !== 'mine') return
  playbackCurrentMs.value = payload.currentMs
  playbackDurationMs.value = payload.durationMs
  playbackProgress.value = payload.progress
}

function handleSegmentEnd() {
  if (playingSource.value !== 'mine') return
  playingSource.value = null
  resetPlaybackProgress()
}

function targetedPracticeKey(word: WordDetail) {
  return `${result.value?.attempt_id || ''}:${word.reference_index ?? word.start_ms}:${normalize(word.word)}`
}

function readTargetedPractice(): TargetedPracticeEntry[] {
  try {
    const value = JSON.parse(localStorage.getItem(TARGETED_PRACTICE_KEY) || '[]')
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

function isInTargetedPractice(word: WordDetail) {
  const key = targetedPracticeKey(word)
  return readTargetedPractice().some(item => item.key === key)
}

function syncTargetedPractice() {
  if (!result.value) return
  try {
    const currentAttempt = result.value.attempt_id
    const queue = readTargetedPractice().filter(item => item.attemptId !== currentAttempt)
    const entries: TargetedPracticeEntry[] = targetedPracticeWords.value.map(word => ({
      key: targetedPracticeKey(word),
      attemptId: currentAttempt,
      referenceIndex: word.reference_index ?? null,
      word: word.word,
      score: wordScore(word),
      addedAt: new Date().toISOString(),
    }))
    localStorage.setItem(TARGETED_PRACTICE_KEY, JSON.stringify([...queue, ...entries]))
  } catch {
    errorMessage.value = '当前浏览器无法保存专项训练，请关闭无痕模式后重试。'
  }
}

function startTargetedPractice() {
  if (!result.value || !targetedPracticeWords.value.length) return
  void router.push(`/student/results/${result.value.attempt_id}/coach`)
}

function retrain() {
  if (!result.value || !teacherFeedback.value?.required_retraining || !result.value.content_item_id) return
  void router.push({ path: '/student/practice', query: { assignment: result.value.assignment_id, content: result.value.content_item_id, correction: result.value.attempt_id } })
}
function handleKey(event: KeyboardEvent) {
  if (event.key === 'Escape' && selectedWord.value) closeWord()
}
async function loadResult() {
  loading.value = true
  errorMessage.value = ''
  referenceText.value = ''
  try {
    const attempt = await cabinlingoApi.learnerAttempt(String(route.params.attemptId))
    result.value = attempt
    syncTargetedPractice()
    try {
      const workspace = await cabinlingoApi.practiceWorkspace(attempt.assignment_id)
      referenceText.value = workspace.contents.find(item => item.id === attempt.content_item_id)?.reference_text || ''
    } catch {
      // 原文只用于读音辅助，不阻断测评详情。
    }
  } catch (error) {
    errorMessage.value = learnerError(error)
  } finally {
    loading.value = false
    await nextTick()
    bindWordClicks()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKey)
  void loadResult()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKey)
  wordFlow.value?.removeEventListener('click', handleWordClick)
  stopPlayback()
  if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
})
</script>

<style scoped>
.figma-result-detail{width:100%;max-width:390px;min-height:844px;margin:auto;padding:24px 16px 40px;background:#f6f8fb;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}.figma-result-detail>.mobile-detail-header{width:390px;margin-left:-16px}.figma-result-meta{margin:4px 38px 12px;color:#75849b;font-size:11px}.figma-result-score{position:relative;width:358px;height:116px;padding:16px 20px;border-radius:28px;background:#fff}.figma-result-score>span{display:block;color:#75849b;font-size:11px}.figma-result-score>strong{position:absolute;left:20px;top:40px;color:#0e131c;font-size:44px;line-height:48px}.figma-result-score>small{position:absolute;left:78px;top:62px;color:#75849b;font-size:11px}.figma-result-score>div{position:absolute;top:48px}.figma-result-score>div:nth-of-type(1){left:137px}.figma-result-score>div:nth-of-type(2){left:207px}.figma-result-score>div:nth-of-type(3){left:277px}.figma-result-score>div span,.figma-result-score>div strong{display:block}.figma-result-score>div span{color:#75849b;font-size:10px}.figma-result-score>div strong{margin-top:5px;color:#12a364;font-size:23px}.figma-result-score>div.pronunciation strong{color:#f58c14}.figma-issue-summary{width:358px;height:88px;margin-top:12px;padding:14px 22px;border-radius:28px;background:#fff}.figma-issue-summary h2{margin:0 0 12px;color:#0e131c;font-size:16px}.figma-issue-summary>div{display:flex;gap:8px}.figma-issue-summary span{display:grid;place-items:center;height:28px;padding:0 14px;border-radius:14px;color:#1a9e63;background:#e8faf0;font-size:10px}.figma-issue-summary span.pronunciation{color:#fa3434;background:#ffedef}.figma-issue-summary span.pause{color:#f58c14;background:#fff3df}.figma-audio-engine{position:fixed!important;left:-10000px!important;top:-10000px!important;width:1px!important;height:1px!important;overflow:hidden!important}.figma-word-flow{position:relative;width:358px;height:476px;margin-top:0;padding:36px 18px 20px;border-radius:28px;background:#fff;overflow-x:hidden;overflow-y:auto}.figma-word-tokens{display:flex;align-content:flex-start;align-items:flex-start;flex-wrap:wrap;gap:5px 7px;width:322px}.figma-word-tokens button{display:grid;min-width:0;min-height:40px;padding:0;border:0;background:transparent;text-align:left}.figma-word-tokens strong{color:#12141a;font-size:16px;font-weight:400;line-height:21px}.figma-word-tokens small{color:#536781;font-size:9px}.figma-word-tokens button.medium strong{color:#f58c14}.figma-word-tokens button.low strong{color:#f03a3a}.figma-word-tokens>p{color:#75849b;font-size:12px}.figma-word-detail{position:absolute;z-index:3;left:10px;top:38px;width:338px;min-height:418px;padding:12px 15px 11px;border:1px solid #e0e5f0;border-radius:18px;background:#fff;box-shadow:0 6px 18px #0000001a;box-sizing:border-box;overflow:hidden}.figma-word-detail header{display:grid;grid-template-columns:minmax(0,1fr) auto 30px;align-items:center;gap:8px;height:30px}.figma-word-detail h2{min-width:0;margin:0;overflow:hidden;color:#141c2b;font-size:17px;line-height:22px;text-overflow:ellipsis;white-space:nowrap}.figma-word-detail header>strong{color:#1a9e63;font-size:11px;font-weight:600;white-space:nowrap}.figma-word-detail header>strong.low{color:#f53845}.figma-word-detail header>strong.medium{color:#f58c14}.figma-word-detail header>button{display:grid;place-items:center;width:30px;height:30px;padding:0;border:0;border-radius:15px;color:#616e80;background:transparent;font-size:16px}.figma-detail-label{margin:9px 0 6px;color:#616e80;font-size:11px;line-height:14px}.figma-recognition-result{display:flex;align-items:center;height:48px;padding:0 12px;border-radius:12px;color:#f53845;background:#ffedf0;font-size:17px;font-weight:600}.figma-correct-pronunciation{min-height:22px;color:#141c2b;font-size:17px;font-weight:600;line-height:22px}.figma-reading-tips{min-height:60px;margin:0;padding:0;list-style:none;color:#141c2b;font-size:11px;line-height:20px}.figma-reading-tips li::before{content:'• ';font-weight:700}.figma-current-word-actions{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px}.figma-current-word-actions button{height:42px;padding:0 6px;border:1px solid #e0e5f0;border-radius:21px;color:#141c2b;background:#fff;font-size:12px;font-weight:600;white-space:nowrap}.figma-current-word-actions button:first-child{border-color:transparent;color:#1459d1;background:#e5f2ff}.figma-current-word-actions button.active{border-color:transparent;color:#1459d1;background:#e5f2ff}.figma-current-word-actions button:disabled{opacity:.45}.figma-segment-progress{height:4px;margin-top:6px;border-radius:2px;background:#e8eef8;overflow:hidden}.figma-segment-progress span{display:block;height:100%;border-radius:2px;background:#1459d1;transition:width 80ms linear}.figma-playback-rule{margin:7px 0 0;color:#616e80;font-size:11px;line-height:14px}.figma-standard-error{margin:6px 0 0;color:#d92d3a;font-size:11px;line-height:15px}.figma-add-practice{width:100%;height:34px;margin-top:8px;border:0;border-radius:17px;color:#fff;background:#1459d1;font-size:12px;font-weight:500}.figma-add-practice.added{background:#1a9e63}.figma-teacher-feedback{width:358px;margin-top:14px;padding:14px;border:1px solid #dce3ee;border-radius:18px;background:#fff}.figma-teacher-feedback header{display:grid;grid-template-columns:44px 1fr auto;align-items:center;gap:12px}.figma-teacher-feedback header>span{display:grid;place-items:center;width:44px;height:44px;border-radius:12px;color:#fff;background:#246bf3;font-size:20px;font-weight:700}.figma-teacher-feedback h2{margin:0;font-size:18px}.figma-teacher-feedback header small{padding:5px 12px;border-radius:12px;color:#246bf3;background:#edf4ff;font-size:10px}.figma-teacher-feedback h3{margin:22px 4px 8px;font-size:14px}.figma-teacher-feedback>p{margin:0;padding:14px;border-radius:16px;color:#60708a;background:#f5f8fd;font-size:13px;line-height:1.65}.figma-teacher-feedback>button{width:100%;height:52px;margin-top:20px;border-radius:14px;color:#fff;background:#246bf3;font-weight:600}
.figma-word-hint{position:absolute;left:18px;top:12px;margin:0;color:#75849b;font-size:10px;line-height:14px}.figma-word-tokens button{padding-inline:2px;border-radius:7px;cursor:pointer}.figma-word-tokens button:focus-visible,.figma-word-tokens button.selected{outline:2px solid #9dc4ff;outline-offset:2px}
@media(min-width:700px){.figma-result-detail{max-width:834px;min-height:1194px;padding-inline:40px}.figma-result-detail>.mobile-detail-header{width:100%;margin:0}.figma-result-score,.figma-issue-summary,.figma-word-flow,.figma-teacher-feedback{width:100%}.figma-word-flow{height:620px}.figma-word-tokens{width:100%}.figma-word-detail{left:50%;transform:translateX(-50%)}}
.figma-add-practice{color:#1a9e63;background:#e8faf0;font-size:11px;opacity:1}.figma-no-practice{margin:8px 0 0;padding:9px;border-radius:17px;color:#6b788f;background:#f5f7fc;font-size:11px;text-align:center}.figma-popover-pointer{position:absolute;left:30px;bottom:0}.targeted-practice-entry{width:358px;margin-top:16px;padding:22px 20px;border-radius:22px;background:#fff}.targeted-practice-entry>header{display:flex;align-items:center;gap:16px}.targeted-practice-entry>header>span{display:grid;width:52px;height:52px;border-radius:18px;color:#1a6bf5;background:#ebf2ff;font-size:24px;font-weight:600;place-items:center}.targeted-practice-entry h2{margin:0;color:#0d1421;font-size:18px}.targeted-practice-entry header p{margin:6px 0 0;color:#6b788f;font-size:12px}.targeted-practice-list{margin-top:16px}.targeted-practice-list article{display:flex;align-items:center;justify-content:space-between;min-height:46px;border-bottom:1px solid #e5ebf2}.targeted-practice-list article:last-child{border-bottom:0}.targeted-practice-list strong{font-size:14px}.targeted-practice-list span{color:#eb8714;font-size:11px}.targeted-practice-entry>p{margin:20px 0 0;color:#1aa361;font-size:12px}.start-targeted-practice{width:358px;height:54px;margin-top:36px;border-radius:16px;color:#fff;background:#1a6bf5;font-size:14px;font-weight:600}.targeted-practice-hint{width:350px;margin:16px 4px 0;color:#6b788f;font-size:11px;line-height:17px}@media(min-width:700px){.targeted-practice-entry,.start-targeted-practice{width:100%}.targeted-practice-hint{width:100%}}
</style>
