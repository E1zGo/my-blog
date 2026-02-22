<script setup lang="ts">
import { ref, computed } from 'vue'
import { useHead } from '@vueuse/head'
import PostCard from '@/components/blog/PostCard.vue'
import { getAllPosts, getAllTags } from '@/utils/posts'
import blogConfig from '../../../blog.config'

useHead({ title: `文章 — ${blogConfig.title}` })

const allPosts = getAllPosts()
const tags = getAllTags()
const selectedTag = ref<string | null>(null)
const page = ref(1)
const perPage = blogConfig.postsPerPage

const filtered = computed(() =>
  selectedTag.value
    ? allPosts.filter(p => p.tags.includes(selectedTag.value!))
    : allPosts
)

const paginated = computed(() =>
  filtered.value.slice(0, page.value * perPage)
)

const hasMore = computed(() => paginated.value.length < filtered.value.length)

function selectTag(tag: string | null) {
  selectedTag.value = tag
  page.value = 1
}
</script>

<template>
  <div class="max-w-6xl mx-auto px-6 py-12">
    <!-- Header -->
    <div class="mb-10 pb-6 border-b-2 border-[var(--color-ink)]">
      <p class="font-mono text-xs tracking-widest uppercase text-[var(--color-accent)] mb-2">// Archive</p>
      <h1 class="font-serif text-4xl font-bold">所有文章</h1>
      <p class="text-[var(--color-muted)] mt-2 font-mono text-sm">共 {{ filtered.length }} 篇</p>
    </div>

    <div class="flex gap-12">
      <!-- Post list -->
      <main class="flex-1 min-w-0">
        <div class="border border-[rgba(26,22,18,0.15)]">
          <PostCard
            v-for="post in paginated"
            :key="post.slug"
            :post="post"
          />
        </div>

        <div v-if="!paginated.length" class="text-center py-16 text-[var(--color-muted)] font-mono text-sm">
          该标签下暂无文章
        </div>

        <!-- Load more -->
        <div v-if="hasMore" class="mt-8 text-center">
          <button
            class="font-mono text-xs tracking-widest uppercase px-8 py-3 border-2 border-[var(--color-ink)] hover:bg-[var(--color-ink)] hover:text-[var(--color-paper)] transition-all cursor-pointer"
            @click="page++"
          >
            加载更多 ({{ filtered.length - paginated.length }} 篇)
          </button>
        </div>
      </main>

      <!-- Sidebar -->
      <aside class="hidden lg:block w-64 shrink-0">
        <div class="sticky top-20">
          <h3 class="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)] mb-3 pb-2 border-b border-[rgba(26,22,18,0.15)]">
            标签筛选
          </h3>
          <div class="flex flex-wrap gap-2">
            <button
              class="font-mono text-xs px-3 py-1.5 border cursor-pointer transition-all"
              :class="selectedTag === null
                ? 'bg-[var(--color-ink)] text-[var(--color-paper)] border-[var(--color-ink)]'
                : 'border-[rgba(26,22,18,0.2)] text-[var(--color-muted)] hover:border-[var(--color-ink)]'"
              @click="selectTag(null)"
            >
              全部
            </button>
            <button
              v-for="tag in tags"
              :key="tag.name"
              class="font-mono text-xs px-3 py-1.5 border cursor-pointer transition-all"
              :class="selectedTag === tag.name
                ? 'bg-[var(--color-accent)] text-white border-[var(--color-accent)]'
                : 'border-[rgba(26,22,18,0.2)] text-[var(--color-muted)] hover:border-[var(--color-ink)]'"
              @click="selectTag(tag.name)"
            >
              {{ tag.name }} <span class="opacity-60">{{ tag.count }}</span>
            </button>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
