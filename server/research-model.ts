import { createHash, timingSafeEqual } from 'node:crypto'

const MODEL = 'gpt-6.1-sol'
const MAX_BODY = 4_000_000
const MAX_TEXT = 80_000
const MAX_RESPONSE = 2_000_000
type Env = Record<string, string | undefined>
type InputPart = { type: 'input_text'; text: string } | { type: 'input_image'; image_url: string; detail: 'high' }
type Input = { role: 'developer' | 'user'; content: InputPart[] }[]
class RequestError extends Error {
  status: number
  constructor(status: number, code: string) { super(code); this.status = status }
}
function object(value: unknown): value is Record<string, unknown> { return !!value && typeof value === 'object' && !Array.isArray(value) }
function exact(value: Record<string, unknown>, keys: string[]) { if (Object.keys(value).some(key => !keys.includes(key))) throw new RequestError(400, 'invalid_request') }
function reply(data: unknown, status = 200) {
  return Response.json(data, { status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...(status === 429 ? { 'Retry-After': '60' } : {}) } })
}
async function readJson(body: ReadableStream<Uint8Array> | null, limit: number, signal: AbortSignal): Promise<unknown> {
  if (!body) throw new RequestError(400, 'invalid_request')
  const reader = body.getReader(); const decoder = new TextDecoder('utf-8', { fatal: true })
  const abort = () => { void reader.cancel().catch(() => {}) }
  signal.addEventListener('abort', abort, { once: true })
  let bytes = 0; let text = ''
  try {
    while (true) {
      signal.throwIfAborted()
      const item = await reader.read()
      signal.throwIfAborted()
      if (item.done) break
      bytes += item.value.byteLength
      if (bytes > limit) { await reader.cancel(); throw new RequestError(413, 'too_large') }
      text += decoder.decode(item.value, { stream: true })
    }
    return JSON.parse(text + decoder.decode())
  } finally { signal.removeEventListener('abort', abort); reader.releaseLock() }
}
function messagesToInput(value: unknown): Input {
  if (!object(value)) throw new RequestError(400, 'invalid_request')
  exact(value, ['messages'])
  if (!Array.isArray(value.messages) || !value.messages.length || value.messages.length > 12) throw new RequestError(400, 'invalid_request')
  let textLength = 0; let images = 0; let hasUser = false
  const input: Input = value.messages.map(message => {
    if (!object(message)) throw new RequestError(400, 'invalid_request')
    exact(message, ['role', 'content'])
    if (message.role !== 'user' && message.role !== 'system') throw new RequestError(400, 'invalid_request')
    if (message.role === 'user') hasUser = true
    const content = typeof message.content === 'string' ? [{ type: 'text', text: message.content }] : message.content
    if (!Array.isArray(content) || !content.length || content.length > 8) throw new RequestError(400, 'invalid_request')
    const parts: InputPart[] = content.map(part => {
      if (!object(part)) throw new RequestError(400, 'invalid_request')
      if (part.type === 'text') {
        exact(part, ['type', 'text'])
        if (typeof part.text !== 'string' || !part.text.trim()) throw new RequestError(400, 'invalid_request')
        textLength += part.text.length
        if (textLength > MAX_TEXT) throw new RequestError(413, 'too_large')
        return { type: 'input_text', text: part.text }
      }
      exact(part, ['type', 'image_url'])
      if (part.type !== 'image_url' || message.role !== 'user' || !object(part.image_url)) throw new RequestError(400, 'invalid_request')
      exact(part.image_url, ['url', 'detail'])
      const url = part.image_url.url
      if (typeof url !== 'string' || url.length > 3_500_000 || !/^data:image\/(jpeg|png);base64,[A-Za-z0-9+/]+={0,2}$/.test(url) || ++images > 1) throw new RequestError(400, 'invalid_image')
      return { type: 'input_image', image_url: url, detail: 'high' }
    })
    return { role: message.role === 'system' ? 'developer' : 'user', content: parts }
  })
  if (!hasUser) throw new RequestError(400, 'invalid_request')
  return input
}
function outputText(value: unknown) {
  if (!object(value) || value.status !== 'completed' || value.error || value.incomplete_details || !Array.isArray(value.output)) throw new RequestError(502, 'incomplete_output')
  const texts: string[] = []
  for (const item of value.output) {
    if (!object(item)) throw new RequestError(502, 'invalid_output')
    if (item.type === 'reasoning') continue
    if (item.type !== 'message' || item.role !== 'assistant' || item.status !== 'completed' || !Array.isArray(item.content)) throw new RequestError(502, 'invalid_output')
    for (const part of item.content) {
      if (!object(part)) throw new RequestError(502, 'invalid_output')
      if (part.type === 'refusal') throw new RequestError(422, 'refused')
      if (part.type !== 'output_text' || typeof part.text !== 'string') throw new RequestError(502, 'invalid_output')
      texts.push(part.text)
    }
  }
  const text = texts.join('\n').trim()
  if (!text || text.length > 100_000) throw new RequestError(502, 'invalid_output')
  return text
}

