import { defineConfig, devices } from '@playwright/test'
import { frontOrigin } from './tests/e2e/environment'

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.pw.ts',
  globalSetup: './tests/e2e/global-setup.ts',
  fullyParallel: false,
  reporter: [['list']],
  use: {
    baseURL: frontOrigin,
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } },
  ],
})
