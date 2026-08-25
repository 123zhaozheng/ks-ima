export const FRONT_URL = process.env.FRONT_URL!
export const ADMIN_URL = process.env.ADMIN_URL!
export const DATABASE_URL = process.env.DATABASE_URL!
export const S3_ENDPOINT = process.env.S3_ENDPOINT!
export const S3_BUCKET = process.env.S3_BUCKET!
export const S3_ACCESS_KEY_ID = process.env.S3_ACCESS_KEY_ID!
export const S3_SECRET_ACCESS_KEY = process.env.S3_SECRET_ACCESS_KEY!
export const { SMTP_USER, SMTP_PASSWORD, SMTP_HOST, SMTP_FROM } = process.env
export const SMTP_PORT = process.env.SMTP_PORT ? parseInt(process.env.SMTP_PORT) : undefined
export const SMTP_SECURE = process.env.SMTP_SECURE === 'true'
export const SITE_NAME = process.env.SITE_NAME!
export const REQUIRE_EMAIL_VERIFICATION = false
export const PYTHON_API_INTERNAL_URL = process.env.PYTHON_API_INTERNAL_URL
export const IMA_BRIDGE_TOKEN = process.env.IMA_BRIDGE_TOKEN
export const IMA_BRIDGE_TIMEOUT_MS = process.env.IMA_BRIDGE_TIMEOUT_MS ? Number(process.env.IMA_BRIDGE_TIMEOUT_MS) : 1500

export function privatePythonOrigin(value = process.env.PYTHON_API_INTERNAL_URL) {
  if (!value) return null
  try {
    const url = new URL(value)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) return null
    const privateHost = url.hostname === 'localhost' || url.hostname === 'api' || url.hostname === 'python' || url.hostname === 'ima-api' || url.hostname.endsWith('.local') || url.hostname.endsWith('.internal') || /^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(url.hostname)
    return privateHost ? url.origin : null
  } catch {
    return null
  }
}
