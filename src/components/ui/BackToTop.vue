<script setup lang="ts">
import { useWindowScroll } from '@vueuse/core'

const { y } = useWindowScroll()

function scrollTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
</script>

<template>
  <Transition name="fade">
    <button
      v-if="y > 300"
      class="fixed bottom-6 right-6 z-50 w-10 h-10 flex items-center justify-center bg-[var(--color-ink)] text-[var(--color-paper)] border-2 border-[var(--color-accent)] hover:bg-[var(--color-accent)] transition-all duration-200 cursor-pointer font-mono text-sm"
      @click="scrollTop"
      title="回到顶部"
    >↑</button>
  </Transition>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: all 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(8px); }
</style>
