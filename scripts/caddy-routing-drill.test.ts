import { describe, expect, test } from 'bun:test'
import {
  BUN_PATHS,
  CADDY_IMAGE,
  INTERNAL_PATH,
  PYTHON_PATHS,
  ZERO_PATHS,
  buildCutoverConfig,
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

  test('derives cutover JSON withdrawing legacy upstreams to Python', () => {
    const legacyRoute = {
      match: [{ path: ['/api/*'] }],
      handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: ['legacy-upstream:9000'] }] }],
    }
    const zeroRoute = {
      match: [{ path: ['/zero-cache/*'] }],
      handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: ['zero-upstream:9001'] }] }],
    }
    const adapted = {
      apps: {
        http: {
          servers: {
            front: { listen: [':8080'], routes: [structuredClone(legacyRoute), structuredClone(zeroRoute)] },
            admin: { listen: [':8081'], routes: [structuredClone(legacyRoute)] },
            private: { listen: [':9090'], routes: [structuredClone(zeroRoute)] },
          },
        },
      },
    }
    const result = buildCutoverConfig(adapted, {
      legacyDial: 'legacy-upstream:9000',
      pythonDial: 'python-upstream:9002',
    })
    const servers = (result.apps as any).http.servers
    expect(servers.front.routes[0]).toEqual({
      match: [{ path: ['/api/mcp'] }],
      handle: [{ handler: 'static_response', status_code: 410 }],
      terminal: true,
    })
    expect(servers.admin.routes[0]).toEqual(servers.front.routes[0])
    expect(servers.front.routes[1].handle[0].upstreams[0].dial).toEqual(['python-upstream:9002'])
    expect(servers.admin.routes[1].handle[0].upstreams[0].dial).toEqual(['python-upstream:9002'])
    expect(servers.front.routes[2].handle[0].upstreams[0].dial).toEqual(['zero-upstream:9001'])
    expect(servers.private.routes).toHaveLength(1)
    expect(JSON.stringify(result)).not.toContain('legacy-upstream:9000')
  })

  test('cutover derivation handles nested subroute handlers with string dials', () => {
    const adapted = {
      apps: {
        http: {
          servers: {
            srv0: {
              listen: [':8080'],
              routes: [
                {
                  match: [{ path: ['/api/*'] }],
                  handle: [
                    {
                      handler: 'subroute',
                      routes: [
                        {
                          handle: [
                            {
                              handler: 'reverse_proxy',
                              upstreams: [{ dial: 'legacy-upstream:9000' }],
                            },
                          ],
                        },
                      ],
                    },
                  ],
                },
              ],
            },
            srv1: {
              listen: [':8081'],
              routes: [
                {
                  match: [{ path: ['/api/*'] }],
                  handle: [
                    {
                      handler: 'subroute',
                      routes: [
                        {
                          handle: [
                            {
                              handler: 'reverse_proxy',
                              upstreams: [{ dial: 'legacy-upstream:9000' }],
                            },
                          ],
                        },
                      ],
                    },
                  ],
                },
              ],
            },
          },
        },
      },
    }
    const result = buildCutoverConfig(adapted, {
      legacyDial: 'legacy-upstream:9000',
      pythonDial: 'python-upstream:9002',
    })
    const servers = (result.apps as any).http.servers
    for (const name of ['srv0', 'srv1']) {
      expect(servers[name].routes[0].handle[0]).toEqual({
        handler: 'static_response',
        status_code: 410,
      })
      const nested = servers[name].routes[1].handle[0].routes[0].handle[0]
      expect(nested.upstreams[0].dial).toBe('python-upstream:9002')
    }
    expect(JSON.stringify(result)).not.toContain('legacy-upstream:9000')
  })

  test('cutover derivation fails closed without a legacy upstream to withdraw', () => {
    const adapted = {
      apps: {
        http: {
          servers: {
            front: { listen: [':8080'], routes: [{ handle: [{ handler: 'static_response' }] }] },
            admin: { listen: [':8081'], routes: [{ handle: [{ handler: 'static_response' }] }] },
          },
        },
      },
    }
    expect(() =>
      buildCutoverConfig(adapted, { legacyDial: 'legacy:1', pythonDial: 'python:2' }),
    ).toThrow('no legacy upstream to withdraw')
  })

  test('cutover derivation fails closed when a legacy dial survives on a skipped server', () => {
    const adapted = {
      apps: {
        http: {
          servers: {
            front: {
              listen: [':8080'],
              routes: [
                { handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: ['legacy:1'] }] }] },
              ],
            },
            admin: {
              listen: [':8081'],
              routes: [
                { handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: ['legacy:1'] }] }] },
              ],
            },
            private: {
              listen: [':9090'],
              routes: [
                { handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: ['legacy:1'] }] }] },
              ],
            },
          },
        },
      },
    }
    expect(() =>
      buildCutoverConfig(adapted, { legacyDial: 'legacy:1', pythonDial: 'python:2' }),
    ).toThrow('survived the cutover rewrite')
  })

  test('selects a deterministic caddy repository digest', () => {
    const one = `caddy@sha256:${'1'.repeat(64)}`
    const two = `caddy@sha256:${'2'.repeat(64)}`
    expect(resolveImageDigest([two, 'other@sha256:bad', one])).toBe(one)
    expect(() => resolveImageDigest([])).toThrow('no caddy repository digest')
  })
})
