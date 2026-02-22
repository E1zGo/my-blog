<script setup lang="ts">
import { watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSearch } from '@/composables/useSearch'
import { useUiStore } from '@/stores/ui'

const router = useRouter()
const ui = useUiStore()
const { query, results } = useSearch()

function go(path: string) {
  router.push(path)
  ui.closeSearch()
  query.value = ''
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    ui.openSearch()
  }
  if (e.key === 'Escape') ui.closeSearch()
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

watch(() => ui.searchOpen, (v) => {
  if (!v) query.value = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="ui.searchOpen"
        class="fixed inset-0 z-[200] flex items-start justify-center pt-24 px-4"
        @click.self="ui.closeSearch"
      >
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="ui.closeSearch" />

        <!-- Panel -->
        <div class="relative w-full max-w-xl bg-[var(--color-paper)] border-2 border-[var(--color-ink)] shadow-2xl">
          <!-- Search Input -->
          <div class="flex items-center border-b-2 border-[var(--color-ink)] px-4">
            <span class="text-[var(--color-muted)] mr-3 text-lg">⌕</span>
            <input
              v-model="query"
              autofocus
              placeholder="搜索文章、标签..."
              class="flex-1 py-4 bg-transparent font-mono text-sm outline-none text-[var(--color-ink)] placeholder:text-[var(--color-muted)]"
            />
            <button
              class="font-mono text-xs text-[var(--color-muted)] border border-[var(--color-muted)] px-2 py-0.5 cursor-pointer hover:text-[var(--color-ink)]"
              @click="ui.closeSearch"
            >ESC</button>
          </div>

          <!-- Results -->
          <div v-if="results.length" class="max-h-80 overflow-y-auto">
            <button
              v-for="post in results"
              :key="post.slug"
              class="w-full text-left px-5 py-4 border-b border-[rgba(26,22,18,0.1)] hover:bg-[var(--color-warm)] transition-colors cursor-pointer"
              @click="go(post.path)"
            >
              <div class="font-serif text-sm font-semibold text-[var(--color-ink)] mb-1">{{ post.title }}</div>
              <div class="font-mono text-[10px] text-[var(--color-muted)]">
                {{ post.date }} · {{ post.tags.join(', ') }}
              </div>
            </button>
          </div>

          <!-- Empty -->
          <div v-else-if="query" class="px-5 py-8 text-center font-mono text-sm text-[var(--color-muted)]">
            没有找到相关文章
          </div>

          <!-- Hint -->
          <div v-else class="px-5 py-4 font-mono text-xs text-[var(--color-muted)]">
            输入关键词搜索文章 · <kbd>Ctrl+K</kbd> 快速打开
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-enter-active, .modal-leave-active { transition: all 0.2s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>
