import { spawn, type ChildProcess } from 'node:child_process'
import { promisify } from 'node:util'
import { execFile } from 'node:child_process'
import { request } from '@playwright/test'
import { apiOrigin, e2eEnvironment, frontOrigin } from './environment'

const exec = promisify(execFile)
const project = e2eEnvironment.composeProject
const compose = ['compose', '-p', project, '-f', 'backend/tests/integration/identity-compose.yml']
let api: ChildProcess | undefined
let front: ChildProcess | undefined

function spawnService(command: string, args: string[], env: NodeJS.ProcessEnv) {
  return spawn(command, args, {
    cwd: process.cwd(),
    env,
    shell: process.platform === 'win32',
    stdio: 'ignore',
  })
}

async function stopService(process: ChildProcess | undefined) {
  if (!process?.pid) return
  if (globalThis.process.platform === 'win32') {
    await exec('taskkill', ['/T', '/F', '/PID', String(process.pid)]).catch(() => undefined)
    return
  }
  process.kill('SIGTERM')
}

async function waitFor(url: string) {
  for (let i = 0; i < 60; i++) {
    try {
      const context = await request.newContext()
      const response = await context.get(url)
      await context.dispose()
      if (response.ok() || response.status() < 500) return
    } catch { /* startup retry */ }
    await new Promise(resolve => setTimeout(resolve, 500))
  }
  throw new Error(`Timed out waiting for ${url}`)
}

export default async function globalSetup() {
  const env = {
    ...process.env,
    IMA_TEST_POSTGRES_PORT: e2eEnvironment.postgresPort,
    IMA_DATABASE_URL: `postgresql+asyncpg://postgres:identity-gate-password@127.0.0.1:${e2eEnvironment.postgresPort}/app`,
    IMA_E2E_API_PORT: e2eEnvironment.apiPort,
    IMA_PUBLIC_ORIGIN: frontOrigin,
    IMA_CORS_ORIGINS: frontOrigin,
    IMA_ENVIRONMENT: 'test',
    IMA_TOTP_ENCRYPTION_KEY: 'e2e-totp-key',
    IMA_TOKEN_PEPPER: 'e2e-token-pepper',
    IMA_SESSION_PEPPER: 'e2e-session-pepper',
    PYTHONWARNINGS: 'error',
  }
  try {
    await exec('docker', [...compose, 'up', '-d', '--wait'], { cwd: process.cwd(), env })
    await exec('uv', ['run', 'ima', 'migrate'], { cwd: 'backend', env })
    await exec('uv', ['run', 'python', 'scripts/seed_identity_e2e.py'], { cwd: 'backend', env })
    for (const projectName of ['chromium', 'mobile-chromium']) {
      await exec('uv', [
        'run', 'ima', 'register-mcp-client',
        '--client-id', `e2e-oauth-${projectName}`,
        '--client-name', `E2E OAuth Client (${projectName})`,
        '--client-type', 'public',
        '--app-type', 'native',
        '--auth-method', 'none',
        '--redirect-uri', `${frontOrigin}/oauth/callback/${projectName}`,
        '--operator-id', 'e2e-super-id',
      ], { cwd: 'backend', env })
    }
    api = spawn('uv', ['run', 'python', '-c', `import asyncio; asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); import uvicorn; uvicorn.run('ima.main:app',host='127.0.0.1',port=${e2eEnvironment.apiPort},ws='none')`], { cwd: 'backend', env, stdio: 'inherit' })
    await waitFor(`${apiOrigin}/health/live`)
    await exec('bun', ['run', 'build'], { cwd: process.cwd(), env })
    front = spawnService('bun', ['tests/e2e/static-server.ts', 'dist/pwa', e2eEnvironment.frontPort], env)
    await waitFor(`${frontOrigin}/auth/sign-in`)
  } catch (error) {
    await Promise.all([stopService(api), stopService(front)])
    await exec('docker', [...compose, 'down', '-v'], { cwd: process.cwd(), env }).catch(() => undefined)
    throw error
  }
  return async () => {
    await Promise.all([stopService(api), stopService(front)])
    await exec('docker', [...compose, 'down', '-v'], { cwd: process.cwd(), env })
  }
}
