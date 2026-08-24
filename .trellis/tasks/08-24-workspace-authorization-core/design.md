# Workspace Authorization Core Design

## 1. Architecture And Authority

Python owns workspace membership, groups, folder structure, ACL mutation, and
authorization decisions. Vue uses generated REST contracts. Platform registry
authorization remains separate from workspace/content authorization.

```text
Vue workspace administration
  -> generated /api/v1/workspaces/* client + cookie/CSRF
  -> workspace application services
  -> canonical policy service/query builders
  -> ima workspace/member/group/folder/ACL tables
  -> append-only audit

Legacy Bun/Zero knowledge path (bounded coexistence only)
  -> named compatibility adapter/projection derived from target ACL state
  -> fail closed and equivalence checked
  -> removed by knowledge-tree-vue-api
```

No platform capability is injected into a policy subject. A platform operator
uses separate `/api/v1/admin/workspaces/*` metadata/repair operations. Content
routes resolve only an explicit active membership.

## 2. Module Boundaries

Target modules follow the existing application/infrastructure/API split:

```text
backend/src/ima/domain/authorization.py
backend/src/ima/application/workspaces.py
backend/src/ima/application/authorization.py
backend/src/ima/application/workspace_migration.py
backend/src/ima/infrastructure/db/authorization.py
backend/src/ima/api/v1/workspaces.py
backend/src/ima/api/v1/workspace_contracts.py
backend/src/ima/api/internal/authorization_bridge.py
```

Domain and application modules do not import FastAPI or API DTOs. API adapters
map domain failures to existing RFC 9457 Problem Details. SQLAlchemy async
transactions own runtime data access; migration/CLI paths use the established
psycopg/Alembic conventions. Do not add a generic repository abstraction that
only wraps `execute`.

## 3. Data Model

All target objects live in `ima`, use UTC `timestamptz`, explicit check/foreign
key constraints, and monotonic integer versions for optimistic mutation.

### 3.1 Workspace Subjects

- `workspace_members`: `(workspace_id,user_id)` unique, role, state, version,
  grantor, joined/invited/disabled/updated metadata. Active content authority
  requires active user, workspace, and membership.
- `workspace_invitations`: UUID, workspace, invited existing user, target role,
  token digest, inviter, expiry/accepted/revoked timestamps. Only a digest is
  stored. SMTP-disabled issuance returns a manual-delivery state and the raw
  bound link once; later reads expose only safe pending metadata.
- `workspace_groups`: UUID, workspace, normalized/display name, version,
  creator/timestamps; name unique per workspace among active groups.
- `workspace_group_members`: `(group_id,user_id)` unique plus grantor/time; a
  composite constraint or locked service proves the user is active in the same
  workspace.

The last-active-admin invariant uses a workspace-keyed PostgreSQL advisory lock
plus locked active-admin rows in the same transaction as the mutation and audit.
The narrow platform repair service acquires the same lock and may only grant an
active user `workspace_admin`.

### 3.2 Folder Structure

- `folders`: preserved string ID, workspace, nullable parent, name and normalized
  name, order key, lifecycle, version, root marker, `acl_anchor_id`, creator and
  lifecycle timestamps. The root ID equals the workspace ID for legacy identity
  preservation and has a null parent.
- `folder_closure`: `(workspace_id,ancestor_id,descendant_id)` primary key with
  non-negative depth. Self rows have depth zero.
- `folder_acls`: UUID, unique folder, version, created/updated actors/timestamps.
  Presence means independent; every root has one.
- `folder_acl_entries`: `(acl_id,subject_type,subject_id,action)` primary key.
  One normalized action per row keeps predicates/indexes simple. Subject type is
  role/group/user in this child; a later migration adds service principal after
  that table exists.

Critical constraints/indexes include workspace+parent+normalized active sibling
name, workspace+anchor, closure ancestor/descendant, ACL folder, ACL subject+
action, member workspace/state/user, and group workspace/name. Root parent is
null, root cannot be trashed, and application services enforce exactly one root.

## 4. Default ACL And Invariants

The root ACL is seeded transactionally:

| Role | Grants |
|---|---|
| `workspace_admin` | all nine actions |
| `knowledge_manager` | all nine actions |
| `editor` | all except `manage_acl` |
| `viewer` | metadata, content, download, ask |

