<script setup lang="ts">
import { useHead } from '@vueuse/head'
import blogConfig from '../../blog.config'

const project = blogConfig.researchPilot
const launchUrl = project.available && project.url === '/research' ? project.url : ''
useHead({
  title: `ResearchPilot — ${blogConfig.title}`,
  meta: [{ name: 'description', content: '在浏览器中阅读 PDF、检索原文、保存引用笔记。无需登录，单篇最大 200 MB。' }],
  link: [{ rel: 'canonical', href: `${blogConfig.siteUrl}/researchpilot` }],
})
const features = [
  { no: '01', title: '带着问题读论文', text: '导入 PDF，按页查看原文与公式，用中文关键词检索英文论文，回到命中的原文核对。', tag: 'PDF · 单文件 200 MB' },
  { no: '02', title: '让结论有出处', text: '在当前论文中限定页码检索，把真实原文摘录与页码一起加入研究笔记。', tag: '检索 · 引用 · 笔记' },
  { no: '03', title: '随时接着读下去', text: '原文、阅读位置与笔记保存在当前浏览器。刷新后继续研读，随时导出 Markdown 笔记。', tag: '本地保存 · 阅读进度 · 导出' },
]
</script>

<template>
  <div class="page-width research-page">
    <section class="research-hero">
      <div>
        <p class="eyebrow">A PROJECT BY E1ZGO <span class="research-separator">/</span> RESEARCHPILOT</p>
        <h1>从论文到理解，<br><span>每一步都有依据。</span></h1>
        <p class="research-intro">一个把论文阅读、证据检索与引用笔记放在一起的本地科研工作台。<br class="desktop-break">少一点来回翻找，多一点有迹可循。</p>
        <div class="research-actions">
          <a v-if="launchUrl" class="button-primary" :href="launchUrl">进入 ResearchPilot <span aria-hidden="true">↗</span></a>
          <span v-else class="research-pending">上线准备中</span>
          <a href="#capabilities" class="text-link">看看能做什么 <span aria-hidden="true">↓</span></a>
        </div>
        <p class="research-note">{{ launchUrl ? '浏览器本地版 · 无需登录 · 资料留在当前设备' : '线上工作台尚未开放，开放后可从这里进入。' }}</p>
      </div>
      <aside class="research-sheet" aria-label="研究流程：论文原文、检索证据、研究记录">
        <div class="sheet-top"><span>RESEARCH NOTEBOOK</span><span aria-hidden="true">↗</span></div>
        <div class="sheet-row"><span class="sheet-number">01</span><div><h2>论文原文</h2><p>页码、段落与公式</p></div><span class="sheet-mark" aria-hidden="true">↘</span></div>
        <div class="sheet-row"><span class="sheet-number">02</span><div><h2>检索证据</h2><p>从问题回到出处</p></div><span class="sheet-mark" aria-hidden="true">↘</span></div>
        <div class="sheet-row"><span class="sheet-number">03</span><div><h2>研究记录</h2><p>理解、引用与笔记</p></div><span class="sheet-mark" aria-hidden="true">✓</span></div>
        <p class="sheet-bottom">READ. VERIFY. RECORD.</p>
      </aside>
    </section>
    <section id="capabilities" aria-labelledby="capabilities-title" class="research-capabilities">
      <div class="section-heading"><div><p class="eyebrow">YOUR RESEARCH, IN ONE PLACE</p><h2 id="capabilities-title">把研究过程串起来</h2></div><span class="research-edition">浏览器本地版</span></div>
      <div class="research-feature-grid">
        <article v-for="feature in features" :key="feature.no" class="research-feature">
          <span class="feature-number">{{ feature.no }}</span><h3>{{ feature.title }}</h3><p>{{ feature.text }}</p><small>{{ feature.tag }}</small>
        </article>
      </div>
    </section>
    <section class="research-expectation" aria-labelledby="expectation-title">
      <div><p class="eyebrow">BEFORE YOU START</p><h2 id="expectation-title">先知道这些，再开始。</h2></div>
      <div><p>单篇 PDF 最大 200 MB、300 页，最多保存 20 篇。文件只在浏览器中解析和保存，不上传服务器，不跨设备同步。清理网站数据或使用隐私模式可能丢失资料，请保留原 PDF 并定期导出笔记。</p><p>中文检索使用内置科研术语对照，结果是真实原文摘录；暂不提供通用翻译、大模型回答或 OCR。公式请查看原版式预览。完整的实验记录与日志对比仍在本机 Python 版中提供。</p></div>
    </section>
    <RouterLink to="/" class="text-link">← 返回博客</RouterLink>
  </div>
