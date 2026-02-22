<script setup lang="ts">
import { useReadingProgress } from '@/composables/useReadingProgress'
const { progress } = useReadingProgress()
</script>

<template>
  <div class="fixed top-[56px] left-0 right-0 z-40 h-[3px] bg-[rgba(26,22,18,0.1)]">
    <div
      class="h-full bg-[var(--color-accent)] transition-[width] duration-100 ease-out"
      :style="{ width: progress + '%' }"
    />
  </div>
</template>
