import { ref, onMounted, onUnmounted, nextTick } from 'vue'

export interface TocItem {
  id: string
  text: string
  level: number
}

export function useToc() {
  const items = ref<TocItem[]>([])
  const activeId = ref('')

  function buildToc() {
    const article = document.querySelector('article')
    if (!article) return
    const headings = article.querySelectorAll('h2, h3')
    items.value = Array.from(headings).map(el => {
      // 确保每个标题有 id
      if (!el.id) {
        el.id = el.textContent!.trim().toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, '')
      }
      return {
        id: el.id,
        text: el.textContent!.trim(),
        level: Number(el.tagName[1]),
      }
    })
  }

  function onScroll() {
    const headings = document.querySelectorAll('article h2, article h3')
    let current = ''
    headings.forEach(el => {
      if (el.getBoundingClientRect().top < 120) current = el.id
    })
    activeId.value = current
  }

  onMounted(async () => {
    await nextTick()
    buildToc()
    window.addEventListener('scroll', onScroll, { passive: true })
  })

  onUnmounted(() => window.removeEventListener('scroll', onScroll))

  function scrollTo(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return { items, activeId, scrollTo }
}
