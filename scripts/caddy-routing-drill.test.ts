import { describe, expect, test } from 'bun:test'
import {
  BUN_PATHS,
  CADDY_IMAGE,
  INTERNAL_PATH,
  PYTHON_PATHS,
  ZERO_PATHS,
  buildRollbackConfig,
  resolveImageDigest,
} from './caddy-routing-drill'

describe('Caddy routing drill contract', () => {
  test('pins the deployed image and complete route matrix', () => {
    expect(CADDY_IMAGE).toBe('caddy:2.10.2-alpine')
    expect(PYTHON_PATHS).toContain('/mcp')
    expect(PYTHON_PATHS).toContain('/.well-known/oauth-protected-resource/mcp')
    expect(PYTHON_PATHS).toContain('/oauth/token')
    expect(PYTHON_PATHS).toContain('/api/v1/oauth/grants')
    expect(BUN_PATHS).toEqual(['/api/mcp', '/api/legacy-check'])
    expect(ZERO_PATHS).toEqual(['/zero-cache/replica'])
    expect(INTERNAL_PATH).toStartWith('/api/v1/internal/')
  })

  test('derives rollback JSON without mutating unrelated routes', () => {
    const adapted = {
      apps: {
        http: {
          servers: {
            front: { listen: [':8080'], routes: [{ handle: [{ handler: 'subroute' }] }] },
            admin: { listen: [':8081'], routes: [{ handle: [{ handler: 'subroute' }] }] },
            private: { listen: [':9090'], routes: [{ handle: [{ handler: 'reverse_proxy' }] }] },
          },
        },
      },
    }
    const result = buildRollbackConfig(adapted)
    const servers = (result.apps as any).http.servers
    expect(servers.front.routes[0]).toEqual({
      match: [{ path: ['/mcp'] }],
      handle: [{ handler: 'static_response', status_code: 404 }],
      terminal: true,
    })
    expect(servers.admin.routes[0]).toEqual(servers.front.routes[0])
    expect(servers.private.routes).toHaveLength(1)
  })

  test('selects a deterministic caddy repository digest', () => {
    const one = `caddy@sha256:${'1'.repeat(64)}`
    const two = `caddy@sha256:${'2'.repeat(64)}`
    expect(resolveImageDigest([two, 'other@sha256:bad', one])).toBe(one)
    expect(() => resolveImageDigest([])).toThrow('no caddy repository digest')
  })
})
