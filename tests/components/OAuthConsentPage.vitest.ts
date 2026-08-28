import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import OAuthConsentPage from '../../src/pages/OAuthConsentPage.vue'

const mocks = vi.hoisted(() => ({
  sessionState: { isPending: false, error: null, data: { user: { id: 'u1' } } as { user: { id: string } } | null },
  route: {
    fullPath: '/oauth/consent?client_id=desktop&state=state-1&code_challenge=challenge',
    query: { client_id: 'desktop', state: 'state-1', code_challenge: 'challenge' } as Record<string, string>,
  },
}))
vi.mock('src/utils/identity-client', async () => {
  const { ref } = await import('vue')
  return {
    session: ref(mocks.sessionState),
    identityClient: {
      previewOAuthConsent: vi.fn(() => Promise.resolve({
        data: {
          clientId: 'desktop',
          clientName: 'Desktop Agent',
          redirectUri: 'http://localhost:8765/callback',
          resource: 'https://ima.example/mcp',
          workspaceId: 'workspace-1',
          folderRootId: 'folder-1',
          scopes: ['mcp:knowledge:read', 'mcp:knowledge:write'],
          writeAccess: true,
          expiresAt: '2030-01-01T00:00:00Z',
          refreshEnabled: true,
          consentRequired: true,
        },
      })),
      submitOAuthConsent: vi.fn(() => Promise.resolve({ data: {} })),
    },
  }
})
vi.mock('vue-router', () => ({ useRoute: () => mocks.route }))

describe('OAuthConsentPage', () => {
  beforeEach(() => {
    mocks.sessionState.data = { user: { id: 'u1' } }
    mocks.route.fullPath = '/oauth/consent?client_id=desktop&state=state-1&code_challenge=challenge'
    mocks.route.query = { client_id: 'desktop', state: 'state-1', code_challenge: 'challenge' }
  })

  test('renders exact grant boundary and write warning', async () => {
    const wrapper = mount(OAuthConsentPage)
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Desktop Agent')
    expect(wrapper.text()).toContain('https://ima.example/mcp')
    expect(wrapper.text()).toContain('workspace-1')
    expect(wrapper.text()).toContain('folder-1')
    expect(wrapper.text()).toContain('knowledge · write')
    expect(wrapper.text()).toContain('This connection can change knowledge content.')
    expect(wrapper.text()).not.toContain('challenge')
  })

  test('renders expired-session state without grant actions', async () => {
    mocks.sessionState.data = null
    const wrapper = mount(OAuthConsentPage)
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Your session expired')
    expect(wrapper.text()).not.toContain('Approve')
  })

  test('offers local sign-in when recent authentication is required', async () => {
    mocks.route.fullPath += '&ui_error=recent_auth'
    mocks.route.query.ui_error = 'recent_auth'
    const wrapper = mount(OAuthConsentPage)
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Sign in again to approve this connection.')
    expect(wrapper.text()).toContain('Sign in')
    expect(wrapper.find('button').exists()).toBe(true)
  })
})
