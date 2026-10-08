import test from 'node:test'
import assert from 'node:assert/strict'
import { createResearchHandler } from '../server/research-model.ts'
import { createHostedCompletion, hostedStatus, HOSTED_MODEL, HOSTED_ENDPOINT } from '../src/research/hosted-model.ts'

const secret = 'sk-fixture-api-key-never-publish-real-keys'
const code = 'fixture-access-code-123456'
const env = { OPENAI_API_KEY: secret, RESEARCH_ACCESS_CODE: code, RESEARCH_AI_ENABLED: 'true', RESEARCH_ALLOWED_ORIGINS: 'https://www.e1zgo.top' }
const messages = [{ role: 'system', content: '解释原文。' }, { role: 'user', content: '为什么采用 Huber loss？' }]
const payload = () => ({ status: 'completed', output: [{ type: 'reasoning', summary: [] }, { type: 'message', role: 'assistant', status: 'completed', content: [{ type: 'output_text', text: '有证据的解释 [E1]。' }] }] })
const request = (body: unknown = { messages }, headers: Record<string, string> = {}, signal?: AbortSignal) => new Request('https://www.e1zgo.top/api/research-model', { method: 'POST', signal, headers: { Origin: 'https://www.e1zgo.top', 'Content-Type': 'application/json', 'X-Research-Access-Code': code, ...headers }, body: JSON.stringify(body) })
const reply = () => Response.json(payload())
const sig = () => new AbortController().signal

