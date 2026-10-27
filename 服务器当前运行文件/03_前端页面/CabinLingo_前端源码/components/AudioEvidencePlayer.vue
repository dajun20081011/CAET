<template>
  <section class="audio-player" :class="{ 'audio-player--instructor': variant === 'instructor' }">
    <template v-if="variant === 'instructor'">
      <header><span><strong>{{ title }}</strong><small v-if="meta">{{ meta }}</small></span></header>
      <input class="audio-player__range" :style="{ '--audio-progress': `${progressPercent}%` }" type="range" min="0" :max="effectiveDuration || 0" step="0.05" :value="currentTime" :disabled="!src || !effectiveDuration" aria-label="录音播放进度" @input="seekFromRange" />
      <div class="audio-player__times"><time>{{ formatTime(currentTime) }}</time><time>{{ formatTime(effectiveDuration) }}</time></div>
      <div class="audio-player__controls">
        <button type="button" class="audio-player__speed" :disabled="loading" :aria-label="`播放速度 ${playbackRate} 倍`" @click="cycleRate">{{ rateLabel }}</button>
        <button type="button" class="audio-player__skip audio-player__skip--back" :disabled="loading" aria-label="后退 15 秒" @click="skip(-15)"><img :src="audioBack" alt=""><img :src="audioBackArrow" alt=""><small>15</small></button>
        <button type="button" class="audio-player__play" :disabled="loading" :aria-label="src ? (playing ? '暂停录音' : '播放录音') : '载入并播放录音'" @click="togglePlayback"><span v-if="loading" class="audio-player__spinner" /><img v-else :src="playing ? audioPause : audioPlay" alt="" aria-hidden="true"></button>
        <button type="button" class="audio-player__skip audio-player__skip--forward" :disabled="loading" aria-label="前进 15 秒" @click="skip(15)"><img :src="audioForward" alt=""><img :src="audioForwardArrow" alt=""><small>15</small></button>
        <button type="button" class="audio-player__more-button" aria-label="更多播放选项" :aria-expanded="moreOpen" @click="moreOpen = !moreOpen"><img :src="audioMore" alt="" aria-hidden="true"></button>
      </div>
      <div v-if="moreOpen" class="audio-player__more"><button type="button" :disabled="!src" @click="restart">从头播放</button><button type="button" :disabled="!src" @click="downloadAudio">下载录音</button></div>
      <audio ref="player" :src="src || undefined" preload="metadata" @loadedmetadata="syncDuration" @durationchange="syncDuration" @timeupdate="syncCurrentTime" @play="playing = true" @pause="playing = false" @ended="playing = false" @error="onAudioError" />
    </template>
    <template v-else>
      <div><strong>{{ title }}</strong><small v-if="meta">{{ meta }}</small></div>
      <audio v-if="src" ref="player" :src="src" controls preload="metadata" :aria-label="title" />
      <button v-else type="button" class="outline-button" :disabled="loading" @click="$emit('load')">{{ loading ? '载入中…' : '载入录音' }}</button>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import audioBack from '@/assets/figma/course-audio-back.svg'
import audioBackArrow from '@/assets/figma/course-audio-back-arrow.svg'
import audioForward from '@/assets/figma/course-audio-forward.svg'
import audioForwardArrow from '@/assets/figma/course-audio-forward-arrow.svg'
import audioMore from '@/assets/figma/course-audio-more.svg'
import audioPause from '@/assets/figma/course-audio-pause.svg'
import audioPlay from '@/assets/figma/course-audio-play.svg'

const props = withDefaults(defineProps<{ title: string; meta?: string; src?: string; loading?: boolean; variant?: 'default' | 'instructor'; knownDurationSeconds?: number | null }>(), { meta: '', src: '', loading: false, variant: 'default', knownDurationSeconds: null })
const emit = defineEmits<{
  load: []
  error: []
  'segment-progress': [payload: { currentMs: number; durationMs: number; progress: number }]
  'segment-end': []
}>()
const player = ref<HTMLAudioElement | null>(null)
const playing = ref(false), currentTime = ref(0), duration = ref(0), playbackRate = ref(1), moreOpen = ref(false), pendingAutoplay = ref(false)
const segmentStartMs = ref<number | null>(null)
const segmentEndMs = ref<number | null>(null)
let segmentGuardTimer: number | undefined
const rates = [1, 1.25, 1.5, 2]
const effectiveDuration = computed(() => duration.value || Math.max(props.knownDurationSeconds || 0, 0))
const progressPercent = computed(() => effectiveDuration.value ? Math.min(100, Math.max(0, currentTime.value / effectiveDuration.value * 100)) : 0)
const rateLabel = computed(() => `${Number.isInteger(playbackRate.value) ? playbackRate.value.toFixed(0) : playbackRate.value}×`)

