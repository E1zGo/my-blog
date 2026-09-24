import { ref, onMounted, onUnmounted } from 'vue'

export interface TocItem { id: string; text: string; level: number }

export function useToc() {
  const items = ref<TocItem[]>([])
  const activeId = ref('')
  let headings: HTMLElement[] = []
  let observer: MutationObserver | undefined
  let frame = 0

  function updateActive() {
    let current = headings[0]?.id || ''
    for (const heading of headings) {
      if (heading.getBoundingClientRect().top <= 145) current = heading.id
    }
    activeId.value = current
  }
  function onScroll() {
    cancelAnimationFrame(frame)
    frame = requestAnimationFrame(updateActive)
  }
  function build() {
    headings = Array.from(document.querySelectorAll<HTMLElement>('[data-post-content] h2, [data-post-content] h3'))
    items.value = headings.map((el, index) => {
      // Fallback IDs stay unique even when headings contain only Chinese or punctuation.
      if (!el.id) el.id = `section-${index + 1}`
      return { id: el.id, text: el.textContent?.trim() || '', level: Number(el.tagName[1]) }
    })
    updateActive()
  }
  onMounted(() => {
    build()
    const article = document.querySelector('[data-post-content]')
    if (article) { observer = new MutationObserver(build); observer.observe(article, { childList: true, subtree: true }) }
    window.addEventListener('scroll', onScroll, { passive: true })
  })
  onUnmounted(() => { observer?.disconnect(); cancelAnimationFrame(frame); window.removeEventListener('scroll', onScroll) })
  return { items, activeId }
}
