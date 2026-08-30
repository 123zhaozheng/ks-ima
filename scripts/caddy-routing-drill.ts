import { createHash, randomUUID } from 'node:crypto'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

export const CADDY_IMAGE = 'caddy:2.10.2-alpine'

export const PYTHON_PATHS = [
  '/mcp',
  '/.well-known/oauth-protected-resource',
  '/.well-known/oauth-protected-resource/mcp',
  '/.well-known/oauth-authorization-server',
  '/oauth/authorize',
  '/oauth/authorize/decision',
  '/oauth/token',
  '/oauth/revoke',
  '/api/v1/oauth/grants',
] as const

// Retired legacy resources; the edge answers 410 Gone so consumers repoint.
export const GONE_PATHS = [
  '/api/mcp',
  '/api/kb',
  '/api/s3',
  '/api/search',
  '/api/v1/chat/completions',
  '/api/connectors',
] as const

// Residual legacy API space with no backend; the edge answers 404.
export const NOT_FOUND_PATHS = ['/api/legacy-check', '/api/nonexistent'] as const

export const INTERNAL_PATH = '/api/v1/internal/session/introspect'

type Marker = 'python' | 'none'

export interface RouteEvidence {
  listener: 8080 | 8081
  path: string
  status: number
  upstream: Marker
}

export interface PhaseEvidence {
  phase: 'terminal'
  routes: RouteEvidence[]
}

interface CommandResult {
  stdout: string
  stderr: string
}

interface MarkerServer {
  marker: Exclude<Marker, 'none'>
  server: ReturnType<typeof Bun.serve>
  hits: string[]
}

const activeProcesses = new Set<ReturnType<typeof Bun.spawn>>()

function assert(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message)
}

async function command(args: string[], timeoutMs = 30_000): Promise<CommandResult> {
  const process = Bun.spawn(args, {
    stdout: 'pipe',
    stderr: 'pipe',
    windowsHide: true,
  })
  activeProcesses.add(process)
  const stdoutPromise = new Response(process.stdout).text()
  const stderrPromise = new Response(process.stderr).text()
  let timeout: ReturnType<typeof setTimeout> | undefined
  let exited = false
  try {
    let exitCode: number
    try {
      exitCode = await Promise.race([
        process.exited,
        new Promise<never>((_resolve, reject) => {
          timeout = setTimeout(() => {
            reject(new Error(`${args[0]} ${args[1] ?? ''} timed out`))
          }, timeoutMs)
        }),
      ])
      exited = true
    } catch (error) {
      process.kill()
      await Promise.race([process.exited, Bun.sleep(5_000)])
      throw error
    }
    const [stdout, stderr] = await Promise.all([stdoutPromise, stderrPromise])
    if (exitCode !== 0) {
      throw new Error(`${args.join(' ')} failed (${exitCode}): ${stderr.trim()}`)
    }
    return { stdout, stderr }
  } finally {
    if (timeout) clearTimeout(timeout)
    if (exited) activeProcesses.delete(process)
  }
}

function markerServer(marker: Exclude<Marker, 'none'>): MarkerServer {
  const hits: string[] = []
  const server = Bun.serve({
    hostname: '0.0.0.0',
    port: 0,
    fetch(request) {
      const path = new URL(request.url).pathname
      hits.push(path)
      return Response.json(
        { marker, path },
        { headers: { 'x-upstream-marker': marker } },
      )
    },
  })
  return { marker, server, hits }
}

function dockerHostUrl(server: MarkerServer): string {
  return `http://host.docker.internal:${server.server.port}`
}

export function resolveImageDigest(value: unknown): string {
  assert(Array.isArray(value), 'Pinned Caddy image has no repository digests')
  const digests = value.filter(
    (item): item is string => typeof item === 'string' && /^caddy@sha256:[a-f0-9]{64}$/.test(item),
  ).sort()
  assert(digests.length > 0, 'Pinned Caddy image has no caddy repository digest')
  return digests[0]
}

async function mappedPort(container: string, port: 8080 | 8081): Promise<number> {
  const { stdout } = await command(['docker', 'port', container, `${port}/tcp`])
  const matches = [...stdout.matchAll(/:(\d+)\s*$/gm)]
  assert(matches.length > 0, `Docker did not publish Caddy listener ${port}`)
  return Number(matches[0][1])
}

