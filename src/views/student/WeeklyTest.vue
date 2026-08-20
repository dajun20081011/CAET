<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
// const _courseId = computed(() => route.params.courseId as string)
const chapter = computed(() => Number(route.params.chapter) || 1)
const day = computed(() => Number(route.params.day) || 7)

// ---------- 预热章节测试题（前端静态题干，评测由后端完成） ----------
const speaking = {
  prompt: '女士们，先生们，欢迎登机。',
  expected: 'Ladies and gentlemen, welcome aboard.',
  keywords: ['welcome', 'aboard', 'ladies', 'gentlemen'],
}

const listening = {
  id: 'l1',
  title: '听力理解',
  // 模拟音频（无真实文件，UI 占位播放）
  transcript: 'Please fasten your seat belt and keep your seat back upright. We will be taking off shortly.',
  question: '广播后，旅客应当首先做什么？',
  options: [
    { id: 'a', text: '系好安全带并保持座椅靠背竖直' },
    { id: 'b', text: '打开行李架取物品' },
    { id: 'c', text: '起身在客舱内走动' },
    { id: 'd', text: '使用电子设备' },
  ],
  answer: 'a',
}

const vocabulary = [
  {
    id: 'v1',
    question: '"fasten" 的意思是？',
    options: [
      { id: 'a', text: '解开' },
      { id: 'b', text: '系紧 / 扣好' },
      { id: 'c', text: '打开' },
      { id: 'd', text: '关闭' },
    ],
    answer: 'b',
  },
  {
    id: 'v2',
    question: '"aisle" 指的是飞机上的？',
    options: [
      { id: 'a', text: '过道 / 走廊' },
      { id: 'b', text: '舷窗' },
      { id: 'c', text: '座椅' },
      { id: 'd', text: '头顶行李架' },
    ],
    answer: 'a',
  },
]

const scenarios = [
  {
    id: 's1',
    scenario: '一位旅客询问洗手间在哪里，最恰当回答是？',
    options: [
      { id: 'a', text: 'The lavatory is at the rear of the cabin.' },
      { id: 'b', text: 'You cannot use the lavatory.' },
      { id: 'c', text: 'Please leave the aircraft.' },
      { id: 'd', text: 'The lavatory is outside.' },
    ],
    answer: 'a',
  },
  {
    id: 's2',
    scenario: '旅客抱怨客舱温度过低，你应？',
    options: [
      { id: 'a', text: '忽略旅客的请求' },
      { id: 'b', text: 'Adjust the air vent and offer a blanket.' },
      { id: 'c', text: 'Tell the passenger to leave' },
      { id: 'd', text: 'Turn off all lights' },
    ],
    answer: 'b',
  },
]

// ---------- Speech recognition ----------
const recognitionSupported = ref(false)
const isRecording = ref(false)
const transcript = ref('')
let recognition: any = null

function setupRecognition() {
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SR) return
  recognition = new SR()
  recognition.lang = 'en-US'
  recognition.interimResults = true
  recognition.continuous = false
  recognition.onresult = (e: any) => {
    let text = ''
    for (let i = 0; i < e.results.length; i++) {
      text += e.results[i][0].transcript
    }
    transcript.value = text
  }
  recognition.onend = () => { isRecording.value = false }
  recognition.onerror = () => { isRecording.value = false }
  recognitionSupported.value = true
}

function toggleRecord() {
  if (!recognition) return
  if (isRecording.value) {
    recognition.stop()
    isRecording.value = false
  } else {
    transcript.value = ''
    try { recognition.start() } catch (e) { /* already started */ }
    isRecording.value = true
  }
}

const matchedKeywords = computed(() => {
  const t = transcript.value.toLowerCase()
  return speaking.keywords.filter((k) => t.includes(k))
})
const keywordMatchRatio = computed(() =>
  speaking.keywords.length ? matchedKeywords.value.length / speaking.keywords.length : 0
)

// ---------- Simulated audio player ----------
const audioPlaying = ref(false)
const audioProgress = ref(0)
let audioTimer: ReturnType<typeof setInterval> | null = null
function toggleAudio() {
  if (audioPlaying.value) {
    audioPlaying.value = false
    if (audioTimer) clearInterval(audioTimer)
  } else {
    audioPlaying.value = true
    audioTimer = setInterval(() => {
      audioProgress.value += 2
      if (audioProgress.value >= 100) {
        audioProgress.value = 100
        audioPlaying.value = false
        if (audioTimer) clearInterval(audioTimer)
      }
    }, 120)
  }
}

// ---------- Multiple choice answers ----------
const listeningAnswer = ref('')
const vocabAnswers = ref<Record<string, string>>({})
const scenarioAnswers = ref<Record<string, string>>({})

