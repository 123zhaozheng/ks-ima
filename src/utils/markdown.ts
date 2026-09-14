import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: true })

/**
 * Wrap the first exact match of `quote` in <mark> at the markdown source
 * level. The quote may contain markdown or HTML syntax; both are processed and
 * sanitized downstream, so the output stays safe for v-html.
 */
function highlightFirstMatch(source: string, quote: string): string {
  if (!quote) return source
  const index = source.indexOf(quote)
  if (index === -1) return source
  return `${source.slice(0, index)}<mark>${quote}</mark>${source.slice(index + quote.length)}`
}

/**
 * Render markdown to sanitized HTML. Output is always safe to inject with
 * v-html: DOMPurify strips scripts, event handlers and dangerous URLs.
 * Synchronous on purpose so computed properties stay simple.
 *
 * `highlight` (optional) wraps the first exact match of the given quote in a
 * <mark> tag — used by the citation pane to locate the cited passage.
 */
export function renderMarkdown(markdown: string | null | undefined, highlight?: string | null): string {
  const source = highlight ? highlightFirstMatch(markdown ?? '', highlight) : (markdown ?? '')
  const html = marked.parse(source, { async: false })
  return DOMPurify.sanitize(html, { ADD_TAGS: ['mark'] })
}

/**
 * Post-process already-rendered (and sanitized) answer HTML: turn citation
 * markers like `[1]` into clickable numbered superscripts. Only ranks present
 * in `ranks` are converted, so plain bracketed text survives untouched.
 * Markers inside <pre>/<code> are left alone (they are code, not citations).
 *
 * The resulting <sup data-citation="n"> elements are wired by the caller via
 * event delegation. Output stays sanitized: we only re-parent existing text
 * and create bare <sup> elements.
 */
export function injectCitationMarks(html: string, ranks: number[]): string {
  if (!html) return html
  const rankSet = new Set(ranks)
  const doc = new DOMParser().parseFromString(html, 'text/html')
  for (const link of Array.from(doc.querySelectorAll('a'))) {
    if (citationMarkers(link.textContent ?? '').length) {
      link.replaceWith(doc.createTextNode(sanitizeCitationMarkers(link.textContent ?? '', ranks)))
    }
  }
  const textNodes: Text[] = []
  const collect = (node: Node) => {
    for (const child of Array.from(node.childNodes)) {
      if (child.nodeType === Node.TEXT_NODE) textNodes.push(child as Text)
      else if (child.nodeType === Node.ELEMENT_NODE) collect(child)
    }
  }
  collect(doc.body)
  for (const node of textNodes) {
    if (node.parentElement?.closest('pre, code')) continue
    const source = canonicalCitationSyntax(node.data)
    const markers = citationMarkers(source)
    if (!markers.length) continue
    const fragment = doc.createDocumentFragment()
    let cursor = 0
    for (const marker of markers) {
      fragment.append(source.slice(cursor, marker.start))
      if (!rankSet.has(marker.rank)) {
        fragment.append(source.slice(marker.start, marker.end))
      } else {
        const sup = doc.createElement('sup')
        sup.className = 'citation-mark'
        sup.setAttribute('data-citation', String(marker.rank))
        sup.setAttribute('data-testid', 'citation-mark')
        sup.setAttribute('role', 'button')
        sup.setAttribute('tabindex', '0')
        sup.textContent = String(marker.rank)
        fragment.append(sup)
      }
      cursor = marker.end
    }
    fragment.append(source.slice(cursor))
    node.replaceWith(fragment)
  }
  return doc.body.innerHTML
}

type CitationMarker = { start: number, markerEnd: number, end: number, rank: number, linked: boolean }

const citationMarkerPattern = /\[(?:\[([0-9０-９]+)\]|([0-9０-９]+))\]/g
const bracketEntityPattern = /&(?:#(?:91|93);|#x(?:5b|5d);|(?:lbrack|rbrack|lsqb|rsqb);)/gi
const numericEntityPattern = /&#(?:x([0-9a-f]+)|([0-9]+));/gi

function canonicalCitationSyntax(content: string): string {
  const brackets = content
    .replace(/\\(?=[\x5B\x5D])/g, '')
    .replace(bracketEntityPattern, entity => {
      const token = entity.toLowerCase()
      return token === '&#91;' || token === '&#x5b;' || token === '&lbrack;' || token === '&lsqb;'
        ? '['
        : ']'
    })
  return brackets.replace(numericEntityPattern, (entity, hexadecimal: string | undefined, decimal: string | undefined) => {
    const codePoint = hexadecimal ? Number.parseInt(hexadecimal, 16) : Number.parseInt(decimal ?? '', 10)
    return (codePoint >= 48 && codePoint <= 57) || (codePoint >= 0xff10 && codePoint <= 0xff19)
      ? String.fromCodePoint(codePoint)
      : entity
  })
}

function canonicalCitationDigits(value: string): string {
  return [...value].map(char => {
    const codePoint = char.codePointAt(0) ?? 0
    return codePoint >= 0xff10 && codePoint <= 0xff19
      ? String.fromCodePoint(codePoint - 0xff10 + 48)
      : char
  }).join('')
}

function optionalCitationLinkEnd(content: string, markerEnd: number): number | null {
  let cursor = markerEnd
  while (cursor < content.length && /[ \t\r\n]/.test(content[cursor])) cursor += 1
  if (cursor >= content.length || content[cursor] !== '(') return markerEnd
  let depth = 0
  while (cursor < content.length) {
    const char = content[cursor]
    if (char === '\\') {
      cursor += 2
      continue
    }
    if (char === '(') depth += 1
    else if (char === ')') {
      depth -= 1
      if (depth === 0) return cursor + 1
    }
    cursor += 1
  }
  return null
}

function citationMarkers(content: string): CitationMarker[] {
  const markers: CitationMarker[] = []
  const source = canonicalCitationSyntax(content)
  const pattern = new RegExp(citationMarkerPattern.source, 'g')
  let match: RegExpExecArray | null
  while ((match = pattern.exec(source)) !== null) {
    const start = match.index ?? 0
    const markerEnd = start + match[0].length
    let end = markerEnd
    let linked = false
    let linkCursor = markerEnd
    while (linkCursor < source.length && /[ \t\r\n]/.test(source[linkCursor])) linkCursor += 1
    if (source[linkCursor] === '(') {
      linked = true
      end = optionalCitationLinkEnd(source, markerEnd) ?? markerEnd
    }
    markers.push({
      start,
      markerEnd,
      end,
      rank: Number(canonicalCitationDigits(match[1] ?? match[2] ?? '0')),
      linked,
    })
    if (end > markerEnd) pattern.lastIndex = end
  }
  return markers
}

/** Normalize accepted marker variants and keep only ranks backed by citations. */
export function sanitizeCitationMarkers(content: string, ranks: number[]): string {
  const allowed = new Set(ranks)
  const source = canonicalCitationSyntax(content)
  const markers = citationMarkers(source)
  if (markers.length === 0) return content
  let result = ''
  let cursor = 0
  for (const marker of markers) {
    result += source.slice(cursor, marker.start)
    if (allowed.has(marker.rank)) result += `[${marker.rank}]`
    cursor = marker.end
  }
  return result + source.slice(cursor)
}

/** Extract distinct ranks from every accepted citation marker variant. */
export function citationMarkerRanks(content: string): number[] {
  const ranks = new Set<number>()
  for (const marker of citationMarkers(content)) {
    ranks.add(marker.rank)
  }
  return [...ranks].sort((a, b) => a - b)
}
