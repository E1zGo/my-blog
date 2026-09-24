<script setup lang="ts">
import { useWindowScroll } from '@vueuse/core'
const { y } = useWindowScroll()
function scrollTop() { window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }) }
</script>
<template><button v-if="y > 500" class="back-to-top" aria-label="回到顶部" title="回到顶部" @click="scrollTop">↑</button></template>