const allChoiceQuestions = computed(() => [listening, ...vocabulary, ...scenarios])
const choiceCorrect = computed(() => {
  let correct = 0
  const map: Record<string, string> = {
    [listening.id]: listeningAnswer.value,
    ...vocabAnswers.value,
    ...scenarioAnswers.value,
  }
  for (const q of allChoiceQuestions.value) {
    if (map[q.id] === q.answer) correct++
  }
  return correct
})
const choiceTotal = computed(() => allChoiceQuestions.value.length)
const choiceRatio = computed(() => (choiceTotal.value ? choiceCorrect.value / choiceTotal.value : 0))

// ---------- Submit & results ----------
const submitted = ref(false)
const contentSimilarity = computed(() => {
  // 内容一致度：结合关键词匹配与选择题正确率
  const base = keywordMatchRatio.value * 0.6 + choiceRatio.value * 0.4
  return Math.round(base * 100)
})

function submit() {
  submitted.value = true
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
}

function reset() {
  submitted.value = false
  transcript.value = ''
  listeningAnswer.value = ''
  vocabAnswers.value = {}
  scenarioAnswers.value = {}
  audioProgress.value = 0
}

onMounted(() => {
  setupRecognition()
})
onUnmounted(() => {
  if (audioTimer) clearInterval(audioTimer)
  if (recognition) { try { recognition.stop() } catch (e) { /* ignore */ } }
})
</script>

