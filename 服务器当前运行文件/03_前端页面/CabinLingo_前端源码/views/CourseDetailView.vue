<template>
  <main class="app-shell course-detail-page">
    <MobileDetailHeader :title="course?.title_zh || '课程详情'" @back="returnToCourses" />
    <PageState v-if="loading" tone="loading" title="正在载入课程" />
    <PageState
      v-else-if="errorMessage || !course"
      tone="error"
      title="课程载入失败"
      :message="errorMessage || '课程不存在或尚未发布。'"
      action-label="返回课程"
      @action="router.replace('/student/courses')"
    />

    <section v-else ref="courseDetailScroll" class="course-detail-scroll" @scroll.passive="scheduleProgressSave">
      <div v-if="course.content_mode === 'video'" class="course-video">
        <video
          v-if="media.videoSrc"
          ref="courseVideo"
          playsinline
          preload="metadata"
          :src="media.videoSrc"
          :controls="videoPlaying"
          @play="videoPlaying = true"
          @loadedmetadata="restoreVideoProgress"
          @timeupdate="scheduleProgressSave"
          @pause="handleVideoPause"
          @ended="handleVideoEnded"
          @error="handleVideoError"
        />
        <span>视频精讲</span>
        <button v-if="!videoPlaying" type="button" :disabled="!media.videoUrl || videoLoading" aria-label="播放课程讲解视频" @click="playVideo">
          <img :src="videoPlayIcon" alt="">
        </button>
        <p>{{ videoLoading ? '正在加载视频…' : mediaErrorMessage || (media.videoUrl ? '点击播放课程讲解视频' : '当前课程暂无视频') }}</p>
      </div>

      <nav class="lecture-tabs" aria-label="精讲语言">
        <button
          v-for="language in languageOptions"
          :key="language"
          type="button"
          :class="{ active: activeLanguage === language }"
          @click="chooseLanguage(language)"
        >{{ language === 'zh' ? '中文精讲' : '英文精讲' }}</button>
      </nav>

      <section class="audio-demo">
        <h2>标准示范</h2>
        <div v-if="activeAudios.length" class="audio-demo__list">
          <article v-for="track in activeAudios" :key="trackKey(track)" class="apple-audio-player">
            <strong>{{ audioTitle(track) }}</strong>
            <small>{{ audioMeta(track) }}</small>
            <div class="audio-scrubber" aria-hidden="true">
              <i><em :style="{ width: `${trackProgress(track)}%` }" /></i>
              <img :src="scrubberThumb" alt="" :style="{ left: `calc(${trackProgress(track)}% - 6px)` }">
            </div>
            <input
              class="audio-seek"
              type="range"
              min="0"
              :max="track.duration || 0"
              step="0.1"
              :value="track.currentTime"
              :disabled="!track.duration"
              :aria-label="`${audioTitle(track)}播放进度`"
              @input="seekAudio(track, $event)"
            >
            <span class="audio-elapsed">{{ formatClock(track.currentTime) }}</span>
            <span class="audio-duration">{{ formatClock(track.duration) }}</span>
            <button class="audio-speed" type="button" :aria-label="`播放速度 ${track.speed} 倍`" @click="cycleSpeed(track)">{{ track.speed }}×</button>
            <button class="audio-skip audio-skip--back" type="button" aria-label="后退十五秒" @click="skipAudio(track, -15)">
              <img :src="audioBack" alt=""><img :src="audioBackArrow" alt=""><b>15</b>
            </button>
            <button class="audio-toggle" type="button" :disabled="track.loading" :aria-label="track.playing ? '暂停' : '播放'" @click="toggleAudio(track)">
              <img :src="track.playing ? audioPause : audioPlay" alt="">
            </button>
            <button class="audio-skip audio-skip--forward" type="button" aria-label="前进十五秒" @click="skipAudio(track, 15)">
              <img :src="audioForward" alt=""><img :src="audioForwardArrow" alt=""><b>15</b>
            </button>
            <button class="audio-more" type="button" aria-label="更多播放选项"><img :src="audioMore" alt=""></button>
            <p v-if="track.loading || track.aligning || track.buffering || track.error" class="audio-status">{{ track.aligning ? '正在精准定位句子…' : track.loading ? '正在准备播放…' : track.buffering ? '正在缓冲…' : track.error }}</p>
            <audio
              :ref="element => setAudioRef(track, element)"
              preload="metadata"
              :src="track.src || undefined"
              @loadedmetadata="restoreAudioProgress(track)"
              @timeupdate="syncAudio(track)"
              @waiting="track.buffering = true"
              @canplay="track.buffering = false"
              @playing="handleAudioPlaying(track)"
              @pause="handleAudioPause(track)"
              @ended="handleAudioEnded(track)"
            />
          </article>
        </div>
        <p v-else class="audio-empty">当前语言暂无标准示范音频。</p>
      </section>

      <section class="pronunciation-tips" :class="{ expanded: mistakesExpanded }">
        <button class="pronunciation-disclosure" type="button" :aria-expanded="mistakesExpanded" @click="mistakesExpanded = !mistakesExpanded">
          <strong>易错词语发音提示</strong>
          <span><img :src="mistakesExpanded ? chevronDown : chevronRight" alt=""></span>
        </button>
        <div v-if="mistakesExpanded" class="pronunciation-card">
          <template v-if="activeMistakes.length">
            <article v-for="(word, index) in activeMistakes" :key="`${word.language}-${word.term}`" class="mistake-word">
              <header>
                <button
                  type="button"
                  class="mistake-word__speech"
                  :class="{ playing: wordSpeechPlayingKey === mistakeSpeechKey(word) }"
                  :disabled="wordSpeechLoadingKey === mistakeSpeechKey(word)"
                  :aria-label="`${word.term}，点击播放标准读音`"
                  @click="playMistakeWord(word)"
                >
                  <strong>{{ word.term }}</strong><span>{{ word.pronunciation }}</span>
                  <i aria-hidden="true">{{ wordSpeechLoadingKey === mistakeSpeechKey(word) ? '…' : wordSpeechPlayingKey === mistakeSpeechKey(word) ? '■' : '▶' }}</i>
                </button>
              </header>
              <div><b class="standard">标准</b><p>{{ standardGuidance(word) }}</p></div>
              <div><b class="mistake">易错</b><p>{{ word.common_mistake || '暂无特别易错提示' }}</p></div>
              <i v-if="index < activeMistakes.length - 1" aria-hidden="true" />
            </article>
          </template>
          <p v-else class="mistake-empty">当前语言没有单独标注的易错词。</p>
          <p v-if="wordSpeechError" class="speech-error" role="alert">{{ wordSpeechError }}</p>
        </div>
      </section>

      <section class="expression-annotation">
        <h2>广播表达标注</h2>
        <div class="annotation-copy">
          <template v-for="(part, partIndex) in annotationDocument.parts" :key="partIndex">
            <span
              v-if="part.sentenceIndex !== undefined"
              class="annotation-sentence"
              :class="{ active: part.sentenceIndex === activeSentenceIndex }"
              :aria-current="part.sentenceIndex === activeSentenceIndex ? 'true' : undefined"
              role="button"
              tabindex="0"
              :aria-label="`播放第 ${part.sentenceIndex + 1} 句`"
              @click="playAnnotationSentence(part.sentenceIndex)"
              @keydown.enter.prevent="playAnnotationSentence(part.sentenceIndex)"
              @keydown.space.prevent="playAnnotationSentence(part.sentenceIndex)"
            ><span v-for="(token, tokenIndex) in part.tokens" :key="tokenIndex" :class="{ emphasis: token.emphasis }">{{ token.text }}</span></span>
            <span v-else aria-hidden="true">{{ part.text }}</span>
          </template>
          <p v-if="!annotationDocument.sentences.length">当前语言暂无专业标注原文。</p>
        </div>
      </section>
      <div class="course-detail-bottom" />
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import MobileDetailHeader from '@/components/MobileDetailHeader.vue'
import PageState from '@/components/PageState.vue'
import videoPlayIcon from '@/assets/figma/course-video-play.svg'
import scrubberThumb from '@/assets/figma/course-scrubber-thumb.svg'
import audioBack from '@/assets/figma/course-audio-back.svg'
import audioBackArrow from '@/assets/figma/course-audio-back-arrow.svg'
import audioForward from '@/assets/figma/course-audio-forward.svg'
import audioForwardArrow from '@/assets/figma/course-audio-forward-arrow.svg'
import audioPause from '@/assets/figma/course-audio-pause.svg'
import audioPlay from '@/assets/figma/course-audio-play.svg'
import audioMore from '@/assets/figma/course-audio-more.svg'
import chevronRight from '@/assets/figma/course-chevron-right.svg'
import chevronDown from '@/assets/figma/course-chevron-down.svg'
import { cabinlingoApi, type CourseAudioAlignment, type CourseMistakeWord, type CourseV23Detail } from '@/api'

