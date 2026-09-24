<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSearch } from '@/composables/useSearch'
import { useUiStore } from '@/stores/ui'
const router = useRouter()
const ui = useUiStore()
const { query, results } = useSearch()
const input = ref<HTMLInputElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const selected = ref(0)
let previousFocus: HTMLElement | null = null
let previousOverflow = ''
function go(path: string) { ui.closeSearch(); router.push(path) }
function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); ui.searchOpen ? ui.closeSearch() : ui.openSearch(); return }
  if (!ui.searchOpen) return
  if (e.key === 'Escape') { e.preventDefault(); ui.closeSearch() }
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && results.value.length) {
    e.preventDefault()
    selected.value = (selected.value + (e.key === 'ArrowDown' ? 1 : -1) + results.value.length) % results.value.length
    panel.value?.querySelector(`#search-result-${selected.value}`)?.scrollIntoView({ block: 'nearest' })
  }
  if (e.key === 'Enter' && document.activeElement === input.value && results.value[selected.value]) { e.preventDefault(); go(results.value[selected.value].path) }
  if (e.key === 'Tab') {
    const focusable = panel.value?.querySelectorAll<HTMLElement>('button, input, a[href]')
    const first = focusable?.[0], last = focusable?.[focusable.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
  }
}
watch(query, () => { selected.value = 0 })
watch(() => ui.searchOpen, async open => {
  if (open) {
    previousFocus = document.activeElement as HTMLElement | null
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    await nextTick()
    input.value?.focus()
  } else {
    query.value = ''
    document.body.style.overflow = previousOverflow
    previousFocus?.focus()
  }
})
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => { window.removeEventListener('keydown', onKeydown); if (ui.searchOpen) document.body.style.overflow = previousOverflow })
</script>
<template>
  <Teleport to="body"><Transition name="modal"><div v-if="ui.searchOpen" class="search-overlay" @click.self="ui.closeSearch"><section ref="panel" class="search-panel" role="dialog" aria-modal="true" aria-labelledby="search-title"><div class="search-heading"><h2 id="search-title">寻找一篇文章</h2><button aria-label="关闭搜索" @click="ui.closeSearch">ESC</button></div><input ref="input" v-model="query" class="search-input" placeholder="输入标题、关键词或标签…" aria-label="搜索文章" autocomplete="off" /><div v-if="results.length" class="search-results"><button v-for="(post, i) in results" :id="`search-result-${i}`" :key="post.slug" class="search-result" :class="{ active: selected === i }" @click="go(post.path)" @focus="selected = i"><strong>{{ post.title }}</strong><span>{{ post.date }} · {{ post.tags.join(' / ') }}</span></button></div><p v-else-if="query.trim()" class="search-empty" role="status">没有找到相关文章，换个关键词试试。</p><p class="search-hint">{{ results.length ? `${results.length} 篇相关记录 · ↑ ↓ 选择 · Enter 打开` : '搜索标题、摘要和标签 · Esc 关闭' }}</p></section></div></Transition></Teleport>
</template>
