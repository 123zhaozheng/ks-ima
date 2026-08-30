import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderMarkdown } from 'src/utils/markdown'

/*
 * DOMPurify itself does not run under happy-dom (its DOM traversal relies on
 * browser parsing behavior happy-dom does not emulate). The stub below mimics
 * its contract closely enough to exercise our wiring: marked output must flow
 * through DOMPurify.sanitize before it reaches v-html.
 */
const sanitize = vi.hoisted(() => vi.fn((html: string) => html
  .replace(/<script\b[\s\S]*?<\/script>/gi, '')
  .replace(/\son\w+="[^"]*"/gi, '')))

vi.mock('dompurify', () => ({
  default: { sanitize },
}))

beforeEach(() => {
  sanitize.mockClear()
})

describe('renderMarkdown', () => {
  it('renders markdown to html through the sanitizer', () => {
    const html = renderMarkdown('# Title\n\n- first\n- second')
    expect(sanitize).toHaveBeenCalledTimes(1)
    expect(html).toContain('<h1>Title</h1>')
    expect(html).toContain('<li>first</li>')
  })

  it('renders empty input to an empty string', () => {
    expect(renderMarkdown('')).toBe('')
    expect(renderMarkdown(null)).toBe('')
  })

  it('routes dangerous markup through the sanitizer', () => {
    const html = renderMarkdown('<script>alert(1)</script>safe <img src="x" onerror="alert(1)">')
    expect(sanitize).toHaveBeenCalled()
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('onerror')
    expect(html).toContain('safe')
  })

  it('keeps benign formatting links', () => {
    const html = renderMarkdown('[docs](https://example.com)')
    expect(html).toContain('<a href="https://example.com">docs</a>')
  })
})
