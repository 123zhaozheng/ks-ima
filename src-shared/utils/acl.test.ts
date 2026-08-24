import { describe, expect, test } from 'bun:test'
import { canAction, parseFolderAcl, personalAcl, resolveActions } from './acl'

describe('folder ACL', () => {
  test('uses role defaults when inheritance is not broken', () => {
    expect([...resolveActions('guest', 'guest-1', [{}, {}])]).toEqual(['view', 'ask'])
    expect(canAction('member', 'member-1', [{}, {}], 'edit')).toBe(true)
  })

  test('uses the nearest inheritance break only', () => {
    const parent = { acl: { inherit: false, aces: [{ principalType: 'role', principalId: 'member', actions: ['view'] }] } }
    const grandparent = { acl: { inherit: false, aces: [{ principalType: 'role', principalId: 'member', actions: ['edit'] }] } }
    expect(canAction('member', 'member-1', [{}, parent, grandparent], 'view')).toBe(true)
    expect(canAction('member', 'member-1', [{}, parent, grandparent], 'edit')).toBe(false)
  })

  test('owner cannot be locked out', () => {
    const denied = { acl: { inherit: false, aces: [] } }
    expect(canAction('owner', 'owner-1', [denied], 'manage')).toBe(true)
  })

  test('ask permission also requires view', () => {
    const askOnly = {
      acl: {
        inherit: false,
        aces: [{ principalType: 'user', principalId: 'u1', actions: ['ask'] }],
      },
    }
    expect(canAction('guest', 'u1', [askOnly], 'ask')).toBe(false)
  })

  test('drops malformed principals and actions', () => {
    const acl = parseFolderAcl({
      acl: {
        inherit: false,
        aces: [
          { principalType: 'user', principalId: 'u1', actions: ['view', 'root'] },
          { principalType: 'group', principalId: 'g1', actions: ['view'] },
        ],
      },
    })
    expect(acl?.aces).toEqual([{ principalType: 'user', principalId: 'u1', actions: ['view'] }])
  })

  test('personal ACL grants every action only to its owner', () => {
    const conf = { acl: personalAcl('u1') }
    expect(canAction('guest', 'u1', [conf], 'manage')).toBe(true)
    expect(canAction('admin', 'u2', [conf], 'view')).toBe(false)
  })
})