async function waitForCaddy(port: number): Promise<void> {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/api/v1/internal/probe`, {
        signal: AbortSignal.timeout(1_000),
      })
      if (response.status === 404) return
    } catch {
      // Container startup retry.
    }
    await Bun.sleep(100)
  }
  throw new Error(`Caddy listener ${port} did not become ready`)
}

async function probe(
  port: number,
  listener: 8080 | 8081,
  path: string,
  expectedStatus: number,
  expectedMarker: Marker,
): Promise<RouteEvidence> {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    redirect: 'manual',
    signal: AbortSignal.timeout(3_000),
  })
  const marker = (response.headers.get('x-upstream-marker') ?? 'none') as Marker
  assert(response.status === expectedStatus, `${listener}${path}: expected ${expectedStatus}, got ${response.status}`)
  assert(marker === expectedMarker, `${listener}${path}: expected ${expectedMarker}, got ${marker}`)
  await response.arrayBuffer()
  return { listener, path, status: response.status, upstream: marker }
}

function totalHits(markers: MarkerServer[]): number {
  return markers.reduce((count, marker) => count + marker.hits.length, 0)
}

async function validateTerminal(container: string, markers: MarkerServer[]): Promise<PhaseEvidence> {
  const ports = {
    8080: await mappedPort(container, 8080),
    8081: await mappedPort(container, 8081),
  }
  await Promise.all([waitForCaddy(ports[8080]), waitForCaddy(ports[8081])])
  const routes: RouteEvidence[] = []
  for (const listener of [8080, 8081] as const) {
    for (const path of PYTHON_PATHS) routes.push(await probe(ports[listener], listener, path, 200, 'python'))
    for (const path of GONE_PATHS) {
      const hitsBefore = totalHits(markers)
      routes.push(await probe(ports[listener], listener, path, 410, 'none'))
      assert(totalHits(markers) === hitsBefore, `${listener}${path} reached an upstream`)
    }
    for (const path of NOT_FOUND_PATHS) {
      const hitsBefore = totalHits(markers)
      routes.push(await probe(ports[listener], listener, path, 404, 'none'))
      assert(totalHits(markers) === hitsBefore, `${listener}${path} reached an upstream`)
    }
    const hitsBeforeInternal = totalHits(markers)
    routes.push(await probe(ports[listener], listener, INTERNAL_PATH, 404, 'none'))
    assert(totalHits(markers) === hitsBeforeInternal, `${listener}${INTERNAL_PATH} reached an upstream`)
  }
  return { phase: 'terminal', routes }
}

async function startCaddy(
  container: string,
  configPath: string,
  configTarget: string,
  frontDir: string,
  adminDir: string,
  markers: MarkerServer[],
): Promise<void> {
  const marker = Object.fromEntries(markers.map(item => [item.marker, item])) as Record<string, MarkerServer>
  await command([
    'docker', 'run', '--detach', '--name', container,
    '--add-host', 'host.docker.internal:host-gateway',
    '--publish', '127.0.0.1::8080', '--publish', '127.0.0.1::8081',
    '--volume', `${configPath}:${configTarget}:ro`,
    '--volume', `${frontDir}:/srv/front:ro`, '--volume', `${adminDir}:/srv/admin:ro`,
    '--env', `PYTHON_API_URL=${dockerHostUrl(marker.python)}`,
    CADDY_IMAGE, 'caddy', 'run', '--config', configTarget,
  ])
}

async function removeContainer(container: string): Promise<void> {
  await command(['docker', 'rm', '--force', container], 15_000).catch(() => undefined)
}

async function main(): Promise<void> {
  const root = resolve(import.meta.dir, '..')
  const caddyfile = join(root, 'Caddyfile')
  const temporary = await mkdtemp(join(tmpdir(), 'ima-caddy-routing-'))
  const frontDir = join(temporary, 'front')
  const adminDir = join(temporary, 'admin')
  const prefix = `ima-caddy-drill-${randomUUID()}`
  const containers = new Set<string>()
  const markers = [markerServer('python')]
  let cleaning = false

  const cleanup = async () => {
    if (cleaning) return
    cleaning = true
    const running = [...activeProcesses]
    for (const process of running) process.kill()
    await Promise.all(
      running.map(process => Promise.race([process.exited, Bun.sleep(5_000)]).catch(() => undefined)),
    )
    await Promise.all([...containers].map(removeContainer))
    for (const marker of markers) marker.server.stop(true)
    await rm(temporary, { recursive: true, force: true })
  }
  const onSignal = async () => {
    await cleanup()
    process.exit(130)
  }
  process.once('SIGINT', onSignal)
  process.once('SIGTERM', onSignal)

  try {
    await Promise.all([mkdir(frontDir), mkdir(adminDir)])
    await Promise.all([
      writeFile(join(frontDir, 'index.html'), 'front'),
      writeFile(join(adminDir, 'index.html'), 'admin'),
    ])
    await command(['docker', 'pull', CADDY_IMAGE], 120_000)
    const { stdout: digestOutput } = await command([
      'docker', 'image', 'inspect', '--format', '{{json .RepoDigests}}', CADDY_IMAGE,
    ])
    const imageDigest = resolveImageDigest(JSON.parse(digestOutput))
    const caddyfileSha256 = createHash('sha256').update(await readFile(caddyfile)).digest('hex')

    const terminalContainer = `${prefix}-terminal`
    containers.add(terminalContainer)
    await startCaddy(terminalContainer, caddyfile, '/etc/caddy/Caddyfile', frontDir, adminDir, markers)
    const terminal = await validateTerminal(terminalContainer, markers)

    console.log(JSON.stringify({
      ok: true,
      image: CADDY_IMAGE,
      imageDigest,
      caddyfileSha256,
      phases: [terminal],
    }, null, 2))
  } finally {
    process.off('SIGINT', onSignal)
    process.off('SIGTERM', onSignal)
    await cleanup()
  }
}

if (import.meta.main) await main()
