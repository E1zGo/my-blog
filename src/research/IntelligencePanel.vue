<script setup lang="ts">
import { computed, onBeforeUnmount, ref, toRaw, watch } from 'vue'
import type { Paper, ResearchResult } from './types'
import { listResults, saveOcrPage, saveResult, storageError } from './store'
import { createCompletion, endpoint, validateSettings } from './model'
import type { ModelSettings } from './model'
import { HOSTED_MODEL, HOSTED_IDENTITY, createHostedCompletion, hostedStatus, validateAccessCode } from './hosted-model'
import { askPaper, explainFormula, translationParts, translatePart } from './intelligence'
import type { Answer, Formula, Translation, TranslationPart } from './intelligence'
import { pageRenderer } from './page-image'
import { ocrWorker } from './ocr'
import { download } from './export'
import RichText from './RichText.vue'

const props = defineProps<{ paper: Paper; page: number; disabled: boolean }>()
const emit = defineEmits<{ busy: [value: boolean]; updated: []; page: [value: number] }>()
const settings = ref<ModelSettings>({ baseUrl: '', model: '', visionModel: '', apiKey: '' })
const modelMode = ref<'hosted' | 'custom'>('hosted')
const accessCode = ref('')
const hostedEnabled = ref(false)
const hostedChecking = ref(false)
const hostedMessage = ref('正在检查站点模型…')
try {
  const saved = JSON.parse(localStorage.getItem('researchpilot:model-preferences') || 'null')
  if (saved) for (const key of ['baseUrl', 'model', 'visionModel'] as const) if (typeof saved[key] === 'string') settings.value[key] = saved[key].slice(0, 2000)
  if (saved?.mode === 'custom' || saved?.mode !== 'hosted' && saved?.baseUrl) modelMode.value = 'custom'
} catch { /* Missing preferences never prevent local reading. */ }
const settingsInitiallyOpen = modelMode.value === 'hosted' || !settings.value.baseUrl
const tab = ref<'answer' | 'ocr' | 'formula' | 'translation'>('answer')
const consent = ref(false)
const working = ref(false)
const message = ref('')
const error = ref('')
const results = ref<ResearchResult[]>([])
const selectedResult = ref<ResearchResult>()
const question = ref('')
const first = ref(1)
const last = ref(props.paper.pageCount)
const formulaTarget = ref('请识别这一页最主要的公式，解释符号、结构和推导条件。')
const ocrLanguage = ref<'eng' | 'eng+chi_sim'>('eng')
const ocrScope = ref<'current' | 'missing'>('current')
const ocrDraft = ref<{ page: number; text: string; confidence: number }>()
const glossary = ref('')
const parts = ref<TranslationPart[]>([])
const translationPage = ref(props.page)
const exportText = ref('')
let controller: AbortController | undefined
let disposed = false
let refreshVersion = 0
const service = computed(() => { if (modelMode.value === 'hosted') return 'OpenAI（通过本站服务端）'; try { return new URL(endpoint(settings.value.baseUrl)).origin } catch { return '尚未填写' } })
const locked = computed(() => working.value || props.disabled)
const savedAnswers = computed(() => results.value.filter(r => r.kind === 'answer' || r.kind === 'formula'))
const answer = computed(() => selectedResult.value?.kind === 'answer' ? selectedResult.value.data as Answer : undefined)
const formula = computed(() => selectedResult.value?.kind === 'formula' ? selectedResult.value.data as Formula : undefined)
const translatedCount = computed(() => parts.value.filter(p => results.value.some(r => r.kind === 'translation' && r.id === p.key)).length)
const translations = computed(() => results.value.filter(r => r.kind === 'translation').map(r => ({ record: r, value: r.data as Translation })))
const visibleTranslations = computed(() => {
  const candidates = translations.value.filter(t => t.value.page === translationPage.value)
  if (parts.value.length) return candidates.filter(t => parts.value.some(p => p.key === t.record.id)).sort((a, b) => a.value.part - b.value.part)
  return candidates.sort((a, b) => a.value.part - b.value.part)
})
const missingPages = computed(() => {
  const pages = new Set(props.paper.passages.filter(p => p.page >= first.value && p.page <= last.value).map(p => p.page))
  return Math.max(0, last.value - first.value + 1 - pages.size)
})
const ocrInfo = computed(() => props.paper.ocrPages?.[props.page])

