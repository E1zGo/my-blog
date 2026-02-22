export interface Post {
  slug: string
  title: string
  date: string
  tags: string[]
  excerpt: string
  readTime?: number
  path: string
  cover?: string        // 封面图（功能11）
  updated?: string      // 最后更新时间（功能5）
  draft?: boolean       // 草稿（功能6）
  wordCount?: number
}

export interface FrontMatter {
  title: string
  date: string
  tags: string[]
  excerpt: string
  cover?: string
  updated?: string
  draft?: boolean
}
