<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDarkMode } from '@/composables/useDarkMode'
import { useUiStore } from '@/stores/ui'
import blogConfig from '../../../blog.config'

const router = useRouter()
const { isDark, toggle: toggleDark } = useDarkMode()
const ui = useUiStore()
const mobileOpen = ref(false)

function goHome() { router.push('/') }
</script>

<template>
  <header class="sticky top-0 z-50 bg-[var(--color-ink)] border-b-[3px] border-[var(--color-accent)]">
    <nav class="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
      <!-- Logo -->
      <button
        class="font-mono text-sm tracking-widest uppercase text-[var(--color-paper)] cursor-pointer"
        @click="goHome"
      >
        {{ blogConfig.title }}<span class="text-[var(--color-accent)]">.dev</span>
      </button>

      <!-- Desktop Nav -->
      <ul class="hidden md:flex gap-8 list-none">
        <li v-for="item in blogConfig.nav" :key="item.path">
          <RouterLink
            :to="item.path"
            class="font-mono text-xs tracking-widest uppercase text-[var(--color-warm)] hover:text-[var(--color-accent2)] transition-colors no-underline"
            :class="{ 'text-[var(--color-accent2)]!': $route.path === item.path }"
          >
            {{ item.label }}
          </RouterLink>
        </li>
      </ul>

      <!-- Actions -->
      <div class="flex items-center gap-3">
        <!-- Search -->
        <button
          class="font-mono text-xs tracking-widest uppercase text-[var(--color-muted)] hover:text-[var(--color-paper)] transition-colors px-2 py-1 border border-[rgba(255,255,255,0.1)] hover:border-[rgba(255,255,255,0.3)] cursor-pointer"
          @click="ui.openSearch"
          title="搜索 (Ctrl+K)"
        >
          ⌕ 搜索
        </button>

        <!-- Dark Mode -->
        <button
          class="w-8 h-8 flex items-center justify-center text-[var(--color-muted)] hover:text-[var(--color-paper)] transition-colors cursor-pointer"
          @click="toggleDark"
          :title="isDark ? '切换亮色' : '切换暗色'"
        >
          <span class="text-base">{{ isDark ? '☀' : '☾' }}</span>
        </button>

        <!-- Mobile Menu -->
        <button
          class="md:hidden w-8 h-8 flex items-center justify-center text-[var(--color-paper)] cursor-pointer"
          @click="mobileOpen = !mobileOpen"
        >
          <span class="text-xl">{{ mobileOpen ? '✕' : '≡' }}</span>
        </button>
      </div>
    </nav>

    <!-- Mobile Menu -->
    <Transition name="slide">
      <div v-if="mobileOpen" class="md:hidden bg-[var(--color-ink)] border-t border-[rgba(255,255,255,0.1)]">
        <ul class="list-none px-6 py-4 flex flex-col gap-4">
          <li v-for="item in blogConfig.nav" :key="item.path">
            <RouterLink
              :to="item.path"
              class="font-mono text-sm tracking-widest uppercase text-[var(--color-warm)] hover:text-[var(--color-accent2)] transition-colors no-underline block"
              @click="mobileOpen = false"
            >
              {{ item.label }}
            </RouterLink>
          </li>
        </ul>
      </div>
    </Transition>
  </header>
</template>

<style scoped>
.slide-enter-active, .slide-leave-active { transition: all 0.25s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(-10px); }
</style>
