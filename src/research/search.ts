import { TERMS } from './terms.ts'
import type { Expansion, Hit, Passage } from './types.ts'

export function tokens(text: string): string[] {
  const value = text.normalize('NFKC').toLowerCase()
  const result: string[] = value.match(/[a-z0-9_]+/g) || []
  for (const run of value.match(/[\u4e00-\u9fff]+/g) || []) {
    if (run.length === 1) result.push(run)
    else for (let i = 0; i < run.length - 1; i++) result.push(run.slice(i, i + 2))
  }
  return result
}

export function expand(query: string): Expansion[] {
  let remaining = query
  const result: Expansion[] = []
  for (const term of Object.keys(TERMS).sort((a, b) => b.length - a.length)) {
    if (!remaining.includes(term)) continue
    result.push({ term, alternatives: TERMS[term] })
    remaining = remaining.split(term).join(' '.repeat(term.length))
  }
  return result
}

export function search(query: string, passages: Passage[], first = 1, last = 300): { hits: Hit[]; expansion: Expansion[] } {
  const expansion = expand(query)
  const docs = passages.filter(p => p.page >= first && p.page <= last)
  const counts = docs.map(p => {
    const map = new Map<string, number>()
    for (const t of tokens(p.text)) map.set(t, (map.get(t) || 0) + 1)
    return map
  })
  const lengths = counts.map(c => [...c.values()].reduce((a, b) => a + b, 0))
  const average = lengths.reduce((a, b) => a + b, 0) / (docs.length || 1) || 1
  const frequency = new Map<string, number>()
  for (const count of counts) for (const token of count.keys()) frequency.set(token, (frequency.get(token) || 0) + 1)
  const bm25 = (words: string[], i: number) => [...new Set(words)].reduce((sum, word) => {
    const count = counts[i].get(word) || 0
    if (!count) return sum
    const idf = Math.log(1 + (docs.length - (frequency.get(word) || 0) + .5) / ((frequency.get(word) || 0) + .5))
    return sum + idf * count * 2.5 / (count + 1.5 * (.25 + .75 * lengths[i] / average))
  }, 0)
  const equation = query.match(/公式\s*[（(]?\s*(\d{1,3})/)
  const equationPattern = equation ? new RegExp(`[（(]\\s*${equation[1]}\\s*[)）]`) : null
  const hits = docs.map((p, i) => {
    let score = bm25(tokens(query), i)
    for (const concept of expansion) {
      let best = 0
      for (const phrase of concept.alternatives) {
        const words = tokens(phrase)
        if (words.length && words.every(t => counts[i].has(t))) best = Math.max(best, bm25(words, i) + 2)
      }
      score += best
    }
    if (equationPattern) score = equationPattern.test(p.text) ? score + 20 : 0
    return { ...p, score }
  }).filter(p => p.score > 0).sort((a, b) => b.score - a.score || a.page - b.page || a.ordinal - b.ordinal).slice(0, 8)
  return { hits, expansion }
}

export function fragments(text: string, page: number): Passage[] {
  const result: Passage[] = []
  let rest = text.trim()
  while (rest) {
    let end = Math.min(rest.length, 900)
    const heading = /\n(?=(?:\d+\.(?:\d+\.?)?|[A-Z]\.)\s+[A-Z][^\n]{2,70}(?:\n|$))/.exec(rest.slice(0, end))
    if (heading && heading.index > 0) end = heading.index
    if (end < rest.length) {
      const boundary = Math.max(rest.lastIndexOf('. ', end), rest.lastIndexOf('。', end), rest.lastIndexOf('\n', end))
      if (!heading && boundary > 450) end = boundary + 1
    }
    result.push({ text: rest.slice(0, end).trim(), page, ordinal: result.length })
    rest = rest.slice(end).trim()
  }
  return result
}
