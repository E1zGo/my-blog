import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { MAX_CHARACTERS, MAX_FILE_BYTES, MAX_PAGES } from './types'
import type { Paper, Passage } from './types'
import { pageText } from './layout'
import { fragments } from './search'

GlobalWorkerOptions.workerSrc = workerUrl
export function pdfTask(data: Uint8Array) {
  return getDocument({ data, cMapUrl: '/pdfjs/cmaps/', cMapPacked: true,
    standardFontDataUrl: '/pdfjs/standard_fonts/', wasmUrl: '/pdfjs/wasm/',
    enableXfa: false, stopAtErrors: false })
}
export async function importPdf(file: File, signal: AbortSignal, progress: (current: number, total: number) => void): Promise<Paper> {
  if (!/\.pdf$/i.test(file.name)) throw new Error('请选择 PDF 文件。')
  if (!file.size || file.size > MAX_FILE_BYTES) throw new Error('请选择大小在 1 字节至 200 MB 之间的 PDF。')
  signal.throwIfAborted()
  const data = new Uint8Array(await file.arrayBuffer())
  if (!new TextDecoder().decode(data.subarray(0, 1024)).includes('%PDF-')) throw new Error('文件内容不是有效 PDF。')
  const id = [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map(v => v.toString(16).padStart(2, '0')).join('')
  signal.throwIfAborted()
  const task = pdfTask(data)
  const cancel = () => { void task.destroy() }
  signal.addEventListener('abort', cancel, { once: true })
  try {
    const pdf = await task.promise
    if (pdf.numPages > MAX_PAGES) throw new Error(`浏览器版每篇最多 ${MAX_PAGES} 页，请拆分后导入。`)
    const passages: Passage[] = []
    const emptyPages: number[] = []
    let characters = 0
    progress(0, pdf.numPages)
    for (let number = 1; number <= pdf.numPages; number++) {
      signal.throwIfAborted()
      const page = await pdf.getPage(number)
      const content = await page.getTextContent()
      const text = pageText(content.items.filter(item => 'str' in item), page.getViewport({ scale: 1 }).width)
      characters += text.length
      if (characters > MAX_CHARACTERS) throw new Error('文本超过 100 万字，请拆分论文后导入。')
      if (!text.trim()) emptyPages.push(number)
      passages.push(...fragments(text, number))
      page.cleanup()
      progress(number, pdf.numPages)
    }
    signal.throwIfAborted()
    return { id, name: file.name.slice(0, 180), size: file.size, pageCount: pdf.numPages, passages, emptyPages,
      createdAt: new Date().toISOString(), lastPage: 1 }
  } catch (error) {
    if (signal.aborted) throw new Error(signal.reason === 'timeout' ? '解析超过 3 分钟，已停止；请拆分 PDF 后重试。' : '已取消导入，没有保存新资料。')
    if (error instanceof Error && error.name === 'PasswordException') throw new Error('暂不支持加密 PDF，请先在本机解除密码保护后导入。')
    throw error
  } finally {
    signal.removeEventListener('abort', cancel)
    await task.destroy()
  }
}
