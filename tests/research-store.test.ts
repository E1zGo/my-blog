import 'fake-indexeddb/auto'
import test from 'node:test'
import assert from 'node:assert/strict'
import { listPapers, readFile, savePaper, savePosition, saveNote, listNotes, removePaper, storageError } from '../src/research/store.ts'
import { MAX_FILE_BYTES, MAX_PAPERS } from '../src/research/types.ts'
import type { Paper } from '../src/research/types.ts'

const blob = new Blob(['%PDF-1.4 test bytes'])
const paper = (id: string): Paper => ({ id, name: `${id}.pdf`, size: blob.size, pageCount: 4, passages: [{ page: 2, ordinal: 0, text: 'loss function' }], emptyPages: [], createdAt: '2026-10-04', lastPage: 1 })
const note = (paperId: string, id = 'note') => ({ id, paperId, page: 2, body: '理解', quote: 'loss function', createdAt: '2026-10-04' })

test('local database commits originals, deduplicates, validates notes and deletes only one paper', async () => {
  assert.equal(await savePaper(paper('a'), blob), false)
  assert.equal(await savePaper(paper('b'), blob), false)
  await savePosition('a', 3)
  assert.equal(await savePaper(paper('a'), new Blob(['different'])), true)
  assert.equal((await listPapers()).find(p => p.id === 'a')!.lastPage, 3)
  assert.equal(await (await readFile('a')).text(), await blob.text())
  await savePosition('a', 99)
  assert.equal((await listPapers()).find(p => p.id === 'a')!.lastPage, 3)
  await saveNote(note('a', 'a-note'))
  await saveNote(note('b', 'b-note'))
  await savePaper({ ...paper('a'), passages: [{ page: 2, ordinal: 0, text: 'Updated clean text' }] }, blob)
  assert.equal((await listPapers()).find(p => p.id === 'a')!.passages[0].text, 'Updated clean text')
  assert.equal((await listPapers()).find(p => p.id === 'a')!.lastPage, 3)
  await assert.rejects(saveNote({ ...note('a', 'bad'), page: 5 }), /页码/)
  await assert.rejects(saveNote(note('missing', 'orphan')), /论文/)
  await assert.rejects(saveNote({ ...note('a', 'empty'), body: '   ' }), /笔记/)
  assert.equal((await listNotes('a')).length, 1)
  await removePaper('a')
  await assert.rejects(readFile('a'), /重新导入/)
  assert.equal((await listNotes('a')).length, 0)
  assert.equal((await listNotes('b')).length, 1)
  assert.equal((await listPapers()).length, 1)
  await removePaper('b')
})

test('capacity enforcement is atomic and concurrent imports cannot exceed the limit', async () => {
  const results = await Promise.allSettled(Array.from({ length: MAX_PAPERS + 2 }, (_, i) => savePaper(paper(`capacity-${i}`), blob)))
  assert.equal(results.filter(r => r.status === 'fulfilled').length, MAX_PAPERS)
  assert.equal((await listPapers()).length, MAX_PAPERS)
  await assert.rejects(readFile(`capacity-${MAX_PAPERS}`), /重新导入/)
  assert.equal(await savePaper(paper('capacity-0'), blob), true)
  for (const p of await listPapers()) await removePaper(p.id)
})

test('200 MiB limit rejects excess bytes before opening a transaction', async () => {
  assert.equal(MAX_FILE_BYTES, 209715200)
  await assert.rejects(savePaper(paper('oversize'), { size: MAX_FILE_BYTES + 1 } as Blob), /200 MB/)
  assert.equal((await listPapers()).length, 0)
  assert.match(storageError(new DOMException('full', 'QuotaExceededError')), /空间不足/)
})