interface AnnotationToken { text: string; emphasis: boolean }
interface AnnotationSentence { tokens: AnnotationToken[]; weight: number }
interface AnnotationPart { text?: string; tokens?: AnnotationToken[]; sentenceIndex?: number }
interface AnnotationDocument { parts: AnnotationPart[]; sentences: AnnotationSentence[] }
interface LazyAudioTrack {
  fileId: string
  role: string
  label: string
  language: 'zh' | 'en' | 'bilingual'
  url: string
  src: string
  expiresAt: number
  loading: boolean
  buffering: boolean
  playing: boolean
  error: string
  currentTime: number
  duration: number
  speed: number
  resumeAt: number
  aligning: boolean
  alignments: Partial<Record<'zh' | 'en', CourseAudioAlignment>>
  preparing?: Promise<string>
  alignmentPreparing: Partial<Record<'zh' | 'en', Promise<CourseAudioAlignment>>>
}

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const course = ref<CourseV23Detail | null>(null)
const activeLanguage = ref<'zh' | 'en'>('zh')
const mistakesExpanded = ref(false)
const loading = ref(true)
const errorMessage = ref('')
const mediaErrorMessage = ref('')
const media = ref<{ videoUrl: string; videoSrc: string; videoExpiresAt: number; audioTracks: LazyAudioTrack[] }>({ videoUrl: '', videoSrc: '', videoExpiresAt: 0, audioTracks: [] })
const courseVideo = ref<HTMLVideoElement | null>(null)
const courseDetailScroll = ref<HTMLElement | null>(null)
const videoPlaying = ref(false)
const videoLoading = ref(false)
const audioPlayers = new Map<string, HTMLAudioElement>()
const unlockingAudioPlayers = new WeakSet<HTMLAudioElement>()
const highlightedTrackKey = ref('')
const silentUnlockAudio = 'data:audio/wav;base64,UklGRkQDAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YSADAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=='
const wordSpeechLoadingKey = ref('')
const wordSpeechPlayingKey = ref('')
const wordSpeechError = ref('')
const wordSpeechCache = new Map<string, Blob>()
let wordSpeechAudio: HTMLAudioElement | null = null
let wordSpeechUrl = ''
let wordSpeechGeneration = 0
let annotationSegment: { trackKey: string; sentenceIndex: number; endSeconds: number } | null = null
let annotationGuardTimer: number | undefined
let annotationGeneration = 0
let mediaGeneration = 0
let progressSaveTimer: number | undefined
let pendingVideoTime = 0
let pendingScrollTop = 0

interface SavedCourseProgress {
  activeLanguage?: 'zh' | 'en'
  audio?: Record<string, { currentTime: number; speed: number }>
  videoTime?: number
  scrollTop?: number
  updatedAt?: number
}