</template>

<style scoped>
.research-page{padding-block:64px 72px}.research-hero{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(260px,1fr);gap:70px;align-items:center;padding-bottom:66px}.research-separator{color:var(--color-muted);margin-inline:6px}.research-hero h1{font-family:var(--font-serif);font-size:clamp(32px,3.8vw,46px);line-height:1.65;font-weight:600;margin:0;letter-spacing:1px}.research-hero h1>span{color:var(--color-accent)}.research-intro{font-size:13px;color:var(--color-muted);line-height:2.1;margin:22px 0 26px}.research-actions{display:flex;align-items:center;gap:24px;flex-wrap:wrap}.research-pending{display:inline-flex;padding:12px 23px;background:var(--surface);color:var(--color-muted);border:1px solid var(--line);border-radius:4px;font-size:12px}.research-note{font-size:11px;color:var(--color-muted);margin-top:18px;line-height:1.8}.research-sheet{border:1px solid var(--line);border-radius:5px;background:var(--surface);padding:25px 28px;box-shadow:8px 8px 0 var(--color-warm)}.sheet-top{display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:18px;font-size:9px;font-family:var(--font-mono);letter-spacing:1.8px;color:var(--color-accent)}.sheet-row{display:flex;align-items:center;gap:18px;padding:22px 0;border-bottom:1px solid var(--line)}.sheet-number{font:11px var(--font-mono);color:var(--color-muted)}.sheet-row h2{font:600 19px var(--font-serif);margin:0 0 7px}.sheet-row p{font-size:11px;color:var(--color-muted);margin:0}.sheet-mark{margin-left:auto;color:var(--color-accent);font-size:20px}.sheet-bottom{font:9px var(--font-mono);letter-spacing:2px;color:var(--color-muted);margin:20px 0 0}.research-edition{font-size:11px;color:var(--color-muted);white-space:nowrap}.research-feature-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:34px;padding-block:30px 40px}.feature-number{font:11px var(--font-mono);color:var(--color-accent2)}.research-feature h3{font:600 22px var(--font-serif);margin:15px 0}.research-feature p{font-size:13px;line-height:2;color:var(--color-muted);margin:0 0 18px}.research-feature small{font-size:10px;color:var(--color-accent)}.research-expectation{display:grid;grid-template-columns:1fr 1.5fr;gap:42px;border-block:1px solid var(--line);padding:34px 0;margin-bottom:28px}.research-expectation .eyebrow{margin-bottom:12px}.research-expectation h2{font:600 24px var(--font-serif);margin:0}.research-expectation p:not(.eyebrow){font-size:12px;color:var(--color-muted);line-height:2;margin:0 0 12px}
@media(max-width:900px){.research-hero{gap:35px}.research-hero .eyebrow{font-size:9px;letter-spacing:1px}.desktop-break{display:none}.research-feature-grid{gap:24px}}
@media(max-width:650px){.research-page{padding-top:36px}.research-hero{grid-template-columns:1fr;gap:32px;padding-bottom:42px}.research-hero h1{font-size:32px}.research-sheet{box-shadow:5px 5px 0 var(--color-warm)}.research-feature-grid{grid-template-columns:1fr;gap:26px}.research-feature{padding-bottom:24px;border-bottom:1px solid var(--line)}.research-feature:last-child{padding-bottom:0;border:0}.research-expectation{grid-template-columns:1fr;gap:20px}.research-capabilities .section-heading{align-items:flex-start}.research-capabilities .section-heading h2{font-size:24px}}
</style>
