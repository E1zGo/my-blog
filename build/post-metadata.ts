import matter from 'gray-matter'

/** Extract only index data at build time, keeping Markdown and its parser out of the homepage. */
export function extractPostMetadata(source: string) {
  const { data, content } = matter(source)
  const text = content.replace(/<[^>]*>/g, '')
  const wordCount = (text.match(/[\u3400-\u9fff]/g)?.length || 0)
    + (text.match(/[a-zA-Z0-9_]+/g)?.length || 0)
  return { ...data, wordCount, readTime: Math.max(1, Math.ceil(wordCount / 300)) }
}
