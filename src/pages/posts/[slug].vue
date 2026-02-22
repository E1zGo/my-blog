<script setup lang="ts">
import { defineAsyncComponent } from 'vue'  // 移除 computed，不需要了
import { useRoute, useRouter } from 'vue-router'
import { useHead } from '@vueuse/head'
import { getPostBySlug, getPrevNextPost } from '@/utils/posts'
import { formatDate } from '@/utils/date'
import ReadingProgress from '@/components/ui/ReadingProgress.vue'
import TableOfContents from '@/components/blog/TableOfContents.vue'
import GiscusComment from '@/components/ui/GiscusComment.vue'
import blogConfig from '../../../blog.config'

const route = useRoute()
const router = useRouter()
const slug = route.params.slug as string

const post = getPostBySlug(slug)
if (!post) router.push('/404')

useHead({
  title: post ? `${post.title} — ${blogConfig.title}` : '404',
  meta: post ? [{ name: 'description', content: post.excerpt }] : [],
})

const { prev: prevPost, next: nextPost } = getPrevNextPost(slug)

// ✅ 用 import.meta.glob 替代动态绝对路径 import，Vite 可以静态分析
const mdModules = import.meta.glob('/content/posts/*.md')
const matchKey = Object.keys(mdModules).find(k => k.endsWith(`/${slug}.md`))
const PostContent = matchKey
  ? defineAsyncComponent(mdModules[matchKey] as () => Promise<{ default: object }>)
  : null
</script>

<template>
  <div v-if="post">
    <!-- 阅读进度条 -->
    <ReadingProgress />

    <!-- 封面图 -->
    <div v-if="post.cover" class="w-full h-64 md:h-80 overflow-hidden border-b-2 border-[var(--color-ink)]">
      <img :src="post.cover" :alt="post.title" class="w-full h-full object-cover" />
    </div>

    <div class="max-w-6xl mx-auto px-6 py-12 flex gap-12">
      <!-- 主体内容 -->
      <div class="flex-1 min-w-0">
        <!-- Back -->
        <button
          class="font-mono text-xs tracking-widest uppercase text-[var(--color-muted)] hover:text-[var(--color-accent)] transition-colors mb-10 flex items-center gap-2 cursor-pointer"
          @click="$router.back()"
        >
          ← 返回
        </button>

        <!-- Header -->
        <header class="mb-10 pb-8 border-b-2 border-[var(--color-ink)]">
          <div class="flex flex-wrap gap-2 mb-4">
            <RouterLink
              v-for="tag in post.tags"
              :key="tag"
              :to="`/tags/${tag}`"
              class="font-mono text-[10px] tracking-widest uppercase text-[var(--color-accent)] no-underline hover:underline"
            >
              // {{ tag }}
            </RouterLink>
          </div>

          <h1 class="font-serif text-3xl md:text-4xl font-bold leading-tight mb-5">
            {{ post.title }}
          </h1>

          <div class="flex flex-wrap items-center gap-4 font-mono text-xs text-[var(--color-muted)]">
            <span>{{ formatDate(post.date) }}</span>
            <span class="text-[var(--color-accent)]">·</span>
            <span>{{ post.readTime }} min read</span>
            <span class="text-[var(--color-accent)]">·</span>
            <span>{{ blogConfig.author }}</span>
            <template v-if="post.updated">
              <span class="text-[var(--color-accent)]">·</span>
              <span>更新于 {{ formatDate(post.updated) }}</span>
            </template>
          </div>
        </header>

        <!-- Excerpt -->
        <p class="text-lg leading-relaxed text-[var(--color-muted)] border-l-4 border-[var(--color-accent)] pl-5 mb-10 italic">
          {{ post.excerpt }}
        </p>

        <!-- Content -->
        <article class="prose prose-lg max-w-none
          prose-headings:font-serif prose-headings:font-semibold
          prose-a:text-[var(--color-accent)] prose-a:no-underline hover:prose-a:underline
          prose-blockquote:border-l-[var(--color-accent)]
          prose-code:text-[var(--color-accent)]
          prose-pre:bg-[var(--color-code-bg)]">
          <component :is="PostContent" v-if="PostContent" />
        </article>

        <!-- Tags -->
        <div class="mt-12 pt-8 border-t border-[rgba(26,22,18,0.15)] flex flex-wrap gap-2">
          <RouterLink
            v-for="tag in post.tags"
            :key="tag"
            :to="`/tags/${tag}`"
            class="font-mono text-xs px-3 py-1.5 bg-[var(--color-warm)] border border-[rgba(26,22,18,0.2)] text-[var(--color-muted)] no-underline hover:bg-[var(--color-ink)] hover:text-[var(--color-paper)] transition-all"
          >
            # {{ tag }}
          </RouterLink>
        </div>

        <!-- Prev / Next — 使用 RouterLink 确保跳转正确 -->
        <nav class="mt-10 grid grid-cols-2 gap-4">
          <RouterLink
            v-if="prevPost"
            :to="prevPost.path"
            class="group border-2 border-[rgba(26,22,18,0.15)] p-5 hover:border-[var(--color-accent)] transition-colors no-underline block"
          >
            <div class="font-mono text-[10px] uppercase tracking-widest text-[var(--color-muted)] mb-2">← 上一篇（更早）</div>
            <div class="font-serif text-sm font-semibold text-[var(--color-ink)] group-hover:text-[var(--color-accent)] transition-colors">
              {{ prevPost.title }}
            </div>
          </RouterLink>
          <div v-else />

          <RouterLink
            v-if="nextPost"
            :to="nextPost.path"
            class="group border-2 border-[rgba(26,22,18,0.15)] p-5 hover:border-[var(--color-accent)] transition-colors no-underline text-right block"
          >
            <div class="font-mono text-[10px] uppercase tracking-widest text-[var(--color-muted)] mb-2">下一篇（更新）→</div>
            <div class="font-serif text-sm font-semibold text-[var(--color-ink)] group-hover:text-[var(--color-accent)] transition-colors">
              {{ nextPost.title }}
            </div>
          </RouterLink>
        </nav>

        <!-- 评论 -->
        <GiscusComment />
      </div>

      <!-- 右侧 TOC -->
      <aside class="hidden xl:block w-56 shrink-0">
        <TableOfContents />
      </aside>
    </div>
  </div>
</template>
