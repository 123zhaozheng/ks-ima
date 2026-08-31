# Knowledge Base Authorization Operations

Python is the authority for knowledge base memberships, folders, and share
links. Platform roles do not grant access to knowledge base content. A
platform operator must be an explicit active member to see folders or
documents.

## Initial assignment

Create a knowledge base through the member API
(`POST /api/v1/knowledge-bases`) or the admin workflow
(`POST /api/v1/admin/knowledge-bases` with an explicit `initialOwnerUserId`).
The transaction creates the knowledge base row, one root folder whose ID
equals the knowledge base ID, the closure self-row, and the active `owner`
membership. Admin-created libraries hand ownership to the named user; the
logged-in platform operator is not silently made a content member.

## Share links

Owners invite collaborators through share links, which replace the retired
email invitation flow. Each link carries a role (`editor` or `viewer`), an
optional expiry, and a salted, peppered token digest; the plaintext link
(`{origin}/join/{token}`) is returned only once, at creation. Acceptance
(`POST /api/v1/kb-share-links/{token}/accept`) is idempotent: joiners become
active members at the link role, and users who are already members are never
demoted. Revocation stops new joins immediately and never disturbs members
who already joined.

## Members

Membership has exactly three roles — `owner`, `editor`, `viewer` — and one
state, `active`. The membership role alone decides every knowledge action;
there are no user groups and no folder-level ACLs. Only the owner changes
roles (editor↔viewer only), removes members, or renames, archives, and
deletes the knowledge base. A knowledge base always keeps one owner: the last
owner can neither leave nor be removed. Permanent deletion requires prior
archival and no remaining folder or document dependencies.

## Audit

Mutation and denial events contain IDs, versions, counts, and stable reason
codes. They do not contain share tokens, document paths, display labels, or
content. No authorization path reads the dropped legacy `public` schema;
membership checks against `ima.kb_members` are the only content authority,
and the maintenance write freeze remains the generic operations gate for all
authorization mutations.
