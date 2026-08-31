# Knowledge Base Authorization Contracts

## 1. Scope / Trigger

Apply this specification to knowledge base membership, share links, folder
structure, knowledge base authorization, and knowledge base lifecycle. Python
is the only mutable knowledge base authority. Platform roles never imply
content membership or folder access. The retired invitation, group, and
folder-ACL system and the legacy authorization importer are gone;
`/api/v1/internal/*` stays a terminal public 404.

## 2. Signatures

```text
GET/POST/PATCH/DELETE /api/v1/knowledge-bases/*
POST /api/v1/kb-share-links/{token}/accept
GET/POST /api/v1/admin/knowledge-bases*
POST /api/v1/admin/knowledge-bases/{id}/archive|restore
DELETE /api/v1/admin/knowledge-bases/{id}

ima.knowledge_bases, ima.kb_members, ima.kb_share_links
ima.folders, ima.folder_closure
```

Every public operation has a stable OpenAPI operation ID. Internal
authorization routes are absent from public OpenAPI and Caddy. `KbService`
owns authorization plus mutation in one transaction; API adapters do not
duplicate mutable SQL.

## 3. Contracts

- Roles are exactly `owner`, `editor`, and `viewer`; membership state is
  exactly `active`. Folder actions are `view_metadata`, `view_content`,
  `download`, `ask`, `create_child`, `edit`, `move`, and `delete`.
  `DEFAULT_ROLE_GRANTS` grants owner all actions, editor the same eight
  actions, and viewer `view_metadata`, `view_content`, `download`, and `ask`.
- Authorization is one vote from the membership role. There are no user
  groups, no folder-level ACLs, and no `knowledge_manager` role. Readers and
  writers call `require_membership` / `require_write_access`; writes need
  editor or above.
- Root folder ID equals knowledge base ID. The knowledge base row, root
  folder, closure self-row, and the creator's active `owner` membership
  commit together. Admin creation names an explicit `initialOwnerUserId`
  instead.
- Share links store a salted, peppered token digest and never the plaintext
  token; the full `{origin}/join/{token}` URL is returned only in the
  creation response. Links confer `editor` or `viewer`, may expire, and may
  be revoked. Acceptance is idempotent: an existing member keeps their
  current role and is never demoted.
- Only the owner manages the knowledge base: role changes are limited to
  editor↔viewer (`role_change_problem` rejects non-owner actors, non-share
  target roles, and owner targets), and rename/archive/restore/delete require
  the owner's active membership.
- A knowledge base always retains one owner: the last owner can neither leave
  nor be removed. Permanent deletion requires prior archival and the absence
  of folder and document dependencies; it removes share links, members,
  closure, and folders in the same transaction.
- Target folder mutations authorize the actor's knowledge base role and check
  the actual folder, not only the root. Closure, lifecycle, version, and
  audit update atomically; sibling folder names are unique per parent.
- All authorization mutations respect the maintenance write freeze
  (`_assert_writes_allowed`) and write redacted audit rows.

## 4. Validation & Error Matrix

| Condition | Required result |
|---|---|
| Platform admin without membership reads content | 404 `KB_NOT_FOUND`; no metadata/count leak |
| Missing/inactive member, account, or archived knowledge base | 404 `KB_NOT_FOUND` on content routes |
| Viewer attempts a write | 403 `KB_EDITOR_REQUIRED` |
| Non-owner changes roles or removes members | 403 `MEMBERSHIP_FORBIDDEN` |
| Role change targets the owner | 400 `OWNER_PROTECTED` |
| Stale member/folder version | 409 `VERSION_CONFLICT`; no partial mutation |
| Final-owner leave/remove races | 409 `LAST_KB_OWNER`; one owner remains |
| Revoked share link accept | 400 `SHARE_LINK_INVALID` |
| Expired share link accept | 400 `SHARE_LINK_EXPIRED` |
| Share link accept into archived knowledge base | 404 `KB_NOT_FOUND` |
| Re-accept by an existing member | Idempotent join; role never demoted |
| Duplicate sibling folder name | 409 `FOLDER_NAME_EXISTS` |
| Root move/reorder | 400 `ROOT_PROTECTED` |
| Folder delete with children/documents | 409 `FOLDER_DEPENDENCIES` |
| Archive an archived / restore an active knowledge base | 409 `KB_ARCHIVED` / `KB_ACTIVE` |
| Delete a knowledge base that is not archived | 409 `KB_NOT_ARCHIVED` |
| Delete with remaining folders/documents | 409 `KB_CONTENT_DEPENDENCY` |
| Public `/api/v1/internal/*` request | Terminal 404 at the edge; no backend mount |

## 5. Good / Base / Bad Cases

- Good: an owner creates a viewer share link; a second user accepts it, sees
  content, and every write attempt fails with `KB_EDITOR_REQUIRED`.
- Good: accepting an editor share link while already a viewer keeps the
  viewer role and returns success without mutation.
- Base: a viewer sees the knowledge base name and member roles but no
  rename, member-management, share-link, or archive controls.
- Bad: derive content access from platform roles or a hidden menu; platform
  roles never read content.
- Bad: reintroduce invitations, user groups, folder ACLs, or any per-folder
  grant table on top of the membership role.

## 6. Tests Required

1. Unit role/action matrix tests and OpenAPI/internal absence.
2. Forced PostgreSQL fresh/repeat migration with `IMA_REQUIRE_POSTGRES=1`
   and zero skips; root/membership seed, owner/editor/viewer action matrix,
   hidden reads, immediate revoke/archive, and indexed `EXPLAIN` assertions.
3. Share-link lifecycle: single-display URL, peppered digest lookup, expiry,
   revocation, idempotent accept, and never-demote.
4. Real concurrent final-owner mutations (leave/remove/role) with the
   one-owner invariant checked afterward.
5. Deep move/reorder/delete closure invariants and archive→delete dependency
   gating.
6. Contract proof that `/api/v1/internal/*` has no backend mount and the
   edge answers a terminal 404.

## 7. Wrong vs Correct

### Wrong

```python
if actor.platform_roles & {"platform_admin", "security_auditor"}:
    return folders_for(kb_id)  # platform role reads content
```

Platform roles never imply membership; this leaks content to operators.

### Correct

```python
# Reads need any active membership; writes need editor or above.
await kb_service.require_membership(actor.id, kb_id)      # 404 when absent
await kb_service.require_write_access(actor.id, kb_id)    # 403 KB_EDITOR_REQUIRED
```
