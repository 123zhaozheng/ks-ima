"""Knowledge tree service; authorization is knowledge base membership."""

# SQL remains readable as complete statements.
# ruff: noqa: E501

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ima.application.maintenance import assert_mutation_allowed
from ima.application.mcp_contracts import McpActor
from ima.domain.authorization import KbAction, KbRole, role_allows
from ima.domain.knowledge import (
    ListingCursor,
    markdown_digest,
    normalize_name,
    safe_metadata,
)
from ima.infrastructure.tasks.service import JobService


def now() -> datetime:
    return datetime.now(UTC)


class KnowledgeError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code, self.code, self.detail = status_code, code, detail


async def kb_membership(conn: AsyncConnection, user_id: str, kb_id: str) -> tuple[str, str] | None:
    """Active membership role and knowledge base name for one user, or None.

    The member role is the single authorization decision for every knowledge
    action; folder-level visibility no longer exists.
    """
    row = (
        (
            await conn.execute(
                text(
                    """SELECT m.role,kb.name FROM ima.kb_members m
                    JOIN ima.knowledge_bases kb ON kb.id=m.kb_id AND kb.is_active
                    JOIN ima.users u ON u.id=m.user_id AND u.is_active
                    WHERE m.kb_id=:kb AND m.user_id=:user AND m.state='active'"""
                ),
                {"kb": kb_id, "user": user_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return str(row["role"]), str(row["name"])


async def effective_user_id(conn: AsyncConnection, actor: str | McpActor) -> str | None:
    """Resolve the human identity behind an interactive or delegated actor.

    Interactive actors are their own user; service principals act through the
    membership of the user who owns them.
    """
    if not isinstance(actor, McpActor):
        return actor
    if actor.actor_type == "human":
        return actor.user_id
    owner = await conn.scalar(
        text(
            "SELECT owner_user_id FROM ima.mcp_service_principals WHERE id=CAST(:principal AS uuid)"
        ),
        {"principal": actor.principal_id},
    )
    return str(owner) if owner else None


def role_permits(role: str | None, action: KbAction) -> bool:
    """Whether a stored membership role grants the requested knowledge action."""
    if role is None:
        return False
    try:
        return role_allows(KbRole(role), action)
    except ValueError:
        return False


class KnowledgeService:
    def __init__(self, engine: AsyncEngine, jobs: JobService) -> None:
        self.engine = engine
        self.jobs = jobs

    async def _folder(self, conn: AsyncConnection, folder_id: str) -> dict[str, Any]:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT id,kb_id,children_version,lifecycle FROM ima.folders WHERE id=:id"
                    ),
                    {"id": folder_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise KnowledgeError(404, "FOLDER_NOT_FOUND", "Folder not found")
        return dict(row)

    async def _document(
        self, conn: AsyncConnection, document_id: UUID, *, for_update: bool = False
    ) -> dict[str, Any]:
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT d.*,f.kb_id AS folder_kb_id FROM ima.documents d
              JOIN ima.folders f ON f.id=d.folder_id WHERE d.id=:id"""
                        + (" FOR UPDATE" if for_update else "")
                    ),
                    {"id": document_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise KnowledgeError(404, "DOCUMENT_NOT_FOUND", "Document not found")
        return dict(row)

    async def _authorize_kb(
        self, conn: AsyncConnection, actor: str | McpActor, kb_id: str, action: KbAction
    ) -> None:
        await assert_mutation_allowed(conn, action)
        user_id = await effective_user_id(conn, actor)
        membership = await kb_membership(conn, user_id, kb_id) if user_id else None
        if not role_permits(membership[0] if membership else None, action):
            raise KnowledgeError(404, "KB_NOT_FOUND", "Knowledge base not found")

    async def _authorize_folder(
        self, conn: AsyncConnection, actor: str | McpActor, folder: dict[str, Any], action: KbAction
    ) -> None:
        await self._authorize_kb(conn, actor, str(folder["kb_id"]), action)

    async def list_contents(
        self,
        actor: str | McpActor,
        folder_id: str,
        cursor: str | None,
        limit: int,
        kind: str | None = None,
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 100))
        async with self.engine.connect() as conn:
            folder = await self._folder(conn, folder_id)
            await self._authorize_folder(conn, actor, folder, KbAction.VIEW_METADATA)
            current_version = int(folder["children_version"])
            decoded = None
            if cursor:
                try:
                    decoded = ListingCursor.decode(cursor)
                except ValueError as exc:
                    raise KnowledgeError(400, "INVALID_CURSOR", "Cursor is invalid") from exc
                if decoded.parent_id != folder_id or decoded.children_version != current_version:
                    raise KnowledgeError(
                        409, "LISTING_CHANGED", "Folder contents changed; restart pagination"
                    )
            params: dict[str, Any] = {
                "kb": folder["kb_id"],
                "folder": folder_id,
                "limit": limit + 1,
            }
            if decoded:
                params.update(
                    {
                        "after_order": decoded.order_key,
                        "after_name": decoded.normalized_name,
                        "after_id": decoded.item_id,
                    }
                )
            # Folder rows and document rows are separate arms of the mixed
            # listing.  A folder-only request must not accidentally return all
            # documents merely because the document arm has no folder kind.
            folder_kind_filter = "" if not kind or kind == "folder" else "AND false"
            document_kind_filter = (
                "" if not kind else "AND kind=:kind" if kind in {"file", "note"} else "AND false"
            )
            if kind:
                params["kind"] = kind
            params["has_after"] = decoded is not None
            params.setdefault("after_order", 0)
            params.setdefault("after_name", "")
            params.setdefault("after_id", "")
            rows = (
                (
                    await conn.execute(
                        text(
                            f"""WITH content AS (
                          SELECT id::text AS id,'folder' AS kind,name AS title,order_key,version,lifecycle,NULL::varchar AS file_state
                           FROM ima.folders
                           WHERE kb_id=:kb AND parent_id=:folder AND lifecycle='active'
                             {folder_kind_filter}
                           UNION ALL
                           SELECT d.id::text,d.kind,d.title,d.order_key,d.version,d.lifecycle,d.file_state
                             FROM ima.documents d
                            WHERE d.kb_id=:kb AND d.folder_id=:folder AND d.lifecycle='active' {document_kind_filter}
                        )
                        SELECT * FROM content
                         WHERE NOT :has_after OR (order_key > :after_order
                           OR (order_key=:after_order AND lower(title)>:after_name)
                           OR (order_key=:after_order AND lower(title)=:after_name AND id>:after_id))
                        ORDER BY order_key,lower(title),id LIMIT :limit"""
                        ),
                        params,
                    )
                )
                .mappings()
                .all()
            )
            payload = [dict(row) for row in rows]
            next_cursor = None
            if len(payload) > limit:
                payload = payload[:limit]
                last = payload[-1]
                next_cursor = ListingCursor(
                    folder_id,
                    current_version,
                    int(last["order_key"]),
                    str(last["title"]).casefold(),
                    str(last["id"]),
                ).encode()
            return {
                "items": [
                    {
                        "id": row["id"],
                        "kind": row["kind"],
                        "title": row["title"],
                        "orderKey": row["order_key"],
                        "version": row["version"],
                        "lifecycle": row["lifecycle"],
                        "fileState": row["file_state"],
                    }
                    for row in payload
                ],
                "nextCursor": next_cursor,
                "childrenVersion": current_version,
            }

    async def get_document(self, actor: str | McpActor, document_id: UUID) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            row = await self._document(conn, document_id)
            if row["lifecycle"] != "active":
                raise KnowledgeError(404, "DOCUMENT_NOT_FOUND", "Document not found")
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize_folder(conn, actor, folder, KbAction.VIEW_CONTENT)
            version = None
            if row["current_version"]:
                version = (
                    await conn.execute(
                        text(
                            "SELECT markdown FROM ima.document_versions WHERE document_id=:id AND version=:version"
                        ),
                        {"id": document_id, "version": row["current_version"]},
                    )
                ).scalar()
            return {
                "id": row["id"],
                "kbId": row["kb_id"],
                "folderId": row["folder_id"],
                "kind": row["kind"],
                "title": row["title"],
                "version": row["version"],
                "currentContentVersion": row["current_version"],
                "lifecycle": row["lifecycle"],
                "markdown": version if row["kind"] == "note" else None,
                "fileState": row["file_state"],
                "metadata": safe_metadata(row),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }

    async def create_note(
        self, actor: str, folder_id: str, title: str, markdown: str
    ) -> dict[str, Any]:
        try:
            display, normalized = normalize_name(title)
        except ValueError as exc:
            raise KnowledgeError(422, "INVALID_TITLE", "Title is invalid") from exc
        if len(markdown.encode("utf-8")) > 1_000_000:
            raise KnowledgeError(413, "CONTENT_TOO_LARGE", "Markdown content exceeds the limit")
        document_id = uuid4()
        async with self.engine.begin() as conn:
            folder = await self._folder(conn, folder_id)
            await self._authorize_folder(conn, actor, folder, KbAction.CREATE_CHILD)
            ts = now()
            try:
                await conn.execute(
                    text("""INSERT INTO ima.documents(id,kb_id,folder_id,kind,title,normalized_title,current_version,created_by,updated_by,created_at,updated_at)
                  VALUES (:id,:kb,:folder,'note',:title,:normalized,1,:actor,:actor,:now,:now)"""),
                    {
                        "id": document_id,
                        "kb": folder["kb_id"],
                        "folder": folder_id,
                        "title": display,
                        "normalized": normalized,
                        "actor": actor,
                        "now": ts,
                    },
                )
                await conn.execute(
                    text("""INSERT INTO ima.document_versions(document_id,version,kind,markdown,digest,created_by,created_at)
                  VALUES (:id,1,'note',:markdown,:digest,:actor,:now)"""),
                    {
                        "id": document_id,
                        "markdown": markdown,
                        "digest": markdown_digest(markdown),
                        "actor": actor,
                        "now": ts,
                    },
                )
            except Exception as exc:
                if "ux_documents_active_name" in str(exc) or "unique" in str(exc).lower():
                    raise KnowledgeError(
                        409, "NAME_CONFLICT", "An item with this name already exists"
                    ) from None
                raise
        return await self.get_document(actor, document_id)

    async def patch_document(
        self,
        actor: str,
        document_id: UUID,
        *,
        title: str | None,
        markdown: str | None,
        expected_version: int,
        expected_content_version: int | None,
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            row = await self._document(conn, document_id, for_update=True)
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize_folder(conn, actor, folder, KbAction.EDIT)
            if int(row["version"]) != expected_version or (
                expected_content_version is not None
                and row["current_version"] != expected_content_version
            ):
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document has changed")
            values: dict[str, Any] = {"id": document_id, "actor": actor, "now": now()}
            assignments = ["version=version+1", "updated_by=:actor", "updated_at=:now"]
            if title is not None:
                try:
                    display, normalized = normalize_name(title)
                except ValueError as exc:
                    raise KnowledgeError(422, "INVALID_TITLE", "Title is invalid") from exc
                values.update(title=display, normalized=normalized)
                assignments.extend(["title=:title", "normalized_title=:normalized"])
            if markdown is not None:
                if row["kind"] != "note":
                    raise KnowledgeError(400, "NOT_A_NOTE", "Only notes have Markdown content")
                if len(markdown.encode("utf-8")) > 1_000_000:
                    raise KnowledgeError(
                        413, "CONTENT_TOO_LARGE", "Markdown content exceeds the limit"
                    )
                next_version = int(row["current_version"] or 0) + 1
                values.update(
                    markdown=markdown,
                    digest=markdown_digest(markdown),
                    content_version=next_version,
                )
                await conn.execute(
                    text(
                        """INSERT INTO ima.document_versions(document_id,version,kind,markdown,digest,created_by,created_at) VALUES (:id,:content_version,'note',:markdown,:digest,:actor,:now)"""
                    ),
                    values,
                )
                assignments.append("current_version=:content_version")
            await conn.execute(
                text(
                    f"UPDATE ima.documents SET {','.join(assignments)} WHERE id=:id AND version=:expected"
                ),
                {**values, "expected": expected_version},
            )
        return await self.get_document(actor, document_id)

    async def move_document(
        self, actor: str, document_id: UUID, folder_id: str, expected_version: int
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            row = await self._document(conn, document_id)
            source = await self._folder(conn, str(row["folder_id"]))
            destination = await self._folder(conn, folder_id)
            await self._authorize_folder(conn, actor, source, KbAction.MOVE)
            await self._authorize_folder(conn, actor, destination, KbAction.CREATE_CHILD)
            if source["kb_id"] != destination["kb_id"]:
                raise KnowledgeError(400, "CROSS_KB", "Destination is outside the knowledge base")
            if int(row["version"]) != expected_version:
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document has changed")
            await conn.execute(
                text(
                    "UPDATE ima.documents SET folder_id=:folder,version=version+1,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {"folder": folder_id, "actor": actor, "now": now(), "id": document_id},
            )
        return await self.get_document(actor, document_id)

    async def delete_document(self, actor: str, document_id: UUID) -> None:
        """Physically delete a document, its versions, and its derived rows.

        Deletion is immediate: citations are dropped with the document, and the
        durable cleanup pipeline removes orphaned storage objects afterwards.
        """
        async with self.engine.begin() as conn:
            row = await self._document(conn, document_id, for_update=True)
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize_folder(conn, actor, folder, KbAction.DELETE)
            file_versions = (
                await conn.execute(
                    text(
                        "SELECT version,object_key FROM ima.document_file_versions WHERE document_id=:id ORDER BY version"
                    ),
                    {"id": document_id},
                )
            ).all()
            await conn.execute(
                text("DELETE FROM ima.message_citations WHERE document_id=:id"),
                {"id": document_id},
            )
            await conn.execute(
                text("DELETE FROM ima.document_chunks WHERE document_id=:id"),
                {"id": document_id},
            )
            await conn.execute(
                text("DELETE FROM ima.ingestion_jobs WHERE document_id=:id"),
                {"id": document_id},
            )
            await conn.execute(
                text("DELETE FROM ima.document_derived_text WHERE document_id=:id"),
                {"id": document_id},
            )
            await conn.execute(
                text("DELETE FROM ima.document_file_versions WHERE document_id=:id"),
                {"id": document_id},
            )
            await conn.execute(
                text("DELETE FROM ima.document_versions WHERE document_id=:id"),
                {"id": document_id},
            )
            result = await conn.execute(
                text("DELETE FROM ima.documents WHERE id=:id"),
                {"id": document_id},
            )
            if result.rowcount != 1:
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document has changed")
        for version, object_key in file_versions:
            await self.jobs.enqueue_cleanup(str(object_key), document_id, int(version))

    async def list_versions(self, actor: str, document_id: UUID) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            row = await self._document(conn, document_id)
            if row["lifecycle"] != "active":
                raise KnowledgeError(404, "DOCUMENT_NOT_FOUND", "Document not found")
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize_folder(conn, actor, folder, KbAction.VIEW_CONTENT)
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT document_id,version,kind,markdown,digest,created_at FROM ima.document_versions WHERE document_id=:id ORDER BY version DESC"
                        ),
                        {"id": document_id},
                    )
                )
                .mappings()
                .all()
            )
            return [
                {
                    "documentId": row["document_id"],
                    "version": row["version"],
                    "kind": row["kind"],
                    "markdown": row["markdown"],
                    "digest": row["digest"],
                    "createdAt": row["created_at"],
                }
                for row in rows
            ]

    async def restore_version(
        self, actor: str, document_id: UUID, version: int, expected_version: int
    ) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            old = await self._document(conn, document_id)
            content = (
                await conn.execute(
                    text(
                        "SELECT markdown FROM ima.document_versions WHERE document_id=:id AND version=:version"
                    ),
                    {"id": document_id, "version": version},
                )
            ).scalar()
        if content is None:
            raise KnowledgeError(404, "VERSION_NOT_FOUND", "Version not found")
        return await self.patch_document(
            actor,
            document_id,
            title=None,
            markdown=str(content),
            expected_version=expected_version,
            expected_content_version=old["current_version"],
        )