No workspace role is an unconditional bypass. Removing a role grant at an
independent ACL can restrict even a workspace admin's content access; member and
group administration remains a workspace-role capability separate from folder
ACL. ACL mutation itself requires `manage_acl` on the folder, except the narrow
platform last-admin repair which cannot mutate ACLs.

Effective action normalization applies these implications at write and decision
time:

```text
ask -> requires view_content
download -> requires view_metadata + view_content
citation -> requires view_metadata + view_content (derived operation)
```

Invalid combinations are rejected rather than silently broadened. There is no
deny row, wildcard subject, platform-role subject, or owner bypass.

## 5. Canonical Policy Query

`SubjectContext` contains actor kind, user ID, workspace ID, active membership
role, group IDs, and later delegated/service constraints. Human resolution is:

```text
active user + active workspace + active membership
  JOIN folder.acl_anchor_id
  JOIN folder_acl_entries
  WHERE (role match OR user match OR group membership match)
    AND requested action/dependency grants match
```

The infrastructure policy module exposes reusable SQLAlchemy expressions/CTEs:

- `accessible_folder_ids(subject, action, optional_root)`;
- `folder_decision(subject, folder_id, action)` using the same CTE;
- `accessible_subtree(subject, ancestor_id, action)` via closure;
- extension composition points that later join a document's `acl_anchor_id`, a
  chunk's document, and OAuth/service root/action restrictions.

Single checks must be membership in the filtered set, never a separate Python
if/else policy. Internal decisions use stable reasons such as
`inactive_actor`, `inactive_workspace`, `missing_membership`, `outside_scope`,
and `missing_grant`; public hidden resources always map to `FOLDER_NOT_FOUND`.
No cache is part of the baseline.

## 6. Folder Transactions

Creation inserts the folder, self closure row, ancestor closure rows, inherited
anchor, audit, and compatibility projection in one database transaction.

Moving a subtree:

1. lock source, destination, affected closure rows, and relevant ACL rows;
2. authorize `move` on source and `create_child` on destination;
3. reject root, cross-workspace, self/descendant destination, stale version,
   lifecycle mismatch, and active sibling conflict;
4. delete old external ancestor links and insert new ancestor x subtree links;
5. update parent/order/version and recompute anchors only for inherited nodes
   whose nearest independent ancestor changed;
6. update the bounded legacy projection and append a safe audit event;
7. commit all effects together.

Trash records original parent/order for deterministic restore. Restore requires
an authorized active destination when the original parent is unavailable.
Permanent deletion requires trashed state and explicit `delete`, then refuses
unknown document/job dependencies; it never silently cascades future data.

## 7. ACL Transactions

- `break inheritance`: lock folder/subtree, read effective entries from current
  anchor, create the independent ACL with copied entries, apply requested edits,
  increment version, repoint the folder and inherited descendants.
- `replace independent ACL`: require expected version and `manage_acl`, validate
  subjects belong to the workspace, replace normalized entries atomically, and
  retain a non-empty administrable policy per the approved action rules.
- `resume inheritance`: refuse root, delete the independent ACL after repointing
  the folder/inherited descendants to the nearest parent anchor.
- `preview`: execute canonical filtered queries as the selected active member;
  return visible folder IDs/names/paths only, effective actions, and the visible
  ACL source. Never return hidden ancestors or negative decision explanations.

Membership/group/ACL changes share a transaction with compatibility expansion
and audit so the next decision observes the new authority.

## 8. Public API Contracts

Representative stable operations (exact DTO names come from OpenAPI):

```text
GET  /api/v1/workspaces
GET  /api/v1/workspaces/{workspace_id}
GET/POST/PATCH/DELETE /api/v1/workspaces/{workspace_id}/members/*
GET/POST/DELETE       /api/v1/workspaces/{workspace_id}/invitations/*
POST                  /api/v1/workspace-invitations/{token}/accept
GET/POST/PATCH/DELETE /api/v1/workspaces/{workspace_id}/groups/*
PUT/DELETE            /api/v1/workspaces/{workspace_id}/groups/{id}/members/{user_id}
GET/POST               /api/v1/workspaces/{workspace_id}/folders
GET/PATCH/DELETE       /api/v1/workspaces/{workspace_id}/folders/{folder_id}
POST                   /api/v1/workspaces/{workspace_id}/folders/{folder_id}/move|trash|restore
GET/PUT/DELETE         /api/v1/workspaces/{workspace_id}/folders/{folder_id}/acl
GET                    /api/v1/workspaces/{workspace_id}/acl-subjects
POST                   /api/v1/workspaces/{workspace_id}/permission-preview
POST /api/v1/admin/workspaces/{workspace_id}/workspace-admin-repair
```

