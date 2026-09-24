<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useHead } from '@vueuse/head'
import PostCard from '@/components/blog/PostCard.vue'
import { getAllPosts } from '@/utils/posts'
import blogConfig from '../../../blog.config'
const tag = useRoute().params.tag as string
const posts = getAllPosts().filter(p => p.tags.includes(tag))
useHead({ title: `${tag} — ${blogConfig.title}` })
</script>
<template><div class="page-width archive-page"><RouterLink to="/tags" class="text-link article-back">← 所有主题</RouterLink><header class="page-heading"><p class="eyebrow">FILED UNDER</p><h1>{{ tag }}<span class="heading-dot">.</span></h1><p>关于这个主题的 {{ posts.length }} 篇记录。</p></header><div class="post-list"><PostCard v-for="(post, i) in posts" :key="post.slug" :post="post" :index="i" /></div><p v-if="!posts.length" class="empty-state">这个主题还没有文章，去其他主题看看吧。</p></div></template>
