<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useHead } from '@vueuse/head'
import PostCard from '@/components/blog/PostCard.vue'
import { getAllPosts, getAllTags } from '@/utils/posts'
import blogConfig from '../../../blog.config'
useHead({ title: `文章 — ${blogConfig.title}` })
const allPosts = getAllPosts()
const tags = getAllTags()
const selectedTag = ref<string | null>(null)
const page = ref(1)
const filtered = computed(() => selectedTag.value ? allPosts.filter(p => p.tags.includes(selectedTag.value!)) : allPosts)
const paginated = computed(() => filtered.value.slice(0, page.value * blogConfig.postsPerPage))
watch(selectedTag, () => { page.value = 1 })
</script>
<template>
  <div class="page-width archive-page"><header class="page-heading"><p class="eyebrow">THE ARCHIVE</p><h1>文字的足迹<span class="heading-dot">.</span></h1><p>关于技术的探索，也关于生活的思考。共 {{ allPosts.length }} 篇记录。</p></header><div class="filter-bar" aria-label="按标签筛选"><button :class="{ selected: selectedTag === null }" :aria-pressed="selectedTag === null" @click="selectedTag = null">全部 <span>{{ allPosts.length }}</span></button><button v-for="tag in tags" :key="tag.name" :class="{ selected: selectedTag === tag.name }" :aria-pressed="selectedTag === tag.name" @click="selectedTag = tag.name">{{ tag.name }} <span>{{ tag.count }}</span></button></div><div class="archive-count" role="status">{{ selectedTag || '全部文章' }}<span>{{ filtered.length }} 篇</span></div><div class="post-list"><PostCard v-for="(post, i) in paginated" :key="post.slug" :post="post" :index="i" /></div><p v-if="!paginated.length" class="empty-state">这里还没有文章，试试其他主题吧。</p><div v-if="paginated.length < filtered.length" class="load-more"><button class="button-secondary" @click="page++">加载更多文章 ↓</button></div><p v-else-if="paginated.length" class="list-end">— 暂时写到这里，下次见 —</p></div>
</template>
