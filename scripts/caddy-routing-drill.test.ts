import { describe, expect, test } from 'bun:test'
import {
  CADDY_IMAGE,
  GONE_PATHS,
  INTERNAL_PATH,
  NOT_FOUND_PATHS,
  PYTHON_PATHS,
  resolveImageDigest,
} from './caddy-routing-drill'

describe('Caddy routing drill contract', () => {
  test('pins the deployed image and the terminal route matrix', () => {
    expect(CADDY_IMAGE).toBe('caddy:2.10.2-alpine')
    expect(PYTHON_PATHS).toContain('/mcp')
    expect(PYTHON_PATHS).toContain('/.well-known/oauth-protected-resource/mcp')
    expect(PYTHON_PATHS).toContain('/oauth/token')
    expect(PYTHON_PATHS).toContain('/api/v1/oauth/grants')
    expect(GONE_PATHS).toEqual([
      '/api/mcp',
      '/api/kb',
      '/api/s3',
      '/api/search',
      '/api/v1/chat/completions',
      '/api/connectors',
    ])
    expect(NOT_FOUND_PATHS).toEqual(['/api/legacy-check', '/api/nonexistent'])
    expect(INTERNAL_PATH).toStartWith('/api/v1/internal/')
  })

  test('keeps terminal route classes disjoint and off the Python surface', () => {
    const pythonPaths = new Set<string>(PYTHON_PATHS)
    for (const path of [...GONE_PATHS, ...NOT_FOUND_PATHS, INTERNAL_PATH]) {
      expect(pythonPaths.has(path)).toBe(false)
    }
    expect(new Set(GONE_PATHS).size).toBe(GONE_PATHS.length)
    expect(new Set(NOT_FOUND_PATHS).size).toBe(NOT_FOUND_PATHS.length)
  })

  test('selects a deterministic caddy repository digest', () => {
    const one = `caddy@sha256:${'1'.repeat(64)}`
    const two = `caddy@sha256:${'2'.repeat(64)}`
    expect(resolveImageDigest([two, 'other@sha256:bad', one])).toBe(one)
    expect(() => resolveImageDigest([])).toThrow('no caddy repository digest')
  })
})
