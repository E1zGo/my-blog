<script setup lang="ts">
import { useHead } from '@vueuse/head'
import { getAllTags } from '@/utils/posts'
import blogConfig from '../../../blog.config'
useHead({ title: `标签 — ${blogConfig.title}` })
const tags = getAllTags()
</script>
<template><div class="page-width archive-page"><header class="page-heading"><p class="eyebrow">EXPLORE BY TOPIC</p><h1>从兴趣出发<span class="heading-dot">.</span></h1><p>给散落的思考分个类，找到你感兴趣的话题。</p></header><div class="tags-grid"><RouterLink v-for="(tag, i) in tags" :key="tag.name" :to="`/tags/${encodeURIComponent(tag.name)}`" class="topic-card"><small>TOPIC {{ String(i + 1).padStart(2, '0') }}</small><h2>{{ tag.name }}</h2><div><span>{{ tag.count }} 篇文章</span><span>↗</span></div></RouterLink></div><p v-if="!tags.length" class="empty-state">更多主题，慢慢收集。</p></div></template>
