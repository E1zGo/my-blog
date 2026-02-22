<script setup lang="ts">
import { useHead } from '@vueuse/head'
import PostCard from '@/components/blog/PostCard.vue'
import TagCloud from '@/components/blog/TagCloud.vue'
import { getAllPosts } from '@/utils/posts'
import blogConfig from '../../blog.config'

useHead({ title: `${blogConfig.title} — ${blogConfig.subtitle}` })

const posts = getAllPosts()
const latestPosts = posts.slice(0, 6)
const featuredPost = posts[0]
</script>

<template>
  <!-- ── HERO ── -->
  <section class="border-b-2 border-[var(--color-ink)] bg-[var(--color-ink)] overflow-hidden">
    <div class="max-w-6xl mx-auto px-6 py-20 grid md:grid-cols-2 gap-12 items-center">
      <!-- Text -->
      <div>
        <p class="font-mono text-xs tracking-[0.2em] uppercase text-[var(--color-accent)] mb-5 animate-fade-in-up">
          // 欢迎来到我的数字空间
        </p>
        <h1 class="font-serif text-4xl md:text-5xl lg:text-6xl font-bold leading-tight text-[var(--color-paper)] mb-6 animate-fade-in-up delay-100">
          {{ blogConfig.subtitle }}
        </h1>
        <p class="text-[var(--color-muted)] leading-relaxed mb-8 animate-fade-in-up delay-200">
          {{ blogConfig.description }}
        </p>
        <div class="flex gap-4 animate-fade-in-up delay-300">
          <RouterLink
            to="/posts"
            class="inline-flex items-center gap-2 bg-[var(--color-accent)] text-white px-6 py-3 font-mono text-xs tracking-widest uppercase no-underline hover:bg-[var(--color-accent2)] transition-colors"
          >
            → 开始阅读
          </RouterLink>
          <RouterLink
            to="/about"
            class="inline-flex items-center gap-2 border-2 border-[rgba(255,255,255,0.2)] text-[var(--color-warm)] px-6 py-3 font-mono text-xs tracking-widest uppercase no-underline hover:border-[var(--color-accent)] transition-colors"
          >
            关于我
          </RouterLink>
        </div>
      </div>

      <!-- Terminal Card -->
      <div class="animate-fade-in-up delay-200">
        <div class="bg-[var(--color-code-bg)] border border-[rgba(255,255,255,0.08)] p-6 font-mono text-sm">
          <div class="flex gap-2 mb-5">
            <div class="w-3 h-3 rounded-full bg-[#ff5f56]" />
            <div class="w-3 h-3 rounded-full bg-[#ffbd2e]" />
            <div class="w-3 h-3 rounded-full bg-[#27c93f]" />
          </div>
          <div class="text-[#6b5c4a] mb-2"># blog.config.ts</div>
          <div class="text-[#c5b9a8] leading-7 text-xs">
            <div><span class="text-[#e67e22]">author</span>: <span class="text-[#a8c5a0]">'{{ blogConfig.author }}'</span>,</div>
            <div><span class="text-[#e67e22]">posts</span>: <span class="text-[#7eb8c4]">{{ posts.length }}</span>,</div>
            <div><span class="text-[#e67e22]">stack</span>: [</div>
            <div class="pl-4"><span class="text-[#a8c5a0]">'Vue 3'</span>, <span class="text-[#a8c5a0]">'Vite'</span>,</div>
            <div class="pl-4"><span class="text-[#a8c5a0]">'TailwindCSS v4'</span>,</div>
            <div class="pl-4"><span class="text-[#a8c5a0]">'TypeScript'</span>,</div>
            <div>],</div>
          </div>
        </div>

        <!-- Stats -->
        <div class="grid grid-cols-2 gap-3 mt-3">
          <div
            v-for="stat in [
              { num: posts.length, label: '篇文章' },
              { num: 6, label: '个项目' },
            ]"
            :key="stat.label"
            class="bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.08)] p-4"
          >
            <div class="font-mono text-2xl font-semibold text-[var(--color-accent2)]">{{ stat.num }}</div>
            <div class="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)] mt-1">{{ stat.label }}</div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ── LATEST POSTS ── -->
  <section class="max-w-6xl mx-auto px-6 py-12">
    <div class="flex items-baseline justify-between mb-8 pb-4 border-b-2 border-[var(--color-ink)]">
      <div class="flex items-baseline gap-4">
        <span class="bg-[var(--color-accent)] text-white font-mono text-[10px] tracking-widest uppercase px-2 py-1">Latest</span>
        <h2 class="font-serif text-2xl font-semibold">最新文章</h2>
      </div>
      <RouterLink
        to="/posts"
        class="font-mono text-xs tracking-widest uppercase text-[var(--color-accent)] no-underline border-b border-[var(--color-accent)] hover:text-[var(--color-accent2)] hover:border-[var(--color-accent2)] transition-colors"
      >
        查看全部 →
      </RouterLink>
    </div>

    <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-0 border border-[rgba(26,22,18,0.15)]">
      <PostCard
        v-for="post in latestPosts"
        :key="post.slug"
        :post="post"
        class="border-r border-[rgba(26,22,18,0.15)] last:border-r-0"
      />
    </div>

    <div v-if="!latestPosts.length" class="text-center py-16 text-[var(--color-muted)] font-mono text-sm">
      暂无文章，请在 content/posts/ 下创建 .md 文件
    </div>
  </section>

  <!-- ── TAG CLOUD ── -->
  <section class="max-w-6xl mx-auto px-6 pb-16 border-t border-[rgba(26,22,18,0.15)] pt-10">
    <h3 class="font-mono text-xs tracking-widest uppercase text-[var(--color-muted)] mb-5">// 标签云</h3>
    <TagCloud />
  </section>
</template>
