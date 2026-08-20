<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useLearningStore } from '@/stores/learning'
import { useLearningHeartbeat } from '@/composables/useLearningHeartbeat'
import { api } from '@/lib/api'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const learningStore = useLearningStore()

const courseId = route.params.courseId as string
const chapter = parseInt(route.params.chapter as string)
const day = parseInt(route.params.day as string)

const currentIndex = ref(0)
const isRecording = ref(false)
const recordedBlob = ref<Blob | null>(null)
const recordedUrl = ref('')
const transcript = ref('')
const isTranscribing = ref(false)
const mediaRecorder = ref<MediaRecorder | null>(null)
const audioChunks = ref<Blob[]>([])
const selectedAnswers = ref<Record<string, string>>({})
const showResults = ref(false)
const score = ref(0)
const contentBlocks = ref<any[]>([])
const loading = ref(true)
const error = ref('')
const favoriteWords = ref<Set<string>>(new Set())
const currentAudio = ref<HTMLAudioElement | null>(null)

const { effectiveSeconds, recordActivity } = useLearningHeartbeat(
  authStore.user?.id || '',
  undefined,
  courseId,
  undefined
)

// ---------------- 测评提交（广播词闭环：中英双录音上传 → submit） ----------------
const assignmentId = computed(() => {
  const t = learningStore.tasks.find((x) => x.course_id === courseId)
  const a = t ? learningStore.assignments.find((x) => x.task_id === t.id) : null
  return a?.id || ''
})
const courseType = computed(() => {
  const t = learningStore.tasks.find((x) => x.course_id === courseId)
  return (t as any)?.course_type || 'broadcast'
})
const isBroadcast = computed(() => courseType.value === 'broadcast')

const assessOpen = ref(false)
const cnBlob = ref<Blob | null>(null)
const cnUrl = ref('')
const enBlob = ref<Blob | null>(null)
const enUrl = ref('')
const slotRecording = ref<'cn' | 'en' | null>(null)
const slotRecorder = ref<MediaRecorder | null>(null)
const slotChunks = ref<Blob[]>([])
const submittingAssessment = ref(false)
const assessError = ref('')
const assessSuccess = ref(false)

async function startSlot(slot: 'cn' | 'en') {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const rec = new MediaRecorder(stream)
    slotRecorder.value = rec
    slotChunks.value = []
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) slotChunks.value.push(e.data)
    }
    rec.onstop = () => {
      const blob = new Blob(slotChunks.value, { type: 'audio/webm' })
      const url = URL.createObjectURL(blob)
      if (slot === 'cn') {
        cnBlob.value = blob
        if (cnUrl.value) URL.revokeObjectURL(cnUrl.value)
        cnUrl.value = url
      } else {
        enBlob.value = blob
        if (enUrl.value) URL.revokeObjectURL(enUrl.value)
        enUrl.value = url
      }
    }
    rec.start()
    slotRecording.value = slot
  } catch {
    alert('无法启动录音，请检查麦克风权限')
  }
}

function stopSlot() {
  slotRecorder.value?.stop()
  slotRecorder.value?.stream.getTracks().forEach((t) => t.stop())
  slotRecording.value = null
}

function playSlot(slot: 'cn' | 'en') {
  const url = slot === 'cn' ? cnUrl.value : enUrl.value
  if (url) {
    const audio = new Audio(url)
    audio.play()
  }
}

async function submitAssessment() {
  if (!cnBlob.value || !enBlob.value) {
    assessError.value = '请先分别录制中文与英文录音'
    return
  }
  if (!assignmentId.value) {
    assessError.value = '未找到对应任务，请从任务详情进入'
    return
  }
  submittingAssessment.value = true
  assessError.value = ''
  try {
    const cn = await api.upload.recording(cnBlob.value, 'cn_recording.webm')
    const en = await api.upload.recording(enBlob.value, 'en_recording.webm')
    await api.assessments.submit({
      assessment_type: 'broadcast_recording',
      assignment_id: assignmentId.value,
      content_id: null,
      answers: { cn_audio_url: cn.url, en_audio_url: en.url },
      attempt_no: 1,
    })
    assessSuccess.value = true
  } catch (e: any) {
    assessError.value = e?.message || '提交失败，请重试'
  } finally {
    submittingAssessment.value = false
  }
}

const totalBlocks = computed(() => contentBlocks.value.length)
const currentBlock = computed(() => contentBlocks.value[currentIndex.value])
const isLastBlock = computed(() => currentIndex.value >= totalBlocks.value - 1)
const isFirstBlock = computed(() => currentIndex.value === 0)

