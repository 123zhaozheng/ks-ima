import { fileURLToPath } from 'node:url'
import { join, dirname } from 'node:path'
import type { Config } from 'i18n-pro'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

export default {
  funcName: 't',
  // entry: join(__dirname, './src/'),
  // fileRegExp: /\.[jt]s$/,
  input: [
    'src/**/*.{js,ts,vue}',
  ],
  output: {
    path: join(__dirname, './i18n/'),
  },
  translator: 'googlex',
  googlexConfig: {
    from: 'en',
    to: ['zh-CN', 'zh-TW'],
    codeLocaleMap: {
      en: 'en-US',
    },
    // proxy: 'http://127.0.0.1:7997',
  },
} satisfies Config
