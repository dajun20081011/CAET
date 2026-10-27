<template>
  <section class="learning-card-viewer" :aria-busy="loading">
    <div v-if="loading || failed" class="learning-card-viewer__loading" role="status">
      <template v-if="failed"><span>学习卡片未能加载，访问地址可能已过期。</span><button type="button" class="outline-button" @click="$emit('refresh')">重新加载</button></template>
      <span v-else>正在载入学习卡片…</span>
    </div>
    <iframe
      ref="frame"
      :src="src"
      :title="title"
      sandbox="allow-scripts"
      referrerpolicy="no-referrer"
      :style="{ height: `${frameHeight}px` }"
    />
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ src: string; title?: string }>(), { title: '学习卡片' })
const emit = defineEmits<{ ready: []; refresh: [] }>()
const frame = ref<HTMLIFrameElement | null>(null)
const frameHeight = ref(680)
const loading = ref(true)
const failed = ref(false)
let deadline: ReturnType<typeof setTimeout> | undefined

function onMessage(event: MessageEvent) {
  if (event.source !== frame.value?.contentWindow || event.data?.type !== 'cabinlingo-learning-card-resize') return
  const height = Number(event.data.height)
  if (Number.isFinite(height)) {
    frameHeight.value = Math.max(480, Math.min(Math.ceil(height), 5000))
    if (loading.value) emit('ready')
    loading.value = false; failed.value = false
    clearTimeout(deadline)
  }
}

watch(() => props.src, () => {
  clearTimeout(deadline); loading.value = true; failed.value = false; frameHeight.value = 680
  deadline = setTimeout(() => { failed.value = true; loading.value = false }, 15000)
}, { immediate: true })
onMounted(() => window.addEventListener('message', onMessage))
onBeforeUnmount(() => { clearTimeout(deadline); window.removeEventListener('message', onMessage) })
</script>

<style scoped>
.learning-card-viewer{position:relative;width:100%;min-height:480px;overflow:hidden;border:1px solid #dce7f6;border-radius:18px;background:#f5f8fd;box-shadow:0 10px 30px #163d7d12}.learning-card-viewer iframe{display:block;width:100%;min-height:480px;border:0;background:#fff;transition:height .2s ease}.learning-card-viewer__loading{position:absolute;inset:0;z-index:1;display:grid;place-items:center;color:#6f809e;background:linear-gradient(135deg,#f7faff,#eef5ff);font-size:13px}@media(max-width:640px){.learning-card-viewer{margin-inline:-10px;width:calc(100% + 20px);border-radius:14px}.learning-card-viewer iframe{min-height:560px}}
</style>
