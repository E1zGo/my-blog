<script setup lang="ts">
import { computed } from 'vue'
import katex from 'katex'
import 'katex/dist/katex.min.css'
const props = defineProps<{ text: string; equation?: boolean }>()
const escaped = (text: string) => text.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!))
function math(text: string, display: boolean) {
  try { return katex.renderToString(text.slice(0, 12000), { displayMode: display, throwOnError: true, trust: false, strict: 'ignore', maxExpand: 1000, maxSize: 15, output: 'htmlAndMathml' }) }
  catch { return `<code class="rp-math-fallback">${escaped(text)}</code>` }
}
const html = computed(() => {
  if (props.equation) return math(props.text, true)
  const pattern = /\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$|\\\(([\s\S]*?)\\\)|\$([^$\n]+)\$/g
  let result = ''; let end = 0
  for (const match of props.text.matchAll(pattern)) {
    result += escaped(props.text.slice(end, match.index)) + math(match[1] ?? match[2] ?? match[3] ?? match[4], match[1] !== undefined || match[2] !== undefined)
    end = match.index! + match[0].length
  }
  return result + escaped(props.text.slice(end))
})
</script>
<template><div class="rp-rich-text" v-html="html"></div></template>
