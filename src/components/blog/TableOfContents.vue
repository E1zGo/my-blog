<script setup lang="ts">
import { useToc } from '@/composables/useToc'
const { items, activeId, scrollTo } = useToc()
</script>

<template>
  <nav v-if="items.length" class="sticky top-24">
    <div class="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)] mb-3 pb-2 border-b border-[rgba(26,22,18,0.15)]">
      // 目录
    </div>
    <ul class="list-none space-y-1">
      <li
        v-for="item in items"
        :key="item.id"
        :class="item.level === 3 ? 'pl-4' : ''"
      >
        <button
          class="text-left w-full font-mono text-xs leading-relaxed transition-colors cursor-pointer hover:text-[var(--color-accent)]"
          :class="activeId === item.id
            ? 'text-[var(--color-accent)] font-semibold'
            : 'text-[var(--color-muted)]'"
          @click="scrollTo(item.id)"
        >
          <span v-if="item.level === 3" class="mr-1 opacity-40">└</span>
          {{ item.text }}
        </button>
      </li>
    </ul>
  </nav>
</template>
