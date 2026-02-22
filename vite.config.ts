import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import Pages from 'vite-plugin-pages'
import Markdown from 'unplugin-vue-markdown/vite'
import path from 'path'

export default defineConfig({
  plugins: [
    Markdown({
      markdownItSetup(md) {
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
      '@': path.resolve(__dirname, './src'),
    },
  },
})