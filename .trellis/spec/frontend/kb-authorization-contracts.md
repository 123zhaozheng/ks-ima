# Knowledge Base Authorization Frontend Contracts

## 1. Scope / Trigger

Apply this specification to knowledge base navigation and switching, the
knowledge base page, members and share-link management, share-link joining,
platform knowledge base administration, and their generated API/component/
browser tests.

## 2. Signatures

```text
src/utils/identity-client.ts                  # single generated DTO transport
src/stores/knowledge-base.ts                  # useKbStore: list/selection/refresh
src/pages/KnowledgeBase.vue                   # tree/list/preview + manage entry
src/components/KbMenuList.vue                 # switcher: list/create/join
src/components/KbManageDialog.vue             # owner panel: rename/members/share/archive
src/components/KbMembersPanel.vue             # member roles/remove/leave
src/components/KbShareLinksPanel.vue          # create/list/revoke share links
src/pages/JoinKnowledgeBase.vue               # /join/:token acceptance
src/admin/pages/KnowledgeBasesPage.vue        # role-aware registry lifecycle
tests/components/KbManagePanels.vitest.ts
tests/components/KnowledgeBasesPage.vitest.ts
tests/e2e/identity.pw.ts

bun run generate:api
bun run test:unit
bun run test:e2e
```

Knowledge base payloads use generated `components['schemas']` types.
Components call the central client and never redefine knowledge base roles,
share-link DTOs, or HTTP error shapes.

## 3. Contracts

- Roles are exactly `owner`, `editor`, `viewer`; share links confer `editor`
  or `viewer` only. Member creation flows through the share-link accept page,
  never through an add-member form; the retired invitation, group, and
  folder-ACL surfaces have no replacement controls.
- The share URL appears only in the creation response and stays visible until
  deliberately copied or dismissed; it never appears in later share-link
  lists, browser storage, logs, or client-generated URLs. Link rows expose
  only safe role/expiry/revocation metadata.
- `KbManageDialog` entry points render for owners only: rename, member role
  change (editor↔viewer), member removal, share-link lifecycle, archive, and
  delete-after-archive. Editors and viewers get read-only membership state
  plus leave.
- Member role mutations send `expectedVersion`; a 409 renders a visible
  conflict and reloads authoritative rows. The last owner sees no leave or
  removal path.
- Knowledge base switching clears scoped caches; the switcher lists owned and
  shared libraries with their role and offers create and join entries.
- UI capability checks are usability only. Viewer/nonmember/platform-role
  journeys assert API denial separately; hidden buttons are not authorization
  evidence.

## 4. Validation & Error Matrix

| Condition | Required UI/result |
|---|---|
| Session/knowledge base list pending | stable loading; no premature denial |
| Viewer opens the knowledge base page | readable tree/list/preview; no mutation controls |
| Nonmember platform admin opens a knowledge base | content request 404 |
| Member/share-link list empty | explicit empty state and available permitted action |
| Share link creation | one-time URL display; list shows only safe metadata |
| Expired/revoked link accept | safe rejection state; token never logged |
| Already-member accept | success without role demotion |
| Role save returns 409 | visible conflict and reload path; no local success |
| Membership revoked while open | clear unavailable state and no stale mutation |
| Generated Problem Details | safe typed message; no raw response/token logging |

## 5. Good / Base / Bad Cases

- Good: an owner creates a viewer share link, copies the one-time URL, and
  the panel afterward shows only role/expiry/revoke controls.
- Good: a second user opens `/join/:token`, joins as viewer, and sees content
  with every write control absent.
- Base: a viewer sees the knowledge base name and member roles but no rename,
  share-link, member-management, or archive actions.
- Bad: derive content access from `platformRoles` or a hidden menu.
- Bad: reintroduce invitation, group, or folder-ACL controls on top of the
  member role.
- Bad: call `/knowledge-bases/*` with local `Record<string,unknown>` response
  casts.

## 6. Tests Required

1. Vitest mounts the real knowledge base page and manage panels and asserts
   concrete owner/editor/viewer rows/controls/errors, not only
   `wrapper.exists()`.
2. Share-link component/client tests cover one-time URL display, safe list
   metadata, revocation, expiry rejection, idempotent accept, and 409 reload
   behavior.
3. Full Playwright uses real Python/PostgreSQL and covers all three roles,
   nonmember platform admin, share-link join, membership revoke,
   archive/delete gating, and cleanup with zero skips.
4. OpenAPI export/generation/drift, ESLint, `vue-tsc`, Bun/Vitest, and
   front/admin builds pass after any contract or component change.

## 7. Wrong vs Correct

### Wrong

```ts
if (session.user.platformRoles.includes('platform_admin')) showKbManage()
await identityClient.updateKbMemberRole(kbId, userId, { role: 'owner' })
```

Platform roles never read content, and `owner` is not an assignable role.

### Correct

```ts
type MemberRolePatchRequest = components['schemas']['MemberRolePatchRequest']
const result = await identityClient.updateKbMemberRole(kbId, userId, {
  role: 'editor',
  expectedVersion: member.version,
} satisfies MemberRolePatchRequest)
if (result.error?.status === 409) await reloadMembers()
```
