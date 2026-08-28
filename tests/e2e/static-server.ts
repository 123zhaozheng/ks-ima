import { resolve, sep } from 'node:path'
import { apiOrigin } from './environment'

const [rootArgument, portArgument] = Bun.argv.slice(2)
if (!rootArgument || !portArgument) throw new Error('Usage: static-server.ts <root> <port>')

const root = resolve(rootArgument)
const port = Number(portArgument)

Bun.serve({
  hostname: '127.0.0.1',
  port,
  async fetch(request) {
    const url = new URL(request.url)
    const oauthProtocolRoute = new Set([
      '/oauth/authorize',
      '/oauth/authorize/decision',
      '/oauth/token',
      '/oauth/revoke',
    ]).has(url.pathname)
    if (url.pathname.startsWith('/api/') || oauthProtocolRoute) {
      const headers = new Headers(request.headers)
      headers.delete('host')
      return fetch(`${apiOrigin}${url.pathname}${url.search}`, {
        method: request.method,
        headers,
        body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer(),
        redirect: 'manual',
      })
    }

    const requestedPath = decodeURIComponent(url.pathname)
    const resolvedPath = resolve(root, `.${requestedPath}`)
    if (resolvedPath !== root && !resolvedPath.startsWith(`${root}${sep}`)) {
      return new Response('Forbidden', { status: 403 })
    }
    const file = Bun.file(resolvedPath)
    if (!requestedPath.endsWith('/') && await file.exists()) return new Response(file)
    return new Response(Bun.file(resolve(root, 'index.html')))
  },
})
