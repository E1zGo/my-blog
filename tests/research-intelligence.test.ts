import 'fake-indexeddb/auto'
import test from 'node:test'
import assert from 'node:assert/strict'
import { createCompletion, endpoint, jsonObject } from '../src/research/model.ts'
import type { Completion, ModelSettings } from '../src/research/model.ts'
import { askPaper, checkCitations, parseFormula, selectEvidence, translationParts, translatePart } from '../src/research/intelligence.ts'
import { listPapers, listResults, readFile, removePaper, saveOcrPage, savePaper, saveResult } from '../src/research/store.ts'
import type { Paper, ResearchResult } from '../src/research/types.ts'

const settings: ModelSettings = { baseUrl: 'https://model.example/v1/', model: 'text', visionModel: 'vision', apiKey: 'secret-test-key' }
const signal = () => new AbortController().signal
const paper = (): Paper => ({ id: 'science', name: 'paper.pdf', size: 10, pageCount: 4, emptyPages: [3], lastPage: 2, createdAt: '2026-10-05', passages: [
  { page: 1, ordinal: 0, text: 'Abstract: A denoising estimator uses a robust reconstruction objective.' },
  { page: 2, ordinal: 0, text: 'The robust objective uses a Huber penalty to reduce sensitivity to outliers.' },
  { page: 4, ordinal: 0, text: 'Limitations: The noise assumption may fail for sensor shifts.' },
] })
const response = (content: string, finish_reason = 'stop') => new Response(JSON.stringify({ choices: [{ message: { content }, finish_reason }] }))