const chapterTitle = 'Warm Up'
const dayTitle = `Day ${day}`
const quotes = [
  'Focus today. Shine tomorrow.',
  'Practice makes progress.',
  'Small steps, big changes.',
  'Learn with purpose. Speak with confidence.',
]
const quote = quotes[day % quotes.length]

// 取音频 URL：payload.audio 可能是 { normal, slow } 或字符串 URL
function audioUrlFor(audio: any, speed: 'normal' | 'slow'): string | null {
  if (!audio) return null
  if (typeof audio === 'string') return audio
  if (typeof audio === 'object') {
    if (speed === 'slow' && audio.slow) return audio.slow
    if (audio.normal) return audio.normal
    if (audio.slow) return audio.slow
  }
  return null
}

async function loadContent() {
  loading.value = true
  error.value = ''
  try {
    const data = await learningStore.loadCourseContent(courseId, chapter, day)
    if (data && data.length > 0) {
      contentBlocks.value = data.map((c: any) => ({ type: c.content_type, payload: c.payload }))
    } else {
      contentBlocks.value = []
    }
  } catch (e: any) {
    error.value = e?.message || '内容加载失败'
    contentBlocks.value = []
  } finally {
    loading.value = false
  }
}

function speak(text: string, rate: number) {
  if ('speechSynthesis' in window) {
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'en-US'
    utterance.rate = rate
    window.speechSynthesis.speak(utterance)
  }
}

function nextBlock() {
  if (!isLastBlock.value) {
    currentIndex.value++
    recordActivity()
  }
}

function prevBlock() {
  if (!isFirstBlock.value) {
    currentIndex.value--
    recordActivity()
  }
}

function playAudio(speed: 'normal' | 'slow') {
  const block = currentBlock.value
  if (block?.type !== 'sentence') return
  const id = block.payload.id || block.payload.en?.slice(0, 20)
  const eventType = speed === 'normal' ? 'audio_standard_play' : 'audio_slow_play'
  learningStore.addEvent(authStore.user?.id || '', eventType, { sentenceId: id, speed }, undefined, courseId)
  recordActivity()

  const url = audioUrlFor(block.payload.audio, speed)
  if (url) {
    try {
      const audio = new Audio(url)
      currentAudio.value = audio
      audio.play().catch(() => speak(block.payload.en, speed === 'slow' ? 0.7 : 1.0))
    } catch {
      speak(block.payload.en, speed === 'slow' ? 0.7 : 1.0)
    }
  } else {
    // 无音频文件时回退到浏览器 TTS
    speak(block.payload.en, speed === 'slow' ? 0.7 : 1.0)
  }
}

function copyText(text: string) {
  navigator.clipboard.writeText(text).catch(() => {
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  })
  learningStore.addEvent(authStore.user?.id || '', 'copy', { text: text.slice(0, 100) }, undefined, courseId)
  alert('已复制')
}

function eudicLookup(word: string) {
  learningStore.addEvent(authStore.user?.id || '', 'eudic_lookup', { word }, undefined, courseId)
  window.open(`eudic://dict/${word}`, '_blank')
  setTimeout(() => {
    copyText(word)
  }, 300)
}

function toggleFavorite(word: string) {
  if (favoriteWords.value.has(word)) {
    favoriteWords.value.delete(word)
  } else {
    favoriteWords.value.add(word)
    learningStore.addEvent(authStore.user?.id || '', 'favorite_word', { word }, undefined, courseId)
  }
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder.value = new MediaRecorder(stream)
    audioChunks.value = []
    mediaRecorder.value.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.value.push(e.data)
    }
    mediaRecorder.value.onstop = () => {
      recordedBlob.value = new Blob(audioChunks.value, { type: 'audio/webm' })
      recordedUrl.value = URL.createObjectURL(recordedBlob.value)
      learningStore.addEvent(authStore.user?.id || '', 'recording_complete', { duration: effectiveSeconds.value }, undefined, courseId)
    }
    mediaRecorder.value.start()
    isRecording.value = true
    learningStore.addEvent(authStore.user?.id || '', 'recording_start', {}, undefined, courseId)
  } catch (e) {
    alert('无法启动录音，请检查麦克风权限')
  }
}

function stopRecording() {
  mediaRecorder.value?.stop()
  isRecording.value = false
  mediaRecorder.value?.stream.getTracks().forEach(t => t.stop())
}

