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
  if (!html || ranks.length === 0) return html
  const rankSet = new Set(ranks)
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const textNodes: Text[] = []
  const collect = (node: Node) => {
    for (const child of Array.from(node.childNodes)) {
      if (child.nodeType === Node.TEXT_NODE) textNodes.push(child as Text)
      else if (child.nodeType === Node.ELEMENT_NODE) collect(child)
    }
  }
  collect(doc.body)
  for (const node of textNodes) {
    if (!/\[\d+\]/.test(node.data)) continue
    if (node.parentElement?.closest('pre, code')) continue
    const fragment = doc.createDocumentFragment()
    let cursor = 0
    node.data.replace(/\[(\d+)\]/g, (match, digits: string, offset: number) => {
      const rank = Number(digits)
      if (!rankSet.has(rank)) return match
      fragment.append(node.data.slice(cursor, offset))
      const sup = doc.createElement('sup')
      sup.className = 'citation-mark'
      sup.setAttribute('data-citation', digits)
      sup.setAttribute('data-testid', 'citation-mark')
      sup.setAttribute('role', 'button')
      sup.setAttribute('tabindex', '0')
      sup.textContent = digits
      fragment.append(sup)
      cursor = offset + match.length
      return match
    })
    if (cursor === 0) continue
    fragment.append(node.data.slice(cursor))
    node.replaceWith(fragment)
  }
  return doc.body.innerHTML
}

/** Extract the distinct `[n]` marker ranks that appear in answer text. */
export function citationMarkerRanks(content: string): number[] {
  const ranks = new Set<number>()
  for (const match of content.matchAll(/\[(\d+)\]/g)) ranks.add(Number(match[1]))
  return [...ranks].sort((a, b) => a - b)
}
