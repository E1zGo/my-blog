/** Recover rows and common two-column layouts; original canvas remains authoritative. */
export interface TextBox { str: string; transform: number[]; width: number; height: number }
interface Row { y: number; size: number; boxes: TextBox[] }
interface Line { y: number; x: number; end: number; size: number; text: string }

export function pageText(items: TextBox[], width: number): string {
  const rows: Row[] = []
  for (const item of items.filter(i => i.str.trim()).sort((a, b) => b.transform[5] - a.transform[5] || a.transform[4] - b.transform[4])) {
    const size = Math.max(1, Math.abs(item.height) || Math.abs(item.transform[3]) || 10)
    const previous = rows[rows.length - 1]
    if (previous && Math.abs(previous.y - item.transform[5]) <= Math.min(3, size * .3)) previous.boxes.push(item)
    else rows.push({ y: item.transform[5], size, boxes: [item] })
  }
  const lines: Line[] = []
  let pairedRows = 0
  for (const row of rows) {
    const boxes = row.boxes.sort((a, b) => a.transform[4] - b.transform[4])
    const groups: TextBox[][] = [[]]
    for (const box of boxes) {
      const current = groups[groups.length - 1]
      const previous = current[current.length - 1]
      if (previous && box.transform[4] - (previous.transform[4] + previous.width) > row.size * 1.8
          && previous.transform[4] + previous.width < width * .6 && box.transform[4] > width * .45) groups.push([])
      groups[groups.length - 1].push(box)
    }
    if (groups.length > 1) pairedRows++
    for (const group of groups) {
      let text = ''
      group.forEach((box, i) => {
        const previous = group[i - 1]
        const gap = previous ? box.transform[4] - previous.transform[4] - previous.width : 0
        text += (i && gap > row.size * .15 && !text.endsWith(' ') ? ' ' : '') + box.str
      })
      const last = group[group.length - 1]
      lines.push({ y: row.y, x: group[0].transform[4], end: last.transform[4] + last.width, size: row.size, text })
    }
  }
  // Opposite columns often have staggered baselines. Detect their repeated
  // paragraph bounds as well as aligned rows, without treating a long heading
  // or a full-width table as evidence against the entire page's columns.
  const prose = items.filter(i => i.str.trim().length >= 25 && i.width >= width * .22)
  const leftProse = prose.filter(i => i.transform[4] < width * .3 && i.transform[4] + i.width < width * .49)
  const rightProse = prose.filter(i => i.transform[4] > width * .49 && i.transform[4] < width * .62)
  const spans = prose.filter(i => i.transform[4] < width * .4 && i.transform[4] + i.width > width * .65)
  const dual = (pairedRows >= 3 && pairedRows >= rows.length * .12)
    || (leftProse.length >= 4 && rightProse.length >= 4 && leftProse.length + rightProse.length > spans.length * 2)
  const ordered: Line[] = []
  let band: Line[] = []
  const flush = () => {
    for (const side of [0, 1]) ordered.push(...band.filter(l => Number(l.x >= width * .45) === side).sort((a, b) => b.y - a.y))
    band = []
  }
  for (const line of lines) {
    if (!dual) ordered.push(line)
    else if (line.x < width * .45 && line.end > width * .6) { flush(); ordered.push(line) }
    else band.push(line)
  }
  flush()
  return ordered.map(l => l.text).join('\n').replace(/([a-z])-\n([a-z])/g, '$1$2').replace(/\0/g, '')
}