<template>
  <div class="min-h-[100dvh] bg-background pb-28">
    <!-- Top bar -->
    <div class="flex items-center gap-3 px-5 pt-12 pb-4">
      <button @click="router.back()" class="w-9 h-9 rounded-full bg-white shadow-sm flex items-center justify-center touch-target">
        <svg class="w-5 h-5 text-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>
      <div>
        <h1 class="text-base font-semibold text-text">周测 Quiz</h1>
        <p class="text-xs text-text-secondary">第 {{ chapter }} 章 · Day {{ day }}</p>
      </div>
    </div>

    <div class="px-5 space-y-5">
      <!-- Notice -->
      <div class="bg-primary-soft rounded-lg px-4 py-3 flex items-start gap-2">
        <svg class="w-4 h-4 text-primary mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p class="text-[12px] text-primary leading-relaxed">转写仅用于内容对照，不代表发音准确度。</p>
      </div>

      <!-- Section A: speaking -->
      <section class="card p-5">
        <div class="flex items-center gap-2 mb-3">
          <span class="w-6 h-6 rounded-full bg-primary text-white text-xs flex items-center justify-center font-bold">A</span>
          <h2 class="text-sm font-semibold text-text">中译英口述</h2>
        </div>
        <div class="bg-gray-50 rounded-lg p-4">
          <p class="text-sm text-text">中文提示：<span class="font-medium">{{ speaking.prompt }}</span></p>
          <p class="text-xs text-text-secondary mt-2">参考：{{ speaking.expected }}</p>
        </div>

        <div class="mt-3 flex items-center gap-3">
          <button
            @click="toggleRecord"
            :disabled="!recognitionSupported"
            class="flex items-center gap-2 px-4 py-3 rounded-lg font-medium transition-all active:scale-95 touch-target"
            :class="isRecording ? 'bg-danger text-white' : recognitionSupported ? 'bg-primary-soft text-primary' : 'bg-gray-100 text-text-secondary'"
          >
            <span class="w-2.5 h-2.5 rounded-full" :class="isRecording ? 'bg-white animate-pulse' : 'bg-current'"></span>
            {{ isRecording ? '停止录制' : '开始口述' }}
          </button>
          <span v-if="!recognitionSupported" class="text-[11px] text-text-secondary">当前浏览器不支持语音识别</span>
        </div>

        <div class="mt-3 min-h-[56px] rounded-lg border border-gray-100 p-3">
          <p v-if="transcript" class="text-sm text-text">{{ transcript }}</p>
          <p v-else class="text-sm text-text-secondary">转写结果会显示在这里…</p>
        </div>

        <div v-if="transcript" class="mt-3">
          <p class="text-xs text-text-secondary mb-1.5">关键词匹配：</p>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="k in speaking.keywords"
              :key="k"
              class="text-[11px] px-2 py-1 rounded-full"
              :class="matchedKeywords.includes(k) ? 'bg-success/10 text-success' : 'bg-gray-100 text-text-secondary line-through'"
            >{{ k }}</span>
          </div>
        </div>
      </section>

      <!-- Section B: listening -->
      <section class="card p-5">
        <div class="flex items-center gap-2 mb-3">
          <span class="w-6 h-6 rounded-full bg-primary text-white text-xs flex items-center justify-center font-bold">B</span>
          <h2 class="text-sm font-semibold text-text">{{ listening.title }}</h2>
        </div>

        <!-- simulated audio player -->
        <div class="bg-gray-50 rounded-lg p-3 flex items-center gap-3">
          <button @click="toggleAudio" class="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center touch-target shrink-0">
            <svg v-if="!audioPlaying" class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
            <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 5h4v14H6zM14 5h4v14h-4z" /></svg>
          </button>
          <div class="flex-1">
            <div class="h-1.5 rounded-full bg-gray-200 overflow-hidden">
              <div class="h-full bg-primary rounded-full" :style="{ width: audioProgress + '%' }"></div>
            </div>
            <p class="text-[11px] text-text-secondary mt-1">示例音频 · {{ audioProgress }}%</p>
          </div>
        </div>

        <p class="text-sm text-text mt-3">{{ listening.question }}</p>
        <div class="mt-2 space-y-2">
          <label
            v-for="opt in listening.options"
            :key="opt.id"
            class="flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors"
            :class="listeningAnswer === opt.id ? 'border-primary bg-primary-soft' : 'border-gray-100'"
          >
            <input type="radio" :value="opt.id" v-model="listeningAnswer" class="accent-primary w-4 h-4" />
            <span class="text-sm text-text">{{ opt.text }}</span>
          </label>
        </div>
      </section>

      <!-- Section C: vocabulary -->
      <section class="card p-5">
        <div class="flex items-center gap-2 mb-3">
          <span class="w-6 h-6 rounded-full bg-primary text-white text-xs flex items-center justify-center font-bold">C</span>
          <h2 class="text-sm font-semibold text-text">词汇选择</h2>
        </div>
        <div class="space-y-4">
          <div v-for="q in vocabulary" :key="q.id">
            <p class="text-sm text-text mb-2">{{ q.question }}</p>
            <div class="space-y-2">
              <label
                v-for="opt in q.options"
                :key="opt.id"
                class="flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors"
                :class="vocabAnswers[q.id] === opt.id ? 'border-primary bg-primary-soft' : 'border-gray-100'"
              >
                <input type="radio" :value="opt.id" v-model="vocabAnswers[q.id]" class="accent-primary w-4 h-4" />
                <span class="text-sm text-text">{{ opt.text }}</span>
              </label>
            </div>
          </div>
        </div>
      </section>

      <!-- Section D: scenario -->
      <section class="card p-5">
        <div class="flex items-center gap-2 mb-3">
          <span class="w-6 h-6 rounded-full bg-primary text-white text-xs flex items-center justify-center font-bold">D</span>
          <h2 class="text-sm font-semibold text-text">情景选择</h2>
        </div>
        <div class="space-y-4">
          <div v-for="q in scenarios" :key="q.id">
            <p class="text-sm text-text mb-2">{{ q.scenario }}</p>
            <div class="space-y-2">
              <label
                v-for="opt in q.options"
                :key="opt.id"
                class="flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors"
                :class="scenarioAnswers[q.id] === opt.id ? 'border-primary bg-primary-soft' : 'border-gray-100'"
              >
                <input type="radio" :value="opt.id" v-model="scenarioAnswers[q.id]" class="accent-primary w-4 h-4" />
                <span class="text-sm text-text">{{ opt.text }}</span>
              </label>
            </div>
          </div>
        </div>
      </section>

      <!-- Results -->
      <section v-if="submitted" class="card p-5 border-primary/30">
        <h2 class="text-sm font-semibold text-text mb-3">测试结果</h2>
        <div class="grid grid-cols-2 gap-3">
          <div class="bg-primary-soft rounded-lg p-3 text-center">
            <p class="text-2xl font-bold text-primary">{{ matchedKeywords.length }}/{{ speaking.keywords.length }}</p>
            <p class="text-[11px] text-text-secondary mt-0.5">关键词匹配</p>
          </div>
          <div class="bg-primary-soft rounded-lg p-3 text-center">
            <p class="text-2xl font-bold text-primary">{{ contentSimilarity }}%</p>
            <p class="text-[11px] text-text-secondary mt-0.5">内容一致度</p>
          </div>
          <div class="bg-gray-50 rounded-lg p-3 text-center">
            <p class="text-2xl font-bold text-text">{{ choiceCorrect }}/{{ choiceTotal }}</p>
            <p class="text-[11px] text-text-secondary mt-0.5">选择题正确</p>
          </div>
          <div class="bg-gray-50 rounded-lg p-3 text-center">
            <p class="text-2xl font-bold" :class="contentSimilarity >= 60 ? 'text-success' : 'text-warning'">
              {{ contentSimilarity >= 60 ? '合格' : '再练练' }}
            </p>
            <p class="text-[11px] text-text-secondary mt-0.5">综合评定</p>
          </div>
        </div>
        <button @click="reset" class="mt-4 w-full py-3 rounded-lg border border-gray-200 text-sm text-text-secondary touch-target">
          重新作答
        </button>
      </section>
    </div>

    <!-- Submit -->
    <div class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-100 px-5 py-3 z-40">
      <div class="max-w-[420px] mx-auto">
        <button
          v-if="!submitted"
          @click="submit"
          class="btn-primary w-full rounded-xl text-base"
        >
          提交周测
        </button>
        <button
          v-else
          @click="router.back()"
          class="btn-primary w-full rounded-xl text-base"
        >
          完成
        </button>
      </div>
    </div>
  </div>
</template>