test('hosted model is disabled unless explicitly enabled with both server credentials; status never bills', async () => {
  let calls = 0
  for (const config of [{}, { ...env, RESEARCH_AI_ENABLED: 'false' }, { ...env, OPENAI_API_KEY: '' }, { ...env, RESEARCH_ACCESS_CODE: '1234' }]) {
    const handle = createResearchHandler({ env: config, fetcher: async () => { calls++; return reply() } })
    const status = await handle(new Request('https://www.e1zgo.top/api/research-model'))
    assert.equal((await status.json()).enabled, false)
    assert.equal((await handle(request())).status, 503)
  }
  const status = await createResearchHandler({ env })(new Request('https://www.e1zgo.top/api/research-model'))
  assert.deepEqual(await status.json(), { enabled: true, model: HOSTED_MODEL, provider: 'OpenAI', access: 'code' })
  assert.equal(status.headers.get('cache-control'), 'no-store'); assert.equal(calls, 0)
})
test('wrong or missing codes, cross-origin requests, unknown overrides and remote image URLs never reach OpenAI', async () => {
  let calls = 0
  const handle = createResearchHandler({ env, fetcher: async () => { calls++; return reply() } })
  for (const headers of [{ 'X-Research-Access-Code': '' }, { 'X-Research-Access-Code': code + 'wrong' }, { Origin: 'https://evil.example' }, { Origin: '' }, { 'Sec-Fetch-Site': 'cross-site' }]) assert.ok((await handle(request({ messages }, headers))).status >= 400)
  for (const body of [{ messages, model: 'expensive-model' }, { messages, baseUrl: 'http://localhost' }, { messages, tools: [] }, { messages: [{ role: 'tool', content: 'fake result' }] }, { messages: [{ role: 'user', content: [{ type: 'image_url', image_url: { url: 'https://private.example/image' } }] }] }]) assert.equal((await handle(request(body))).status, 400)
  assert.equal(calls, 0)
})
test('server sends only its key to a fixed Responses endpoint and converts text/images without client credentials', async () => {
  const imageMessages = [...messages, { role: 'user', content: [{ type: 'image_url', image_url: { url: 'data:image/jpeg;base64,/9j/AA==', detail: 'high' } }] }]
  const handle = createResearchHandler({ env, fetcher: async (url, init) => {
    assert.equal(url, 'https://api.openai.com/v1/responses')
    const headers = new Headers(init!.headers)
    assert.equal(headers.get('authorization'), `Bearer ${secret}`); assert.equal(headers.has('x-research-access-code'), false)
    assert.equal(init!.redirect, 'error')
    const body = JSON.parse(init!.body as string)
    assert.equal(body.model, HOSTED_MODEL); assert.equal(body.store, false); assert.equal(body.stream, false)
    assert.deepEqual(body.reasoning, { effort: 'medium' }); assert.equal(body.max_output_tokens, 12000)
    assert.equal(body.input[0].role, 'developer'); assert.equal(body.input[2].content[0].type, 'input_image')
    assert.equal(JSON.stringify(body).includes(code), false); assert.equal(JSON.stringify(body).includes(secret), false)
    return reply()
  } })
  assert.deepEqual(await (await handle(request({ messages: imageMessages }))).json(), { text: '有证据的解释 [E1]。', model: HOSTED_MODEL })
})
test('request limits count real bytes and text even without Content-Length', async () => {
  let calls = 0
  const handle = createResearchHandler({ env, fetcher: async () => { calls++; return reply() } })
  assert.equal((await handle(request({ messages }, { 'Content-Length': '4000001' }))).status, 413)
  assert.equal((await handle(request({ messages: [{ role: 'user', content: '中'.repeat(80001) }] }))).status, 413)
  assert.equal((await handle(request({ messages: [{ role: 'user', content: '中'.repeat(1_400_000) }] }))).status, 413)
  assert.equal(calls, 0)
})
test('provider failures, truncated output, refusals and corrupt bodies are sanitized and not retried', async () => {
  const fixtures: [() => Response, string][] = [
    [() => new Response(secret + code, { status: 401 }), 'provider_error'],
    [() => new Response(secret, { status: 429 }), 'provider_limit'],
    [() => Response.json({ ...payload(), status: 'incomplete', incomplete_details: { reason: 'max_output_tokens' } }), 'incomplete_output'],
    [() => Response.json({ ...payload(), output: [{ type: 'message', role: 'assistant', status: 'completed', content: [{ type: 'refusal', refusal: secret }] }] }), 'refused'],
    [() => new Response('broken ' + secret), 'invalid_output'],
    [() => new Response('x'.repeat(2_000_001)), 'invalid_output'],
  ]
  for (const [fixture, expected] of fixtures) {
    let calls = 0
    const handle = createResearchHandler({ env, fetcher: async () => { calls++; return fixture() } })
    const result = await handle(request()); const body = await result.text()
    assert.ok(result.status >= 400); assert.deepEqual(JSON.parse(body), { error: expected })
    assert.equal(calls, 1); assert.ok(!body.includes(secret) && !body.includes(code))
  }
})
test('server handles multiple output messages and does not expose reasoning items', async () => {
  const data = payload(); data.output.push({ type: 'message', role: 'assistant', status: 'completed', content: [{ type: 'output_text', text: '补充解释。' }] })
  const handle = createResearchHandler({ env, fetcher: async () => Response.json(data) })
  assert.equal((await (await handle(request())).json()).text, '有证据的解释 [E1]。\n补充解释。')
})
test('per-instance request limit stops paid calls then resets; it is not a cross-instance spending cap', async () => {
  let clock = 0; let calls = 0
  const handle = createResearchHandler({ env, now: () => clock, fetcher: async () => { calls++; return reply() } })
  for (let i = 0; i < 12; i++) assert.equal((await handle(request())).status, 200)
  const blocked = await handle(request()); assert.equal(blocked.status, 429); assert.equal(blocked.headers.get('retry-after'), '60'); assert.equal(calls, 12)
  clock = 60_001
  assert.equal((await handle(request())).status, 200); assert.equal(calls, 13)
})
test('concurrency limit and cancellation release slots without retrying a paid request', async () => {
  let starts = 0
  const handle = createResearchHandler({ env, fetcher: async (_url, init) => {
    starts++
    return new Promise<Response>((_resolve, reject) => init!.signal!.addEventListener('abort', () => reject(new Error('cancelled')), { once: true }))
  } })
  const a = new AbortController(); const b = new AbortController()
  const one = handle(request({ messages }, {}, a.signal)); const two = handle(request({ messages }, {}, b.signal))
  while (starts < 2) await new Promise(resolve => setImmediate(resolve))
  assert.equal((await handle(request())).status, 429)
  a.abort(); b.abort()
  assert.equal((await one).status, 499); assert.equal((await two).status, 499)
  const expired = createResearchHandler({ env, timeoutMs: 5, fetcher: async (_url, init) => new Promise((_resolve, reject) => init!.signal!.addEventListener('abort', () => reject(new Error(secret)))) })
  assert.equal((await expired(request())).status, 504)
})
test('hosted browser client sends code in header only and keeps model selection on server', async () => {
  const complete = createHostedCompletion(code, async (url, init) => {
    assert.equal(url, HOSTED_ENDPOINT); assert.equal(new Headers(init!.headers).get('x-research-access-code'), code)
    assert.deepEqual(JSON.parse(init!.body as string), { messages }); assert.equal(init!.credentials, 'omit'); assert.equal(init!.redirect, 'error')
    return Response.json({ text: '中文解释', model: HOSTED_MODEL })
  })
  assert.equal(await complete(messages as any, sig(), true), '中文解释')
  const stopped = new AbortController(); stopped.abort(); let calls = 0
  await assert.rejects(createHostedCompletion(code, async () => { calls++; return reply() })(messages as any, stopped.signal))
  assert.equal(calls, 0)
  await assert.rejects(createHostedCompletion('short')(messages as any, sig()), /访问码/)
})
test('hosted browser client handles status/errors and never reflects server error text', async () => {
  assert.equal(await hostedStatus(async () => Response.json({ enabled: false, model: HOSTED_MODEL })), false)
  await assert.rejects(hostedStatus(async () => new Response('<html>SPA fallback</html>', { headers: { 'Content-Type': 'text/html' } })))
  for (const error of ['invalid_code', 'not_configured', 'incomplete_output', secret]) {
    await assert.rejects(createHostedCompletion(code, async () => Response.json({ error, message: secret }, { status: 401 }))(messages as any, sig()), e => e instanceof Error && !e.message.includes(secret))
  }
  await assert.rejects(createHostedCompletion(code, async () => Response.json({ text: 'text', model: 'other-model' }))(messages as any, sig()), /完整文本/)
})
