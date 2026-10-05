export interface ModelSettings { baseUrl: string; model: string; visionModel: string; apiKey: string }
export interface Message { role: 'system' | 'user' | 'assistant'; content: string | ({ type: 'text'; text: string } | { type: 'image_url'; image_url: { url: string; detail: 'high' } })[] }
export type Completion = (messages: Message[], signal: AbortSignal, vision?: boolean) => Promise<string>

export function endpoint(value: string): string {
  let url: URL
  try { url = new URL(value.trim()) } catch { throw new Error('请填写完整的模型服务地址，例如 https://你的服务/v1。') }
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if ((url.protocol !== 'https:' && !(local && url.protocol === 'http:')) || url.username || url.password || url.search || url.hash) {
    throw new Error('服务地址须为 HTTPS（本机可用 HTTP），不能含账号、密钥、查询参数或片段。')
  }
  url.pathname = url.pathname.replace(/\/+$/, '').replace(/\/chat\/completions$/, '') + '/chat/completions'
  return url.href
}

export function validateSettings(settings: ModelSettings, vision = false) {
  endpoint(settings.baseUrl)
  if (!(vision ? settings.visionModel : settings.model).trim()) throw new Error(vision ? '请先填写支持图片输入的视觉模型名称。' : '请先填写文本模型名称。')
  if (/[\r\n]/.test(settings.apiKey) || settings.apiKey.length > 8192) throw new Error('密钥格式不正确，请重新填写。')
}

export function createCompletion(settings: ModelSettings, fetcher: typeof fetch = fetch): Completion {
  const config = { ...settings }
  return async (messages, signal, vision = false) => {
    validateSettings(config, vision)
    signal.throwIfAborted()
    const control = new AbortController()
    const abort = () => control.abort(signal.reason)
    signal.addEventListener('abort', abort, { once: true })
    const timer = setTimeout(() => control.abort('timeout'), 120_000)
    try {
      const response = await fetcher(endpoint(config.baseUrl), {
        method: 'POST', signal: control.signal, credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', ...(config.apiKey.trim() ? { Authorization: `Bearer ${config.apiKey.trim()}` } : {}) },
        body: JSON.stringify({ model: vision ? config.visionModel.trim() : config.model.trim(), messages, stream: false }),
      })
      if (!response.ok) {
        await response.body?.cancel()
        throw new ModelError(response.status === 429 ? '服务限流或余额不足（HTTP 429），已暂停，请稍后继续。' : `模型服务返回 HTTP ${response.status}，请核对服务地址、密钥、模型权限和余额。`)
      }
      if (!response.body) throw new ModelError('模型没有返回内容。')
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let body = ''; let bytes = 0
      try {
        while (true) {
          const item = await reader.read()
          if (item.done) break
          bytes += item.value.byteLength
          if (bytes > 2_000_000) { await reader.cancel(); throw new ModelError('模型响应过大，已停止；请缩小处理范围。') }
          body += decoder.decode(item.value, { stream: true })
        }
        body += decoder.decode()
      } finally { reader.releaseLock() }
      signal.throwIfAborted()
      const data = JSON.parse(body)
      const choice = data?.choices?.[0]
      if (choice?.finish_reason === 'length') throw new ModelError('模型输出被长度限制截断，未保存为完成结果；请减小范围或调整模型服务的输出限制后重试。')
      if (choice?.message?.refusal || choice?.finish_reason === 'content_filter') throw new ModelError('模型未能处理这次请求，请调整输入后重试。')
      const text = choice?.message?.content
      if (typeof text !== 'string' || !text.trim() || text.length > 100_000) throw new ModelError('模型没有返回有效文本，请确认服务支持 Chat Completions。')
      return text.trim()
    } catch (error) {
      if (signal.aborted) throw new DOMException('已停止；已保存的结果仍保留。', 'AbortError')
      if (control.signal.aborted) throw new ModelError('模型响应超过 2 分钟，已暂停；已保存的结果仍保留。')
      if (error instanceof ModelError) throw error
      throw new ModelError('模型连接失败或响应格式不正确。请检查网络及服务是否允许浏览器跨域访问（CORS）；密钥与服务错误正文不会显示在这里。')
    } finally { clearTimeout(timer); signal.removeEventListener('abort', abort) }
  }
}
class ModelError extends Error {}

export function jsonObject(text: string): Record<string, unknown> {
  try {
    const clean = text.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')
    const data = JSON.parse(clean)
    if (!data || Array.isArray(data) || typeof data !== 'object') throw new Error()
    return data
  } catch { throw new Error('模型没有按要求返回结构化结果，本次未保存。可以重试或更换模型。') }
}

export async function digest(text: string): Promise<string> {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))].map(n => n.toString(16).padStart(2, '0')).join('')
}
