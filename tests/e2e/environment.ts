function port(name: string, fallback: string) {
  const value = process.env[name] ?? fallback
  const parsed = Number(value)
  if (!/^\d+$/.test(value) || !Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
    throw new Error(`${name} must be a TCP port between 1 and 65535`)
  }
  return value
}

const postgresPort = port('IMA_E2E_POSTGRES_PORT', '55432')
const explicitProject = process.env.IMA_E2E_COMPOSE_PROJECT
const composeProject = explicitProject ?? (
  postgresPort === '55432' ? 'ima-identity-e2e' : `ima-identity-e2e-${postgresPort}`
)
if (!/^[a-z0-9][a-z0-9_-]*$/.test(composeProject)) {
  throw new Error('IMA_E2E_COMPOSE_PROJECT must contain only lowercase letters, digits, _ or -')
}

export const e2eEnvironment = {
  postgresPort,
  apiPort: port('IMA_E2E_API_PORT', '8787'),
  frontPort: port('IMA_E2E_FRONT_PORT', '9016'),
  composeProject,
} as const

export const frontOrigin = `http://127.0.0.1:${e2eEnvironment.frontPort}`
export const apiOrigin = `http://127.0.0.1:${e2eEnvironment.apiPort}`
