import { describe, expect, it, vi } from 'vitest'
import { citationMarkerRanks, injectCitationMarks, renderMarkdown } from 'src/utils/markdown'

/*
 * DOMPurify does not run under happy-dom; the stub mirrors the contract from
 * MarkdownRender.vitest.ts so marked output flows through sanitize() before
 * reaching v-html.
 */
const sanitize = vi.hoisted(() => vi.fn((html: string, _config?: { ADD_TAGS: string[] }) => html
  .replace(/<script\b[\s\S]*?<\/script>/gi, '')
  .replace(/\son\w+="[^"]*"/gi, '')))

vi.mock('dompurify', () => ({
  default: { sanitize },
}))

describe('renderMarkdown highlight', () => {
  it('wraps the first exact match of the quote in a mark tag', () => {
    const html = renderMarkdown('First line.\n\nThe policy quote lives here.\n\nThe policy quote lives here again.', 'The policy quote lives here.')
    expect(html).toContain('<mark>The policy quote lives here.</mark>')
    // Only the first occurrence is highlighted.
    expect(html.match(/<mark>/g)).toHaveLength(1)
  })

  it('leaves the output untouched when the quote does not match', () => {
    expect(renderMarkdown('plain text', 'missing quote')).not.toContain('<mark>')
  })

  it('keeps the highlight safe when the quote contains markup', () => {
    const html = renderMarkdown('before after', '<img src="x" onerror="alert(1)">')
    expect(sanitize).toHaveBeenCalled()
    expect(html).not.toContain('onerror')
  })

  it('asks the sanitizer to keep the mark tag', () => {
    renderMarkdown('text', 'text')
    const [, config] = sanitize.mock.calls.at(-1) as [string, { ADD_TAGS: string[] }]
    expect(config.ADD_TAGS).toContain('mark')
  })
})

describe('injectCitationMarks', () => {
  it('converts known [n] markers into clickable superscripts', () => {
    const html = injectCitationMarks('<p>Answer from [1] and [2]</p>', [1, 2])
    expect(html).toContain('data-citation="1"')
    expect(html).toContain('data-citation="2"')
    expect(html).toContain('data-testid="citation-mark"')
    expect(html).toContain('role="button"')
    expect(html).not.toContain('[1]')
  })

  it('leaves markers with unknown ranks untouched', () => {
    const html = injectCitationMarks('<p>Answer [1] and [9]</p>', [1])
    expect(html).toContain('data-citation="1"')
    expect(html).toContain('[9]')
  })

  it('ignores markers inside code blocks', () => {
    const html = injectCitationMarks('<pre><code>[1]</code></pre><p>text [1]</p>', [1])
    const codeStart = html.indexOf('<code>')
    const codeEnd = html.indexOf('</code>')
    expect(html.slice(codeStart, codeEnd)).not.toContain('data-citation')
    expect(html).toContain('data-citation="1"')
  })

  it('returns the input unchanged without ranks', () => {
    expect(injectCitationMarks('<p>[1]</p>', [])).toBe('<p>[1]</p>')
    expect(injectCitationMarks('', [1])).toBe('')
  })

  it('handles several markers in one text node', () => {
    const html = injectCitationMarks('<p>a [1] b [2] c [1]</p>', [1, 2])
    expect(html.match(/data-citation="1"/g)).toHaveLength(2)
    expect(html.match(/data-citation="2"/g)).toHaveLength(1)
  })
})

describe('citationMarkerRanks', () => {
  it('extracts sorted unique ranks', () => {
    expect(citationMarkerRanks('a [3] b [1] c [3] d')).toEqual([1, 3])
  })

  it('returns empty without markers', () => {
    expect(citationMarkerRanks('no markers here')).toEqual([])
  })
})
