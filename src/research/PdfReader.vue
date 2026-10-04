<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import type { PDFDocumentLoadingTask, PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import type { Paper } from './types'
import { readFile } from './store'
import { pdfTask } from './pdf'
const props = defineProps<{ paper: Paper; page: number }>()
const emit = defineEmits<{ 'update:page': [page: number] }>()
const canvas = ref<HTMLCanvasElement>()
const zoom = ref(1)
const busy = ref(false)
const error = ref('')
let task: PDFDocumentLoadingTask | undefined
let pdf: PDFDocumentProxy | undefined
let render: RenderTask | undefined
let generation = 0
let drawing = Promise.resolve()
let drawId = 0

function draw() {
  const id = ++drawId
  const version = generation
  render?.cancel()
  drawing = drawing.catch(() => {}).then(async () => {
    if (id !== drawId || version !== generation || !pdf || !canvas.value) return
    busy.value = true; error.value = ''
    try {
      const page = await pdf.getPage(props.page)
      if (id !== drawId || version !== generation || !canvas.value) return
      const base = page.getViewport({ scale: 1 })
      const scale = Math.min(1280 * zoom.value / base.width, Math.sqrt(5_000_000 / (base.width * base.height)))
      const viewport = page.getViewport({ scale })
      canvas.value.width = Math.floor(viewport.width)
      canvas.value.height = Math.floor(viewport.height)
      render = page.render({ canvas: canvas.value, viewport })
      await render.promise
    } catch (cause) {
      if (id === drawId && version === generation && !(cause instanceof Error && cause.name === 'RenderingCancelledException')) error.value = '这一页暂时无法绘制，请重新打开论文或下载原文件查看。'
    } finally { if (id === drawId && version === generation) busy.value = false }
  })
}
function go(value: number) { if (Number.isFinite(value)) emit('update:page', Math.max(1, Math.min(props.paper.pageCount, Math.round(value)))) }
watch(() => props.paper.id, async () => {
  const version = ++generation
  ++drawId; render?.cancel(); pdf = undefined; busy.value = true; error.value = ''
  const previous = task
  task = undefined
  try {
    if (previous) await previous.destroy()
    const blob = await readFile(props.paper.id)
    if (version !== generation) return
    const data = new Uint8Array(await blob.arrayBuffer())
    if (version !== generation) return
    task = pdfTask(data)
    const document = await task.promise
    if (version !== generation) return
    pdf = document
    draw()
  } catch (cause) {
    if (version === generation) { error.value = cause instanceof Error ? cause.message : '无法打开原文件，请重新导入。'; busy.value = false }
  }
}, { immediate: true })
watch(() => [props.page, zoom.value], draw)
onBeforeUnmount(() => { ++generation; ++drawId; render?.cancel(); void task?.destroy() })
</script>

<template>
  <section class="rp-reader" aria-label="论文原文">
    <div class="rp-reader-controls">
      <button :disabled="page <= 1" @click="go(page - 1)" aria-label="上一页">←</button>
      <label>第 <input type="number" :value="page" min="1" :max="paper.pageCount" aria-label="原文页码" @change="go(Number(($event.target as HTMLInputElement).value))"> / {{ paper.pageCount }} 页</label>
      <button :disabled="page >= paper.pageCount" @click="go(page + 1)" aria-label="下一页">→</button>
      <label class="rp-zoom">清晰度 <select v-model.number="zoom" aria-label="原文清晰度"><option :value="1">标准</option><option :value="1.5">高清</option><option :value="2">超清</option></select></label>
    </div>
    <p class="rp-reader-status" role="status">{{ error || (busy ? '正在绘制原文…' : '公式与版式以这一页原文为准。') }}</p>
    <div class="rp-canvas-wrap" :aria-busy="busy"><canvas ref="canvas" v-show="!error && !busy" :aria-label="`${paper.name} 第 ${page} 页原文`">当前浏览器不支持画布，请下载原文查看。</canvas></div>
  </section>
</template>
