<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDarkMode } from '@/composables/useDarkMode'
import { useUiStore } from '@/stores/ui'
import blogConfig from '../../../blog.config'
const route = useRoute()
const { isDark, toggle } = useDarkMode()
const ui = useUiStore()
const mobileOpen = ref(false)
watch(() => route.path, () => { mobileOpen.value = false })
const active = (path: string) => path === '/' ? route.path === '/' : route.path.startsWith(path)
</script>
<template>
  <header class="site-header" @keydown.esc="mobileOpen = false">
    <nav class="site-nav page-width" aria-label="主导航">
      <RouterLink to="/" class="brand" aria-label="返回首页">{{ blogConfig.title }}<span class="brand-dot">.</span><span class="brand-caption">独立博客</span></RouterLink>
      <div class="desktop-nav"><RouterLink v-for="item in blogConfig.nav" :key="item.path" :to="item.path" :class="{ active: active(item.path) }" :aria-current="active(item.path) ? 'page' : undefined">{{ item.label }}</RouterLink></div>
      <div class="nav-actions">
        <button v-if="blogConfig.features.search" class="search-trigger" aria-label="搜索文章" @click="ui.openSearch"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></svg><span>搜索</span><kbd>Ctrl K</kbd></button>
        <button v-if="blogConfig.features.darkMode" class="icon-button" :aria-label="isDark ? '切换浅色模式' : '切换深色模式'" :title="isDark ? '切换浅色模式' : '切换深色模式'" @click="toggle">
          <svg v-if="isDark" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>
          <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 14A8.5 8.5 0 0 1 10 3.5 8.5 8.5 0 1 0 20.5 14Z"/></svg>
        </button>
        <button class="icon-button mobile-toggle" :aria-expanded="mobileOpen" aria-controls="mobile-nav" :aria-label="mobileOpen ? '关闭导航' : '展开导航'" @click="mobileOpen = !mobileOpen"><svg viewBox="0 0 24 24" aria-hidden="true"><path :d="mobileOpen ? 'm6 6 12 12M6 18 18 6' : 'M4 7h16M4 12h16M4 17h16'"/></svg></button>
      </div>
    </nav>
    <nav v-if="mobileOpen" id="mobile-nav" class="mobile-nav page-width" aria-label="移动端导航"><RouterLink v-for="item in blogConfig.nav" :key="item.path" :to="item.path" :class="{ active: active(item.path) }">{{ item.label }}<span>↗</span></RouterLink></nav>
  </header>
</template>
