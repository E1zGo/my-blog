import 'fake-indexeddb/auto'
import test from 'node:test'
import assert from 'node:assert/strict'
import { listPapers, listNotes, readFile, listResults } from '../src/research/store.ts'

test('v1 database upgrades without dropping originals, notes or reading positions', async () => {
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.open('researchpilot-browser-v1', 1)
    request.onupgradeneeded = () => {
      const db = request.result
      db.createObjectStore('papers', { keyPath: 'id' }); db.createObjectStore('files', { keyPath: 'id' }); db.createObjectStore('notes', { keyPath: 'id' }).createIndex('paper', 'paperId')
    }
    request.onerror = () => reject(request.error)
    request.onsuccess = () => {
      const db = request.result; const tx = db.transaction(['papers', 'files', 'notes'], 'readwrite')
      tx.objectStore('papers').add({ id: 'old', name: 'old.pdf', lastPage: 3, createdAt: '2026-10-04' })
      tx.objectStore('files').add({ id: 'old', blob: new Blob(['old original']) })
      tx.objectStore('notes').add({ id: 'note', paperId: 'old', body: '保留的笔记', createdAt: '2026-10-04' })
      tx.oncomplete = () => { db.close(); resolve() }; tx.onerror = () => reject(tx.error)
    }
  })
  assert.equal((await listPapers())[0].lastPage, 3)
  assert.equal((await listNotes('old'))[0].body, '保留的笔记')
  assert.equal(await (await readFile('old')).text(), 'old original')
  assert.deepEqual(await listResults('old'), [])
})
