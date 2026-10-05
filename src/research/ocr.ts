import { createWorker } from 'tesseract.js'

export async function ocrWorker(language: 'eng' | 'eng+chi_sim', signal: AbortSignal, progress: (message: string) => void) {
  signal.throwIfAborted()
  let worker: Awaited<ReturnType<typeof createWorker>> | undefined
  let rejectAbort: (reason: unknown) => void = () => {}
  const stopped = new Promise<never>((_, reject) => { rejectAbort = reject })
  const abort = () => { void worker?.terminate(); rejectAbort(new DOMException('OCR 已停止，已保存的页面仍保留。', 'AbortError')) }
  signal.addEventListener('abort', abort, { once: true })
  let timer: ReturnType<typeof setTimeout> | undefined
  const resetTimer = () => { clearTimeout(timer); timer = setTimeout(() => { void worker?.terminate(); rejectAbort(new Error('单页 OCR 超过 2 分钟，已暂停。可以更换识别语言或拆分文件后重试。')) }, 120_000) }
  resetTimer()
  let closed = false
  const starting = createWorker(language, 1, { workerPath: '/ocr/worker.min.js', corePath: '/ocr/core', langPath: '/ocr/lang', workerBlobURL: false,
    logger: event => { if (event.status === 'recognizing text') progress(`文字识别 ${Math.round(event.progress * 100)}%`); else progress('正在加载本地 OCR 引擎与语言数据…') },
    errorHandler: () => rejectAbort(new Error('OCR 引擎加载或识别失败，请检查网络、刷新页面后重试。')),
  }).then(value => { worker = value; if (closed || signal.aborted) { void value.terminate(); throw new DOMException('OCR 已停止。', 'AbortError') }; return value })
  try {
    await Promise.race([starting, stopped]); clearTimeout(timer)
    return {
      async recognize(canvas: HTMLCanvasElement) {
        signal.throwIfAborted(); resetTimer()
        try {
          const { data } = await Promise.race([worker!.recognize(canvas), stopped])
          signal.throwIfAborted()
          return { text: data.text.trim(), confidence: Math.max(0, Math.min(100, data.confidence)) }
        } finally { clearTimeout(timer) }
      },
      async close() { closed = true; clearTimeout(timer); signal.removeEventListener('abort', abort); await worker?.terminate() },
    }
  } catch (error) { closed = true; clearTimeout(timer); signal.removeEventListener('abort', abort); await worker?.terminate(); throw error }
}
