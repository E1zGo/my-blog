import { ref, computed } from 'vue'
import Fuse from 'fuse.js'
import { getAllPosts } from '@/utils/posts'
import type { Post } from '@/types/blog'

const posts = getAllPosts()

const fuse = new Fuse(posts, {
  keys: ['title', 'excerpt', 'tags'],
  threshold: 0.3,
  includeScore: true,
})

export function useSearch() {
  const query = ref('')
  const isOpen = ref(false)

  const results = computed<Post[]>(() => {
    if (!query.value.trim()) return []
    return fuse.search(query.value).map(r => r.item).slice(0, 8)
  })

  function open() { isOpen.value = true }
  function close() { isOpen.value = false; query.value = '' }
  function toggle() { isOpen.value ? close() : open() }

  return { query, isOpen, results, open, close, toggle }
}