async function checkHosted() {
  if (hostedChecking.value) return
  hostedChecking.value = true
  try {
    const enabled = await hostedStatus()
    if (disposed) return
    hostedEnabled.value = enabled
    hostedMessage.value = enabled ? '站点模型已启用，填写访问码后即可使用；模型调用费用由站长承担。' : '站点模型尚未启用，等待站长配置。阅读、检索和本地 OCR 可正常使用。'
  } catch { if (!disposed) { hostedEnabled.value = false; hostedMessage.value = '暂时无法检查站点模型，请稍后重新检查。' } }
  finally { hostedChecking.value = false }
}
void checkHosted()
function modelName(vision = false) { return modelMode.value === 'hosted' ? HOSTED_MODEL : (vision ? settings.value.visionModel : settings.value.model).trim() }

async function reload() {
  const id = props.paper.id; const version = ++refreshVersion
  const records = await listResults(id)
  if (!disposed && props.paper.id === id && version === refreshVersion) results.value = records
}
function applySettings() {
  error.value = ''
  try {
    if (modelMode.value === 'custom') validateSettings(settings.value)
    localStorage.setItem('researchpilot:model-preferences', JSON.stringify({ mode: modelMode.value, baseUrl: settings.value.baseUrl.trim(), model: settings.value.model.trim(), visionModel: settings.value.visionModel.trim() }))
    message.value = '服务选项已记住。访问码和密钥只在当前页面内存中，刷新或离开工作台后需重新填写。'
  } catch (cause) { error.value = storageError(cause) }
}
function forgetKey() { settings.value.apiKey = ''; accessCode.value = ''; consent.value = false; message.value = '已清除当前页面中的访问码和密钥。' }
function ready(vision = false) {
  if (modelMode.value === 'hosted') {
    if (!hostedEnabled.value) throw new Error(hostedMessage.value)
    validateAccessCode(accessCode.value)
  } else validateSettings(settings.value, vision)
  if (!consent.value) throw new Error('请先确认允许将任务所需内容发送至上方显示的模型服务。')
  return modelMode.value === 'hosted' ? createHostedCompletion(accessCode.value) : createCompletion(toRaw(settings.value))
}
async function run(operation: (signal: AbortSignal, paper: Paper) => Promise<void>) {
  if (locked.value) return
  working.value = true; emit('busy', true); error.value = ''; message.value = ''; exportText.value = ''
  controller = new AbortController()
  const signal = controller.signal
  const paper = structuredClone(toRaw(props.paper))
  try { await operation(signal, paper) }
  catch (cause) { if (!disposed) { if (signal.aborted) message.value = '已停止，已保存的结果仍然保留。'; else { error.value = storageError(cause); message.value = '任务已暂停，已保存的结果仍然保留。' } } }
  finally { controller = undefined; working.value = false; emit('busy', false) }
}
async function store(record: ResearchResult, signal: AbortSignal) {
  signal.throwIfAborted()
  await saveResult(record)
  await reload()
}
function record(paper: Paper, kind: ResearchResult['kind'], page: number, title: string, data: unknown, id: string = crypto.randomUUID()): ResearchResult {
  return { id, paperId: paper.id, kind, page, title, data, model: modelName(kind === 'formula'), createdAt: new Date().toISOString() }
}
function ask() { void run(async (signal, paper) => {
  const complete = ready()
  const value = await askPaper(paper, question.value.trim(), Number(first.value), Number(last.value), complete, signal, text => { message.value = text })
  const result = record(paper, 'answer', Number(first.value), question.value.trim(), value)
  await store(result, signal); selectedResult.value = result
  message.value = '中文解释已保存。请通过下方证据核对事实；引用编号有效不代表每项结论都已验证。'
}) }
function testConnection() { void run(async signal => {
  const complete = ready()
  message.value = '正在发送一条简短测试消息（不发送论文）…'
  await complete([{ role: 'user', content: '请回复“连接成功”。' }], signal)
  message.value = modelMode.value === 'hosted' ? '站点模型连接成功，问答、公式与翻译均使用 GPT-6.1 Sol。' : '文本模型连接成功。公式识别还需要单独配置支持图片的视觉模型。'
}) }
function recognize() { void run(async (signal, paper) => {
  const pages = ocrScope.value === 'current' ? [props.page] : paper.emptyPages.slice()
  if (!pages.length) throw new Error('没有待识别的空文字页；需要重新识别时请选择当前页。')
  const renderer = await pageRenderer(paper.id, signal)
  let ocr: Awaited<ReturnType<typeof ocrWorker>> | undefined
  let completed = 0; const failures: number[] = []
  try {
    let current = pages[0]
    ocr = await ocrWorker(ocrLanguage.value, signal, text => { message.value = `第 ${current} 页 · ${text}` })
    for (const page of pages) {
      current = page; signal.throwIfAborted()
      const canvas = await renderer.render(page)
      let value: { text: string; confidence: number }
      try { value = await ocr.recognize(canvas) } finally { canvas.width = 0; canvas.height = 0 }
      signal.throwIfAborted()
      if (!value.text) { failures.push(page); continue }
      if (ocrScope.value === 'current') {
        ocrDraft.value = { page, ...value }
      } else {
        await saveOcrPage(paper.id, page, value.text, value.confidence, false)
        emit('updated')
      }
      completed++
    }
    message.value = ocrScope.value === 'current' ? '识别完成，请校对下方文字，再保存到论文索引。' : `已识别并保存 ${completed} 页（待校对）。${failures.length ? `第 ${failures.join('、')} 页未识别到文字。` : ''}可打开某页校对文字。`
  } finally { await ocr?.close(); await renderer.close() }
}) }
function editOcr() {
  const page = props.page
  const text = props.paper.passages.filter(p => p.page === page).sort((a, b) => a.ordinal - b.ordinal).map(p => p.text).join('\n\n')
  ocrDraft.value = { page, text, confidence: props.paper.ocrPages?.[page]?.confidence || 0 }
}
function acceptOcr() { void run(async (signal, paper) => {
  if (!ocrDraft.value) return
  const value = { ...ocrDraft.value }
  signal.throwIfAborted()
  await saveOcrPage(paper.id, value.page, value.text, value.confidence, true)
  emit('updated'); ocrDraft.value = undefined; parts.value = []
  message.value = '校对文字已保存，并用于后续检索、问答和翻译。原 PDF 保持不变。'
}) }
function analyzeFormula() { void run(async (signal, paper) => {
  const complete = ready(true); const page = props.page
  const renderer = await pageRenderer(paper.id, signal)
  try {
    message.value = `正在读取第 ${page} 页公式图片…`
    const canvas = await renderer.render(page)
    const image = canvas.toDataURL('image/jpeg', .9)
    canvas.width = 0; canvas.height = 0
    const context = paper.passages.filter(p => Math.abs(p.page - page) <= 1).map(p => `[第 ${p.page} 页] ${p.text}`).join('\n')
    message.value = '正在识别公式结构并生成可核对的解释与推导…'
    const value = await explainFormula(image, page, formulaTarget.value, context, complete, signal)
    const result = record(paper, 'formula', page, formulaTarget.value, value)
    await store(result, signal); selectedResult.value = result
    message.value = '公式结果已保存，请核对原图与识别符号。推导未经过计算机代数证明。'
  } finally { await renderer.close() }
}) }
async function makeParts(paper: Paper) {
  return translationParts(paper, Number(first.value), Number(last.value), modelMode.value === 'hosted' ? HOSTED_IDENTITY : `${endpoint(settings.value.baseUrl)}|${settings.value.model.trim()}`, glossary.value.trim())
}
function prepareTranslation() { void run(async (_signal, paper) => {
  if (modelMode.value === 'custom') validateSettings(settings.value)
  parts.value = await makeParts(paper)
  if (!parts.value.length) throw new Error('所选页没有可翻译文字，请先 OCR。')
  message.value = `共 ${parts.value.length} 个片段，已有 ${translatedCount.value} 个相同配置的译文；继续将发送 ${parts.value.length - translatedCount.value} 次请求。${missingPages.value ? `另有 ${missingPages.value} 页没有文字，需 OCR 后才能覆盖全文。` : ''}`
}) }
function translate() { void run(async (signal, paper) => {
  const complete = ready()
  parts.value = await makeParts(paper)
  if (!parts.value.length) throw new Error('所选页没有可翻译文字，请先 OCR。')
  const existing = new Set(results.value.filter(r => r.kind === 'translation').map(r => r.id))
  let count = parts.value.filter(p => existing.has(p.key)).length
  const total = parts.value.length
  for (const part of parts.value) {
    signal.throwIfAborted()
    if (existing.has(part.key)) continue
    translationPage.value = part.page
    message.value = `正在翻译第 ${part.page} 页第 ${part.part + 1} 段 · 已保存 ${count} / ${total} 段…`
    const value = await translatePart(part, glossary.value.trim(), complete, signal)
    await store(record(paper, 'translation', part.page, `第 ${part.page} 页第 ${part.part + 1} 段`, value, part.key), signal)
    count++
  }
  message.value = `所选范围的 ${total} 个文本片段已翻译并保存。${missingPages.value ? `仍有 ${missingPages.value} 页没有文字，全文尚不完整，请先 OCR 再继续。` : '可逐页对照原文和译文。'}图表内文字未必被提取，公式须对照原页。`
}) }
function scopeAll() { first.value = 1; last.value = props.paper.pageCount }
function scopeCurrent() { first.value = props.page; last.value = props.page }
function showResult(result: ResearchResult) { selectedResult.value = result; tab.value = result.kind === 'formula' ? 'formula' : 'answer'; emit('page', result.page) }
function exportResults() {
  const intro = `# ${props.paper.name} · 智能研读\n\n论文 SHA256：${props.paper.id}\n\n模型生成内容需对照原文核对；页码为 PDF 实际页序。\n\n`
  const content: string[] = []
  if (tab.value === 'translation') {
    const selected = parts.value.length ? translations.value.filter(t => parts.value.some(p => p.key === t.record.id)) : translations.value
    content.push(`导出 ${selected.length} 个已保存译文片段；未保存或无文字的页面不在译文中，不能据此认定全文已完成。\n`)
    for (const { record: r, value: t } of selected.sort((a, b) => a.value.page - b.value.page || a.value.part - b.value.part)) content.push(`## 第 ${t.page} 页 · 片段 ${t.part + 1}\n\n模型：${r.model}；时间：${r.createdAt}\n\n### 原文\n\n${t.source}\n\n### 中文译文\n\n${t.text}\n\n${t.warnings ? `待核对：${t.warnings}\n` : ''}`)
  } else if (selectedResult.value) {
    const r = selectedResult.value
    content.push(`## ${r.title}\n\n模型：${r.model}；时间：${r.createdAt}；第 ${r.page} 页\n`)
    if (r.kind === 'answer') {
      const a = r.data as Answer
      content.push(a.text, ...a.warnings.map(w => `待核对：${w}`), '## 引用原文', ...a.evidence.map(e => `[${e.label}] 第 ${e.page} 页${e.ocr ? '（OCR）' : ''}\n\n${e.text}`))
    } else {
      const f = r.data as Formula
      content.push(`$$\n${f.latex}\n$$`, f.structure, ...f.symbols.map(s => `${s.symbol}：${s.meaning}`), `前提：${f.assumptions}`, ...f.steps.map((s, i) => `${i + 1}. ${s.explanation}\n\n$$\n${s.equation}\n$$`), `检查：${f.verification}`, `不确定事项：${f.uncertainty}`)
    }
  }
  exportText.value = intro + content.join('\n\n')
}
function downloadExport() { download(new Blob([exportText.value], { type: 'text/markdown;charset=utf-8' }), `${props.paper.name.replace(/\.pdf$/i, '')}-智能研读.md`) }
watch(() => [modelMode.value, accessCode.value, settings.value.baseUrl, settings.value.model, settings.value.visionModel, settings.value.apiKey], () => { consent.value = false; parts.value = [] })
watch(modelMode, () => { accessCode.value = ''; settings.value.apiKey = '' })
watch([first, last, glossary], () => {
  parts.value = []
  try { localStorage.setItem(`researchpilot:translation-options:${props.paper.id}`, JSON.stringify({ first: first.value, last: last.value, glossary: glossary.value })) }
  catch { error.value = '翻译设置暂时无法缓存，请保留术语表；已保存译文不受影响。' }
})
watch(() => props.paper.id, () => {
  controller?.abort(); ++refreshVersion; results.value = []; selectedResult.value = undefined; ocrDraft.value = undefined; parts.value = []; exportText.value = ''
  first.value = 1; last.value = props.paper.pageCount; translationPage.value = props.page; error.value = ''; message.value = ''
  glossary.value = ''
  try {
    const saved = JSON.parse(localStorage.getItem(`researchpilot:translation-options:${props.paper.id}`) || 'null')
    if (saved && typeof saved.glossary === 'string') glossary.value = saved.glossary.slice(0, 6000)
    if (saved && Number.isInteger(saved.first) && Number.isInteger(saved.last) && saved.first >= 1 && saved.last <= props.paper.pageCount && saved.first <= saved.last) { first.value = saved.first; last.value = saved.last }
  } catch { /* Invalid settings do not block reading saved results. */ }
  void reload().catch(cause => { error.value = storageError(cause) })
}, { immediate: true })
onBeforeUnmount(() => { disposed = true; ++refreshVersion; controller?.abort(); settings.value.apiKey = ''; accessCode.value = '' })
</script>