function playRecording() {
  if (recordedUrl.value) {
    const audio = new Audio(recordedUrl.value)
    audio.play()
  }
}

async function startTranscription() {
  if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
    alert('您的浏览器不支持语音识别')
    return
  }
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  const recognition = new SpeechRecognition()
  recognition.lang = 'en-US'
  recognition.continuous = false
  recognition.interimResults = false
  isTranscribing.value = true
  recognition.onresult = (e: any) => {
    transcript.value = e.results[0][0].transcript
    isTranscribing.value = false
    const original = currentBlock.value?.payload?.en || ''
    const keywords = extractKeywords(original)
    const matched = keywords.filter(k => transcript.value.toLowerCase().includes(k.toLowerCase()))
    learningStore.addEvent(authStore.user?.id || '', 'speech_transcription', {
      original: original.slice(0, 200),
      transcript: transcript.value.slice(0, 200),
      keywordMatch: matched.length,
      totalKeywords: keywords.length,
    }, undefined, courseId)
  }
  recognition.onerror = () => {
    isTranscribing.value = false
    alert('识别失败，请重试')
  }
  recognition.start()
}

function extractKeywords(text: string): string[] {
  return text.toLowerCase().replace(/[^a-z\s]/g, '').split(/\s+/).filter(w => w.length > 3)
}

function keywordMatchPercent(): number {
  const original = currentBlock.value?.payload?.en || ''
  const keywords = [...new Set(extractKeywords(original))]
  if (!keywords.length || !transcript.value) return 0
  const matched = keywords.filter(k => transcript.value.toLowerCase().includes(k))
  return Math.round((matched.length / keywords.length) * 100)
}

function submitPractice() {
  const questions = currentBlock.value?.payload?.questions || []
  let correct = 0
  questions.forEach((q: any) => {
    if (selectedAnswers.value[q.id] === q.answer) correct++
  })
  score.value = questions.length > 0 ? Math.round((correct / questions.length) * 100) : 0
  showResults.value = true
  learningStore.addEvent(authStore.user?.id || '', 'answer_submit', {
    score,
    correct,
    total: questions.length,
    day,
  }, undefined, courseId)
  recordActivity()
}

function completeDay() {
  learningStore.addEvent(authStore.user?.id || '', 'learning_heartbeat', {
    totalSeconds: effectiveSeconds.value,
    day,
    chapter,
  }, undefined, courseId)
  router.push(`/student/tasks`)
}

onMounted(() => {
  // 刷新直达时补齐任务/分配上下文（assignment_id 依赖）
  if (authStore.user?.id && !learningStore.tasks.length) {
    learningStore.loadTasks(authStore.user.id).catch(() => {})
  }
  loadContent()
})

onUnmounted(() => {
  currentAudio.value?.pause()
  if (recordedUrl.value) URL.revokeObjectURL(recordedUrl.value)
})

function playAudioForWord(word: string) {
  if ('speechSynthesis' in window) {
    const utterance = new SpeechSynthesisUtterance(word)
    utterance.lang = 'en-US'
    window.speechSynthesis.speak(utterance)
  }
}
</script>