test('model endpoints reject credentials, query secrets, remote HTTP and normalize one completion suffix', () => {
  assert.equal(endpoint('https://model.example/v1/'), 'https://model.example/v1/chat/completions')
  assert.equal(endpoint('http://localhost:11434/v1/chat/completions'), 'http://localhost:11434/v1/chat/completions')
  for (const address of ['http://model.example/v1', 'https://user:pass@model.example/v1', 'https://model.example/v1?key=secret', 'https://model.example/#secret', 'javascript:alert(1)']) assert.throws(() => endpoint(address))
})
test('model requests omit cookies and redirects, send image to vision model, and never put key in body', async () => {
  let called = false
  const complete = createCompletion(settings, async (url, init) => {
    called = true
    assert.equal(url, 'https://model.example/v1/chat/completions')
    assert.equal(init!.credentials, 'omit'); assert.equal(init!.redirect, 'error'); assert.equal(init!.referrerPolicy, 'no-referrer')
    const body = JSON.parse(init!.body as string)
    assert.equal(body.model, 'vision'); assert.ok(!JSON.stringify(body).includes(settings.apiKey))
    assert.equal((init!.headers as Record<string, string>).Authorization, 'Bearer secret-test-key')
    return response('公式结果')
  })
  assert.equal(await complete([{ role: 'user', content: [{ type: 'image_url', image_url: { url: 'data:image/png;base64,abc', detail: 'high' } }] }], signal(), true), '公式结果')
  assert.ok(called)
})
test('HTTP errors cannot reflect upstream secrets into the UI', async () => {
  const complete = createCompletion(settings, async () => new Response('secret-test-key was rejected', { status: 401 }))
  await assert.rejects(complete([], signal()), error => error instanceof Error && /401/.test(error.message) && !error.message.includes('secret-test-key'))
})
test('network errors are sanitized and invalid, refused, oversized and truncated responses are rejected', async () => {
  await assert.rejects(createCompletion(settings, async () => { throw new Error('secret-test-key') })([], signal()), /CORS/)
  for (const r of [response('partial', 'length'), new Response('not-json'), response(''), response('x'.repeat(100001)), new Response(JSON.stringify({ choices: [{ message: { refusal: 'no' } }] }))]) {
    await assert.rejects(createCompletion(settings, async () => r)([], signal()))
  }
  await assert.rejects(createCompletion(settings, async () => new Response('x'.repeat(2_000_001)))([], signal()), /响应过大/)
})
test('already-cancelled tasks do not send a model request', async () => {
  const controller = new AbortController(); controller.abort()
  let count = 0
  await assert.rejects(createCompletion(settings, async () => { count++; return response('ok') })([], controller.signal))
  assert.equal(count, 0)
})
test('structured responses permit JSON fences but reject nonobjects and malformed content', () => {
  assert.deepEqual(jsonObject('```json\n{"a":1}\n```'), { a: 1 })
  for (const text of ['[]', 'null', 'hello', '{bad}']) assert.throws(() => jsonObject(text))
})
test('multilingual question uses model English expressions, source page limits and real evidence', async () => {
  const calls: string[] = []
  const complete: Completion = async messages => {
    calls.push(JSON.stringify(messages))
    return calls.length === 1 ? '{"queries":["Huber penalty outliers"],"overview":false}' : '采用稳健惩罚来减弱异常值影响 [E1]。'
  }
  const result = await askPaper(paper(), '少量离群点为什么不会主导这个目标？', 2, 2, complete, signal(), () => {})
  assert.equal(result.evidence[0].page, 2); assert.equal(result.warnings.length, 0)
  assert.ok(result.evidence.every(e => e.page === 2))
  assert.ok(calls[1].includes('Huber')); assert.ok(!calls[1].includes('sensor shifts'))
})
test('missing matches and empty OCR pages stop before answer generation', async () => {
  let calls = 0
  const complete: Completion = async () => { calls++; return '{"queries":["nonexistent987"],"overview":false}' }
  await assert.rejects(askPaper(paper(), 'question', 2, 2, complete, signal(), () => {}), /未找到匹配证据/)
  assert.equal(calls, 1)
  await assert.rejects(askPaper(paper(), 'question', 3, 3, complete, signal(), () => {}), /OCR/)
  assert.equal(calls, 1)
})
test('citations reject invented identifiers without treating an uncited answer as verified', () => {
  const evidence = selectEvidence(paper(), ['Huber'], 1, 4, false)
  const result = checkCitations('这是原文 [E1]，这是虚构引用 [E999]。', evidence)
  assert.match(result.text, /引用无效/); assert.equal(result.warnings.length, 1)
  assert.equal(checkCitations('没有引用的说法', evidence).warnings.length, 1)
})
test('formula parsing preserves structure and assumptions and rejects absent formula', () => {
  const f = { latex: '\\frac{x^2}{2}', symbols: [{ symbol: 'x', meaning: '变量' }], structure: '分式', assumptions: 'x 为实数', steps: [{ equation: 'f\'(x)=x', explanation: '幂函数求导' }], verification: '未执行代数验证', uncertainty: '核对原文' }
  assert.deepEqual(parseFormula(JSON.stringify(f)), f)
  assert.throws(() => parseFormula(JSON.stringify({ ...f, latex: '' })), /没有识别/)
  assert.throws(() => parseFormula(JSON.stringify({ ...f, steps: 'invented' })), /结构/)
})
test('translation cache fingerprints source, model and glossary and is stable across selected ranges', async () => {
  const all = await translationParts(paper(), 1, 4, 'model-a', '')
  const page2 = await translationParts(paper(), 2, 2, 'model-a', '')
  assert.equal(all.length, 3); assert.equal(page2[0].key, all[1].key)
  assert.notEqual((await translationParts(paper(), 2, 2, 'model-b', ''))[0].key, page2[0].key)
  assert.notEqual((await translationParts(paper(), 2, 2, 'model-a', 'Huber=胡贝尔'))[0].key, page2[0].key)
  const changed = paper(); changed.passages[1].text += ' corrected OCR'
  assert.notEqual((await translationParts(changed, 2, 2, 'model-a', ''))[0].key, page2[0].key)
})
test('translation sends complete bounded segments and stores original text with page provenance', async () => {
  const p = paper(); p.passages = Array.from({ length: 12 }, (_, ordinal) => ({ page: 2, ordinal, text: `Paragraph ${ordinal}: ` + 'text '.repeat(170) }))
  const parts = await translationParts(p, 1, 4, 'model', '')
  assert.ok(parts.every(part => part.source.length < 3502 && part.page === 2))
  assert.equal(parts.map(part => part.source).join('\n\n'), p.passages.map(p => p.text.trim()).join('\n\n'))
  const translated = await translatePart(parts[0], '', async () => '{"translation":"中文译文","warnings":"核对公式"}', signal())
  assert.equal(translated.source, parts[0].source); assert.equal(translated.page, 2)
})
test('OCR corrections persist atomically, preserve originals/position, survive reparse and enforce size', async () => {
  const p = paper(); const blob = new Blob(['original-pdf'])
  await savePaper(p, blob)
  await saveOcrPage(p.id, 3, 'Scanned evidence of reconstruction', 83, false)
  let saved = (await listPapers()).find(v => v.id === p.id)!
  assert.ok(!saved.emptyPages.includes(3)); assert.equal(saved.ocrPages![3].reviewed, false)
  assert.ok(saved.passages.some(v => v.page === 3))
  await saveOcrPage(p.id, 3, 'Corrected equation context', 83, true)
  await savePaper(p, blob)
  saved = (await listPapers()).find(v => v.id === p.id)!
  assert.equal(saved.lastPage, 2); assert.equal(saved.ocrPages![3].reviewed, true)
  assert.equal(saved.passages.find(v => v.page === 3)!.text, 'Corrected equation context')
  assert.equal(await (await readFile(p.id)).text(), 'original-pdf')
  await assert.rejects(saveOcrPage(p.id, 5, 'bad', 20, false), /页码/)
  await assert.rejects(saveOcrPage(p.id, 3, 'x'.repeat(100001), 20, false), /过长/)
  await removePaper(p.id)
})
test('saved AI work survives reload, cannot resurrect deleted papers, and deletion is paper-scoped', async () => {
  const p = paper(); const other = { ...p, id: 'other' }; const blob = new Blob(['pdf'])
  await savePaper(p, blob); await savePaper(other, blob)
  const r: ResearchResult = { id: 'translation-key', paperId: p.id, page: 2, kind: 'translation', title: 'page2', model: 'test-model', createdAt: '2026-10-05', data: { text: '译文' } }
  await saveResult(r); await saveResult({ ...r, data: { text: '更新译文' } })
  assert.equal((await listResults(p.id)).length, 1)
  await assert.rejects(saveResult({ ...r, paperId: other.id }), /冲突/)
  await saveResult({ ...r, id: 'other-key', paperId: other.id })
  await removePaper(p.id)
  assert.equal((await listResults(p.id)).length, 0); assert.equal((await listResults(other.id)).length, 1)
  await assert.rejects(saveResult(r), /论文/)
  await removePaper(other.id)
})
