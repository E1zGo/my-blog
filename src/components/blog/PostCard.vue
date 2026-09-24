<script setup lang="ts">
import { formatDateShort } from '@/utils/date'
import type { Post } from '@/types/blog'
defineProps<{ post: Post; featured?: boolean; index?: number }>()
</script>
<template>
  <article class="post-card" :class="{ 'post-card-featured': featured }">
    <div v-if="index !== undefined" class="post-number">{{ String(index + 1).padStart(2, '0') }}</div>
    <div class="post-card-body"><div class="post-meta"><time :datetime="post.date">{{ formatDateShort(post.date) }}</time><span class="meta-dot">·</span><span>{{ post.readTime }} 分钟阅读</span></div><h2><RouterLink :to="post.path" class="post-title-link">{{ post.title }}</RouterLink></h2><p class="post-excerpt">{{ post.excerpt }}</p><div class="post-card-bottom"><div class="post-tags"><RouterLink v-for="tag in post.tags" :key="tag" :to="`/tags/${encodeURIComponent(tag)}`">{{ tag }}</RouterLink></div><span class="post-arrow" aria-hidden="true">↗</span></div></div>
    <img v-if="post.cover" class="post-cover" :src="post.cover" :alt="post.title" loading="lazy" width="240" height="160" />
  </article>
</template>