Unsafe operations require exact Origin, active session, CSRF, expected version
where mutable, and recent auth for platform repair/permanent deletion. List APIs
use stable cursor pagination where the result can be large. Bulk ACL writes are
bounded and use a single request/version, not one request per checkbox.

## 9. Vue Information Architecture

The existing workspace settings route becomes generated-API based with tabs for
Members, Groups, and Directory permissions. Members/groups use dense tables,
search, role menus, state badges, and explicit confirmations. Directory
permissions use an unframed tree plus detail pane/dialog: inheritance toggle,
role/group/user subject picker, action checkbox grid, effective source, preview,
save conflict recovery, and accessible keyboard/focus states.

No plan/member-limit, owner, price/quota, provider/model, or infrastructure
control appears. Controls are hidden/disabled from generated capability data for
usability, while API tests prove rejection independently.

## 10. Legacy Slice Migration And Coexistence

Add `ima migrate-legacy-authorization plan|apply|verify|report` with per-record
checkpoints. It imports members, the folder portion of `entity`, closure, and
valid JSON ACLs after detecting roots, cycles, missing parents/users, duplicate
members, cross-workspace edges, and malformed subjects/actions. It never guesses
an ACL; invalid records block verify with safe IDs/reasons.

Until `knowledge-tree-vue-api` moves the remaining Zero knowledge readers:

- target `ima` rows are authoritative for new membership/group/folder/ACL writes;
- one named compatibility adapter expands group grants for legacy consumers and
  projects required folder/permission state transactionally;
- legacy ACL mutation endpoints are removed or routed through Python;
- the existing legacy policy engine remains only where a live Zero subscription
  or Bun document/search/RAG consumer cannot yet query target data;
- action-by-action equivalence and fail-closed tests gate every release;
- metrics count compatibility decisions/projection failures;
- child 5 deletes the projection, JSON ACL, SQL functions/triggers,
  `entityPermission`, TS policy helpers, and Zero permission relations after its
  route cutover.

This is a bounded strangler adapter, not an unnamed permanent dual write. No two
editable ACL sources exist.

## 11. Audit, Privacy, And Observability

Audit action, actor ID, workspace/folder/group/member IDs, result, safe reason,
version, and affected counts. Exclude names, paths, email/display labels, token
material, ACL display labels, and content. Metrics cover policy latency/denials,
last-admin conflicts, closure/anchor mutation failures, migration counts,
compatibility mismatches, and projection failures without high-cardinality
resource labels.

## 12. Rollout And Rollback

1. Apply additive target migration and import on a disposable production-shaped
   copy; verify closure, anchors, role mapping, ACL equivalence, and plans.
2. Deploy Python APIs/internal adapter and generated frontend behind exact Caddy
   routes; keep legacy reads available.
3. Switch workspace/member/group/folder/ACL writes to Python, monitor mismatch
   and policy metrics, then remove replaced mutation/UI code.
4. Keep a read-only legacy authorization export and pre-cutover DB/deployment
   snapshot until the knowledge-tree child closes the compatibility window.

Rollback before that window closes routes writes/UI to the prior artifact and
restores the database snapshot/export. Do not attempt reverse dual writes from
partially changed authority. Migration downgrade refuses destructive rollback
when target-only membership/group/folder mutations exist unless the operator
explicitly restores the checkpoint.

## 13. Trade-offs

- Closure plus anchors adds transactional move work, but makes authorization and
  subtree filters set-based and predictable for deep trees.
- Grant-only ACLs cannot express a deny exception beneath a broader user/group
  grant; breaking inheritance gives a simpler deterministic restriction model.
- An uncached policy baseline favors immediate revocation and correctness.
  Caching is deferred until invalidation can be proven rather than assumed.
- The bounded compatibility projection is temporary complexity required by the
  approved strangler order. Its hard deletion owner prevents it from becoming a
  second permanent policy system.
