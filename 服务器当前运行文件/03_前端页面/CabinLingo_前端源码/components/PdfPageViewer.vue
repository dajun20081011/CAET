<template>
  <section class="pdf-viewer" aria-label="PDF 课程页面">
    <div class="pdf-viewer__bar">
      <strong>原始 PDF 课件</strong>
      <span v-if="pageCount">第 {{ pageNumber }} / {{ pageCount }} 页</span>
    </div>
    <div class="pdf-viewer__canvas-wrap">
      <p v-if="loading" class="pdf-viewer__hint">正在载入课件…</p>
      <p v-else-if="errorMessage" class="pdf-viewer__hint pdf-viewer__hint--error">{{ errorMessage }}</p>
      <canvas ref="canvas" aria-label="PDF 页面预览" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy, type RenderTask } from 'pdfjs-dist'
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

GlobalWorkerOptions.workerSrc = workerSrc

const props = withDefaults(defineProps<{
  bytes: Uint8Array | null
  pageNumber?: number
  pageCount?: number | null
}>(), { pageNumber: 1, pageCount: null })

const canvas = ref<HTMLCanvasElement | null>(null)
const loading = ref(false)
const errorMessage = ref('')
let documentProxy: PDFDocumentProxy | null = null
let renderTask: RenderTask | null = null
let generation = 0

async function renderPage() {
  const currentGeneration = ++generation
  renderTask?.cancel()
  renderTask = null
  documentProxy?.destroy()
  documentProxy = null
  errorMessage.value = ''
  const target = canvas.value
  if (!target || !props.bytes) return
  loading.value = true
  try {
    const loadingTask = getDocument({ data: props.bytes })
    documentProxy = await loadingTask.promise
    if (currentGeneration !== generation) return
    const page = await documentProxy.getPage(Math.max(1, Math.min(props.pageNumber, documentProxy.numPages)))
    const baseViewport = page.getViewport({ scale: 1 })
    const maxWidth = Math.max(target.parentElement?.clientWidth || 720, 320)
    const scale = Math.min(1.8, Math.max(0.75, (maxWidth - 24) / baseViewport.width))
    const viewport = page.getViewport({ scale })
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
    target.width = Math.ceil(viewport.width * pixelRatio)
    target.height = Math.ceil(viewport.height * pixelRatio)
    target.style.width = `${Math.ceil(viewport.width)}px`
    target.style.height = `${Math.ceil(viewport.height)}px`
    renderTask = page.render({ canvasContext: target.getContext('2d')!, viewport, transform: [pixelRatio, 0, 0, pixelRatio, 0, 0] })
    await renderTask.promise
  } catch (error) {
    if (error instanceof Error && error.name === 'RenderingCancelledException') return
    if (currentGeneration === generation) errorMessage.value = 'PDF 课件载入失败，请重新打开本篇'
  } finally {
    if (currentGeneration === generation) loading.value = false
  }
}

watch(() => [props.bytes, props.pageNumber], renderPage, { immediate: true })
onBeforeUnmount(() => {
  generation += 1
  renderTask?.cancel()
  documentProxy?.destroy()
})
</script>

<style scoped>
.pdf-viewer{margin:16px 0;border:1px solid #dfe7f3;border-radius:14px;background:#f5f8fc;overflow:hidden}.pdf-viewer__bar{display:flex;justify-content:space-between;gap:12px;padding:11px 14px;color:#31517f;font-size:12px;background:#edf3fb}.pdf-viewer__bar span{color:#71819d}.pdf-viewer__canvas-wrap{display:grid;place-items:center;min-height:280px;padding:12px;overflow:auto}.pdf-viewer canvas{display:block;max-width:100%;height:auto;box-shadow:0 8px 24px #24478124;background:#fff}.pdf-viewer__hint{margin:0;color:#71819d;font-size:12px}.pdf-viewer__hint--error{color:#b14c5d}
</style>
