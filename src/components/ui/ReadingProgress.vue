<script setup lang="ts">
import { useReadingProgress } from '@/composables/useReadingProgress'
const { progress } = useReadingProgress()
</script>
<template><div class="reading-progress" aria-hidden="true"><div :style="{ transform: `scaleX(${progress / 100})` }" /></div></template>
