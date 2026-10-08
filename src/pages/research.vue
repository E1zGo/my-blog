<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useHead } from '@vueuse/head'
import PdfReader from '../research/PdfReader.vue'
const IntelligencePanel = defineAsyncComponent(() => import('../research/IntelligencePanel.vue'))
import { MAX_FILE_BYTES, MAX_PAPERS } from '../research/types'
import type { Expansion, Hit, Note, Paper } from '../research/types'
import { importPdf } from '../research/pdf'
import { listPapers, listNotes, saveNote, savePaper, removePaper, readFile, savePosition, storageError } from '../research/store'
import { download, notesMarkdown } from '../research/export'

useHead({ title: 'ResearchPilot · 浏览器工作台', meta: [{ name: 'robots', content: 'noindex' }] })
const papers = ref<Paper[]>([])
const selectedId = ref('')
const active = computed(() => papers.value.find(p => p.id === selectedId.value))
const currentPage = ref(1)
const fileInput = ref<HTMLInputElement>()
const loading = ref(true)
const busy = ref(false)
const aiBusy = ref(false)
const saving = ref(false)
const progress = ref({ current: 0, total: 0 })
const status = ref('')
const error = ref('')
const query = ref('')
const searched = ref(false)
const searching = ref(false)
const hits = ref<Hit[]>([])
const expansion = ref<Expansion[]>([])
const limited = ref(false)
const firstPage = ref(1)
const lastPage = ref(1)
const notes = ref<Note[]>([])
const noteBody = ref('')
const noteQuote = ref('')
const notePage = ref(1)
const noteBusy = ref(false)
const pendingDelete = ref(false)
const deleting = ref(false)
const exportOpen = ref(false)
const exportText = ref('')
const exportName = ref('')
const storageRemaining = ref<number | null>(null)
const persistent = ref(false)
let controller: AbortController | undefined
let worker: Worker | undefined
let searchId = 0
let paperChange = 0
const used = computed(() => papers.value.reduce((n, p) => n + p.size, 0))
const formatSize = (value: number) => value < 1024 * 1024 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`
const suggestions = ['主要内容', '创新点', '损失函数', '实验结果', '局限性']

async function storageInfo() {
  try {
    const estimate = await navigator.storage?.estimate()
    storageRemaining.value = estimate?.quota === undefined ? null : Math.max(0, estimate.quota - (estimate.usage || 0))
    persistent.value = await navigator.storage?.persisted() || false
  } catch { storageRemaining.value = null }
}
async function refresh() {
  papers.value = await listPapers()
  await storageInfo()
}
function draftKey(id: string) { return `researchpilot:draft:${id}` }
function writeDraft() {
  if (!selectedId.value) return
  try { localStorage.setItem(draftKey(selectedId.value), JSON.stringify({ body: noteBody.value, quote: noteQuote.value, page: notePage.value })) }
  catch { error.value = '笔记草稿暂时无法缓存，请点击保存笔记，或先复制文字。' }
}
function restoreDraft(paper: Paper) {
  noteBody.value = ''; noteQuote.value = ''; notePage.value = currentPage.value
  try {
    const draft = JSON.parse(localStorage.getItem(draftKey(paper.id)) || 'null')
    if (draft && typeof draft.body === 'string' && typeof draft.quote === 'string' && Number.isInteger(draft.page)) {
      noteBody.value = draft.body.slice(0, 10000); noteQuote.value = draft.quote.slice(0, 1500)
      notePage.value = Math.min(paper.pageCount, Math.max(1, draft.page))
    }
  } catch { /* An invalid draft never prevents reading a saved paper. */ }
}
async function selectPaper(paper: Paper) {
  if (busy.value || aiBusy.value || noteBusy.value || deleting.value) return
  const change = ++paperChange
  exportOpen.value = false
  selectedId.value = paper.id
  currentPage.value = paper.lastPage || 1
  firstPage.value = 1; lastPage.value = paper.pageCount; limited.value = false
  hits.value = []; expansion.value = []; searched.value = false; searching.value = false; ++searchId
  pendingDelete.value = false; notes.value = []; error.value = ''; restoreDraft(paper)
  try {
    localStorage.setItem('researchpilot:selected', paper.id)
    const saved = await listNotes(paper.id)
    if (change === paperChange) notes.value = saved
  } catch (cause) { error.value = storageError(cause) }
}
async function importFile(file?: File) {
  if (!file || busy.value || aiBusy.value || noteBusy.value || deleting.value) return
  error.value = ''; status.value = ''
  if (file.size > MAX_FILE_BYTES) { error.value = '单篇 PDF 不能超过 200 MB。'; return }
  busy.value = true; progress.value = { current: 0, total: 0 }
  controller = new AbortController()
  const signal = controller.signal
  const timeout = setTimeout(() => controller?.abort('timeout'), 180_000)
  let imported: Paper | undefined
  try {
    await storageInfo()
    if (storageRemaining.value !== null && storageRemaining.value < file.size + 10 * 1024 * 1024) throw new Error('浏览器剩余空间不足以保存这份 PDF 与索引，请先导出并移除旧资料。')
    imported = await importPdf(file, signal, (current, total) => { progress.value = { current, total } })
    signal.throwIfAborted()
    saving.value = true
    const duplicate = await savePaper(imported, file)
    status.value = duplicate ? '已有论文已重新解析，阅读位置与笔记已保留。' : `已保存到当前浏览器：${file.name}，共 ${imported.pageCount} 页。`
    await refresh()
  } catch (cause) {
    imported = undefined
    error.value = signal.aborted ? (signal.reason === 'timeout' ? '解析超过 3 分钟，已停止；请拆分 PDF 后重试。' : '已取消导入，没有保存新资料。') : storageError(cause)
  }
  finally { clearTimeout(timeout); busy.value = false; saving.value = false; controller = undefined; if (fileInput.value) fileInput.value.value = '' }
  if (imported) { const paper = papers.value.find(p => p.id === imported!.id); if (paper) await selectPaper(paper) }
}
function dropped(event: DragEvent) {
  const files = event.dataTransfer?.files
  if (files && files.length > 1) { error.value = '请每次导入一篇论文，完成后再添加下一篇。'; return }
  void importFile(files?.[0])
}
function find() {
  error.value = ''
  if (!active.value || !query.value.trim()) return
  if (!worker) { error.value = '检索暂不可用，请刷新页面重试。'; return }
  const first = limited.value ? Number(firstPage.value) : 1
  const last = limited.value ? Number(lastPage.value) : active.value.pageCount
  if (!Number.isInteger(first) || !Number.isInteger(last) || first < 1 || last > active.value.pageCount || first > last) { error.value = '请填写有效的起止页码。'; return }
  searching.value = true; searched.value = true; hits.value = []; expansion.value = []
  worker.postMessage({ id: ++searchId, query: query.value.trim(), passages: toRaw(active.value.passages), first, last })
}
function suggest(text: string) { query.value = text; find() }
function pageChanged(page: number) {
  currentPage.value = page
  if (active.value) { active.value.lastPage = page; void savePosition(active.value.id, page).catch(cause => { error.value = storageError(cause) }) }
}
function cite(hit: Hit) {
  pageChanged(hit.page)
  noteQuote.value = hit.text; notePage.value = hit.page
  if (!noteBody.value.trim()) noteBody.value = '我的理解：'
  writeDraft(); status.value = `已将第 ${hit.page} 页原文加入笔记草稿，请补充自己的理解后保存。`
}
function useCurrentPage() { notePage.value = currentPage.value; noteQuote.value = ''; writeDraft() }
async function addNote() {
  const paper = active.value
  if (!paper || noteBusy.value) return
  const draft = { body: noteBody.value, quote: noteQuote.value, page: notePage.value }
  noteBusy.value = true; error.value = ''
  try {
    await saveNote({ id: crypto.randomUUID(), paperId: paper.id, page: draft.page, quote: draft.quote,
      body: draft.body.trim(), createdAt: new Date().toISOString() })
    notes.value = await listNotes(paper.id)
    if (noteBody.value === draft.body && noteQuote.value === draft.quote && notePage.value === draft.page) {
      noteBody.value = ''; noteQuote.value = ''; notePage.value = currentPage.value
      localStorage.removeItem(draftKey(paper.id))
    }
    status.value = '笔记已保存到当前浏览器。'
  } catch (cause) { error.value = storageError(cause) }
  finally { noteBusy.value = false }
}
async function original() {
  if (!active.value) return
  try { download(await readFile(active.value.id), active.value.name) } catch (cause) { error.value = storageError(cause) }
}
async function reparse() {
  const paper = active.value
  if (!paper || busy.value || aiBusy.value || noteBusy.value || deleting.value) return
  try { await importFile(new File([await readFile(paper.id)], paper.name, { type: 'application/pdf' })) }
  catch (cause) { error.value = storageError(cause) }
}
function exportNotes() {
  if (!active.value) return
  exportText.value = notesMarkdown(active.value, notes.value)
  exportName.value = `${active.value.name.replace(/\.pdf$/i, '')}-研究笔记.md`
  exportOpen.value = true
}
function downloadNotes() {
  download(new Blob([exportText.value], { type: 'text/markdown;charset=utf-8' }), exportName.value)
  status.value = '已请求下载；如果浏览器未显示下载，可在导出预览中复制全部文字。'
}
async function copyNotes() {
  try { await navigator.clipboard.writeText(exportText.value); status.value = '已复制完整笔记与来源页码。' }
  catch { error.value = '浏览器未允许复制，请选中导出预览中的文字后手动复制。' }
}
async function deletePaper() {
  if (!active.value || busy.value || aiBusy.value || noteBusy.value || deleting.value) return
  const id = active.value.id
  deleting.value = true
  try {
    await removePaper(id)
    localStorage.removeItem(draftKey(id)); localStorage.removeItem(`researchpilot:translation-options:${id}`); selectedId.value = ''; notes.value = []; noteBody.value = ''; noteQuote.value = ''
    await refresh(); deleting.value = false
    if (papers.value[0]) await selectPaper(papers.value[0])
    pendingDelete.value = false; status.value = '已从当前浏览器移除该论文及其笔记。'
  } catch (cause) { error.value = storageError(cause) }
  finally { deleting.value = false }
}
async function protectStorage() {
  try {
    persistent.value = await navigator.storage?.persist() || false
    status.value = persistent.value ? '浏览器已允许持续保存；手动清理网站数据仍会删除资料，请定期导出笔记。' : '浏览器未授予持续保存权限，现有资料仍保留；请定期导出笔记。'
  } catch { error.value = '当前浏览器不支持持续保存请求，请定期导出笔记。' }
}
async function refreshAfterOcr() {
  ++searchId; hits.value = []; searched.value = false; searching.value = false
  try { await refresh() } catch (cause) { error.value = storageError(cause) }
}
function leaving(event: BeforeUnloadEvent) { if (busy.value || aiBusy.value) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(() => !(busy.value || aiBusy.value) || window.confirm('论文任务正在处理，离开会停止未完成部分。仍要离开吗？'))
onMounted(async () => {
  try {
    worker = new Worker(new URL('../research/search.worker.ts', import.meta.url), { type: 'module' })
    worker.onmessage = event => {
      if (event.data.id !== searchId) return
      searching.value = false
      if (event.data.error) error.value = event.data.error
      else { hits.value = event.data.hits; expansion.value = event.data.expansion }
    }
    worker.onerror = () => { searching.value = false; error.value = '检索线程未能启动，请刷新页面或更新浏览器。' }
    await refresh()
    const id = localStorage.getItem('researchpilot:selected')
    const paper = papers.value.find(p => p.id === id) || papers.value[0]
    if (paper) await selectPaper(paper)
  } catch (cause) { error.value = storageError(cause) }
  finally { loading.value = false }
  window.addEventListener('beforeunload', leaving)
})
onBeforeUnmount(() => { controller?.abort(); worker?.terminate(); window.removeEventListener('beforeunload', leaving) })
watch([query, limited, firstPage, lastPage], () => {
  ++searchId; searching.value = false; searched.value = false; hits.value = []; expansion.value = []
}, { flush: 'sync' })
</script>

<template>
  <div class="rp-workspace" @dragover.prevent @drop.prevent="dropped">
    <header class="rp-heading"><div><p class="eyebrow">RESEARCHPILOT / BROWSER EDITION</p><h1>你的论文，本地研读。</h1><p>读原文、找证据、留笔记。可选接入模型，深入问答、理解公式与翻译全文。</p></div><RouterLink to="/researchpilot" class="text-link">项目说明 ↗</RouterLink></header>
    <aside class="rp-privacy"><span aria-hidden="true">◉</span><div><strong>浏览器本地版 · 本地阅读无需登录</strong><p>论文与笔记保存在当前浏览器，不跨设备同步。本地阅读、检索和 OCR 不上传论文。确认启用站点模型后，所需文字或页面图片经本站服务端发送给 OpenAI，费用由站长承担；自有模型则直接发送到你指定的服务。清理网站数据、更换浏览器或使用隐私模式可能丢失资料，请保留原 PDF 并定期导出笔记。</p></div></aside>
    <p v-if="error" class="rp-message rp-error" role="alert">{{ error }}</p>
    <p v-if="status" class="rp-message" role="status">{{ status }}</p>
    <section v-if="exportOpen" class="rp-export" aria-label="笔记导出预览"><div class="rp-panel-heading"><h2>笔记导出预览</h2><button @click="exportOpen = false">关闭预览</button></div><p class="rp-small">{{ exportName }} · 包含原文引用、来源校验值与 PDF 页码。</p><textarea aria-label="Markdown 笔记内容" :value="exportText" readonly rows="10" @focus="($event.target as HTMLTextAreaElement).select()"></textarea><div><button class="rp-primary" @click="downloadNotes">下载 Markdown 文件</button><button class="rp-primary" @click="copyNotes">复制全部笔记</button></div></section>
    <div v-if="busy" class="rp-import-status" role="status"><div><strong>{{ saving ? '正在保存到浏览器…' : progress.total ? `正在解析第 ${progress.current} / ${progress.total} 页` : '正在读取与校验 PDF…' }}</strong><button :disabled="saving" @click="controller?.abort()">取消导入</button></div><progress :value="progress.current" :max="progress.total || 1" aria-label="论文解析进度"></progress><p>请保持此页面打开；完成后可在同一浏览器继续阅读。</p></div>
    <div class="rp-layout">
      <aside class="rp-library" aria-label="本地论文库">
        <div class="rp-panel-heading"><h2>论文库</h2><span>{{ papers.length }} / {{ MAX_PAPERS }}</span></div>
        <input ref="fileInput" class="rp-hidden" type="file" accept=".pdf,application/pdf" aria-label="选择 PDF 论文" @change="importFile(($event.target as HTMLInputElement).files?.[0])">
        <button class="rp-import-button" :disabled="busy || aiBusy || loading || noteBusy || deleting" @click="fileInput?.click()">＋ 导入 PDF</button>
        <p class="rp-small">每次一篇 · 最大 200 MB / 300 页<br>也可以将 PDF 拖入这里。</p>
        <p v-if="loading" role="status">正在读取本地资料…</p>
        <p v-else-if="!papers.length" class="rp-empty-library">还没有论文。<br>导入后即可查看原文与检索。</p>
        <ul class="rp-paper-list"><li v-for="paper in papers" :key="paper.id"><button :class="{ selected: selectedId === paper.id }" :aria-current="selectedId === paper.id ? 'true' : undefined" :disabled="busy || aiBusy || noteBusy || deleting" @click="selectPaper(paper)"><strong>{{ paper.name }}</strong><span>{{ paper.pageCount }} 页 · {{ formatSize(paper.size) }}</span></button></li></ul>
        <div class="rp-storage"><p>已保存原文 {{ formatSize(used) }}</p><p v-if="storageRemaining !== null">浏览器剩余约 {{ formatSize(storageRemaining) }}</p><button @click="protectStorage" :disabled="persistent">{{ persistent ? '已获持续保存权限' : '请求浏览器持续保存' }}</button><p>容量由浏览器管理，剩余空间为估算值。</p></div>
      </aside>
      <div v-if="active" class="rp-document">
        <div class="rp-document-heading"><div><h2>{{ active.name }}</h2><p>{{ active.pageCount }} 页 · {{ active.passages.length }} 个检索片段 · 离线术语检索</p></div><div class="rp-file-actions"><button @click="original">下载原文</button><button :disabled="busy || aiBusy || noteBusy || deleting" @click="reparse">重新解析</button><button :disabled="busy || aiBusy || noteBusy || deleting" @click="pendingDelete = !pendingDelete">移除</button></div></div>
        <div v-if="pendingDelete" class="rp-delete-confirm"><p>移除后，这篇论文、阅读位置、笔记、问答、公式结果和译文将从当前浏览器删除，无法撤销。请先下载原文、导出笔记。</p><button @click="exportNotes">先导出笔记</button><button @click="deletePaper">确认移除本地资料</button><button @click="pendingDelete = false">保留</button></div>
        <p v-if="active.emptyPages.length" class="rp-scan-warning">第 {{ active.emptyPages.slice(0, 12).join('、') }}{{ active.emptyPages.length > 12 ? ' 等' : '' }} 页没有提取到文字，可能为扫描页；仍可查看原文；可在下方“智能精读 → 扫描 OCR”识别文字。</p>
        <div class="rp-reading-layout">
          <PdfReader :paper="active" :page="currentPage" @update:page="pageChanged" />
          <div class="rp-research-panel">
            <IntelligencePanel :paper="active" :page="currentPage" :disabled="busy || noteBusy || deleting" @busy="aiBusy = $event" @updated="refreshAfterOcr" @page="pageChanged" />
            <section class="rp-search-section" aria-labelledby="rp-search-title"><div class="rp-panel-heading"><h2 id="rp-search-title">带着问题找证据</h2><span>当前论文</span></div><p class="rp-small">支持中文或英文关键词。结果为真实原文摘录，不是大模型回答。</p><form @submit.prevent="find"><label class="rp-label" for="rp-query">研究问题或关键词</label><textarea id="rp-query" v-model="query" maxlength="2000" rows="3" placeholder="例如：这篇论文的损失函数是什么？" required></textarea><div class="rp-suggestions"><button v-for="text in suggestions" :key="text" type="button" @click="suggest(text)">{{ text }}</button></div><label class="rp-range-toggle"><input v-model="limited" type="checkbox"> 限定页码范围</label><div v-if="limited" class="rp-range"><label>从 <input v-model.number="firstPage" type="number" min="1" :max="active.pageCount" required> 页</label><label>到 <input v-model.number="lastPage" type="number" min="1" :max="active.pageCount" required> 页</label></div><button type="submit" class="rp-primary" :disabled="searching">{{ searching ? '正在检索…' : '检索原文 →' }}</button></form>
              <p v-if="expansion.length" class="rp-expansion">术语对照：{{ expansion.map(item => `${item.term} → ${item.alternatives.join(' / ')}`).join('；') }}</p>
              <p v-if="searched && !searching && !hits.length" class="rp-no-hits">没有找到匹配证据。可换一个关键词、扩大页码范围，或使用论文中的英文术语；中文支持来自内置术语对照，暂不提供通用翻译。</p>
              <div class="rp-results" aria-live="polite"><article v-for="(hit, index) in hits" :key="`${hit.page}-${hit.ordinal}`"><h3>[{{ index + 1 }}] 第 {{ hit.page }} 页</h3><p>{{ hit.text }}</p><small>提取文本用于检索；公式和复杂版式请核对原文。</small><div><button @click="pageChanged(hit.page)">查看这一页 ↗</button><button @click="cite(hit)">引用到笔记 ＋</button></div></article></div>
            </section>
            <section class="rp-notes-section" aria-labelledby="rp-notes-title"><div class="rp-panel-heading"><h2 id="rp-notes-title">研究笔记</h2><button :disabled="!notes.length" @click="exportNotes">导出 {{ notes.length }} 条笔记 ↓</button></div><p class="rp-small">当前草稿关联第 {{ notePage }} 页。<button @click="useCurrentPage">改为当前阅读页</button></p><blockquote v-if="noteQuote">{{ noteQuote }}<button @click="noteQuote = ''; writeDraft()">移除引用</button></blockquote><label class="rp-label" for="rp-note">我的理解与待验证问题</label><textarea id="rp-note" v-model="noteBody" rows="4" maxlength="10000" placeholder="记录自己的理解，保留原文出处。" @input="writeDraft"></textarea><button class="rp-primary" :disabled="!noteBody.trim() || noteBusy" @click="addNote">{{ noteBusy ? '正在保存…' : '保存笔记' }}</button><p class="rp-small">输入草稿会缓存在当前浏览器；保存后可导出 Markdown。</p><details v-if="notes.length" class="rp-saved-notes"><summary>已保存的 {{ notes.length }} 条笔记</summary><article v-for="note in notes" :key="note.id"><button @click="pageChanged(note.page)">第 {{ note.page }} 页 ↗</button><blockquote v-if="note.quote">{{ note.quote }}</blockquote><p>{{ note.body }}</p></article></details></section>
          </div>
        </div>
      </div>
      <section v-else class="rp-welcome" aria-label="开始研读"><span class="rp-welcome-symbol" aria-hidden="true">▤</span><p class="eyebrow">READ. VERIFY. RECORD.</p><h2>从一篇论文开始。</h2><p>导入 PDF 后，左侧看原文，右侧找证据。<br>公式保留原始版式，笔记随时导出。</p><ol><li><span>01</span><div><strong>在浏览器里导入</strong><p>文件留在自己的设备，无需账户或模型密钥。</p></div></li><li><span>02</span><div><strong>中文查找英文证据</strong><p>对照实际原文，支持常见科研术语与页码范围。</p></div></li><li><span>03</span><div><strong>记下理解与出处</strong><p>引用片段关联到页，刷新后继续阅读。</p></div></li></ol><p class="rp-small">建议使用最新版 Chrome、Edge、Firefox 或 Safari。首次打开需要联网加载网页；当前未提供断网安装包。</p></section>
    </div>
  </div>
</template>

<style src="../research/workspace.css"></style>