watch(() => props.src, async value => { playing.value = false; currentTime.value = 0; duration.value = 0; moreOpen.value = false; if (value && pendingAutoplay.value) { pendingAutoplay.value = false; await nextTick(); try { await player.value?.play() } catch { playing.value = false } } })
watch(playbackRate, value => { if (player.value) player.value.playbackRate = value })
function syncDuration() { const value = player.value?.duration; duration.value = typeof value === 'number' && Number.isFinite(value) ? value : 0; if (player.value) player.value.playbackRate = playbackRate.value }
function syncCurrentTime() {
  currentTime.value = player.value?.currentTime || 0
  if (segmentStartMs.value === null || segmentEndMs.value === null) return
  const absoluteMs = currentTime.value * 1000
  const durationMs = Math.max(segmentEndMs.value - segmentStartMs.value, 1)
  const elapsedMs = Math.min(Math.max(absoluteMs - segmentStartMs.value, 0), durationMs)
  emit('segment-progress', { currentMs: elapsedMs, durationMs, progress: elapsedMs / durationMs })
  if (absoluteMs + 10 < segmentEndMs.value) return
  finishSegment()
}
function clearSegmentGuard() {
  if (segmentGuardTimer !== undefined) window.clearInterval(segmentGuardTimer)
  segmentGuardTimer = undefined
}
function finishSegment() {
  if (segmentStartMs.value === null || segmentEndMs.value === null) return
  const durationMs = Math.max(segmentEndMs.value - segmentStartMs.value, 1)
  player.value?.pause()
  emit('segment-progress', { currentMs: durationMs, durationMs, progress: 1 })
  segmentStartMs.value = null
  segmentEndMs.value = null
  clearSegmentGuard()
  emit('segment-end')
}
function startSegmentGuard() {
  clearSegmentGuard()
  segmentGuardTimer = window.setInterval(() => {
    const current = player.value
    if (!current || segmentEndMs.value === null) {
      clearSegmentGuard()
      return
    }
    if (current.currentTime * 1000 + 10 >= segmentEndMs.value) finishSegment()
  }, 25)
}
async function togglePlayback() { if (!props.src) { pendingAutoplay.value = true; emit('load'); return } if (!player.value) return; if (player.value.paused) { try { await player.value.play() } catch { playing.value = false; emit('error') } } else player.value.pause() }
function seekFromRange(event: Event) { if (!player.value) return; const value = Number((event.target as HTMLInputElement).value); player.value.currentTime = Number.isFinite(value) ? value : 0; currentTime.value = player.value.currentTime }
function skip(seconds: number) { if (!props.src) { pendingAutoplay.value = true; emit('load'); return } if (!player.value) return; const cap = effectiveDuration.value || Number.POSITIVE_INFINITY; player.value.currentTime = Math.min(Math.max(player.value.currentTime + seconds, 0), cap); currentTime.value = player.value.currentTime }
function cycleRate() { const index = rates.indexOf(playbackRate.value); playbackRate.value = rates[(index + 1) % rates.length] }
async function restart() { moreOpen.value = false; if (!player.value) return; player.value.currentTime = 0; try { await player.value.play() } catch { emit('error') } }
function downloadAudio() { moreOpen.value = false; if (!props.src) return; const link = document.createElement('a'); link.href = props.src; link.download = `${props.title || '录音'}.webm`; link.click() }
function onAudioError() { playing.value = false; if (props.src) emit('error') }
function formatTime(seconds: number) { const safe = Math.max(0, Math.floor(seconds || 0)); return `${Math.floor(safe / 60).toString().padStart(2, '0')}:${(safe % 60).toString().padStart(2, '0')}` }
async function seekAndPlay(milliseconds: number) { if (!props.src) { pendingAutoplay.value = true; emit('load'); return false } if (!player.value) return false; stop(); try { if (player.value.readyState === 0) { player.value.load(); await new Promise<void>(resolve => { const current = player.value; if (!current) { resolve(); return } const done = () => { current.removeEventListener('loadedmetadata', done); current.removeEventListener('error', done); resolve() }; current.addEventListener('loadedmetadata', done, { once: true }); current.addEventListener('error', done, { once: true }); window.setTimeout(done, 2000) }) } player.value.currentTime = Math.max(milliseconds, 0) / 1000; await player.value.play(); return true } catch { return false } }
async function seekAndPlayRange(startMilliseconds: number, endMilliseconds: number) {
  if (!props.src || !player.value) return false
  const startMs = Math.max(0, startMilliseconds)
  const endMs = Math.max(startMs + 100, endMilliseconds)
  const current = player.value
  try {
    if (current.readyState === 0) {
      current.load()
      await new Promise<void>(resolve => {
        const done = () => {
          current.removeEventListener('loadedmetadata', done)
          current.removeEventListener('error', done)
          resolve()
        }
        current.addEventListener('loadedmetadata', done, { once: true })
        current.addEventListener('error', done, { once: true })
        window.setTimeout(done, 2000)
      })
    }
    segmentStartMs.value = startMs
    segmentEndMs.value = endMs
    current.currentTime = startMs / 1000
    emit('segment-progress', { currentMs: 0, durationMs: endMs - startMs, progress: 0 })
    await current.play()
    startSegmentGuard()
    return true
  } catch {
    segmentStartMs.value = null
    segmentEndMs.value = null
    clearSegmentGuard()
    return false
  }
}
function stop() {
  player.value?.pause()
  segmentStartMs.value = null
  segmentEndMs.value = null
  clearSegmentGuard()
}
onBeforeUnmount(stop)
defineExpose({ seekAndPlay, seekAndPlayRange, stop })
</script>

