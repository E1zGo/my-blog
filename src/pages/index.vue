<script setup lang="ts">
import { useHead } from '@vueuse/head'
import PostCard from '@/components/blog/PostCard.vue'
import TagCloud from '@/components/blog/TagCloud.vue'
import blogConfig from '../../blog.config'
import { getAllPosts, getAllTags } from '@/utils/posts'
useHead({ title: `${blogConfig.title} — ${blogConfig.subtitle}` })
const posts = getAllPosts()
const tags = getAllTags()
const latestPosts = posts.slice(0, blogConfig.postsPerPage)
</script>
<template>
  <div class="page-width">
    <section class="home-hero">
      <div class="hero-copy"><p class="eyebrow"><span class="status-dot" /> A PERSONAL JOURNAL</p><h1>在代码里探索，<br />在生活里<span class="serif-emphasis">拾光。</span></h1><p class="hero-description">你好，我是 {{ blogConfig.author }}。<br />这里记录技术、思考，以及日常生活里的小小发现。</p><div class="hero-actions"><RouterLink to="/posts" class="button-primary">读一篇文章 <span>↗</span></RouterLink><RouterLink to="/about" class="text-link">认识一下我 <span>→</span></RouterLink></div><div class="hero-footnote"><span>{{ blogConfig.subtitle }}</span><span class="small-line" /><span>{{ blogConfig.description }}</span></div></div>
      <div class="landscape-card" role="img" aria-label="暖色太阳照耀着层叠的青绿色山峦，山前山后各有风景">
        <div class="landscape-caption"><span>FIELD NOTES</span><span>01 / ∞</span></div>
        <svg class="landscape" viewBox="0 0 480 430" fill="none" aria-hidden="true"><defs><linearGradient id="sky" x1="240" y1="0" x2="240" y2="430" gradientUnits="userSpaceOnUse"><stop stop-color="#ecebda"/><stop offset="1" stop-color="#d8dfce"/></linearGradient><pattern id="contours" width="480" height="430" patternUnits="userSpaceOnUse"><path d="M-100 130Q150-20 530 120M-100 145Q150-5 530 135M-100 160Q150 10 530 150M-100 175Q150 25 530 165" stroke="#53694e" stroke-opacity=".1"/></pattern></defs><path fill="url(#sky)" d="M0 0h480v430H0z"/><circle cx="330" cy="113" r="42" fill="#cf895a"/><path fill="url(#contours)" d="M0 0h480v430H0z"/><path d="M0 249 111 121 242 276 342 192 480 281V430H0Z" fill="#a7b69b"/><path d="m0 284 164-95 170 138 146-73v176H0Z" fill="#708d77"/><path d="M0 350Q112 210 269 306T480 319v111H0Z" fill="#436c5d"/><path d="M0 395Q127 286 281 370t199-7v67H0Z" fill="#244e42"/><path d="M232 430q-67-27-21-55t-6-40q-32-15-20-28" stroke="#d6d5b8" stroke-width="2" stroke-linecap="round"/><path d="m55 82 5-3 5 3m8-10 5-3 5 3" stroke="#687b68" stroke-width="1.5" stroke-linecap="round"/></svg>
        <div class="landscape-note"><span>山前山后<br /><strong>各有风景</strong></span><span class="landscape-seal">山<br />野</span></div><div class="landscape-bottom"><span>KEEP EXPLORING, KEEP WRITING.</span><span>↗</span></div>
      </div>
    </section>
    <div class="home-content"><section class="latest-section"><div class="section-heading"><div><p class="eyebrow">THE LATEST</p><h2>最近在写<span class="count-label">{{ posts.length }} 篇文章</span></h2></div><RouterLink to="/posts" class="text-link">全部文章 ↗</RouterLink></div><div class="post-list"><PostCard v-for="(post, i) in latestPosts" :key="post.slug" :post="post" :index="i" /></div><p v-if="!latestPosts.length" class="empty-state">文字还在酝酿中，过些时候再来看看。</p></section>
      <aside class="home-sidebar"><section class="author-card"><div class="author-card-top"><img :src="blogConfig.avatar" :alt="blogConfig.author" width="48" height="48" /><div><h2>{{ blogConfig.author }}</h2><span>开发者 · 生活记录者</span></div><span class="tiny-star" aria-hidden="true">✳</span></div><p>保持好奇，持续学习。<br />把踩过的坑、想通的事，<br />和沿途的风景留在这里。</p><RouterLink to="/about" class="text-link">更多关于我 <span>↗</span></RouterLink></section><section class="sidebar-topics"><div class="sidebar-title"><h2>按主题探索</h2><span>{{ tags.length }} TOPICS</span></div><TagCloud /></section><div class="sidebar-note"><span aria-hidden="true">“</span><p>写下来，<br />让思考有迹可循。</p><small>NOTES TO SELF</small></div></aside>
    </div>
  </div>
</template>
