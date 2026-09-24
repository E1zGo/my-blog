<script setup lang="ts">
import TheNav from '@/components/layout/TheNav.vue'
import TheFooter from '@/components/layout/TheFooter.vue'
import SearchModal from '@/components/ui/SearchModal.vue'
import BackToTop from '@/components/ui/BackToTop.vue'
import blogConfig from '../blog.config'
import { useHead } from '@vueuse/head'
useHead({ meta: [{ name: 'description', content: blogConfig.description }] })
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <a href="#main-content" class="skip-link">跳到正文</a>
    <TheNav />
    <main id="main-content" class="flex-1" tabindex="-1">
      <RouterView :key="$route.path" />
    </main>
    <TheFooter />
    <SearchModal v-if="blogConfig.features.search" />
    <BackToTop />
  </div>
</template>
