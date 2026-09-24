<script setup lang="ts">
import { getAllTags } from '@/utils/posts'
const tags = getAllTags()
</script>
<template><div class="tag-cloud"><RouterLink v-for="tag in tags" :key="tag.name" :to="`/tags/${encodeURIComponent(tag.name)}`">{{ tag.name }}<span>{{ tag.count }}</span></RouterLink></div></template>
