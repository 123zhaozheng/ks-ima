import { spawn, type ChildProcess } from 'node:child_process'
import { promisify } from 'node:util'
import { execFile } from 'node:child_process'
import { request } from '@playwright/test'

const exec = promisify(execFile)
const project = 'ima-identity-e2e'
const compose = ['compose', '-p', project, '-f', 'backend/tests/integration/identity-compose.yml']
let api: ChildProcess | undefined
let front: ChildProcess | undefined
let admin: ChildProcess | undefined

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
    IMA_DATABASE_URL: 'postgresql+asyncpg://postgres:identity-gate-password@127.0.0.1:55432/app',
    IMA_PUBLIC_ORIGIN: 'http://127.0.0.1:9016',
    IMA_CORS_ORIGINS: 'http://127.0.0.1:9016,http://127.0.0.1:9017',
    IMA_ENVIRONMENT: 'test',
    IMA_TOTP_ENCRYPTION_KEY: 'e2e-totp-key',
    IMA_TOKEN_PEPPER: 'e2e-token-pepper',
    IMA_SESSION_PEPPER: 'e2e-session-pepper',
    PYTHONWARNINGS: 'error',
  }
  try {
    await exec('docker', [...compose, 'up', '-d', '--wait'], { cwd: process.cwd() })
    await exec('uv', ['run', 'ima', 'migrate'], { cwd: 'backend', env })
    await exec('uv', ['run', 'python', 'scripts/seed_identity_e2e.py'], { cwd: 'backend', env })
    api = spawn('uv', ['run', 'python', '-c', "import asyncio; asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()); import uvicorn; uvicorn.run('ima.main:app',host='127.0.0.1',port=8787,ws='none')"], { cwd: 'backend', env, stdio: 'inherit' })
    await waitFor('http://127.0.0.1:8787/health/live')
    await exec('bun', ['run', 'build:front'], { cwd: process.cwd(), env })
    await exec('bun', ['run', 'build:admin'], { cwd: process.cwd(), env })
    front = spawnService('bun', ['tests/e2e/static-server.ts', 'dist/pwa', '9016'], env)
    admin = spawnService('bun', ['tests/e2e/static-server.ts', 'dist/spa', '9017'], env)
    await Promise.all([
      waitFor('http://127.0.0.1:9016/auth/sign-in'),
      waitFor('http://127.0.0.1:9017/auth/sign-in'),
    ])
  } catch (error) {
    await Promise.all([stopService(api), stopService(front), stopService(admin)])
    await exec('docker', [...compose, 'down', '-v'], { cwd: process.cwd() }).catch(() => undefined)
    throw error
  }
  return async () => {
    await Promise.all([stopService(api), stopService(front), stopService(admin)])
    await exec('docker', [...compose, 'down', '-v'], { cwd: process.cwd() })
  }
}
