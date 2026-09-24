<script setup lang="ts">
import { defineAsyncComponent, ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useHead } from '@vueuse/head'
import { getPostBySlug, getPrevNextPost } from '@/utils/posts'
import { formatDate } from '@/utils/date'
import ReadingProgress from '@/components/ui/ReadingProgress.vue'
import TableOfContents from '@/components/blog/TableOfContents.vue'
import GiscusComment from '@/components/ui/GiscusComment.vue'
import NotFound from '@/pages/[...all].vue'
import blogConfig from '../../../blog.config'

const route = useRoute()
const slug = route.params.slug as string
const post = getPostBySlug(slug)
useHead({
  title: post ? `${post.title} — ${blogConfig.title}` : `404 — ${blogConfig.title}`,
  meta: post ? [{ name: 'description', content: post.excerpt }] : [{ name: 'robots', content: 'noindex' }],
  link: post ? [{ rel: 'canonical', href: `${blogConfig.siteUrl}${post.path}` }] : [],
})
const { prev: prevPost, next: nextPost } = getPrevNextPost(slug)
const modules = import.meta.glob('/content/posts/*.md')
const loader = modules[`/content/posts/${slug}.md`]
const loadError = ref(false)
const contentReady = ref(false)
const PostContent = post && loader ? defineAsyncComponent({
  loader: loader as () => Promise<{ default: object }>,
  onError() { loadError.value = true },
}) : null

async function onContentReady() {
  await nextTick()
  contentReady.value = true
  document.querySelectorAll<HTMLElement>('[data-post-content] pre').forEach(pre => {
    if (pre.querySelector('.copy-code')) return
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'copy-code'
    button.textContent = '复制代码'
    button.setAttribute('aria-label', '复制代码')
    pre.dataset.language = pre.querySelector('code')?.className.replace('language-', '') || 'text'
    pre.appendChild(button)
  })
  if (route.hash) {
    try { document.getElementById(decodeURIComponent(route.hash.slice(1)))?.scrollIntoView({ behavior: 'instant' }) } catch { /* Invalid URL fragments do not affect the article. */ }
  }
}
const timers = new Set<ReturnType<typeof setTimeout>>()
async function copyCode(event: MouseEvent) {
  const target = event.target
  if (!(target instanceof HTMLButtonElement) || !target.classList.contains('copy-code')) return
  const code = target.parentElement?.querySelector('code')?.textContent || ''
  try {
    await navigator.clipboard.writeText(code)
    target.textContent = '已复制 ✓'
  } catch { target.textContent = '请手动选择复制' }
  const timer = setTimeout(() => { target.textContent = '复制代码'; timers.delete(timer) }, 2000)
  timers.add(timer)
}
onMounted(() => { if (!PostContent && post) loadError.value = true })
onUnmounted(() => timers.forEach(clearTimeout))
</script>

<template>
  <div v-if="post">
    <ReadingProgress v-if="blogConfig.features.readingProgress" />
    <div class="page-width reading-layout">
      <div class="reading-main">
        <RouterLink to="/posts" class="text-link article-back">← 返回文章列表</RouterLink>
        <header class="article-header"><div class="post-tags"><RouterLink v-for="tag in post.tags" :key="tag" :to="`/tags/${encodeURIComponent(tag)}`">{{ tag }}</RouterLink></div><h1>{{ post.title }}</h1><div class="post-meta"><span>{{ blogConfig.author }}</span><span>·</span><time :datetime="post.date">{{ formatDate(post.date) }}</time><span>·</span><span>{{ post.readTime }} 分钟阅读</span><span v-if="post.updated">更新于 {{ formatDate(post.updated) }}</span></div></header>
        <img v-if="post.cover" :src="post.cover" :alt="post.title" class="article-cover" />
        <p v-if="post.excerpt" class="article-excerpt">{{ post.excerpt }}</p>
        <details v-if="blogConfig.features.toc && contentReady" class="mobile-toc"><summary>文章目录</summary><TableOfContents /></details>
        <p v-if="loadError" role="alert" class="empty-state">文章暂时加载失败。<button class="text-link" @click="() => { $router.go(0) }">重新加载 ↻</button></p>
        <p v-else-if="!contentReady" class="empty-state" role="status">正在打开文章…</p>
        <article data-post-content class="prose" @click="copyCode"><component :is="PostContent" v-if="PostContent" @vue:mounted="onContentReady" /></article>
        <p class="article-end">— 感谢阅读，希望对你有所启发 —</p>
        <nav class="post-pagination" aria-label="相邻文章"><RouterLink v-if="prevPost" :to="prevPost.path"><span>← 上一篇</span><strong>{{ prevPost.title }}</strong></RouterLink><div v-else /><RouterLink v-if="nextPost" :to="nextPost.path" class="next"><span>下一篇 →</span><strong>{{ nextPost.title }}</strong></RouterLink></nav>
        <GiscusComment v-if="blogConfig.features.comments" />
      </div>
      <aside v-if="blogConfig.features.toc" class="reading-sidebar"><TableOfContents /></aside>
    </div>
  </div>
  <NotFound v-else />
</template>
