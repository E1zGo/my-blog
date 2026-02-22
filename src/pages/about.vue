<script setup lang="ts">
import { useHead } from '@vueuse/head'
import blogConfig from '../../blog.config'

useHead({ title: `关于 — ${blogConfig.title}` })

const skills = ['Vue 3', 'TypeScript', 'Node.js', 'Vite', 'CSS / TailwindCSS', 'Git']
</script>

<template>
  <div class="max-w-4xl mx-auto px-6 py-12">
    <!-- Header -->
    <div class="mb-12 pb-6 border-b-2 border-[var(--color-ink)]">
      <p class="font-mono text-xs tracking-widest uppercase text-[var(--color-accent)] mb-2">// About</p>
      <h1 class="font-serif text-4xl font-bold">关于我</h1>
    </div>

    <div class="grid md:grid-cols-3 gap-12">
      <!-- Avatar & Info -->
      <div class="text-center md:text-left">
        <!-- Avatar placeholder -->
        <div class="w-32 h-32 mx-auto md:mx-0 bg-[var(--color-ink)] flex items-center justify-center mb-5 border-4 border-[var(--color-accent)]">
          <span class="font-serif text-5xl font-bold text-[var(--color-paper)]">
            {{ blogConfig.author.charAt(0) }}
          </span>
        </div>
        <h2 class="font-serif text-2xl font-bold mb-2">{{ blogConfig.author }}</h2>
        <p class="font-mono text-xs text-[var(--color-muted)] mb-5">开发者 / 写作者</p>

        <!-- Socials -->
        <div class="flex flex-col gap-2">
          <a :href="blogConfig.socials.github" target="_blank"
             class="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent)] transition-colors no-underline">
            GitHub →
          </a>
          <a :href="blogConfig.socials.twitter" target="_blank"
             class="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent)] transition-colors no-underline">
            Twitter →
          </a>
          <a :href="`mailto:${blogConfig.socials.email}`"
             class="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent)] transition-colors no-underline">
            Email →
          </a>
        </div>
      </div>

      <!-- Bio & Skills -->
      <div class="md:col-span-2">
        <div class="prose prose-lg max-w-none mb-10
          prose-headings:font-serif prose-headings:font-semibold
          prose-a:text-[var(--color-accent)]">
          <p>
            你好！我是 <strong>{{ blogConfig.author }}</strong>，一名热爱技术与写作的开发者。
            在这里我会分享关于前端开发、软件工程以及个人思考的文章。
          </p>
          <p>
            这个博客使用 <strong>Vue 3 + Vite + TailwindCSS v4</strong> 搭建，文章以 Markdown 格式存储在
            <code>content/posts/</code> 目录下，开箱即用，简单高效。
          </p>
          <p>
            如果你对某篇文章有想法，或者想要交流合作，欢迎通过上方任意方式联系我。
          </p>
        </div>

        <!-- Skills -->
        <div>
          <h3 class="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)] mb-4 pb-2 border-b border-[rgba(26,22,18,0.15)]">
            技术栈
          </h3>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="skill in skills"
              :key="skill"
              class="font-mono text-xs px-3 py-1.5 border border-[rgba(26,22,18,0.2)] text-[var(--color-muted)] hover:bg-[var(--color-ink)] hover:text-[var(--color-paper)] hover:border-[var(--color-ink)] transition-all cursor-default"
            >
              {{ skill }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
