import type { Post } from '@/types/blog'

const modules = import.meta.glob('/content/posts/*.md', { eager: true })

function calcReadTime(content: string): number {
  const words = content.replace(/<[^>]+>/g, '').length
  return Math.max(1, Math.ceil(words / 300))
}

// 缓存，避免多次调用顺序不一致导致上/下篇错乱
let _cache: Post[] | null = null

export function getAllPosts(): Post[] {
  if (_cache) return _cache

  _cache = Object.entries(modules)
    .map(([path, mod]) => {
      const m = mod as Record<string, unknown>
      const filename = path.split('/').pop()!.replace('.md', '')

      // 兼容多种 frontmatter 导出方式
      const fm = (
        m['frontmatter'] ??
        m['meta'] ??
        {}
      ) as Record<string, unknown>

      // 部分插件版本把 title 直接挂在模块上
      const title =
        (fm['title'] as string) ??
        (m['title'] as string) ??
        filename

      const tags = Array.isArray(fm['tags'])
        ? (fm['tags'] as string[])
        : []

      const date =
        (fm['date'] as string) ??
        (m['date'] as string) ??
        '1970-01-01'

      const excerpt =
        (fm['excerpt'] as string) ??
        (m['excerpt'] as string) ??
        ''

      return {
        title,
        date,
        tags,
        excerpt,
        slug: filename,
        path: `/posts/${filename}`,
        readTime: calcReadTime(
          typeof m['__raw'] === 'string' ? m['__raw'] : ''
        ),
      } as Post
    })
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())

  return _cache
}

export function getPostBySlug(slug: string): Post | undefined {
  return getAllPosts().find(p => p.slug === slug)
}

export function getPrevNextPost(slug: string): { prev: Post | null; next: Post | null } {
  const posts = getAllPosts()
  const idx = posts.findIndex(p => p.slug === slug)
  return {
    prev: idx < posts.length - 1 ? posts[idx + 1] : null,  // 更旧的
    next: idx > 0                ? posts[idx - 1] : null,  // 更新的
  }
}

export function getAllTags(): { name: string; count: number }[] {
  const map = new Map<string, number>()
  getAllPosts().forEach(p =>
    p.tags.forEach(t => map.set(t, (map.get(t) ?? 0) + 1))
  )
  return Array.from(map.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
}