/** Limits are per warm function instance, not a durable spend cap across Vercel instances. */
export function createResearchHandler({ env = process.env, fetcher = fetch, now = Date.now, timeoutMs = 100_000 }: { env?: Env; fetcher?: typeof fetch; now?: () => number; timeoutMs?: number } = {}) {
  let windowStart = now(); let attempts = 0; let requests = 0; let active = 0
  return async (request: Request): Promise<Response> => {
    const apiKey = env.OPENAI_API_KEY?.trim() || ''
    const code = env.RESEARCH_ACCESS_CODE?.trim() || ''
    const enabled = env.RESEARCH_AI_ENABLED === 'true' && apiKey.length > 15 && apiKey.length <= 8192 && !/[\r\n]/.test(apiKey) && /^[A-Za-z0-9_-]{16,128}$/.test(code)
    if (request.method === 'GET') return reply({ enabled, model: MODEL, provider: 'OpenAI', access: 'code' })
    if (request.method !== 'POST') return reply({ error: 'method_not_allowed' }, 405)
    if (!enabled) return reply({ error: 'not_configured' }, 503)
    if (request.signal.aborted) return reply({ error: 'cancelled' }, 499)
    const allowed = (env.RESEARCH_ALLOWED_ORIGINS || 'https://www.e1zgo.top,https://e1zgo.top').split(',').map(s => s.trim()).filter(Boolean)
    const origin = request.headers.get('origin')
    if (!origin || !allowed.includes(origin) || request.headers.get('sec-fetch-site') === 'cross-site') return reply({ error: 'forbidden_origin' }, 403)
    if (now() - windowStart >= 60_000) { windowStart = now(); attempts = 0; requests = 0 }
    if (++attempts > 60) return reply({ error: 'rate_limited' }, 429)
    const supplied = request.headers.get('x-research-access-code') || ''
    if (!/^[A-Za-z0-9_-]{16,128}$/.test(supplied) || !timingSafeEqual(createHash('sha256').update(supplied).digest(), createHash('sha256').update(code).digest())) return reply({ error: 'invalid_code' }, 401)
    if (requests >= 12 || active >= 2) return reply({ error: 'rate_limited' }, 429)
    if (request.headers.get('content-type')?.split(';')[0]?.trim() !== 'application/json') return reply({ error: 'invalid_request' }, 415)
    const length = request.headers.get('content-length')
    if (length && (!/^\d+$/.test(length) || Number(length) > MAX_BODY)) return reply({ error: 'too_large' }, 413)
    requests++; active++
    const controller = new AbortController()
    const abort = () => controller.abort()
    request.signal.addEventListener('abort', abort, { once: true })
    const timer = setTimeout(abort, timeoutMs)
    try {
      const value = await readJson(request.body, MAX_BODY, controller.signal)
      const input = messagesToInput(value)
      controller.signal.throwIfAborted()
      const response = await fetcher('https://api.openai.com/v1/responses', {
        method: 'POST', redirect: 'error', signal: controller.signal,
        headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: MODEL, input, store: false, stream: false, reasoning: { effort: 'medium' }, max_output_tokens: 12_000 }),
      })
      if (!response.ok) {
        await response.body?.cancel()
        throw new RequestError(response.status === 429 ? 429 : 502, response.status === 429 ? 'provider_limit' : 'provider_error')
      }
      let data: unknown
      try { data = await readJson(response.body, MAX_RESPONSE, controller.signal) }
      catch { throw new RequestError(502, 'invalid_output') }
      return reply({ text: outputText(data), model: MODEL })
    } catch (error) {
      if (controller.signal.aborted) return reply({ error: request.signal.aborted ? 'cancelled' : 'timeout' }, request.signal.aborted ? 499 : 504)
      if (error instanceof RequestError) return reply({ error: error.message }, error.status)
      if (error instanceof SyntaxError || error instanceof TypeError && error.message.includes('encoded data')) return reply({ error: 'invalid_request' }, 400)
      return reply({ error: 'provider_error' }, 502)
    } finally { clearTimeout(timer); request.signal.removeEventListener('abort', abort); active-- }
  }
}
