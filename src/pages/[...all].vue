<script setup lang="ts">
import { useHead } from '@vueuse/head'
import blogConfig from '../../blog.config'
useHead({ title: `404 — ${blogConfig.title}`, meta: [{ name: 'robots', content: 'noindex' }] })
</script>
<template>
  <div class="page-width not-found">
    <p class="eyebrow">404 / A LITTLE OFF THE PATH</p>
    <h1>这条小路，暂时走不通。</h1>
    <p>页面可能已搬家，也可能还没写好。回去看看其他风景吧。</p>
    <RouterLink to="/" class="button-primary">回到首页 <span>↗</span></RouterLink>
  </div>
</template>
