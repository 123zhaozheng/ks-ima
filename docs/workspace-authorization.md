# Workspace Authorization Operations

Python is the authority for workspace memberships, groups, folders, and ACLs.
Platform roles do not grant access to workspace content. A platform operator
must be an explicit active workspace member to see folders or ACLs.

## Initial assignment

Create a workspace through the Python platform API or `ima` admin workflow. The
transaction creates one root folder, its independent ACL, closure self-row, and
the selected active `workspace_admin`. If an administrator was removed, use the
narrow `POST /api/v1/admin/workspaces/{workspace_id}/workspace-admin-repair`
operation with a recent authenticated platform session. This operation only
repairs membership and does not expose content.

## Migration

Run the additive migrations with `ima migrate`, then inspect the source without
changing it:

```text
ima migrate-legacy-authorization plan
ima migrate-legacy-authorization apply
ima migrate-legacy-authorization verify
ima migrate-legacy-authorization report
```

Apply commits each workspace, member, and folder checkpoint separately. Cycles,
cross-workspace parents, unknown roles, missing users, and malformed records are
reported by stable source ID and are never guessed into the target tree. A
failed apply can be rerun after the source or target issue is corrected.

## Rollback

Keep the pre-cutover database snapshot and a read-only legacy authorization
export until the knowledge-tree migration removes its remaining Zero readers.
Rollback restores that snapshot and routes the old artifact; it does not
reverse-sync partially changed target state into legacy tables.

## Audit and compatibility

Mutation and denial events contain IDs, versions, counts, and stable reason
codes. They do not contain names, paths, display labels, invitation tokens, or
content. The temporary Bun/Zero compatibility reader is target-derived and
fail-closed; its deletion owner is `knowledge-tree-vue-api`.

The retained compatibility callers are deliberately enumerated here (historical:
all of them were deleted with the Bun/Zero subtree in the legacy deletion
release; this list is closure evidence, not live architecture):

- `src-server/utils/permissions.ts`: Bun document/search/RAG and connector/MCP
  reads that still query `public.entity`; it calls `/internal/authorization`
  with a bounded 500-row batch and `AbortSignal.timeout`, and denies on bridge
  timeout, malformed responses, or an unavailable target. The target result is
  authoritative whenever the folder exists. Removal owner:
  `knowledge-tree-vue-api`, after its document/search routes use the Python
  folder API.
- `src-server/zero/mutators.ts`: the live Zero mutation boundary rejects ACL
  JSON writes and delegates legacy folder checks to the target-derived bridge.
  It remains only until the knowledge-tree route cutover; the same child owns
  deleting the mutator wrappers and `entityPermission` joins.
- `src-shared/utils/acl.ts`, `src-shared/table-permission.ts`, and the Zero
  permission relations in `src-shared/schema.gen.ts`: read-only fallback for
  legacy records when the target bridge explicitly reports `source=legacy`.
  They are covered by bridge fail-closed/equivalence tests and are deleted by
  `knowledge-tree-vue-api` once no legacy record remains routed through Bun.

No retained compatibility path writes a legacy ACL or treats a platform role as
content authority. The pre-cutover snapshot and read-only export are the
rollback owner for this bounded window.