<template>
  <div class="min-h-screen bg-background">
    <!-- Header -->
    <div class="sticky top-0 z-40 bg-white/80 backdrop-blur-md border-b border-gray-100">
      <div class="max-w-[420px] mx-auto px-4 py-3 flex items-center justify-between">
        <button @click="router.back()" class="touch-target flex items-center text-text-secondary">
          <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" /></svg>
        </button>
        <div class="text-center">
          <p class="text-xs text-text-secondary">{{ chapterTitle }}</p>
          <p class="text-sm font-semibold text-text">{{ dayTitle }}</p>
        </div>
        <div class="w-5"><!-- spacer --></div>
      </div>
      <!-- Progress bar -->
      <div class="h-1 bg-gray-100">
        <div class="h-full bg-primary transition-all duration-300" :style="{ width: `${((currentIndex + 1) / Math.max(totalBlocks, 1)) * 100}%` }"></div>
      </div>
    </div>

    <div class="max-w-[420px] mx-auto px-4 py-4 pb-24">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-20">
        <div class="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="card p-6 text-center">
        <p class="text-sm text-danger">{{ error }}</p>
        <button @click="loadContent" class="mt-4 px-4 py-2 rounded-lg bg-primary text-white text-sm">重试</button>
      </div>

      <!-- Empty -->
      <div v-else-if="!currentBlock" class="card p-8 text-center text-text-secondary text-sm">
        本章暂无学习内容
      </div>

      <template v-else>
        <!-- Hero Block -->
        <div v-if="currentBlock.type === 'hero'" class="text-center py-8">
          <div class="w-20 h-20 rounded-2xl bg-primary-soft flex items-center justify-center mx-auto mb-4">
            <svg class="w-10 h-10 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
          </div>
          <h2 class="text-xl font-bold text-text mb-1">{{ currentBlock.payload.title }}</h2>
          <p class="text-sm text-text-secondary">{{ currentBlock.payload.subtitle }}</p>
          <p class="text-xs text-primary mt-4 italic">"{{ quote }}"</p>
        </div>

        <!-- Explanation Block -->
        <div v-else-if="currentBlock.type === 'explanation'" class="card p-5">
          <div class="flex items-start gap-3">
            <div class="w-8 h-8 rounded-lg bg-primary-soft flex items-center justify-center flex-shrink-0 mt-0.5">
              <svg class="w-4 h-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </div>
            <p class="text-sm text-text leading-relaxed">{{ currentBlock.payload.text }}</p>
          </div>
        </div>

        <!-- Sentence Block -->
        <div v-else-if="currentBlock.type === 'sentence'" class="space-y-4">
          <div class="card p-5">
            <div class="flex items-center gap-2 mb-3">
              <span class="text-xs px-2 py-1 rounded bg-primary-soft text-primary font-medium">核心句</span>
              <span class="text-xs text-text-secondary">{{ currentBlock.payload.id }}</span>
            </div>
            <p class="text-base text-text mb-3">{{ currentBlock.payload.zh }}</p>
            <div class="bg-gray-50 rounded-lg p-4 mb-3">
              <p class="text-lg text-text font-medium leading-relaxed">{{ currentBlock.payload.en }}</p>
            </div>
            <p class="text-xs text-text-secondary leading-relaxed">{{ currentBlock.payload.note }}</p>
          </div>

          <!-- Audio Controls -->
          <div class="flex gap-3">
            <button @click="playAudio('normal')" class="flex-1 flex items-center justify-center gap-2 py-3 rounded-lg bg-primary text-white text-sm font-medium touch-target active:scale-95 transition-transform">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              标准范读
            </button>
            <button @click="playAudio('slow')" class="flex-1 flex items-center justify-center gap-2 py-3 rounded-lg border-2 border-primary text-primary text-sm font-medium touch-target active:scale-95 transition-transform">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              慢速范读
            </button>
          </div>

          <!-- Recording -->
          <div class="card p-4">
            <div class="flex items-center justify-between mb-3">
              <span class="text-sm font-medium text-text">跟读录音</span>
              <span class="text-xs text-text-secondary">{{ isRecording ? '录音中...' : '点击开始录音' }}</span>
            </div>
            <div class="flex items-center gap-3">
              <button
                @click="isRecording ? stopRecording() : startRecording()"
                class="w-14 h-14 rounded-full flex items-center justify-center touch-target transition-transform active:scale-95"
                :class="isRecording ? 'bg-danger animate-pulse' : 'bg-primary'"
              >
                <svg v-if="!isRecording" class="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                <svg v-else class="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" /></svg>
              </button>
              <button v-if="recordedUrl" @click="playRecording" class="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-gray-100 text-sm text-text touch-target">
                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                播放录音
              </button>
            </div>
          </div>

          <!-- Transcription -->
          <div class="card p-4">
            <div class="flex items-center justify-between mb-3">
              <span class="text-sm font-medium text-text">语音转写</span>
              <span class="text-xs text-danger">*转写仅用于内容对照，不代表发音准确度</span>
            </div>
            <button @click="startTranscription" :disabled="isTranscribing" class="w-full py-2.5 rounded-lg border border-gray-200 text-sm text-text-secondary touch-target mb-3">
              {{ isTranscribing ? '识别中...' : '点击开始语音转写' }}
            </button>
            <div v-if="transcript" class="bg-gray-50 rounded-lg p-3 mb-3">
              <p class="text-sm text-text">{{ transcript }}</p>
            </div>
            <div v-if="transcript" class="flex items-center gap-2">
              <span class="text-xs text-text-secondary">关键词匹配:</span>
              <span class="text-xs font-medium" :class="keywordMatchPercent() > 70 ? 'text-success' : keywordMatchPercent() > 40 ? 'text-warning' : 'text-danger'">
                {{ keywordMatchPercent() }}%
              </span>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-2">
            <button @click="copyText(currentBlock.payload.en)" class="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-100 text-xs text-text-secondary touch-target">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
              复制
            </button>
            <button @click="eudicLookup(currentBlock.payload.en.split(' ')[0])" class="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-100 text-xs text-text-secondary touch-target">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg>
              欧陆词典
            </button>
          </div>
        </div>

        <!-- Vocabulary Block -->
        <div v-else-if="currentBlock.type === 'vocabulary'" class="space-y-3">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-xs px-2 py-1 rounded bg-warning/10 text-warning font-medium">重难点词</span>
          </div>
          <div v-for="item in currentBlock.payload.items" :key="item.word" class="card p-4">
            <div class="flex items-start justify-between">
              <div>
                <div class="flex items-center gap-2 mb-1">
                  <h3 class="text-lg font-bold text-text">{{ item.word }}</h3>
                  <span class="text-xs text-text-secondary">{{ item.phonetic }}</span>
                </div>
                <p class="text-sm text-text-secondary">{{ item.meaning }}</p>
              </div>
              <div class="flex gap-1">
                <button @click="playAudioForWord(item.word)" class="w-9 h-9 rounded-lg bg-primary-soft flex items-center justify-center touch-target">
                  <svg class="w-4 h-4 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>
                </button>
                <button @click="toggleFavorite(item.word)" class="w-9 h-9 rounded-lg flex items-center justify-center touch-target" :class="favoriteWords.has(item.word) ? 'bg-warning/10' : 'bg-gray-100'">
                  <svg class="w-4 h-4" :class="favoriteWords.has(item.word) ? 'text-warning' : 'text-text-secondary'" fill="currentColor" viewBox="0 0 24 24"><path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" /></svg>
                </button>
              </div>
            </div>
            <div class="flex gap-2 mt-3">
              <button @click="copyText(item.word)" class="px-3 py-1.5 rounded text-xs bg-gray-100 text-text-secondary touch-target">复制</button>
              <button @click="eudicLookup(item.word)" class="px-3 py-1.5 rounded text-xs bg-gray-100 text-text-secondary touch-target">欧陆词典</button>
            </div>
          </div>
        </div>

        <!-- Practice Block -->
        <div v-else-if="currentBlock.type === 'practice'" class="space-y-4">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-xs px-2 py-1 rounded bg-success/10 text-success font-medium">练习</span>
          </div>
          <div v-for="(q, idx) in currentBlock.payload.questions" :key="q.id" class="card p-4">
            <p class="text-sm font-medium text-text mb-3">{{ idx + 1 }}. {{ q.question }}</p>
            <div class="space-y-2">
              <button
                v-for="(opt, oIdx) in q.options"
                :key="oIdx"
                @click="selectedAnswers[q.id] = String.fromCharCode(65 + oIdx)"
                class="w-full text-left p-3 rounded-lg border-2 text-sm transition-all touch-target"
                :class="selectedAnswers[q.id] === String.fromCharCode(65 + oIdx)
                  ? 'border-primary bg-primary-soft text-primary'
                  : 'border-gray-100 text-text hover:border-gray-200'"
              >
                <span class="font-medium mr-2">{{ String.fromCharCode(65 + oIdx) }}.</span>{{ opt }}
              </button>
            </div>
          </div>
          <button v-if="!showResults" @click="submitPractice" class="w-full btn-primary rounded-xl py-3.5">
            提交答案
          </button>
          <div v-else class="card p-4 text-center">
            <p class="text-lg font-bold mb-1" :class="score >= 80 ? 'text-success' : score >= 60 ? 'text-warning' : 'text-danger'">
              {{ score }}分
            </p>
            <p class="text-xs text-text-secondary">{{ score >= 80 ? '很棒！' : score >= 60 ? '继续加油！' : '再复习一下吧' }}</p>
          </div>
        </div>

        <!-- Summary Block -->
        <div v-else-if="currentBlock.type === 'summary'" class="space-y-4">
          <div class="card p-5 text-center">
            <div class="w-16 h-16 rounded-full bg-success/10 flex items-center justify-center mx-auto mb-4">
              <svg class="w-8 h-8 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </div>
            <h3 class="text-lg font-bold text-text mb-2">今日学习完成!</h3>
            <p class="text-sm text-text-secondary mb-4">{{ currentBlock.payload.text }}</p>
            <div class="bg-gray-50 rounded-lg p-3 mb-4">
              <p class="text-xs text-text-secondary">有效学习时长</p>
              <p class="text-lg font-bold text-primary">{{ Math.floor(effectiveSeconds / 60) }} 分 {{ effectiveSeconds % 60 }} 秒</p>
            </div>
            <button @click="completeDay" class="w-full btn-primary rounded-xl py-3.5">
              完成并返回
            </button>
          </div>

          <!-- 广播词测评提交（闭环） -->
          <div v-if="isBroadcast" class="card p-5">
            <div class="flex items-center justify-between mb-3">
              <div>
                <h4 class="text-base font-semibold text-text">广播词测评提交</h4>
                <p class="text-xs text-text-secondary mt-0.5">需同时提交中文与英文录音，提交后由教员评分</p>
              </div>
              <button v-if="!assessOpen && !assessSuccess" @click="assessOpen = true" class="px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium touch-target">
                去提交
              </button>
              <el-tag v-if="assessSuccess" type="success" size="small">已提交</el-tag>
            </div>

            <template v-if="assessOpen && !assessSuccess">
              <!-- CN recording -->
              <div class="flex items-center justify-between p-3 rounded-lg bg-gray-50 mb-3">
                <div>
                  <p class="text-sm font-medium text-text">中文录音</p>
                  <p class="text-xs text-text-secondary">{{ cnBlob ? '已录制' : '朗读中文广播词' }}</p>
                </div>
                <div class="flex items-center gap-2">
                  <button v-if="cnUrl" @click="playSlot('cn')" class="w-9 h-9 rounded-lg bg-white border border-gray-200 flex items-center justify-center">
                    <svg class="w-4 h-4 text-text" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  </button>
                  <button
                    @click="slotRecording === 'cn' ? stopSlot() : startSlot('cn')"
                    class="w-10 h-10 rounded-full flex items-center justify-center"
                    :class="slotRecording === 'cn' ? 'bg-danger animate-pulse' : 'bg-primary'"
                  >
                    <svg v-if="slotRecording !== 'cn'" class="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                    <svg v-else class="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" /></svg>
                  </button>
                </div>
              </div>

              <!-- EN recording -->
              <div class="flex items-center justify-between p-3 rounded-lg bg-gray-50 mb-3">
                <div>
                  <p class="text-sm font-medium text-text">英文录音</p>
                  <p class="text-xs text-text-secondary">{{ enBlob ? '已录制' : '朗读英文广播词' }}</p>
                </div>
                <div class="flex items-center gap-2">
                  <button v-if="enUrl" @click="playSlot('en')" class="w-9 h-9 rounded-lg bg-white border border-gray-200 flex items-center justify-center">
                    <svg class="w-4 h-4 text-text" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                  </button>
                  <button
                    @click="slotRecording === 'en' ? stopSlot() : startSlot('en')"
                    class="w-10 h-10 rounded-full flex items-center justify-center"
                    :class="slotRecording === 'en' ? 'bg-danger animate-pulse' : 'bg-primary'"
                  >
                    <svg v-if="slotRecording !== 'en'" class="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                    <svg v-else class="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" /></svg>
                  </button>
                </div>
              </div>

              <p v-if="assessError" class="text-xs text-danger mb-2">{{ assessError }}</p>

              <button
                @click="submitAssessment"
                :disabled="submittingAssessment"
                class="w-full py-3 rounded-xl text-white text-sm font-medium touch-target disabled:opacity-50"
                :class="cnBlob && enBlob ? 'bg-primary' : 'bg-gray-300'"
              >
                {{ submittingAssessment ? '提交中…' : '提交测评' }}
              </button>
              <p class="text-[11px] text-text-secondary mt-2 text-center">提交后可在「我的测评」查看评分与反馈</p>
            </template>
          </div>
        </div>
      </template>
    </div>

    <!-- Bottom Navigation -->
    <div v-if="!loading && currentBlock && currentBlock.type !== 'summary'" class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-100 z-50">
      <div class="max-w-[420px] mx-auto flex items-center justify-between px-4 py-3">
        <button
          @click="prevBlock"
          :disabled="isFirstBlock"
          class="flex items-center gap-1 text-sm text-text-secondary touch-target"
          :class="{ 'opacity-30': isFirstBlock }"
        >
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" /></svg>
          上一步
        </button>
        <span class="text-xs text-text-secondary">{{ currentIndex + 1 }} / {{ totalBlocks }}</span>
        <button
          @click="nextBlock"
          :disabled="isLastBlock"
          class="flex items-center gap-1 text-sm text-primary font-medium touch-target"
          :class="{ 'opacity-30': isLastBlock }"
        >
          下一步
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" /></svg>
        </button>
      </div>
    </div>
  </div>
</template>