const languageOptions = computed<Array<'zh' | 'en'>>(() => !course.value ? [] : course.value.language === 'bilingual' ? ['zh', 'en'] : [course.value.language])
const activeMistakes = computed(() => course.value?.mistake_words.filter(item => item.language === activeLanguage.value) || [])
const annotationDocument = computed(() => parseAnnotation(course.value?.annotated_scripts[activeLanguage.value] || ''))
const activeSentenceIndex = computed(() => {
  if (!highlightedTrackKey.value || !annotationDocument.value.sentences.length) return -1
  const track = media.value.audioTracks.find(item => trackKey(item) === highlightedTrackKey.value)
  if (!track || !track.duration) return -1
  const precise = track.alignments[activeLanguage.value]
  if (precise?.status === 'ready' && precise.sentences.length === annotationDocument.value.sentences.length) {
    const positionMs = track.currentTime * 1000
    const match = precise.sentences.find(item => positionMs >= item.start_ms && positionMs < item.end_ms)
    return match?.index ?? -1
  }
  const weights = annotationDocument.value.sentences.map(sentence => sentence.weight)
  const totalWeight = weights.reduce((sum, value) => sum + value, 0)
  if (!totalWeight) return -1
  const position = Math.min(1, Math.max(0, track.currentTime / track.duration)) * totalWeight
  let boundary = 0
  for (let index = 0; index < weights.length; index += 1) {
    boundary += weights[index]
    if (position < boundary || index === weights.length - 1) return index
  }
  return -1
})
const activeAudios = computed(() => {
  const rows = media.value.audioTracks
  const matched = rows.filter(track => track.language === activeLanguage.value || track.language === 'bilingual')
  if (matched.length) return matched
  const wanted = activeLanguage.value === 'zh' ? /(中文|zh|chinese)/i : /(英文|en|english)/i
  return rows.filter(track => wanted.test(`${track.role} ${track.label}`) || track.role === 'audio')
})

