import { pdfTask } from './pdf'
import { readFile } from './store'

export async function pageRenderer(id: string, signal: AbortSignal) {
  signal.throwIfAborted()
  const task = pdfTask(new Uint8Array(await (await readFile(id)).arrayBuffer()))
  const abort = () => { void task.destroy() }
  signal.addEventListener('abort', abort, { once: true })
  try {
    signal.throwIfAborted()
    const pdf = await task.promise
    return {
      async render(number: number): Promise<HTMLCanvasElement> {
        signal.throwIfAborted()
        const page = await pdf.getPage(number)
        const base = page.getViewport({ scale: 1 })
        const viewport = page.getViewport({ scale: Math.min(2300 / Math.max(base.width, base.height), Math.sqrt(4_000_000 / (base.width * base.height))) })
        const canvas = document.createElement('canvas')
        canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height)
        const drawing = page.render({ canvas, viewport })
        const cancel = () => drawing.cancel()
        signal.addEventListener('abort', cancel, { once: true })
        try { await drawing.promise; signal.throwIfAborted(); return canvas }
        finally { signal.removeEventListener('abort', cancel); page.cleanup() }
      },
      async close() { signal.removeEventListener('abort', abort); await task.destroy() },
    }
  } catch (error) { signal.removeEventListener('abort', abort); await task.destroy(); throw error }
}
