import test from 'node:test'
import assert from 'node:assert/strict'
import { expand, fragments, search } from '../src/research/search.ts'
import { pageText } from '../src/research/layout.ts'
import { notesMarkdown } from '../src/research/export.ts'
import type { Paper } from '../src/research/types.ts'

test('Chinese scientific questions find English evidence without inventing answers', () => {
  const passages = [
    { page: 1, ordinal: 0, text: 'Introduction to images and datasets.' },
    { page: 2, ordinal: 0, text: 'The loss function is a weighted sum of reconstruction loss and regularization.' },
    { page: 3, ordinal: 0, text: 'Limitations include computational cost and image resolution.' },
  ]
  const result = search('这篇论文的损失函数是什么？', passages)
  assert.equal(result.hits[0].page, 2)
  assert.equal(result.hits[0].text, passages[1].text)
  assert.ok(result.expansion.some(e => e.term === '损失函数'))
  assert.equal(search('损失函数', passages, 3, 3).hits.length, 0)
  assert.equal(search('nonsense_unrelated_token', passages).hits.length, 0)
})

test('longest Chinese term is expanded once', () => {
  const terms = expand('低光照图像增强与图像增强')
  assert.equal(terms.filter(t => t.term === '低光照图像增强').length, 1)
  assert.equal(terms.filter(t => t.term === '图像增强').length, 1)
})

test('equation lookup uses equation markers rather than PDF page numbers', () => {
  const docs = [
    { page: 8, ordinal: 0, text: 'Related work [8] and no equations.' },
    { page: 3, ordinal: 0, text: 'E = mc2 (8)' },
  ]
  assert.deepEqual(search('公式8', docs).hits.map(h => h.page), [3])
})

test('chunks are bounded, complete, non-overlapping and retain page provenance', () => {
  const text = Array.from({ length: 220 }, (_, i) => `Unique sentence ${i}.`).join(' ')
  const chunks = fragments(text, 9)
  assert.ok(chunks.length > 1)
  assert.ok(chunks.every(c => c.text.length <= 900 && c.page === 9))
  assert.equal(chunks.map(c => c.text).join(' '), text)
  assert.deepEqual(chunks.map(c => c.ordinal), chunks.map((_, i) => i))
})

test('two-column pages read down each column and preserve full-width headings', () => {
  const box = (str: string, x: number, y: number, width: number) => ({ str, transform: [10, 0, 0, 10, x, y], width, height: 10 })
  const items = [box('Full width heading', 40, 750, 500)]
  for (let i = 0; i < 4; i++) items.push(box(`Left ${i}`, 40, 700 - i * 20, 180), box(`Right ${i}`, 330, 700 - i * 20, 180))
  assert.equal(pageText(items.reverse(), 600), 'Full width heading\nLeft 0\nLeft 1\nLeft 2\nLeft 3\nRight 0\nRight 1\nRight 2\nRight 3')
})

test('single-column extraction joins line-break hyphenation', () => {
  const boxes = ['recon-', 'struction'].map((str, i) => ({ str, transform: [10, 0, 0, 10, 30, 200 - i * 20], width: 60, height: 10 }))
  assert.equal(pageText(boxes, 600), 'reconstruction')
})

test('staggered double-column baselines stay in separate reading order', () => {
  const box = (str: string, x: number, y: number) => ({ str, transform: [10, 0, 0, 10, x, y], width: 235, height: 10 })
  const left = Array.from({ length: 5 }, (_, i) => `Left paragraph sentence number ${i}.`)
  const right = Array.from({ length: 5 }, (_, i) => `Right paragraph sentence number ${i}.`)
  const items = left.map((s, i) => box(s, 50, 240 - i * 12)).concat(right.map((s, i) => box(s, 309, 234 - i * 12)))
  assert.equal(pageText(items, 612), [...left, ...right].join('\n'))
})

test('section headings begin a fresh passage instead of trailing figure labels', () => {
  const text = 'Original 13.93 0.63 75.16\nFigure 4. Qualitative results.\n5. Loss Function\nThe reconstruction loss recovers the original image.'
  const chunks = fragments(text, 6)
  assert.equal(chunks.length, 2)
  assert.ok(chunks[1].text.startsWith('5. Loss Function'))
  assert.equal(chunks.map(c => c.text).join('\n'), text)
})

test('note export retains source hash, page, quote and user writing', () => {
  const paper = { name: 'test.pdf', id: 'abc123' } as Paper
  const output = notesMarkdown(paper, [{ id: 'n', paperId: paper.id, page: 4, quote: 'first\nsecond', body: '我的理解', createdAt: '2026-10-04' }])
  for (const part of ['abc123', '第 4 页', '> first\n> second', '我的理解']) assert.ok(output.includes(part))
})
