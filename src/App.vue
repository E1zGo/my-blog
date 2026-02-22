<script setup lang="ts">
import TheNav from '@/components/layout/TheNav.vue'
import TheFooter from '@/components/layout/TheFooter.vue'
import SearchModal from '@/components/ui/SearchModal.vue'
import BackToTop from '@/components/ui/BackToTop.vue'
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <TheNav />
    <main class="flex-1">
      <RouterView :key="$route.fullPath" />
    </main>
    <TheFooter />
    <SearchModal />
    <BackToTop />
  </div>
</template>