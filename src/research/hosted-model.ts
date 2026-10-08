import type { Completion } from './model'

export const HOSTED_MODEL = 'gpt-6.1-sol'
export const HOSTED_ENDPOINT = '/api/research-model'
export const HOSTED_IDENTITY = `${HOSTED_ENDPOINT}|${HOSTED_MODEL}|responses-v1`
const errors: Record<string, string> = {
  not_configured: '站点模型尚未启用，请联系站长；本地阅读、检索与 OCR 可继续使用。',
  invalid_code: '访问码不正确或已更换，请重新填写站长提供的访问码。',
  forbidden_origin: '当前网址未获准使用站点模型，请从博客正式域名打开。',
  rate_limited: '试用请求较多，已暂停。请至少等待 1 分钟再继续，已保存结果不会丢失。',
  provider_limit: '模型服务限流或站点额度不足，已暂停，请稍后重试或联系站长。',
  provider_error: 'OpenAI 服务暂不可用，或站点密钥/模型权限需要配置，请联系站长。',
  timeout: '模型处理超时，已暂停。已保存结果仍然保留。',
  too_large: '这次文字或页面图片过大，请缩小范围或使用自己的模型服务。',
  invalid_image: '页面图片不符合站点模型要求，请更换页面或使用自己的模型服务。',
  incomplete_output: '模型输出未完成或被截断，本次未保存为完整结果，请缩小范围后重试。',
  invalid_output: '模型没有返回有效的完整文本，本次未保存，请稍后重试。',
  refused: '模型未能处理这次请求，请调整输入后重试。',
  invalid_request: '这次请求不符合站点模型要求，请缩小处理范围后重试。',
}
export async function hostedStatus(fetcher: typeof fetch = fetch): Promise<boolean> {
  const response = await fetcher(HOSTED_ENDPOINT, { credentials: 'omit', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(10_000) })
  if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('暂时无法检查站点模型，请稍后重新检查。')
  const value = await response.json()
  if (typeof value.enabled !== 'boolean' || value.model !== HOSTED_MODEL) throw new Error('站点模型配置已更新，请刷新页面。')
  return value.enabled
}
export function validateAccessCode(code: string) {
  if (!/^[A-Za-z0-9_-]{16,128}$/.test(code.trim())) throw new Error('请填写站长提供的完整访问码（至少 16 位字母、数字、下划线或短横线）。')
}
class HostedError extends Error {}
export function createHostedCompletion(accessCode: string, fetcher: typeof fetch = fetch): Completion {
  const code = accessCode.trim()
  return async (messages, signal) => {
    signal.throwIfAborted(); validateAccessCode(code)
    const controller = new AbortController()
    const abort = () => controller.abort()
    signal.addEventListener('abort', abort, { once: true })
    const timer = setTimeout(abort, 120_000)
    try {
      const body = JSON.stringify({ messages })
      if (new TextEncoder().encode(body).byteLength > 4_000_000) throw new HostedError(errors.too_large)
      const response = await fetcher(HOSTED_ENDPOINT, {
        method: 'POST', credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer', cache: 'no-store', signal: controller.signal,
        headers: { 'Content-Type': 'application/json', 'X-Research-Access-Code': code }, body,
      })
      if (!response.body) throw new HostedError(errors.invalid_output)
      const reader = response.body.getReader(); const decoder = new TextDecoder()
      let bytes = 0; let text = ''
      try {
        while (true) {
          const item = await reader.read()
          if (item.done) break
          bytes += item.value.byteLength
          if (bytes > 2_000_000) { await reader.cancel(); throw new HostedError(errors.invalid_output) }
          text += decoder.decode(item.value, { stream: true })
        }
      } finally { reader.releaseLock() }
      const value = JSON.parse(text + decoder.decode())
      signal.throwIfAborted()
      if (!response.ok) throw new HostedError(errors[value?.error] || (response.status === 429 ? errors.rate_limited : '站点模型请求失败，请稍后重试。'))
      if (value.model !== HOSTED_MODEL || typeof value.text !== 'string' || !value.text.trim() || value.text.length > 100_000) throw new HostedError(errors.invalid_output)
      return value.text.trim()
    } catch (error) {
      if (signal.aborted) throw new DOMException('已停止，已保存结果仍然保留。', 'AbortError')
      if (controller.signal.aborted) throw new HostedError(errors.timeout)
      if (error instanceof HostedError) throw error
      throw new HostedError('无法连接站点模型，请检查网络；已保存结果仍然保留。')
    } finally { clearTimeout(timer); signal.removeEventListener('abort', abort) }
  }
}
