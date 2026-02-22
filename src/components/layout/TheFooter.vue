<script setup lang="ts">
import blogConfig from '../../../blog.config'
const year = new Date().getFullYear()
</script>

<template>
  <footer class="bg-[var(--color-ink)] border-t-[3px] border-[var(--color-accent)] mt-auto">
    <div class="max-w-6xl mx-auto px-6 py-12 grid grid-cols-1 md:grid-cols-3 gap-8">
      <!-- Brand -->
      <div>
        <div class="font-mono text-sm tracking-widest uppercase text-[var(--color-paper)] mb-3">
          {{ blogConfig.title }}<span class="text-[var(--color-accent)]">.dev</span>
        </div>
        <p class="text-sm text-[var(--color-muted)] leading-relaxed">{{ blogConfig.description }}</p>
      </div>

      <!-- Navigation -->
      <div>
        <h4 class="font-mono text-xs tracking-widest uppercase text-[var(--color-paper)] mb-4">导航</h4>
        <ul class="list-none space-y-2">
          <li v-for="item in blogConfig.nav" :key="item.path">
            <RouterLink
              :to="item.path"
              class="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent2)] transition-colors no-underline"
            >
              {{ item.label }}
            </RouterLink>
          </li>
        </ul>
      </div>

      <!-- Socials -->
      <div>
        <h4 class="font-mono text-xs tracking-widest uppercase text-[var(--color-paper)] mb-4">联系</h4>
        <ul class="list-none space-y-2">
          <li>
            <a :href="blogConfig.socials.github" target="_blank"
               class="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent2)] transition-colors no-underline">
              GitHub →
            </a>
          </li>
          <li>
            <a :href="blogConfig.socials.twitter" target="_blank"
               class="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent2)] transition-colors no-underline">
              Twitter →
            </a>
          </li>
          <li>
            <a :href="`mailto:${blogConfig.socials.email}`"
               class="font-mono text-xs text-[var(--color-muted)] hover:text-[var(--color-accent2)] transition-colors no-underline">
              Email →
            </a>
          </li>
        </ul>
      </div>
    </div>

    <!-- Bottom bar -->
    <div class="border-t border-[rgba(255,255,255,0.08)] px-6 py-4 max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-2">
      <span class="font-mono text-xs text-[var(--color-muted)]">
        © {{ year }} {{ blogConfig.author }} — Built with Vue 3 + Vite
      </span>
      <div class="flex gap-2">
        <span
          v-for="badge in ['Vue 3', 'Vite', 'TailwindCSS', 'TypeScript']"
          :key="badge"
          class="font-mono text-[10px] px-2 py-1 bg-[rgba(255,255,255,0.06)] border border-[rgba(255,255,255,0.1)] text-[var(--color-muted)]"
        >{{ badge }}</span>
      </div>
    </div>
  </footer>
</template>
