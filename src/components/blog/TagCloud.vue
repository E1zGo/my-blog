<script setup lang="ts">
import { useRouter } from 'vue-router'
import { getAllTags } from '@/utils/posts'

const router = useRouter()
const tags = getAllTags()
</script>

<template>
  <div class="flex flex-wrap gap-2">
    <button
      v-for="tag in tags"
      :key="tag.name"
      class="font-mono text-xs px-3 py-1.5 bg-[var(--color-paper)] border border-[rgba(26,22,18,0.2)] text-[var(--color-muted)] hover:bg-[var(--color-ink)] hover:text-[var(--color-paper)] transition-all duration-150 cursor-pointer"
      @click="router.push(`/tags/${tag.name}`)"
    >
      {{ tag.name }}
      <span class="ml-1 text-[var(--color-accent)]">{{ tag.count }}</span>
    </button>
  </div>
</template>
