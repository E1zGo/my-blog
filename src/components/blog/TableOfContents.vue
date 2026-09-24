<script setup lang="ts">
import { useToc } from '@/composables/useToc'
const { items, activeId } = useToc()
</script>
<template>
  <nav v-if="items.length" class="toc" aria-label="文章目录"><div class="toc-label">本文目录<span>ON THIS PAGE</span></div><ul><li v-for="item in items" :key="item.id" :class="{ nested: item.level === 3 }"><a :href="`#${encodeURIComponent(item.id)}`" :class="{ active: activeId === item.id }" :aria-current="activeId === item.id ? 'location' : undefined">{{ item.text }}</a></li></ul></nav>
</template>
