import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { extractPostMetadata } from '../build/post-metadata.ts'

test('preserves YAML metadata, including Chinese tags and optional fields', () => {
  const post = extractPostMetadata('---\ntitle: 测试文章\ndate: 2026-02-22\nupdated: 2026-02-23\ntags: [前端, Vue3]\ncover: /cover.png\ndraft: true\n---\n正文内容')
  assert.equal(post.title, '测试文章')
  assert.deepEqual(post.tags, ['前端', 'Vue3'])
  assert.equal(post.cover, '/cover.png')
  assert.equal(post.draft, true)
  assert.equal(new Date(post.date).toISOString().slice(0, 10), '2026-02-22')
  assert.equal(new Date(post.updated).toISOString().slice(0, 10), '2026-02-23')
})

test('calculates reading time from content rather than frontmatter', () => {
  const post = extractPostMetadata(`---\ntitle: ${'标题'.repeat(500)}\n---\n${'字'.repeat(601)}`)
  assert.equal(post.wordCount, 601)
  assert.equal(post.readTime, 3)
  assert.equal(extractPostMetadata('hello world').wordCount, 2)
  assert.equal(extractPostMetadata('').readTime, 1)
})

test('all current articles provide usable index metadata', () => {
  const directory = new URL('../content/posts/', import.meta.url)
  const files = readdirSync(directory).filter(file => file.endsWith('.md'))
  assert.ok(files.length)
  for (const file of files) {
    const post = extractPostMetadata(readFileSync(new URL(file, directory), 'utf8'))
    assert.equal(typeof post.title, 'string', file)
    assert.ok(Array.isArray(post.tags) && post.tags.length, file)
    assert.ok(!Number.isNaN(new Date(post.date).getTime()), file)
    assert.ok(post.wordCount > 0, file)
  }
})
