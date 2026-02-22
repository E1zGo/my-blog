<script setup lang="ts">
import { useRouter } from 'vue-router'
import { formatDateShort } from '@/utils/date'
import type { Post } from '@/types/blog'

const props = defineProps<{ post: Post; featured?: boolean }>()
const router = useRouter()

function go() { router.push(props.post.path) }
</script>

<template>
  <article
    class="group relative cursor-pointer transition-all duration-200 hover:bg-[var(--color-warm)]"
    :class="featured ? 'p-8' : 'p-6'"
    @click="go"
  >
    <!-- top accent line -->
    <div class="absolute top-0 left-0 right-0 h-[3px] bg-[var(--color-accent)] scale-x-0 group-hover:scale-x-100 transition-transform duration-200 origin-left" />

    <!-- 封面图 -->
    <div v-if="post.cover" class="mb-4 overflow-hidden h-40">
      <img :src="post.cover" :alt="post.title" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
    </div>

    <!-- Tags -->
    <div class="flex flex-wrap gap-2 mb-3">
      <span
        v-for="tag in post.tags.slice(0, 2)"
        :key="tag"
        class="font-mono text-[10px] tracking-widest uppercase text-[var(--color-accent)]"
      >
        // {{ tag }}
      </span>
      <!-- 无标签时占位，确保布局稳定 -->
      <span v-if="!post.tags.length" class="font-mono text-[10px] text-[var(--color-muted)]">// 随笔</span>
    </div>

    <!-- Title — 强制显示，fallback 到 slug -->
    <h2
      class="font-serif font-semibold leading-snug mb-3 transition-colors group-hover:text-[var(--color-accent)]"
      :class="featured ? 'text-2xl' : 'text-xl'"
    >
      {{ post.title || post.slug }}
    </h2>

    <!-- Excerpt -->
    <p v-if="post.excerpt" class="text-sm leading-relaxed text-[var(--color-muted)] mb-4 line-clamp-3">
      {{ post.excerpt }}
    </p>

    <!-- Meta -->
    <div class="flex items-center justify-between font-mono text-[11px] tracking-wide text-[var(--color-muted)]">
      <span>{{ formatDateShort(post.date) }}</span>
      <span class="bg-[var(--color-warm)] px-2 py-0.5 group-hover:bg-[var(--color-paper)] transition-colors">
        {{ post.readTime ?? 1 }} min read
      </span>
    </div>
  </article>
</template>
