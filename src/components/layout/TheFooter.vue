<script setup lang="ts">
import blogConfig from '../../../blog.config'
const year = new Date().getFullYear()
</script>
<template>
  <footer class="site-footer">
    <div class="page-width footer-content"><div><RouterLink to="/" class="brand">{{ blogConfig.title }}<span class="brand-dot">.</span></RouterLink><p>{{ blogConfig.description }}，慢慢记录。</p></div><div class="footer-links"><a v-if="blogConfig.socials.github" :href="blogConfig.socials.github" target="_blank" rel="noopener noreferrer">GitHub ↗</a><a v-if="blogConfig.socials.twitter" :href="blogConfig.socials.twitter" target="_blank" rel="noopener noreferrer">Twitter ↗</a><a v-if="blogConfig.socials.email" :href="`mailto:${blogConfig.socials.email}`">联系我 ↗</a></div></div>
    <div class="page-width footer-bottom"><span>© {{ year }} {{ blogConfig.author }}</span><span>用代码探索，用文字记录。</span><a href="#main-content">回到顶部 ↑</a></div>
  </footer>
</template>
