import type { Post } from '@/types/blog'

const modules = import.meta.glob<Record<string, unknown>>('/content/posts/*.md', {
  query: '?post-meta', import: 'default', eager: true,
})
let cache: Post[] | null = null

function dateString(value: unknown, fallback: string): string {
  if (value instanceof Date) return value.toISOString().slice(0, 10)
  return typeof value === 'string' && !Number.isNaN(Date.parse(value)) ? value.slice(0, 10) : fallback
}
export function getAllPosts(): Post[] {
  if (cache) return cache
  cache = Object.entries(modules).map(([path, fm]) => {
    const slug = path.split('/').pop()!.replace(/\.md$/, '')
    const count = typeof fm.wordCount === 'number' ? fm.wordCount : 0
    return {
      slug,
      title: typeof fm.title === 'string' ? fm.title : slug,
      date: dateString(fm.date, slug.match(/^\d{4}-\d{2}-\d{2}/)?.[0] || '1970-01-01'),
      tags: Array.isArray(fm.tags) ? [...new Set(fm.tags.filter((t): t is string => typeof t === 'string'))] : [],
      excerpt: typeof fm.excerpt === 'string' ? fm.excerpt : '',
      cover: typeof fm.cover === 'string' ? fm.cover : undefined,
      updated: fm.updated ? dateString(fm.updated, '') : undefined,
      draft: fm.draft === true,
      path: `/posts/${encodeURIComponent(slug)}`,
      wordCount: count,
      readTime: Math.max(1, Math.ceil(count / 300)),
    }
  }).filter(p => !p.draft).sort((a, b) => b.date.localeCompare(a.date) || a.slug.localeCompare(b.slug))
  return cache
}
export function getPostBySlug(slug: string): Post | undefined { return getAllPosts().find(p => p.slug === slug) }
export function getPrevNextPost(slug: string): { prev: Post | null; next: Post | null } {
  const posts = getAllPosts()
  const index = posts.findIndex(p => p.slug === slug)
  if (index < 0) return { prev: null, next: null }
  return { prev: posts[index + 1] ?? null, next: posts[index - 1] ?? null }
}
export function getAllTags(): { name: string; count: number }[] {
  const counts = new Map<string, number>()
  getAllPosts().forEach(post => post.tags.forEach(tag => counts.set(tag, (counts.get(tag) ?? 0) + 1)))
  return [...counts].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh-CN'))
}
