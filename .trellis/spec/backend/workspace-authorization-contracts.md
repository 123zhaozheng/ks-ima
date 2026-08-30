# Workspace Authorization Contracts

## 1. Scope / Trigger

Apply this specification to workspace membership, groups, invitations, folder
structure, normalized ACLs, folder authorization, and platform workspace
lifecycle. Python is the only mutable workspace/ACL authority. Platform roles never
imply content membership or folder access. The legacy authorization importer and
the temporary Bun/Zero authorization bridge were retired by the legacy deletion
release; `/api/v1/internal/*` stays a terminal public 404.

## 2. Signatures

```text
GET/POST/PATCH/DELETE /api/v1/workspaces/*
POST /api/v1/workspace-invitations/{token}/accept
POST /api/v1/admin/workspaces/{id}/workspace-admin-repair

ima.workspace_members, workspace_invitations
ima.workspace_groups, workspace_group_members
ima.folders, folder_closure, folder_acls, folder_acl_entries
```

Every public operation has a stable OpenAPI operation ID. Internal authorization
routes are absent from public OpenAPI and Caddy. `WorkspaceService` owns
authorization plus mutation in one transaction; API adapters do not duplicate
mutable SQL.

## 3. Contracts

- Roles are `workspace_admin`, `knowledge_manager`, `editor`, and `viewer`.
  Folder actions are `view_metadata`, `view_content`, `download`, `ask`,
  `create_child`, `edit`, `move`, `delete`, and `manage_acl`.
- Root folder ID equals workspace ID. Root, closure self-row, independent default
  ACL, and the explicitly selected initial workspace admin commit together.
- Policy joins active account/workspace/membership, ACL anchor, role/user/group
  subjects, and closure in one set-based predicate. Direct checks are membership
  tests against the same filtered set used by collection reads.
- Required actions must match the same ACL subject: `ask` also needs
  `view_content`; `download` also needs `view_metadata` and `view_content`.
  `IN(required_actions)` is insufficient; use a required-action anti-join or
  equivalent relational division.
- ACL replacement validates actions per `(subject_type,subject_id)`, requires a
  valid active workspace subject, uses an expected version, and keeps an
  administrable independent ACL. ACL reads/preview require `manage_acl`.
- Target folder mutations authorize the actual source/destination/parent action,
  not only the workspace root. Closure, anchors, lifecycle, compatibility state,
  and audit update atomically.
- A workspace always retains one active workspace admin under concurrent role,
  disable, leave, and remove operations. Platform repair uses the same advisory
  lock but grants no folder read.
- No authorization path reads or falls back to the dropped legacy `public`
  schema; workspace deletion checks only `ima` content dependencies.

## 4. Validation & Error Matrix

| Condition | Required result |
|---|---|
| Platform admin without membership reads content | 404; no metadata/count leak |
| Missing/inactive member, account, or workspace | 404 on content routes |
| Missing requested/dependent grant on same subject | denied |
| Stale member/folder/ACL version | 409; no partial mutation |
| Move to self/descendant/cross-workspace | 400/409; closure unchanged |
| Final active workspace-admin mutation races | one mutation fails; one admin remains |
| ACL subject belongs to another workspace | 400 |
| SMTP disabled | manual link returned once; safe pending metadata later |
| Invitation expired/revoked/reused/wrong user | rejected atomically |
| Archived workspace has content dependency | permanent delete returns 409 |
| Public `/api/v1/internal/*` request | Terminal 404 at the edge; no backend mount |

## 5. Good / Base / Bad Cases

- Good: a group has `ask` plus `view_content`; the same group satisfies both and
  the folder appears in direct and list checks.
- Good: moving an inherited subtree changes closure and anchors in one commit;
  an independent descendant keeps its own anchor.
- Bad: combine `ask` from a user grant with `view_content` from a role grant.
- Bad: authorize rename/delete on the root and mutate an inaccessible child.
- Bad: reintroduce any read or fallback against the dropped legacy `public`
  authorization tables.

## 6. Tests Required

1. Unit role/action/dependency tests and OpenAPI/internal absence.
2. Forced PostgreSQL fresh/repeat migration with `IMA_REQUIRE_POSTGRES=1` and
   zero skips; root/ACL seed, role/group/user matrix, hidden reads, immediate
   revoke/archive, and indexed `EXPLAIN` assertions.
3. Real concurrent final-admin mutations and single-use invitations.
4. Deep move/reorder/trash/restore/delete closure and anchor invariants.
5. Contract proof that `/api/v1/internal/*` has no backend mount and the edge
   answers a terminal 404.

## 7. Wrong vs Correct

### Wrong

```sql
JOIN folder_acl_entries e ON e.action IN (:ask, :view_content)
```

This accepts either action and may combine unrelated principals.

### Correct

```sql
WHERE NOT EXISTS (
  SELECT 1 FROM required_actions required
  WHERE NOT EXISTS (
    SELECT 1 FROM folder_acl_entries grant_row
    WHERE grant_row.acl_id = folder.acl_anchor_id
      AND grant_row.subject_type = matched_subject.type
      AND grant_row.subject_id = matched_subject.id
      AND grant_row.action = required.action
  )
)
```
