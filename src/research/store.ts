import { MAX_CHARACTERS, MAX_FILE_BYTES, MAX_PAPERS } from './types.ts'
import type { Note, Paper, ResearchResult } from './types.ts'
import { fragments } from './search.ts'

const DATABASE = 'researchpilot-browser-v1'
let opening: Promise<IDBDatabase> | undefined
function database(): Promise<IDBDatabase> {
  if (opening) return opening
  opening = new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 2)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains('papers')) db.createObjectStore('papers', { keyPath: 'id' })
      if (!db.objectStoreNames.contains('files')) db.createObjectStore('files', { keyPath: 'id' })
      if (!db.objectStoreNames.contains('notes')) db.createObjectStore('notes', { keyPath: 'id' }).createIndex('paper', 'paperId')
      if (!db.objectStoreNames.contains('results')) db.createObjectStore('results', { keyPath: 'id' }).createIndex('paper', 'paperId')
    }
    request.onerror = () => { opening = undefined; reject(request.error) }
    request.onblocked = () => { opening = undefined; reject(new Error('请关闭其他 ResearchPilot 标签页后重试。')) }
    request.onsuccess = () => {
      const db = request.result
      db.onversionchange = () => { db.close(); opening = undefined }
      resolve(db)
    }
  })
  return opening
}
function result<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => { request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error) })
}
function completed(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => { tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error || new Error('本地保存已取消。')) })
}
export async function listPapers(): Promise<Paper[]> {
  const db = await database()
  return (await result<Paper[]>(db.transaction('papers').objectStore('papers').getAll())).sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}
export async function readFile(id: string): Promise<Blob> {
  const db = await database()
  const row = await result<{ id: string; blob: Blob } | undefined>(db.transaction('files').objectStore('files').get(id))
  if (!row) throw new Error('原文件已不在浏览器存储中，请重新导入。')
  return row.blob
}
export async function savePaper(paper: Paper, blob: Blob): Promise<boolean> {
  if (blob.size > MAX_FILE_BYTES) throw new Error('单篇 PDF 不能超过 200 MB。')
  const db = await database()
  const tx = db.transaction(['papers', 'files'], 'readwrite')
  const done = completed(tx)
  let duplicate = false
  let failure = ''
  const papers = tx.objectStore('papers')
  papers.get(paper.id).onsuccess = event => {
    const existing = (event.target as IDBRequest<Paper | undefined>).result
    if (existing) {
      duplicate = true
      const ocrPages = Object.keys(existing.ocrPages || {}).map(Number)
      papers.put({ ...existing, passages: [...paper.passages.filter(p => !ocrPages.includes(p.page)), ...existing.passages.filter(p => ocrPages.includes(p.page))].sort((a, b) => a.page - b.page || a.ordinal - b.ordinal), emptyPages: paper.emptyPages.filter(p => !ocrPages.includes(p)),
        pageCount: paper.pageCount, lastPage: Math.min(existing.lastPage, paper.pageCount) })
      return
    }
    papers.count().onsuccess = count => {
      if ((count.target as IDBRequest<number>).result >= MAX_PAPERS) { failure = `浏览器工作台最多保留 ${MAX_PAPERS} 篇论文，请先导出并移除不需要的资料。`; tx.abort(); return }
      papers.add(paper)
      tx.objectStore('files').add({ id: paper.id, blob })
    }
  }
  try { await done } catch (error) { throw failure ? new Error(failure) : error }
  return duplicate
}
export async function savePosition(id: string, page: number): Promise<void> {
  const db = await database()
  const tx = db.transaction('papers', 'readwrite')
  const done = completed(tx)
  const store = tx.objectStore('papers')
  store.get(id).onsuccess = event => {
    const paper = (event.target as IDBRequest<Paper | undefined>).result
    if (paper && Number.isInteger(page) && page >= 1 && page <= paper.pageCount) store.put({ ...paper, lastPage: page })
  }
  await done
}
export async function listNotes(paperId: string): Promise<Note[]> {
  const db = await database()
  return (await result<Note[]>(db.transaction('notes').objectStore('notes').index('paper').getAll(paperId))).sort((a, b) => a.createdAt.localeCompare(b.createdAt))
}
export async function saveNote(note: Note): Promise<void> {
  if (!note.body.trim() || note.body.length > 10000 || note.quote.length > 1500) throw new Error('笔记须为 1–10000 字，引用最多 1500 字。')
  const db = await database()
  const tx = db.transaction(['notes', 'papers'], 'readwrite')
  const done = completed(tx)
  let failure = ''
  tx.objectStore('papers').get(note.paperId).onsuccess = event => {
    const paper = (event.target as IDBRequest<Paper | undefined>).result
    if (!paper || !Number.isInteger(note.page) || note.page < 1 || note.page > paper.pageCount) { failure = '论文或页码已失效，请重新选择。'; tx.abort(); return }
    tx.objectStore('notes').index('paper').count(note.paperId).onsuccess = count => {
      if ((count.target as IDBRequest<number>).result >= 200) { failure = '每篇论文最多 200 条笔记，请先导出整理。'; tx.abort(); return }
      tx.objectStore('notes').add(note)
    }
  }
  try { await done } catch (error) { throw failure ? new Error(failure) : error }
}
export async function removePaper(id: string): Promise<void> {
  const db = await database()
  const tx = db.transaction(['papers', 'files', 'notes', 'results'], 'readwrite')
  const done = completed(tx)
  tx.objectStore('papers').delete(id)
  tx.objectStore('files').delete(id)
  tx.objectStore('notes').index('paper').openCursor(IDBKeyRange.only(id)).onsuccess = event => {
    const cursor = (event.target as IDBRequest<IDBCursorWithValue | null>).result
    if (cursor) { cursor.delete(); cursor.continue() }
  }
  tx.objectStore('results').index('paper').openCursor(IDBKeyRange.only(id)).onsuccess = event => {
    const cursor = (event.target as IDBRequest<IDBCursorWithValue | null>).result
    if (cursor) { cursor.delete(); cursor.continue() }
  }
  await done
}
export async function saveOcrPage(id: string, page: number, text: string, confidence: number, reviewed: boolean): Promise<void> {
  if (!text.trim() || text.length > 100_000 || !Number.isFinite(confidence) || confidence < 0 || confidence > 100) throw new Error('OCR 文本为空、过长或置信度无效，请核对后再保存。')
  const db = await database(); const tx = db.transaction('papers', 'readwrite'); const done = completed(tx)
  let failure = ''
  const store = tx.objectStore('papers')
  store.get(id).onsuccess = event => {
    const paper = (event.target as IDBRequest<Paper | undefined>).result
    if (!paper || !Number.isInteger(page) || page < 1 || page > paper.pageCount) { failure = '论文或页码已失效。'; tx.abort(); return }
    const passages = [...paper.passages.filter(p => p.page !== page), ...fragments(text, page)].sort((a, b) => a.page - b.page || a.ordinal - b.ordinal)
    if (passages.reduce((n, p) => n + p.text.length, 0) > MAX_CHARACTERS) { failure = '识别后文字超过 100 万字，请拆分论文。'; tx.abort(); return }
    store.put({ ...paper, passages, emptyPages: paper.emptyPages.filter(p => p !== page), ocrPages: { ...paper.ocrPages, [page]: { confidence, reviewed, updatedAt: new Date().toISOString() } } })
  }
  try { await done } catch (error) { throw failure ? new Error(failure) : error }
}
export async function listResults(paperId: string): Promise<ResearchResult[]> {
  const db = await database()
  return (await result<ResearchResult[]>(db.transaction('results').objectStore('results').index('paper').getAll(paperId))).sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}
