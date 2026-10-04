import type { Note, Paper } from './types.ts'
export function notesMarkdown(paper: Paper, notes: Note[]): string {
  return `# ${paper.name.replace(/[\r\n]/g, ' ')} · 研究笔记\n\n来源校验值（SHA256）：${paper.id}\n\n` + notes.map((note, index) =>
    `## ${index + 1}. 第 ${note.page} 页\n\n记录时间：${note.createdAt}\n\n${note.quote ? note.quote.split('\n').map(line => '> ' + line).join('\n') + '\n\n' : ''}${note.body}\n`).join('\n')
}
export function download(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = name
  document.body.appendChild(link)
  link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}
