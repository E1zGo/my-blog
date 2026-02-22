<script setup lang="ts">
import { useHead } from '@vueuse/head'
import { getAllTags } from '@/utils/posts'
import blogConfig from '../../../blog.config'

useHead({ title: `标签 — ${blogConfig.title}` })
const tags = getAllTags()
</script>

<template>
  <div class="max-w-4xl mx-auto px-6 py-12">
    <div class="mb-10 pb-6 border-b-2 border-[var(--color-ink)]">
      <p class="font-mono text-xs tracking-widest uppercase text-[var(--color-accent)] mb-2">// Tags</p>
      <h1 class="font-serif text-4xl font-bold">所有标签</h1>
    </div>

    <div class="grid sm:grid-cols-2 md:grid-cols-3 gap-4">
      <RouterLink
        v-for="tag in tags"
        :key="tag.name"
        :to="`/tags/${tag.name}`"
        class="group flex items-center justify-between p-5 border-2 border-[rgba(26,22,18,0.15)] hover:border-[var(--color-accent)] transition-all no-underline"
      >
        <div>
          <div class="font-mono text-[10px] tracking-widest uppercase text-[var(--color-accent)] mb-1">// tag</div>
          <div class="font-serif text-lg font-semibold group-hover:text-[var(--color-accent)] transition-colors">{{ tag.name }}</div>
        </div>
        <div class="font-mono text-3xl font-bold text-[var(--color-warm)] group-hover:text-[var(--color-accent)] transition-colors">
          {{ tag.count }}
        </div>
      </RouterLink>
    </div>
  </div>
</template>
