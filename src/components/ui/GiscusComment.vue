<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useDarkMode } from '@/composables/useDarkMode'

// 请到 https://giscus.app 填写你的仓库信息后替换以下配置
const config = {
  repo: 'your-github/your-repo',         // ← 改成你的 GitHub 仓库
  repoId: 'YOUR_REPO_ID',                // ← 从 giscus.app 获取
  category: 'Announcements',
  categoryId: 'YOUR_CATEGORY_ID',        // ← 从 giscus.app 获取
  mapping: 'pathname',
  reactionsEnabled: '1',
  emitMetadata: '0',
  inputPosition: 'top',
  lang: 'zh-CN',
}

const { isDark } = useDarkMode()
const container = ref<HTMLElement | null>(null)

onMounted(() => {
  const script = document.createElement('script')
  script.src = 'https://giscus.app/client.js'
  script.setAttribute('data-repo', config.repo)
  script.setAttribute('data-repo-id', config.repoId)
  script.setAttribute('data-category', config.category)
  script.setAttribute('data-category-id', config.categoryId)
  script.setAttribute('data-mapping', config.mapping)
  script.setAttribute('data-reactions-enabled', config.reactionsEnabled)
  script.setAttribute('data-emit-metadata', config.emitMetadata)
  script.setAttribute('data-input-position', config.inputPosition)
  script.setAttribute('data-theme', isDark.value ? 'dark' : 'light')
  script.setAttribute('data-lang', config.lang)
  script.setAttribute('crossorigin', 'anonymous')
  script.async = true
  container.value?.appendChild(script)
})
</script>

<template>
  <div class="mt-12 pt-8 border-t border-[rgba(26,22,18,0.15)]">
    <div class="font-mono text-[10px] tracking-widest uppercase text-[var(--color-muted)] mb-6">
      // 评论
    </div>
    <!-- 未配置时显示引导提示 -->
    <div
      v-if="config.repoId === 'YOUR_REPO_ID'"
      class="bg-[var(--color-warm)] border border-[rgba(26,22,18,0.15)] p-6 font-mono text-xs text-[var(--color-muted)]"
    >
      <p class="mb-2">💬 评论功能未配置，请：</p>
      <ol class="list-decimal list-inside space-y-1">
        <li>前往 <a href="https://giscus.app" target="_blank" class="text-[var(--color-accent)] underline">giscus.app</a> 生成配置</li>
        <li>将 repo、repoId、categoryId 填入 <code>GiscusComment.vue</code></li>
      </ol>
    </div>
    <div v-else ref="container" />
  </div>
</template>