function trackKey(track: LazyAudioTrack) { return `${track.role}-${track.url}` }
function progressKey(courseVersionId: string) { return `cabinlingo.course-progress.v1:${session.user?.id || 'learner'}:${courseVersionId}` }
function readProgress(courseVersionId: string): SavedCourseProgress {
  try {
    const value = JSON.parse(localStorage.getItem(progressKey(courseVersionId)) || '{}')
    return value && typeof value === 'object' ? value : {}
  } catch {
    return {}
  }
}
function saveProgressNow() {
  if (!course.value) return
  if (progressSaveTimer !== undefined) window.clearTimeout(progressSaveTimer)
  progressSaveTimer = undefined
  const audio = Object.fromEntries(media.value.audioTracks.map(track => [trackKey(track), {
    currentTime: Math.max(0, track.currentTime),
    speed: track.speed,
  }]))
  const value: SavedCourseProgress = {
    activeLanguage: activeLanguage.value,
    audio,
    videoTime: Math.max(0, pendingVideoTime || courseVideo.value?.currentTime || 0),
    scrollTop: Math.max(0, courseDetailScroll.value?.scrollTop ?? pendingScrollTop),
    updatedAt: Date.now(),
  }
  try { localStorage.setItem(progressKey(course.value.course_version_id), JSON.stringify(value)) } catch { /* Browser storage can be disabled. */ }
}
function scheduleProgressSave() {
  if (progressSaveTimer !== undefined) return
  progressSaveTimer = window.setTimeout(saveProgressNow, 700)
}
function returnToCourses() {
  saveProgressNow()
  void router.push({ path: '/student/courses', query: { kind: course.value?.course_kind || 'lesson' } })
}
function fileIdFromMediaUrl(url: string) { return url.split('/').filter(Boolean).at(-1) || '' }
function setAudioRef(track: LazyAudioTrack, element: unknown) {
  if (element instanceof HTMLAudioElement) audioPlayers.set(trackKey(track), element)
  else audioPlayers.delete(trackKey(track))
}
function playerFor(track: LazyAudioTrack) { return audioPlayers.get(trackKey(track)) || null }
function formatClock(seconds: number) {
  const safe = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0
  return `${Math.floor(safe / 60).toString().padStart(2, '0')}:${(safe % 60).toString().padStart(2, '0')}`
}
function trackProgress(track: LazyAudioTrack) { return track.duration > 0 ? Math.min(100, track.currentTime / track.duration * 100) : 0 }
function audioTitle(track: LazyAudioTrack) {
  if (track.label && !/完整示范音频/.test(track.label)) return track.label
  return activeLanguage.value === 'zh' ? '中文标准示范' : 'English Standard Demo'
}
function audioMeta(track: LazyAudioTrack) {
  const suffix = /女|female/i.test(track.label) ? (activeLanguage.value === 'zh' ? '女声' : 'Female') : /男|male/i.test(track.label) ? (activeLanguage.value === 'zh' ? '男声' : 'Male') : ''
  return [activeLanguage.value === 'zh' ? '标准示范' : 'Standard demo', suffix].filter(Boolean).join(' · ')
}
function pauseAllAudio(except?: LazyAudioTrack) {
  media.value.audioTracks.forEach((track) => {
    if (track === except) return
    playerFor(track)?.pause()
    track.playing = false
  })
}
function mistakeSpeechKey(word: CourseMistakeWord) { return `${word.language}:${word.term.trim().toLocaleLowerCase()}` }
async function unlockAudioElement(player: HTMLAudioElement, restoreSrc = '') {
  unlockingAudioPlayers.add(player)
  player.src = silentUnlockAudio
  player.load()
  try {
    await player.play()
  } catch {
    // The real playback attempt below reports a visible error if the browser still refuses audio.
  }
  player.pause()
  player.currentTime = 0
  if (restoreSrc) {
    player.src = restoreSrc
    player.load()
  } else {
    player.removeAttribute('src')
    player.load()
  }
  window.setTimeout(() => unlockingAudioPlayers.delete(player), 0)
}
function stopWordSpeech(invalidate = true) {
  if (invalidate) wordSpeechGeneration += 1
  if (wordSpeechAudio) {
    wordSpeechAudio.pause()
    wordSpeechAudio = null
  }
  if (wordSpeechUrl) {
    URL.revokeObjectURL(wordSpeechUrl)
    wordSpeechUrl = ''
  }
  wordSpeechLoadingKey.value = ''
  wordSpeechPlayingKey.value = ''
}
async function playMistakeWord(word: CourseMistakeWord) {
  const key = mistakeSpeechKey(word)
  if (wordSpeechPlayingKey.value === key) {
    stopWordSpeech()
    return
  }
  stopWordSpeech()
  stopAnnotationSegment()
  pauseAllAudio()
  wordSpeechError.value = ''
  wordSpeechLoadingKey.value = key
  const request = wordSpeechGeneration
  const player = new Audio()
  wordSpeechAudio = player
  const unlocked = unlockAudioElement(player)
  try {
    await unlocked
    let blob = wordSpeechCache.get(key)
    if (!blob) {
      if (!course.value) return
      blob = await cabinlingoApi.learnerCoursePronunciation(course.value.course_version_id, { text: word.term, language: word.language })
      wordSpeechCache.set(key, blob)
    }
    if (request !== wordSpeechGeneration || wordSpeechAudio !== player) return
    wordSpeechUrl = URL.createObjectURL(blob)
    player.src = wordSpeechUrl
    player.load()
    player.onended = () => { if (wordSpeechAudio === player) stopWordSpeech(false) }
    player.onerror = () => {
      if (wordSpeechAudio !== player) return
      stopWordSpeech(false)
      wordSpeechError.value = '标准读音暂时无法播放，请稍后重试。'
    }
    await player.play()
    if (request === wordSpeechGeneration) wordSpeechPlayingKey.value = key
  } catch {
    if (request === wordSpeechGeneration) wordSpeechError.value = '标准读音暂时无法生成，请稍后重试。'
    stopWordSpeech(false)
  } finally {
    if (request === wordSpeechGeneration) wordSpeechLoadingKey.value = ''
  }
}
function clearAnnotationGuard() {
  if (annotationGuardTimer !== undefined) window.clearInterval(annotationGuardTimer)
  annotationGuardTimer = undefined
}
function stopAnnotationSegment(pause = true) {
  annotationGeneration += 1
  const segment = annotationSegment
  annotationSegment = null
  clearAnnotationGuard()
  if (!segment) return
  const track = media.value.audioTracks.find(item => trackKey(item) === segment.trackKey)
  if (track) {
    if (pause) playerFor(track)?.pause()
    track.playing = false
  }
  if (highlightedTrackKey.value === segment.trackKey) highlightedTrackKey.value = ''
}
async function ensureTrackAlignment(track: LazyAudioTrack) {
  const language = activeLanguage.value
  const cached = track.alignments[language]
  if (cached?.status === 'ready' && cached.sentences.length === annotationDocument.value.sentences.length) return cached
  if (!course.value || !track.fileId) throw new Error('audio_alignment_unavailable')
  if (!track.alignmentPreparing[language]) {
    track.aligning = true
    track.error = ''
    track.alignmentPreparing[language] = cabinlingoApi.courseV23AudioAlignment(course.value.course_version_id, track.fileId, language)
      .then((alignment) => {
        track.alignments[language] = alignment
        return alignment
      })
      .finally(() => {
        delete track.alignmentPreparing[language]
        track.aligning = Object.keys(track.alignmentPreparing).length > 0
      })
  }
  return track.alignmentPreparing[language]!
}
function alignedSentenceRange(track: LazyAudioTrack, sentenceIndex: number, duration: number) {
  const alignment = track.alignments[activeLanguage.value]
  const timing = alignment?.sentences.find(item => item.index === sentenceIndex)
  if (!timing || timing.end_ms <= timing.start_ms) return null
  return {
    start: Math.max(0, Math.min(duration, timing.start_ms / 1000)),
    end: Math.max(0, Math.min(duration, timing.end_ms / 1000)),
  }
}
async function waitForMetadata(player: HTMLAudioElement) {
  if (Number.isFinite(player.duration) && player.duration > 0) return
  await new Promise<void>((resolve) => {
    const done = () => {
      player.removeEventListener('loadedmetadata', done)
      player.removeEventListener('error', done)
      resolve()
    }
    player.addEventListener('loadedmetadata', done, { once: true })
    player.addEventListener('error', done, { once: true })
    player.load()
    window.setTimeout(done, 4000)
  })
}
async function playAnnotationSentence(sentenceIndex: number) {
  const track = activeAudios.value[0]
  if (!track) {
    mediaErrorMessage.value = '当前语言暂无可用于逐句朗读的标准音频。'
    return
  }
  if (annotationSegment?.sentenceIndex === sentenceIndex && annotationSegment.trackKey === trackKey(track)) {
    stopAnnotationSegment()
    return
  }
  stopWordSpeech()
  stopAnnotationSegment()
  const request = annotationGeneration
  pauseAllAudio(track)
  track.buffering = true
  const initialPlayer = playerFor(track)
  const unlocked = initialPlayer ? unlockAudioElement(initialPlayer, track.src) : Promise.resolve()
  await unlocked
  if (request !== annotationGeneration) return
  let src = ''
  try {
    ;[src] = await Promise.all([ensureAudio(track), ensureTrackAlignment(track)])
  } catch {
    if (request === annotationGeneration) {
      track.buffering = false
      track.error = '该句暂时无法完成精准定位，请稍后重试'
    }
    return
  }
  if (request !== annotationGeneration) return
  if (!src) {
    track.buffering = false
    return
  }
  await nextTick()
  const player = playerFor(track)
  if (!player) return
  await waitForMetadata(player)
  if (request !== annotationGeneration) return
  if (!Number.isFinite(player.duration) || player.duration <= 0) {
    track.buffering = false
    track.error = '标准示范时长读取失败'
    return
  }
  const range = alignedSentenceRange(track, sentenceIndex, player.duration)
  if (!range) {
    track.buffering = false
    track.error = '该句缺少有效的精准时间轴'
    return
  }
  annotationSegment = { trackKey: trackKey(track), sentenceIndex, endSeconds: range.end }
  highlightedTrackKey.value = trackKey(track)
  player.playbackRate = track.speed
  player.currentTime = range.start
  syncAudio(track)
  try {
    await player.play()
    annotationGuardTimer = window.setInterval(() => {
      if (!annotationSegment || annotationSegment.trackKey !== trackKey(track)) return
      if (player.currentTime + 0.01 >= annotationSegment.endSeconds) stopAnnotationSegment()
    }, 25)
  } catch {
    stopAnnotationSegment(false)
    track.buffering = false
    track.error = '当前句暂时无法播放'
  }
}
function chooseLanguage(language: 'zh' | 'en') {
  if (language === activeLanguage.value) return
  pauseAllAudio()
  stopAnnotationSegment()
  stopWordSpeech()
  wordSpeechError.value = ''
  highlightedTrackKey.value = ''
  activeLanguage.value = language
  mistakesExpanded.value = false
  mediaErrorMessage.value = ''
}
function syncAudio(track: LazyAudioTrack) {
  const player = playerFor(track)
  if (!player || unlockingAudioPlayers.has(player) || track.resumeAt > 0) return
  track.currentTime = Number.isFinite(player.currentTime) ? player.currentTime : 0
  track.duration = Number.isFinite(player.duration) ? player.duration : 0
  if (annotationSegment?.trackKey === trackKey(track) && player.currentTime + 0.01 >= annotationSegment.endSeconds) stopAnnotationSegment()
  scheduleProgressSave()
}
function startAudioHighlight(track: LazyAudioTrack) {
  track.playing = true
  track.buffering = false
  highlightedTrackKey.value = trackKey(track)
  syncAudio(track)
}
function handleAudioPlaying(track: LazyAudioTrack) {
  const player = playerFor(track)
  if (!player || unlockingAudioPlayers.has(player)) return
  startAudioHighlight(track)
}
function handleAudioPause(track: LazyAudioTrack) {
  const player = playerFor(track)
  if (player && unlockingAudioPlayers.has(player)) return
  track.playing = false
  track.buffering = false
  saveProgressNow()
}
function handleAudioEnded(track: LazyAudioTrack) {
  const player = playerFor(track)
  if (player && unlockingAudioPlayers.has(player)) return
  finishAudio(track)
}
function finishAudio(track: LazyAudioTrack) {
  if (annotationSegment?.trackKey === trackKey(track)) stopAnnotationSegment(false)
  track.playing = false
  track.buffering = false
  track.currentTime = 0
  if (highlightedTrackKey.value === trackKey(track)) highlightedTrackKey.value = ''
  saveProgressNow()
}
function restoreAudioProgress(track: LazyAudioTrack) {
  const player = playerFor(track)
  if (!player || unlockingAudioPlayers.has(player)) return
  if (track.resumeAt > 0 && Number.isFinite(player.duration) && player.duration > 0) {
    player.currentTime = Math.min(track.resumeAt, Math.max(0, player.duration - 0.25))
    track.resumeAt = 0
  }
  syncAudio(track)
}
async function ensureAudio(track: LazyAudioTrack) {
  if (track.src && track.expiresAt - Date.now() > 60_000) return track.src
  track.loading = true
  track.error = ''
  const generation = mediaGeneration
  if (!track.preparing) {
    track.preparing = (async () => {
      const playback = await cabinlingoApi.courseV23MediaPlayback(track.url)
      if (generation !== mediaGeneration) return ''
      track.resumeAt = track.currentTime
      track.src = playback.url
      track.expiresAt = playback.expiresAt
      return track.src
    })()
  }
  try {
    return await track.preparing
  } catch {
    track.error = '标准示范暂时无法载入'
    return ''
  } finally {
    track.preparing = undefined
    track.loading = false
  }
}
async function toggleAudio(track: LazyAudioTrack) {
  let player = playerFor(track)
  if (player && !player.paused) {
    stopAnnotationSegment()
    player.pause()
    return
  }
  stopWordSpeech()
  stopAnnotationSegment(false)
  pauseAllAudio(track)
  track.buffering = true
  const src = await ensureAudio(track)
  if (!src) {
    track.buffering = false
    return
  }
  await nextTick()
  player = playerFor(track)
  if (!player) return
  player.playbackRate = track.speed
  try {
    await player.play()
    highlightedTrackKey.value = trackKey(track)
  } catch {
    track.buffering = false
    track.error = '标准示范暂时无法播放'
  }
}
function skipAudio(track: LazyAudioTrack, seconds: number) {
  stopAnnotationSegment(false)
  const player = playerFor(track)
  if (!player) return
  player.currentTime = Math.max(0, Math.min(player.duration || 0, player.currentTime + seconds))
  syncAudio(track)
}
function seekAudio(track: LazyAudioTrack, event: Event) {
  stopAnnotationSegment(false)
  const player = playerFor(track)
  const value = Number((event.target as HTMLInputElement).value)
  if (!player || !Number.isFinite(value)) return
  player.currentTime = value
  syncAudio(track)
  scheduleProgressSave()
}
function cycleSpeed(track: LazyAudioTrack) {
  const speeds = [1, 0.75, 1.25]
  track.speed = speeds[(speeds.indexOf(track.speed) + 1) % speeds.length]
  const player = playerFor(track)
  if (player) player.playbackRate = track.speed
  saveProgressNow()
}
function clearMedia() {
  saveProgressNow()
  stopAnnotationSegment()
  stopWordSpeech()
  pauseAllAudio()
  audioPlayers.clear()
  mediaGeneration += 1
  highlightedTrackKey.value = ''
  media.value = { videoUrl: '', videoSrc: '', videoExpiresAt: 0, audioTracks: [] }
  videoLoading.value = false
  videoPlaying.value = false
}
function restoreVideoProgress() {
  const player = courseVideo.value
  if (!player || pendingVideoTime <= 0 || !Number.isFinite(player.duration) || player.duration <= 0) return
  player.currentTime = Math.min(pendingVideoTime, Math.max(0, player.duration - 0.25))
  pendingVideoTime = 0
}
function handleVideoPause() {
  videoPlaying.value = false
  saveProgressNow()
}
function handleVideoEnded() {
  videoPlaying.value = false
  pendingVideoTime = 0
  saveProgressNow()
}
async function playVideo() {
  if (!media.value.videoUrl || videoLoading.value) return
  if (!media.value.videoSrc || media.value.videoExpiresAt - Date.now() < 60_000) {
    videoLoading.value = true
    mediaErrorMessage.value = ''
    const generation = mediaGeneration
    try {
      const playback = course.value?.cos_video_key
        ? await cabinlingoApi.learnerCourseV23VideoPlayback(course.value.course_version_id)
        : await cabinlingoApi.courseV23MediaPlayback(media.value.videoUrl)
      if (generation !== mediaGeneration) return
      media.value.videoSrc = playback.url
      media.value.videoExpiresAt = playback.expiresAt
      await nextTick()
    } catch {
      mediaErrorMessage.value = '课程视频暂时无法载入'
    } finally {
      videoLoading.value = false
    }
  }
  try {
    await courseVideo.value?.play()
  } catch {
    mediaErrorMessage.value = '课程视频暂时无法播放'
  }
}
function handleVideoError() {
  videoPlaying.value = false
  media.value.videoSrc = ''
  media.value.videoExpiresAt = 0
  mediaErrorMessage.value = '课程视频加载失败，点击播放按钮重试'
}
function standardGuidance(word: CourseMistakeWord) {
  return [word.pronunciation, word.tip].filter(Boolean).join('；') || '请按标准读音完整连贯地朗读。'
}
function parseAnnotation(source: string): AnnotationDocument {
  const clean = source
    .replace(/\r\n?/g, '\n')
    .replace(/\[[^\]\n]+\][ \t]*/g, '')
    .replace(/[↘↗↙↖↓↑→←⌒‿]+/g, '')
  const parts: AnnotationPart[] = []
  const sentences: AnnotationSentence[] = []
  if (!clean.trim()) return { parts, sentences }

  const appendSentence = (text: string) => {
    if (!text.trim()) {
      if (text) parts.push({ text })
      return
    }
    const sentenceIndex = sentences.length
    const sentence = { tokens: tokenizeAnnotation(text), weight: annotationWeight(text) }
    sentences.push(sentence)
    parts.push({ tokens: sentence.tokens, sentenceIndex })
  }

  // Pauses still define clickable audio ranges, but never create visual paragraphs.
  // Newlines and blank lines are emitted untouched so the learner sees the exact
  // paragraph structure entered in the admin textarea.
  clean.split(/(\n+)/).forEach((line) => {
    if (/^\n+$/.test(line)) {
      parts.push({ text: line })
      return
    }
    let cursor = 0
    for (const match of line.matchAll(/\/{2,3}/g)) {
      const end = (match.index || 0) + match[0].length
      appendSentence(line.slice(cursor, end))
      cursor = end
    }
    appendSentence(line.slice(cursor))
  })
  return { parts, sentences }
}
function annotationWeight(value: string) {
  const spoken = value.replace(/[【】＿_]/g, '').replace(/\/{1,3}/g, ' ').trim()
  const cjk = (spoken.match(/[\u3400-\u9fff]/g) || []).length
  const words = (spoken.match(/[A-Za-z]+(?:['’-][A-Za-z]+)*/g) || []).length
  const other = spoken.replace(/[\u3400-\u9fffA-Za-z\s，。；：！？,.;:!?/]/g, '').length
  const pause = value.endsWith('///') ? 5 : value.endsWith('//') ? 3 : 0
  return Math.max(1, cjk + words * 1.7 + other * 0.5 + pause)
}
function tokenizeAnnotation(paragraph: string): AnnotationToken[] {
  const tokens: AnnotationToken[] = []
  let plain = ''
  const flush = () => {
    if (plain) tokens.push({ text: plain, emphasis: false })
    plain = ''
  }
  for (let index = 0; index < paragraph.length;) {
    if (paragraph[index] === '【') {
      const end = paragraph.indexOf('】', index + 1)
      if (end > index) {
        flush()
        tokens.push({ text: paragraph.slice(index + 1, end), emphasis: true })
        index = end + 1
        continue
      }
    }
    if (paragraph[index] === '＿' || paragraph[index] === '_') {
      flush()
      while (paragraph[index] === '＿' || paragraph[index] === '_') index += 1
      let end = index
      while (end < paragraph.length && !/[\/，。；：！？,.;:!?\n]/.test(paragraph[end])) end += 1
      const emphasized = paragraph.slice(index, end).trimEnd()
      if (emphasized) tokens.push({ text: emphasized, emphasis: true })
      index += emphasized.length
      continue
    }
    plain += paragraph[index]
    index += 1
  }
  flush()
  return tokens
}
async function loadCourse() {
  loading.value = true
  errorMessage.value = ''
  mediaErrorMessage.value = ''
  clearMedia()
  try {
    course.value = await cabinlingoApi.learnerCourseV23(String(route.params.courseId))
  } catch {
    course.value = null
    errorMessage.value = '课程不存在、尚未发布，或当前账号没有访问权限。'
    loading.value = false
    return
  }
  const savedProgress = readProgress(course.value.course_version_id)
  const defaultLanguage = course.value.language === 'en' ? 'en' : 'zh'
  activeLanguage.value = languageOptions.value.includes(savedProgress.activeLanguage || defaultLanguage) ? (savedProgress.activeLanguage || defaultLanguage) : defaultLanguage
  pendingVideoTime = Number.isFinite(savedProgress.videoTime) ? Math.max(0, Number(savedProgress.videoTime)) : 0
  pendingScrollTop = Number.isFinite(savedProgress.scrollTop) ? Math.max(0, Number(savedProgress.scrollTop)) : 0
  const tracks = course.value.audio_tracks?.length
    ? course.value.audio_tracks
    : course.value.audio_url
      ? [{ file_id: fileIdFromMediaUrl(course.value.audio_url), role: 'audio', label: '完整示范音频', language: 'bilingual' as const, filename: course.value.audio_filename || '', url: course.value.audio_url, alignment: {} }]
      : []
  media.value = {
    videoUrl: course.value.cos_video_key ? `cos:${course.value.cos_video_key}` : course.value.video_url || '',
    videoSrc: '',
    videoExpiresAt: 0,
    audioTracks: tracks.map(track => {
      const savedTrack = savedProgress.audio?.[`${track.role}-${track.url}`]
      const resumeAt = Number.isFinite(savedTrack?.currentTime) ? Math.max(0, Number(savedTrack?.currentTime)) : 0
      return ({
      fileId: track.file_id || fileIdFromMediaUrl(track.url),
      role: track.role,
      label: track.label,
      language: track.language,
      url: track.url,
      src: '',
      expiresAt: 0,
      loading: false,
      buffering: false,
      playing: false,
      error: '',
      currentTime: resumeAt,
      duration: 0,
      speed: [0.75, 1, 1.25].includes(Number(savedTrack?.speed)) ? Number(savedTrack?.speed) : 1,
      resumeAt,
      aligning: false,
      alignments: { ...(track.alignment || {}) },
      alignmentPreparing: {},
    })}),
  }
  loading.value = false
  await nextTick()
  if (courseDetailScroll.value && pendingScrollTop > 0) courseDetailScroll.value.scrollTop = pendingScrollTop
  pendingScrollTop = 0
}

onMounted(() => {
  window.addEventListener('pagehide', saveProgressNow)
  void loadCourse()
})
onBeforeUnmount(() => {
  window.removeEventListener('pagehide', saveProgressNow)
  clearMedia()
})
</script>

<style scoped>
.course-detail-page{position:relative;width:100%;max-width:390px;height:100dvh;min-height:720px;margin:auto;padding-top:28px;border-radius:44px;background:#eef4fe;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;overflow:hidden}.course-detail-page>.mobile-detail-header{position:absolute;left:0;top:28px;z-index:3}.course-detail-page>:deep(.page-state){position:absolute;left:16px;right:16px;top:110px}.course-detail-scroll{position:absolute;left:8px;right:8px;top:105px;bottom:15px;overflow-x:hidden;overflow-y:auto;display:flex;flex-direction:column;gap:16px;padding-bottom:8px;overscroll-behavior:contain;scrollbar-width:none}.course-detail-scroll::-webkit-scrollbar{display:none}.course-video{position:relative;flex:none;width:100%;height:188px;border-radius:18px;background:#141c2b;overflow:hidden}.course-video video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#141c2b}.course-video>span{position:absolute;left:16px;top:14px;color:#ccd6eb;font-size:12px;line-height:16px}.course-video>button{position:absolute;left:50%;top:67px;display:grid;place-items:center;width:54px;height:54px;min-height:54px;transform:translateX(-50%);border-radius:50%;background:#1a6bf5}.course-video>button img{width:18px;height:18px;max-width:none}.course-video>p{position:absolute;left:50%;top:145px;width:240px;margin:0;transform:translateX(-50%);color:#ccd6eb;font-size:12px;line-height:16px;text-align:center}.lecture-tabs{display:grid;grid-template-columns:repeat(auto-fit,minmax(0,1fr));gap:8px;flex:none;width:100%;height:46px;padding:3px 0}.lecture-tabs button{height:40px;min-height:40px;border-radius:12px;color:#636e80;background:#f5f7fc;font-size:14px;font-weight:600}.lecture-tabs button.active{color:#0d59d6;background:#e8f2ff}.audio-demo{flex:none;width:100%}.audio-demo h2,.expression-annotation h2{height:24px;margin:0 0 6px 16px;color:#0f141f;font-size:16px;line-height:22px}.audio-demo__list{display:grid;gap:12px;padding:0 8px}.apple-audio-player{position:relative;height:132px;border:1px solid rgba(224,229,240,.9);border-radius:18px;background:#fff;overflow:hidden}.apple-audio-player>strong{position:absolute;left:15px;top:12px;color:#171f2e;font-size:15px;line-height:18px}.apple-audio-player>small{position:absolute;left:15px;top:35px;color:#6b788f;font-size:11px;line-height:13px}.audio-scrubber{position:absolute;left:15px;right:15px;top:55px;height:12px}.audio-scrubber i{position:absolute;left:0;right:0;top:4px;height:4px;border-radius:2px;background:#e0e5f0;overflow:hidden}.audio-scrubber em{display:block;height:100%;border-radius:2px;background:#0a7aff}.audio-scrubber img{position:absolute;top:0;width:12px;height:12px;max-width:none}.audio-seek{position:absolute;left:15px;right:15px;top:51px;width:calc(100% - 30px);height:20px;margin:0;opacity:0;cursor:pointer}.audio-elapsed,.audio-duration{position:absolute;top:68px;color:#6b788f;font-size:10px;line-height:12px}.audio-elapsed{left:15px}.audio-duration{right:28px}.audio-speed,.audio-more{position:absolute;top:89px;height:28px;min-height:28px;border-radius:14px;background:#f0f2f7}.audio-speed{left:15px;width:44px;color:#171f2e;font-size:11px;font-weight:600}.audio-more{right:15px;display:grid;place-items:center;width:32px}.audio-more img{width:20px;height:20px;max-width:none}.audio-toggle{position:absolute;left:50%;top:83px;display:grid;place-items:center;width:40px;height:40px;min-height:40px;transform:translateX(-50%);border-radius:50%;background:#0a7aff}.audio-toggle img{width:22px;height:22px;max-width:none}.audio-skip{position:absolute;top:93px;width:22px;height:22px;min-height:22px;padding:0;background:transparent}.audio-skip--back{left:25%}.audio-skip--forward{right:25%}.audio-skip img:first-child{position:absolute;inset:0;width:22px;height:22px;max-width:none}.audio-skip img:nth-child(2){position:absolute;width:4px;height:4px;max-width:none}.audio-skip--back img:nth-child(2){left:4px;top:4px}.audio-skip--forward img:nth-child(2){right:4px;top:4px}.audio-skip b{position:absolute;left:8px;top:7px;color:#111827;font-size:6px;line-height:8px;font-weight:400}.audio-status{position:absolute;right:15px;top:13px;max-width:150px;margin:0;color:#ca5e10;font-size:10px;text-align:right}.apple-audio-player audio{display:none}.audio-empty{margin:0 8px;padding:20px;border-radius:16px;color:#6b788f;background:#fff;font-size:12px;text-align:center}.pronunciation-tips{flex:none;padding:4px 8px 0}.pronunciation-disclosure{display:flex;align-items:center;justify-content:space-between;width:100%;height:56px;padding:0 12px 0 16px;border-radius:14px;color:#12141a;background:#f1f6ff;text-align:left}.pronunciation-disclosure strong{font-size:16px;line-height:22px}.pronunciation-disclosure span{display:grid;place-items:center;width:32px;height:32px;border-radius:50%;background:#f1f6ff}.pronunciation-disclosure img{width:16px;height:16px;max-width:none}.pronunciation-card{margin-top:8px;padding:14px 16px 16px;border-radius:22px;background:#fff;box-shadow:0 8px 14px rgba(13,26,61,.1)}.mistake-word{position:relative;padding:12px 0 11px}.mistake-word:first-child{padding-top:0}.mistake-word header{display:flex;align-items:center;gap:8px;min-height:30px}.mistake-word header strong{color:#121f29;font-size:13px;line-height:19px}.mistake-word header span{color:#1463f2;font-size:11px;line-height:16px}.mistake-word>div{display:flex;align-items:flex-start;gap:8px;margin-top:5px}.mistake-word b{flex:none;padding:4px 8px;border-radius:999px;font-size:11px;line-height:15px}.mistake-word b.standard{color:#1a4ff0;background:#e8f1ff}.mistake-word b.mistake{color:#ca5e10;background:#fff1e1}.mistake-word p{flex:1;margin:3px 0 0;color:#1c1c1e;font-size:11px;line-height:16px;font-weight:600}.mistake-word>i{position:absolute;left:0;right:0;bottom:0;height:1px;background:#e8ebf0}.mistake-empty{margin:0;color:#6b788f;font-size:12px;line-height:18px}.expression-annotation{flex:none;width:100%}.expression-annotation>div{margin:0 8px;padding:15px;border:1px solid #e8ebf0;border-radius:16px;background:#fff}.annotation-copy{color:#1c1c1e;font-size:13px;line-height:21px;white-space:pre-wrap;overflow-wrap:anywhere}.annotation-copy>p{margin:0}.expression-annotation .emphasis{color:#1a4ff0;font-weight:600}.course-detail-bottom{flex:none;height:24px}
.annotation-sentence{border-radius:5px;cursor:pointer;outline:none;transition:color .18s ease,background .18s ease,box-shadow .18s ease}.annotation-sentence:hover,.annotation-sentence:focus-visible{background:#f2f7ff;box-shadow:0 0 0 2px #d6e7ff}.annotation-sentence.active{color:#0b397f;background:#e8f2ff;box-shadow:0 0 0 2px #c4dcff}.annotation-sentence.active .emphasis{color:#075dcc}
.mistake-word__speech{display:flex;align-items:center;gap:8px;max-width:100%;min-height:32px;padding:0 2px;border:0;border-radius:9px;background:transparent;text-align:left;cursor:pointer}.mistake-word__speech:focus-visible{outline:2px solid #9dc4ff;outline-offset:2px}.mistake-word__speech>i{display:grid;place-items:center;flex:none;width:24px;height:24px;margin-left:2px;border-radius:50%;color:#fff;background:#0a7aff;font-size:9px;font-style:normal}.mistake-word__speech.playing>i{background:#1459d1}.mistake-word__speech:disabled{cursor:wait;opacity:.7}.speech-error{margin:10px 0 0!important;padding:8px 10px;border-radius:9px;color:#b4232f!important;background:#fff0f2;font-size:11px!important;line-height:16px!important}
@media(min-width:700px) and (max-width:1279px){.course-detail-page{max-width:834px;min-height:900px;border-radius:44px}.course-detail-page>.mobile-detail-header{left:220px;width:394px}.course-detail-scroll{left:40px;right:40px}.audio-demo__list{grid-template-columns:1fr 1fr}.audio-skip--back{left:27%}.audio-skip--forward{right:27%}}
.course-detail-scroll{animation:course-detail-in .3s ease-out both}.lecture-tabs button,.pronunciation-disclosure,.apple-audio-player button{transition:transform .18s ease,background .18s ease,color .18s ease,box-shadow .18s ease}.lecture-tabs button:active,.pronunciation-disclosure:active,.apple-audio-player button:active{transform:scale(.98)}
@keyframes course-detail-in{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
</style>
<style scoped>
.course-detail-page{height:100dvh;min-height:0;border-radius:0;max-width:834px}
.course-detail-page>.mobile-detail-header{left:0;width:100%}
.course-detail-scroll{bottom:max(15px,env(safe-area-inset-bottom))}
.audio-toggle:active{transform:translateX(-50%) scale(.98)}
.course-video>span,.course-video>p{pointer-events:none}
@media(min-width:1280px){.course-detail-page{max-width:1000px}.course-detail-scroll{left:32px;right:32px}.audio-demo__list{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