export async function saveResult(record: ResearchResult): Promise<void> {
  if (!['answer', 'formula', 'translation'].includes(record.kind) || JSON.stringify(record).length > 150_000 || !record.id || record.id.length > 200) throw new Error('结果格式不正确或内容过大，未保存。')
  const db = await database(); const tx = db.transaction(['results', 'papers'], 'readwrite'); const done = completed(tx)
  let failure = ''
  tx.objectStore('papers').get(record.paperId).onsuccess = event => {
    const paper = (event.target as IDBRequest<Paper | undefined>).result
    if (!paper || !Number.isInteger(record.page) || record.page < 1 || record.page > paper.pageCount) { failure = '论文已移除或页码无效，结果未保存。'; tx.abort(); return }
    const store = tx.objectStore('results')
    store.get(record.id).onsuccess = existingEvent => {
      const existing = (existingEvent.target as IDBRequest<ResearchResult | undefined>).result
      if (existing && existing.paperId !== record.paperId) { failure = '结果标识冲突，未覆盖其他论文。'; tx.abort(); return }
      store.index('paper').count(record.paperId).onsuccess = countEvent => {
        if (!existing && (countEvent.target as IDBRequest<number>).result >= 2500) { failure = '当前论文已达 2500 条处理结果，请先导出。'; tx.abort(); return }
        store.put(record)
      }
    }
  }
  try { await done } catch (error) { throw failure ? new Error(failure) : error }
}
export function storageError(error: unknown): string {
  if (error instanceof DOMException && error.name === 'QuotaExceededError') return '浏览器空间不足，资料没有保存。请先导出并移除旧资料，或换用空间充足的浏览器。'
  return error instanceof Error ? error.message : '浏览器存储暂不可用，请确认没有禁用网站数据，并避免使用隐私模式。'
}
