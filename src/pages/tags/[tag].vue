<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useHead } from '@vueuse/head'
import PostCard from '@/components/blog/PostCard.vue'
import { getAllPosts } from '@/utils/posts'
import blogConfig from '../../../blog.config'

const route = useRoute()
const tag = route.params.tag as string

const posts = computed(() => getAllPosts().filter(p => p.tags.includes(tag)))

useHead({ title: `#${tag} — ${blogConfig.title}` })
</script>

<template>
  <div class="max-w-4xl mx-auto px-6 py-12">
    <div class="mb-10 pb-6 border-b-2 border-[var(--color-ink)]">
      <RouterLink
        to="/tags"
        class="font-mono text-xs tracking-widest uppercase text-[var(--color-muted)] hover:text-[var(--color-accent)] transition-colors no-underline mb-4 block"
      >
        ← 所有标签
      </RouterLink>
      <p class="font-mono text-xs tracking-widest uppercase text-[var(--color-accent)] mb-2">// Tag</p>
      <h1 class="font-serif text-4xl font-bold"># {{ tag }}</h1>
      <p class="text-[var(--color-muted)] font-mono text-sm mt-2">共 {{ posts.length }} 篇</p>
    </div>

    <div class="border border-[rgba(26,22,18,0.15)]">
      <PostCard v-for="post in posts" :key="post.slug" :post="post" />
    </div>

    <div v-if="!posts.length" class="text-center py-16 text-[var(--color-muted)] font-mono text-sm">
      该标签下暂无文章
    </div>
  </div>
</template>
