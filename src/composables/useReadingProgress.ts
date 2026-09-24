import { ref, onMounted, onUnmounted } from 'vue'
export function useReadingProgress() {
  const progress = ref(0)
  let observer: ResizeObserver | undefined
  let frame = 0
  function update() {
    const article = document.querySelector('[data-post-content]')
    if (!article) return
    const rect = article.getBoundingClientRect()
    const start = rect.top + window.scrollY - 110
    const end = rect.bottom + window.scrollY - window.innerHeight
    progress.value = end <= start ? (rect.bottom <= window.innerHeight ? 100 : 0) : Math.max(0, Math.min(100, ((window.scrollY - start) / (end - start)) * 100))
  }
  function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(update) }
  onMounted(() => {
    const article = document.querySelector('[data-post-content]')
    if (article) { observer = new ResizeObserver(schedule); observer.observe(article) }
    update()
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
  })
  onUnmounted(() => { observer?.disconnect(); cancelAnimationFrame(frame); window.removeEventListener('scroll', schedule); window.removeEventListener('resize', schedule) })
  return { progress }
}