<template>
  <section class="rp-intelligence" aria-labelledby="rp-intelligence-title">
    <div class="rp-panel-heading"><div><p class="eyebrow">READ WITH EVIDENCE</p><h2 id="rp-intelligence-title">智能精读</h2></div><span>结果保存到当前浏览器</span></div>
    <details class="rp-model-settings" :open="settingsInitiallyOpen">
      <summary>模型服务设置 · {{ service }}</summary>
      <fieldset :disabled="locked"><label>使用方式<select v-model="modelMode"><option value="hosted">站点模型 · GPT-6.1 Sol · 访问码试用</option><option value="custom">自己的模型服务 · 自行付费</option></select></label>
      <div v-if="modelMode === 'hosted'">
        <p class="rp-small">由站长提供 OpenAI API，问答、公式与翻译统一使用 GPT-6.1 Sol。无需填写 API 密钥；访问码只在当前页面内存中保留，刷新或离开后清除。</p>
        <p role="status">{{ hostedMessage }}</p>
        <label>试用访问码<input v-model="accessCode" type="password" autocomplete="off" spellcheck="false" maxlength="128" placeholder="填写站长提供的访问码"></label>
        <button :disabled="hostedChecking" @click="checkHosted">{{ hostedChecking ? '检查中…' : '重新检查站点模型' }}</button>
      </div>
      <template v-else><p class="rp-small">使用兼容 Chat Completions 且允许浏览器跨域访问的服务。密钥仅保留在当前页面内存中，刷新、离开后清除。调用费用由你承担。</p><div class="rp-settings-grid">
        <label>服务地址<input v-model="settings.baseUrl" type="url" placeholder="https://你的服务/v1" autocomplete="off" maxlength="2000"></label>
        <label>文本模型<input v-model="settings.model" placeholder="填写服务商提供的模型名称" maxlength="200"></label>
        <label>视觉模型（公式识别）<input v-model="settings.visionModel" placeholder="填写支持图片输入的模型名称" maxlength="200"></label>
        <label>API 密钥<input v-model="settings.apiKey" type="password" autocomplete="off" spellcheck="false" placeholder="仅在当前页面使用" maxlength="8192"></label>
      </div></template><div class="rp-action-row"><button @click="applySettings">记住服务选项</button><button @click="forgetKey">清除访问码 / 密钥</button><button :disabled="modelMode === 'hosted' && !hostedEnabled" @click="testConnection">测试模型连接</button></div></fieldset>
    </details>
    <label class="rp-consent"><input v-model="consent" type="checkbox" :disabled="locked">我允许将本次任务所需的问题、论文片段或公式页图片发送至 {{ service }}。{{ modelMode === 'hosted' ? '本站处理后转发给 OpenAI，模型调用费用由站长承担。' : '模型服务可能向我收取费用。' }} OCR 在本机运行，不需要此授权。</label>
    <div class="rp-tabs" role="tablist" aria-label="智能精读功能"><button v-for="item in ([['answer','中文问答'],['ocr','扫描 OCR'],['formula','公式与推导'],['translation','全文翻译']] as const)" :id="`rp-tab-${item[0]}`" :key="item[0]" role="tab" :aria-selected="tab === item[0]" :aria-controls="`rp-panel-${item[0]}`" :disabled="locked" @click="tab = item[0]">{{ item[1] }}</button></div>
    <p v-if="error" class="rp-message rp-error" role="alert">{{ error }}</p>
    <div v-if="message || working" class="rp-ai-progress" role="status"><span>{{ message || '正在处理…' }}</span><button v-if="working" @click="controller?.abort()">停止处理</button></div>

    <div v-if="tab === 'answer' || tab === 'translation'" class="rp-ai-scope"><fieldset :disabled="locked"><label>起始页 <input v-model.number="first" type="number" min="1" :max="paper.pageCount"></label><label>结束页 <input v-model.number="last" type="number" min="1" :max="paper.pageCount"></label><button @click="scopeAll">整篇论文</button><button @click="scopeCurrent">当前页</button></fieldset><p class="rp-small">仅处理这个页码范围；页码按 PDF 实际页序计算。</p></div>
    <section v-if="tab === 'answer'" id="rp-panel-answer" role="tabpanel" aria-labelledby="rp-tab-answer">
      <p>用中文提出问题，模型检索英文原文并解释方法、公式背景和证据边界。未检索到的内容不会自动当作论文结论。</p>
      <form @submit.prevent="ask"><label class="rp-label" for="rp-ai-question">你想深入理解什么？</label><textarea id="rp-ai-question" v-model="question" :disabled="locked" maxlength="4000" rows="3" required placeholder="例如：为什么作者采用这种训练目标？它依赖哪些假设，什么情况下可能失效？"></textarea><button class="rp-primary" :disabled="locked || !question.trim()">基于原文生成中文解释</button></form>
      <article v-if="answer" class="rp-ai-result"><h3>{{ selectedResult?.title }}</h3><p class="rp-small">{{ selectedResult?.model }} · {{ selectedResult?.createdAt }}</p><p v-for="warning in answer.warnings" :key="warning" class="rp-scan-warning">{{ warning }}</p><RichText :text="answer.text"/><details><summary>查看 {{ answer.evidence.length }} 段引用证据与英文检索表达</summary><p class="rp-small">{{ answer.queries.join('；') }}</p><article v-for="e in answer.evidence" :key="e.label"><button @click="emit('page', e.page)">[{{ e.label }}] 第 {{ e.page }} 页 ↗</button><span v-if="e.ocr"> · OCR 文字</span><blockquote>{{ e.text }}</blockquote></article></details><button @click="exportResults">导出这次解释</button></article>
    </section>
    <section v-if="tab === 'ocr'" id="rp-panel-ocr" role="tabpanel" aria-labelledby="rp-tab-ocr">
      <p>扫描页先在你的浏览器里识别，再用于检索、问答和翻译。首次使用需下载本站的识别引擎与语言数据；不会把页面传到识别服务器。</p>
      <fieldset :disabled="locked"><label>识别语言 <select v-model="ocrLanguage"><option value="eng">英文</option><option value="eng+chi_sim">英文与简体中文</option></select></label><label>处理范围 <select v-model="ocrScope"><option value="current">当前第 {{ page }} 页（先预览再保存）</option><option value="missing">所有无文字页（{{ paper.emptyPages.length }} 页，逐页保存）</option></select></label><div class="rp-action-row"><button class="rp-primary" @click="recognize">开始本地 OCR</button><button @click="editOcr">校对当前页文字</button></div></fieldset>
      <p class="rp-small">普通 OCR 主要识别正文；双栏、表格和数学符号可能有误。批量结果会标为待校对，公式请使用“公式与推导”。</p>
      <p v-if="ocrInfo">当前页 OCR 置信度约 {{ Math.round(ocrInfo.confidence) }}% · {{ ocrInfo.reviewed ? '已人工校对' : '待校对' }}（不是准确率保证）。</p>
      <div v-if="ocrDraft" class="rp-ocr-editor"><h3>第 {{ ocrDraft.page }} 页文字校对</h3><textarea v-model="ocrDraft.text" :disabled="locked" maxlength="100000" rows="12" aria-label="OCR 识别文字"></textarea><button class="rp-primary" :disabled="locked || !ocrDraft.text.trim()" @click="acceptOcr">保存校对文字并更新索引</button><button :disabled="locked" @click="ocrDraft = undefined">放弃这次编辑</button></div>
    </section>
    <section v-if="tab === 'formula'" id="rp-panel-formula" role="tabpanel" aria-labelledby="rp-tab-formula">
      <p>发送当前第 {{ page }} 页的原图和相邻页文字给视觉模型，识别公式结构、解释符号，并给出带前提的数学推导。请先在阅读器定位公式所在页。</p>
      <form @submit.prevent="analyzeFormula"><label class="rp-label" for="rp-formula-target">公式编号、位置与想理解的问题</label><textarea id="rp-formula-target" v-model="formulaTarget" :disabled="locked" maxlength="2000" rows="3" required></textarea><button class="rp-primary" :disabled="locked">识别当前页公式并解释</button></form>
      <article v-if="formula" class="rp-ai-result"><button @click="emit('page', selectedResult!.page)">核对第 {{ selectedResult?.page }} 页原图 ↗</button><p class="rp-small">{{ selectedResult?.model }} · 模型辅助识别与推导，未经过形式化证明。</p><h3>识别公式</h3><RichText :text="formula.latex" equation/><details><summary>LaTeX 源码（可复制）</summary><textarea :value="formula.latex" readonly aria-label="公式 LaTeX 源码" rows="3"></textarea></details><h3>公式结构</h3><RichText :text="formula.structure"/><dl class="rp-symbols"><template v-for="(symbol, i) in formula.symbols" :key="i"><dt><RichText :text="symbol.symbol" equation/></dt><dd>{{ symbol.meaning }}</dd></template></dl><h3>推导前提</h3><RichText :text="formula.assumptions"/><h3>推导步骤</h3><ol><li v-for="(step, i) in formula.steps" :key="i"><RichText :text="step.explanation"/><RichText v-if="step.equation" :text="step.equation" equation/></li></ol><h3>检查与不确定事项</h3><RichText :text="formula.verification"/><p class="rp-scan-warning">{{ formula.uncertainty || '模型未指出歧义，仍需核对上下标、矩阵维度及推导前提。' }}</p><button @click="exportResults">导出公式与推导</button></article>
    </section>
    <section v-if="tab === 'translation'" id="rp-panel-translation" role="tabpanel" aria-labelledby="rp-tab-translation">
      <p>按页分段翻译全部可提取正文，保留原文对照。每完成一段立即保存；停止或断线后，使用相同模型、术语表和范围继续，会跳过已保存片段。</p>
      <label class="rp-label" for="rp-glossary">术语表（可选，每行一个对应关系）</label><textarea id="rp-glossary" v-model="glossary" :disabled="locked" rows="3" maxlength="6000" placeholder="diffusion model = 扩散模型&#10;denoising = 去噪"></textarea>
      <p v-if="missingPages" class="rp-scan-warning">所选范围有 {{ missingPages }} 页没有可提取文字，需先 OCR，才能完整翻译这些页面。</p>
      <div class="rp-action-row"><button :disabled="locked" @click="prepareTranslation">检查范围与请求数量</button><button class="rp-primary" :disabled="locked" @click="translate">开始 / 继续翻译</button><button :disabled="!translations.length || locked" @click="exportResults">导出已保存译文</button></div><p v-if="parts.length">当前配置：已保存 {{ translatedCount }} / {{ parts.length }} 段。</p>
      <label class="rp-translation-page">查看译文页码 <input v-model.number="translationPage" type="number" min="1" :max="paper.pageCount"><button @click="emit('page', Math.max(1, Math.min(paper.pageCount, translationPage)))">查看这一页原文 ↗</button></label>
      <p v-if="!visibleTranslations.length" class="rp-small">这一页还没有当前处理范围的已保存译文。历史译文会在打开论文后显示；更换模型或术语表会生成新的版本。</p>
      <article v-for="t in visibleTranslations" :key="t.record.id" class="rp-translation-pair"><p class="rp-small">第 {{ t.value.page }} 页 · 第 {{ t.value.part + 1 }} 段 · {{ t.record.model }}</p><details><summary>英文原文</summary><p>{{ t.value.source }}</p></details><RichText :text="t.value.text"/><p v-if="t.value.warnings" class="rp-scan-warning">{{ t.value.warnings }}</p></article>
    </section>
    <details v-if="savedAnswers.length" class="rp-ai-history"><summary>已保存的问答与公式结果（{{ savedAnswers.length }}）</summary><ul><li v-for="r in savedAnswers" :key="r.id"><button :disabled="locked" @click="showResult(r)">{{ r.kind === 'formula' ? '公式' : '问答' }} · {{ r.title }} · 第 {{ r.page }} 页</button></li></ul></details>
    <section v-if="exportText" class="rp-export"><div class="rp-panel-heading"><h3>智能研读导出预览</h3><button @click="exportText = ''">关闭</button></div><textarea :value="exportText" readonly rows="12" aria-label="智能研读 Markdown 导出" @focus="($event.target as HTMLTextAreaElement).select()"></textarea><button @click="downloadExport">下载 Markdown</button><p class="rp-small">如下载未启动，可选中预览内容后复制。</p></section>
  </section>
</template>
<style src="./intelligence.css"></style>
