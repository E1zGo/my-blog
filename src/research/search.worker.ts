/// <reference lib="webworker" />
import { search } from './search'
import type { Passage } from './types'
self.onmessage = (event: MessageEvent<{ id: number; query: string; passages: Passage[]; first: number; last: number }>) => {
  const { id, query, passages, first, last } = event.data
  try { self.postMessage({ id, ...search(query, passages, first, last) }) }
  catch { self.postMessage({ id, error: '检索未完成，请缩小范围后再试。' }) }
}
