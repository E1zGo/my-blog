import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import Pages from 'vite-plugin-pages'
import Markdown from 'unplugin-vue-markdown/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [
    Markdown({
      markdownItSetup(md) {
        // 自定义 fence 渲染，把 vue/ts/sh 等别名统一映射为 prism 支持的语言
        // 不使用 markdown-it-prism，避免 ESM 环境下 require() 报错
        const defaultFence = md.renderer.rules.fence!.bind(md.renderer.rules)
        md.renderer.rules.fence = (tokens, idx, options, env, self) => {
          const token = tokens[idx]
          const lang = token.info.trim().split(/\s+/)[0] || 'text'
          const alias: Record<string, string> = {
            vue: 'html',
            ts: 'typescript',
            js: 'javascript',
            sh: 'bash',
            shell: 'bash',
          }
          token.info = alias[lang] ?? lang
          return defaultFence(tokens, idx, options, env, self)
        }
      },
    }),
    vue({
      include: [/\.vue$/, /\.md$/],
    }),
    Pages({
      extensions: ['vue', 'md'],
      dirs: 'src/pages',
    }),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})