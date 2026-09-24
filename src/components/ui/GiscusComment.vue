<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useDarkMode } from '@/composables/useDarkMode'
const { isDark } = useDarkMode()
const container = ref<HTMLElement | null>(null)
const loaded = ref(false)
const error = ref(false)
async function loadComments() {
  loaded.value = true
  error.value = false
  await nextTick()
  container.value?.replaceChildren()
  const script = document.createElement('script')
  script.src = 'https://giscus.app/client.js'
  const config = { repo: 'E1zGo/my-blog', 'repo-id': 'R_kgDORVXFOg', category: 'Announcements', 'category-id': 'DIC_kwDORVXFOs4C2-At', mapping: 'pathname', 'reactions-enabled': '1', 'emit-metadata': '0', 'input-position': 'top', theme: isDark.value ? 'dark' : 'light', lang: 'zh-CN' }
  for (const [key, value] of Object.entries(config)) script.setAttribute(`data-${key}`, value)
  script.crossOrigin = 'anonymous'
  script.async = true
  script.onerror = () => { error.value = true }
  container.value?.appendChild(script)
}
watch(isDark, value => {
  container.value?.querySelector<HTMLIFrameElement>('iframe.giscus-frame')?.contentWindow?.postMessage({ giscus: { setConfig: { theme: value ? 'dark' : 'light' } } }, 'https://giscus.app')
})
</script>
<template><section class="comment-section"><h2>聊聊你的想法</h2><p>欢迎补充、提问，或分享你的经验。</p><button v-if="!loaded || error" class="button-secondary" @click="loadComments">{{ error ? '加载失败，重试' : '展开评论' }} ↓</button><div v-if="loaded" ref="container" /></section></template>
