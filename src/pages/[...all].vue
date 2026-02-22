<script setup lang="ts">
import { useHead } from '@vueuse/head'
import blogConfig from '../../blog.config'
useHead({ title: `404 — ${blogConfig.title}` })
</script>

<template>
  <div class="min-h-[60vh] flex flex-col items-center justify-center text-center px-6">
    <div class="font-mono text-8xl font-bold text-[var(--color-warm)] mb-4 select-none">404</div>
    <h1 class="font-serif text-3xl font-bold mb-4">页面不存在</h1>
    <p class="text-[var(--color-muted)] mb-8 font-mono text-sm">你访问的页面已消失在数字宇宙中。</p>
    <RouterLink
      to="/"
      class="font-mono text-xs tracking-widest uppercase px-8 py-3 bg-[var(--color-ink)] text-[var(--color-paper)] no-underline hover:bg-[var(--color-accent)] transition-colors"
    >
      ← 回到首页
    </RouterLink>
  </div>
</template>
