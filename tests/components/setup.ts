import { config } from '@vue/test-utils'

globalThis.fetch = (() => Promise.resolve(new Response('{}', { status: 200 }))) as unknown as typeof fetch

config.global.stubs = {
  'q-page-container': { template: '<div><slot /></div>' },
  'q-page': { template: '<div><slot /></div>' },
  'q-card': { template: '<div><slot /></div>' },
  'q-card-section': { template: '<div><slot /></div>' },
  'q-card-actions': { template: '<div><slot /></div>' },
  'q-btn': { props: { label: { type: String, default: '' } }, template: '<button><slot />{{ label }}</button>' },
  'q-input': { template: '<input />' },
  'q-list': { template: '<div><slot /></div>' },
  'q-item': { template: '<div><slot /></div>' },
  'q-item-section': { template: '<div><slot /></div>' },
  'q-item-label': { template: '<div><slot /></div>' },
  'q-space': { template: '<span />' },
  'q-banner': { template: '<div><slot /><slot name="action" /></div>' },
  'q-badge': { template: '<span><slot /></span>' },
  'q-icon': { template: '<span><slot /></span>' },
  'q-checkbox': { props: ['label'], template: '<label>{{ label }}<input type="checkbox" /></label>' },
  'q-table': { template: '<div><slot /></div>' },
  'q-td': { template: '<div><slot /></div>' },
  'q-dialog': { template: '<div><slot /></div>' },
  'q-toggle': { template: '<input type="checkbox" />' },
  'q-separator': { template: '<hr />' },
}
config.global.provide = { _q_: { notify: () => undefined, dialog: () => undefined } }