<style scoped>
.audio-player{display:grid;grid-template-columns:minmax(100px,.45fr) minmax(220px,1fr);align-items:center;gap:12px;padding:10px 0}.audio-player strong,.audio-player small{display:block}.audio-player strong{color:var(--ink);font-size:13px}.audio-player small{margin-top:4px;color:var(--muted);font-size:10px}.audio-player audio{width:100%;height:38px}
.audio-player--instructor{position:relative;display:block;width:100%;height:120px;padding:0;border:1px solid rgba(224,229,240,.9);border-radius:18px;background:#fff;overflow:visible}.audio-player--instructor>audio{display:none}.audio-player--instructor header{position:absolute;left:15px;top:13px}.audio-player--instructor header strong{font-size:16px;line-height:19px}.audio-player--instructor header small{margin-top:0;color:#6b788f;font-size:11px;line-height:13px}.audio-player__range{--audio-progress:0%;position:absolute;left:15px;top:44px;width:calc(100% - 30px);height:18px;margin:0;padding:0;appearance:none;background:transparent;cursor:pointer}.audio-player__range::-webkit-slider-runnable-track{height:4px;border-radius:2px;background:linear-gradient(to right,#0a7aff 0 var(--audio-progress),#e0e5f0 var(--audio-progress) 100%)}.audio-player__range::-webkit-slider-thumb{width:18px;height:18px;margin-top:-7px;border:0;appearance:none;background:url('@/assets/figma/course-scrubber-thumb.svg') center/18px 18px no-repeat}.audio-player__range::-moz-range-track{height:4px;border:0;border-radius:2px;background:#e0e5f0}.audio-player__range::-moz-range-progress{height:4px;border-radius:2px;background:#0a7aff}.audio-player__range::-moz-range-thumb{width:18px;height:18px;border:0;background:url('@/assets/figma/course-scrubber-thumb.svg') center/18px 18px no-repeat}.audio-player__range:disabled{cursor:default;opacity:.55}.audio-player__times{position:absolute;left:15px;right:15px;top:59px;display:flex;justify-content:space-between;color:#6b788f;font-size:10px;line-height:12px;font-variant-numeric:tabular-nums}
.audio-player__controls{position:absolute;left:15px;right:15px;top:71px;height:40px;margin:0}.audio-player__controls button{position:absolute;display:grid;padding:0;border:0;color:#111827;background:transparent;place-items:center}.audio-player__controls button:disabled{opacity:.55}.audio-player__speed{left:0;top:6px;width:44px;height:28px;border-radius:14px!important;background:#f0f2f7!important;font-size:11px;font-weight:700}.audio-player__skip{top:10px;width:22px;height:22px}.audio-player__skip--back{left:72px}.audio-player__skip--forward{right:74px}.audio-player__skip>img:first-child{position:absolute;width:14.2px;height:14.2px;left:4px;top:6px}.audio-player__skip>img:nth-child(2){position:absolute;width:5.1px;height:5.1px;top:4px}.audio-player__skip--back>img:nth-child(2){left:4px}.audio-player__skip--forward>img:nth-child(2){right:4px}.audio-player__skip>small{position:absolute;left:7px;top:7px;margin:0;color:#111827;font-size:6.2px;line-height:8px}.audio-player__play{left:50%;top:0;width:40px;height:40px;transform:translateX(-50%);border-radius:20px!important;background:#0a7aff!important}.audio-player__play>img{width:22px;height:22px}.audio-player__spinner{width:17px;height:17px;border:2px solid #ffffff66;border-top-color:#fff;border-radius:50%;animation:spin .8s linear infinite}.audio-player__more-button{right:0;top:6px;width:32px;height:28px;border-radius:14px!important;background:#f0f2f7!important}.audio-player__more-button>img{width:20px;height:20px}.audio-player__more{position:absolute;z-index:5;right:12px;bottom:-64px;display:grid;width:126px;padding:6px;border:1px solid #dce5f0;border-radius:12px;background:#fff;box-shadow:0 12px 26px #14203a20}.audio-player__more button{min-height:36px;border:0;border-radius:8px;text-align:left;background:transparent}.audio-player__more button:hover{background:#f1f6fd}
@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:560px){.audio-player:not(.audio-player--instructor){grid-template-columns:1fr}}
@media(prefers-reduced-motion:reduce){.audio-player__spinner{animation:none}}
</style>
