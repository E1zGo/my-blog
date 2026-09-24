import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import Pages from 'vite-plugin-pages'
import Markdown from 'unplugin-vue-markdown/vite'
import path from 'path'
import { createRequire } from 'node:module'
import { readFile } from 'node:fs/promises'
import { extractPostMetadata } from './build/post-metadata'
const require = createRequire(import.meta.url)
const Prism = require('prismjs')
require('prismjs/components/prism-typescript')
require('prismjs/components/prism-bash')
require('prismjs/components/prism-json')
require('prismjs/components/prism-css')

export default defineConfig({
  plugins: [
    {
      name: 'blog-post-metadata',
      enforce: 'pre',
      async resolveId(source, importer) {
        if (!source.endsWith('.md?post-meta')) return
        const resolved = await this.resolve(source.slice(0, -'?post-meta'.length), importer, { skipSelf: true })
        return resolved ? `${resolved.id}.post-meta.js` : undefined
      },
      async load(id) {
        if (!id.endsWith('.md.post-meta.js')) return
        const filename = id.slice(0, -'.post-meta.js'.length)
        this.addWatchFile(filename)
        const metadata = extractPostMetadata(await readFile(filename, 'utf8'))
        return `export default ${JSON.stringify(metadata)}`
      },
    },
    Markdown({
      markdownItOptions: {
        highlight(code, language) {
          const aliases: Record<string, string> = { vue: 'markup', html: 'markup', ts: 'typescript', js: 'javascript', sh: 'bash', shell: 'bash' }
          const lang = aliases[language] || language
          return Prism.languages[lang] ? Prism.highlight(code, Prism.languages[lang], lang) : ''
        },
      },
      markdownItSetup(md) {
        md.core.ruler.push('article-headings', state => {
          const used = new Set<string>()
          for (let i = 0; i < state.tokens.length; i++) {
            const token = state.tokens[i]
            if (token.type !== 'heading_open') continue
            const text = state.tokens[i + 1]?.content || ''
            // The article template already presents the title once.
            if (i === 0 && token.tag === 'h1' && text === state.env.frontmatter?.title) {
              token.hidden = true
              state.tokens[i + 1].content = ''
              state.tokens[i + 1].children = []
              state.tokens[i + 2].hidden = true
              continue
            }
            const base = text.toLowerCase().trim().replace(/[^\p{L}\p{N}\s-]/gu, '').replace(/\s+/g, '-') || 'section'
            let id = base
            let suffix = 1
            while (used.has(id)) id = `${base}-${suffix++}`
            used.add(id)
            token.attrSet('id', id)
          }
        })
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
