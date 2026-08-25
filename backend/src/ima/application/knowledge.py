"""Knowledge tree service; SQL policy is delegated to WorkspaceService."""

# SQL remains readable as complete statements.
# ruff: noqa: E501

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ima.application.authorization import WorkspaceError, WorkspaceService
from ima.domain.authorization import AclAction
from ima.domain.knowledge import (
    ListingCursor,
    TrashCursor,
    markdown_digest,
    normalize_name,
    safe_metadata,
)
from ima.infrastructure.db.authorization import accessible_folder_ids


def now() -> datetime:
    return datetime.now(UTC)


class KnowledgeError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code, self.code, self.detail = status_code, code, detail


class KnowledgeService:
    def __init__(self, engine: AsyncEngine, workspace: WorkspaceService) -> None:
        self.engine = engine
        self.workspace = workspace

    async def _folder(self, conn: AsyncConnection, folder_id: str) -> dict[str, Any]:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT id,workspace_id,children_version,lifecycle FROM ima.folders WHERE id=:id"
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
                        """SELECT d.*,f.workspace_id AS folder_workspace_id FROM ima.documents d
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

    async def _authorize_folder(
        self,
        conn: AsyncConnection,
        actor: str,
        folder: dict[str, Any],
        action: AclAction,
        *,
        include_trashed: bool = False,
    ) -> Any:
        info = await self.workspace._require_member(conn, actor, str(folder["workspace_id"]))
        try:
            await self.workspace._require_folder_action(
                conn,
                info["subject"],
                str(folder["workspace_id"]),
                str(folder["id"]),
                action,
                include_trashed=include_trashed,
            )
        except WorkspaceError as exc:
            raise KnowledgeError(exc.status_code, exc.code, exc.detail) from exc
        return info["subject"]

    async def capabilities(self, actor: str, workspace_id: str) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            await self.workspace._require_member(conn, actor, workspace_id)
        pending = {"status": "unavailable", "reason": "STORAGE_MIGRATION_PENDING"}
        return {"upload": pending, "download": pending, "preview": pending}

    async def list_contents(
        self,
        actor: str,
        folder_id: str,
        cursor: str | None,
        limit: int,
        kind: str | None = None,
        tag_id: UUID | None = None,
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 100))
        async with self.engine.connect() as conn:
            folder = await self._folder(conn, folder_id)
            subject = await self._authorize_folder(conn, actor, folder, AclAction.VIEW_METADATA)
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
            visible_folders = await accessible_folder_ids(conn, subject, AclAction.VIEW_METADATA)
            params: dict[str, Any] = {
                "workspace": folder["workspace_id"],
                "folder": folder_id,
                "ids": list(visible_folders),
                "tag_id": tag_id,
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
                           WHERE workspace_id=:workspace AND parent_id=:folder AND lifecycle='active' AND id=ANY(:ids)
                             {folder_kind_filter}
                           UNION ALL
                           SELECT d.id::text,d.kind,d.title,d.order_key,d.version,d.lifecycle,d.file_state
                             FROM ima.documents d
                            WHERE d.workspace_id=:workspace AND d.folder_id=:folder AND d.lifecycle='active' {document_kind_filter}
                             AND (CAST(:tag_id AS uuid) IS NULL OR EXISTS(SELECT 1 FROM ima.document_tags dt WHERE dt.document_id=d.id AND dt.tag_id=CAST(:tag_id AS uuid)))
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
                    {**row, "orderKey": row.pop("order_key"), "fileState": row.pop("file_state")}
                    for row in payload
                ],
                "nextCursor": next_cursor,
                "childrenVersion": current_version,
            }

    async def get_document(self, actor: str, document_id: UUID) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            row = await self._document(conn, document_id)
            if row["lifecycle"] != "active":
                raise KnowledgeError(404, "DOCUMENT_NOT_FOUND", "Document not found")
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize_folder(conn, actor, folder, AclAction.VIEW_CONTENT)
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
                "workspaceId": row["workspace_id"],
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
            await self._authorize_folder(conn, actor, folder, AclAction.CREATE_CHILD)
            ts = now()
            try:
                await conn.execute(
                    text("""INSERT INTO ima.documents(id,workspace_id,folder_id,kind,title,normalized_title,current_version,created_by,updated_by,created_at,updated_at)
                  VALUES (:id,:workspace,:folder,'note',:title,:normalized,1,:actor,:actor,:now,:now)"""),
                    {
                        "id": document_id,
                        "workspace": folder["workspace_id"],
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
            await self._authorize_folder(conn, actor, folder, AclAction.EDIT)
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
            await self._authorize_folder(conn, actor, source, AclAction.MOVE)
            await self._authorize_folder(conn, actor, destination, AclAction.CREATE_CHILD)
            if source["workspace_id"] != destination["workspace_id"]:
                raise KnowledgeError(400, "CROSS_WORKSPACE", "Destination is outside the workspace")
            if int(row["version"]) != expected_version:
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document has changed")
            await conn.execute(
                text(
                    "UPDATE ima.documents SET folder_id=:folder,version=version+1,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {"folder": folder_id, "actor": actor, "now": now(), "id": document_id},
            )
        return await self.get_document(actor, document_id)

    async def trash_document(self, actor: str, document_id: UUID, expected_version: int) -> None:
        async with self.engine.begin() as conn:
            row = await self._document(conn, document_id)
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize_folder(conn, actor, folder, AclAction.DELETE)
            if row["lifecycle"] != "active":
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document has changed")
            if row["version"] != expected_version:
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document has changed")
            await conn.execute(
                text(
                    "UPDATE ima.documents SET lifecycle='trashed',original_folder_id=folder_id,version=version+1,trashed_at=:now,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {"id": document_id, "actor": actor, "now": now()},
            )

    async def restore_document(
        self,
        actor: str,
        document_id: UUID,
        expected_version: int,
        destination_folder_id: str | None = None,
    ) -> None:
        async with self.engine.begin() as conn:
            row = await self._document(conn, document_id)
            destination_id = destination_folder_id or str(
                row["original_folder_id"] or row["folder_id"]
            )
            destination = await self._folder(conn, destination_id)
            await self._authorize_folder(conn, actor, destination, AclAction.CREATE_CHILD)
            if row["lifecycle"] != "trashed":
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document has changed")
            if row["version"] != expected_version:
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document has changed")
            await conn.execute(
                text(
                    "UPDATE ima.documents SET lifecycle='active',folder_id=:folder,original_folder_id=NULL,version=version+1,trashed_at=NULL,updated_by=:actor,updated_at=:now WHERE id=:id"
                ),
                {"id": document_id, "folder": destination_id, "actor": actor, "now": now()},
            )

    async def list_versions(self, actor: str, document_id: UUID) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            row = await self._document(conn, document_id)
            if row["lifecycle"] != "active":
                raise KnowledgeError(404, "DOCUMENT_NOT_FOUND", "Document not found")
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize_folder(conn, actor, folder, AclAction.VIEW_CONTENT)
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
            return [dict(row) for row in rows]

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

    async def list_tags(self, actor: str, workspace_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            info = await self.workspace._require_member(conn, actor, workspace_id)
            visible_folders = await accessible_folder_ids(
                conn, info["subject"], AclAction.VIEW_METADATA
            )
            rows = (
                (
                    await conn.execute(
                        text("""SELECT t.id,t.name,t.version,count(*) AS count
              FROM ima.tags t
              JOIN ima.document_tags dt ON dt.tag_id=t.id
              JOIN ima.documents d ON d.id=dt.document_id
              WHERE t.workspace_id=:workspace AND t.lifecycle='active'
                AND d.lifecycle='active' AND d.folder_id=ANY(:folders)
              GROUP BY t.id ORDER BY t.normalized_name,t.id"""),
                        {"workspace": workspace_id, "folders": list(visible_folders)},
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def create_tag(self, actor: str, workspace_id: str, name: str) -> dict[str, Any]:
        display, normalized = normalize_name(name, limit=120)
        async with self.engine.begin() as conn:
            info = await self.workspace._require_member(conn, actor, workspace_id)
            if info["role"] not in {"workspace_admin", "knowledge_manager"}:
                raise KnowledgeError(403, "TAG_FORBIDDEN", "Tag administration is required")
            tag_id = uuid4()
            try:
                await conn.execute(
                    text(
                        "INSERT INTO ima.tags(id,workspace_id,name,normalized_name,created_by,updated_by,created_at,updated_at) VALUES (:id,:workspace,:name,:normalized,:actor,:actor,:now,:now)"
                    ),
                    {
                        "id": tag_id,
                        "workspace": workspace_id,
                        "name": display,
                        "normalized": normalized,
                        "actor": actor,
                        "now": now(),
                    },
                )
            except Exception as exc:
                if "unique" in str(exc).lower():
                    raise KnowledgeError(409, "NAME_CONFLICT", "Tag already exists") from None
                raise
        return {"id": tag_id, "name": display, "version": 1, "count": 0}

    async def patch_tag(
        self, actor: str, workspace_id: str, tag_id: UUID, name: str, expected_version: int
    ) -> dict[str, Any]:
        display, normalized = normalize_name(name, limit=120)
        async with self.engine.begin() as conn:
            info = await self.workspace._require_member(conn, actor, workspace_id)
            if info["role"] not in {"workspace_admin", "knowledge_manager"}:
                raise KnowledgeError(403, "TAG_FORBIDDEN", "Tag administration is required")
            result = await conn.execute(
                text(
                    "UPDATE ima.tags SET name=:name,normalized_name=:normalized,version=version+1,updated_by=:actor,updated_at=:now WHERE id=:id AND workspace_id=:workspace AND lifecycle='active' AND version=:version"
                ),
                {
                    "name": display,
                    "normalized": normalized,
                    "actor": actor,
                    "now": now(),
                    "id": tag_id,
                    "workspace": workspace_id,
                    "version": expected_version,
                },
            )
            if result.rowcount != 1:
                raise KnowledgeError(409, "VERSION_CONFLICT", "Tag has changed")
        return {"id": tag_id, "name": display, "version": expected_version + 1, "count": 0}

    async def _manage_tag(
        self, conn: AsyncConnection, actor: str, workspace_id: str, tag_id: UUID
    ) -> dict[str, Any]:
        info = await self.workspace._require_member(conn, actor, workspace_id)
        if info["role"] not in {"workspace_admin", "knowledge_manager"}:
            raise KnowledgeError(403, "TAG_FORBIDDEN", "Tag administration is required")
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT id,workspace_id,lifecycle,version FROM ima.tags "
                        "WHERE id=:id AND workspace_id=:workspace FOR UPDATE"
                    ),
                    {"id": tag_id, "workspace": workspace_id},
                )
            )
            .mappings()
            .first()
        )
        if not row or row["lifecycle"] != "active":
            raise KnowledgeError(404, "TAG_NOT_FOUND", "Tag not found")
        return dict(row)

    async def delete_tag(
        self, actor: str, workspace_id: str, tag_id: UUID, expected_version: int
    ) -> None:
        async with self.engine.begin() as conn:
            tag = await self._manage_tag(conn, actor, workspace_id, tag_id)
            if int(tag["version"]) != expected_version:
                raise KnowledgeError(409, "VERSION_CONFLICT", "Tag has changed")
            dependencies = int(
                await conn.scalar(
                    text("SELECT count(*) FROM ima.document_tags WHERE tag_id=:id"), {"id": tag_id}
                )
                or 0
            )
            if dependencies:
                await self.workspace._audit(
                    conn,
                    actor,
                    "knowledge.tag.delete.denied",
                    "failure",
                    workspace=workspace_id,
                    target=str(tag_id),
                    reason="dependency_exists",
                )
                raise KnowledgeError(409, "DEPENDENCY_EXISTS", "Tag has assigned documents")
            await conn.execute(
                text(
                    "UPDATE ima.tags SET lifecycle='disabled',version=version+1,updated_by=:actor,"
                    "updated_at=:now WHERE id=:id AND version=:version"
                ),
                {"id": tag_id, "version": expected_version, "actor": actor, "now": now()},
            )
            await self.workspace._audit(
                conn,
                actor,
                "knowledge.tag.deleted",
                "success",
                workspace=workspace_id,
                target=str(tag_id),
            )

    async def merge_tag(
        self,
        actor: str,
        workspace_id: str,
        source_tag_id: UUID,
        target_tag_id: UUID,
        expected_version: int,
        expected_target_version: int,
    ) -> None:
        if source_tag_id == target_tag_id:
            raise KnowledgeError(400, "INVALID_TAG_MERGE", "Tags must be different")
        async with self.engine.begin() as conn:
            info = await self.workspace._require_member(conn, actor, workspace_id)
            if info["role"] not in {"workspace_admin", "knowledge_manager"}:
                raise KnowledgeError(403, "TAG_FORBIDDEN", "Tag administration is required")
            tags = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,workspace_id,lifecycle,version FROM ima.tags "
                            "WHERE workspace_id=:workspace AND id=ANY(:ids) ORDER BY id FOR UPDATE"
                        ),
                        {"workspace": workspace_id, "ids": sorted((source_tag_id, target_tag_id))},
                    )
                )
                .mappings()
                .all()
            )
            by_id = {row["id"]: dict(row) for row in tags}
            source = by_id.get(source_tag_id)
            target = by_id.get(target_tag_id)
            if not source or not target or source["lifecycle"] != "active" or target["lifecycle"] != "active":
                raise KnowledgeError(404, "TAG_NOT_FOUND", "Tag not found")
            if int(source["version"]) != expected_version or int(target["version"]) != expected_target_version:
                raise KnowledgeError(409, "VERSION_CONFLICT", "Tag has changed")
            await conn.execute(
                text(
                    "INSERT INTO ima.document_tags(document_id,tag_id,assigned_by,assigned_at) "
                    "SELECT document_id,:target,:actor,:now FROM ima.document_tags WHERE tag_id=:source "
                    "ON CONFLICT(document_id,tag_id) DO NOTHING"
                ),
                {"source": source_tag_id, "target": target_tag_id, "actor": actor, "now": now()},
            )
            await conn.execute(
                text("DELETE FROM ima.document_tags WHERE tag_id=:source"), {"source": source_tag_id}
            )
            await conn.execute(
                text(
                    "UPDATE ima.tags SET lifecycle='disabled',version=version+1,updated_by=:actor,"
                    "updated_at=:now WHERE id=:id AND version=:version"
                ),
                {"id": source_tag_id, "version": expected_version, "actor": actor, "now": now()},
            )
            await self.workspace._audit(
                conn,
                actor,
                "knowledge.tag.merged",
                "success",
                workspace=workspace_id,
                target=str(source_tag_id),
                metadata={"targetTagId": str(target_tag_id)},
            )

    async def assign_tags(self, actor: str, document_id: UUID, tag_ids: tuple[UUID, ...]) -> None:
        async with self.engine.begin() as conn:
            row = await self._document(conn, document_id)
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize_folder(conn, actor, folder, AclAction.EDIT)
            valid = await conn.scalar(
                text(
                    "SELECT count(*) FROM ima.tags WHERE workspace_id=:workspace AND id=ANY(:ids) AND lifecycle='active'"
                ),
                {"workspace": row["workspace_id"], "ids": list(tag_ids)},
            )
            if int(valid or 0) != len(set(tag_ids)):
                raise KnowledgeError(404, "TAG_NOT_FOUND", "Tag not found")
            await conn.execute(
                text("DELETE FROM ima.document_tags WHERE document_id=:id"), {"id": document_id}
            )
            for tag_id in set(tag_ids):
                await conn.execute(
                    text(
                        "INSERT INTO ima.document_tags(document_id,tag_id,assigned_by,assigned_at) VALUES (:id,:tag,:actor,:now)"
                    ),
                    {"id": document_id, "tag": tag_id, "actor": actor, "now": now()},
                )

    async def list_trash(
        self, actor: str, workspace_id: str, cursor: str | None, limit: int
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 100))
        async with self.engine.connect() as conn:
            info = await self.workspace._require_member(conn, actor, workspace_id)
            decoded = None
            if cursor:
                try:
                    decoded = TrashCursor.decode(cursor)
                except ValueError as exc:
                    raise KnowledgeError(400, "INVALID_CURSOR", "Cursor is invalid") from exc
                if decoded.workspace_id != workspace_id:
                    raise KnowledgeError(400, "INVALID_CURSOR", "Cursor is invalid")
            visible_folders = await accessible_folder_ids(
                conn, info["subject"], AclAction.VIEW_METADATA, include_trashed=True
            )
            params: dict[str, Any] = {
                "workspace": workspace_id,
                "folders": list(visible_folders),
                "limit": limit + 1,
                "has_after": decoded is not None,
                "after_trashed_at": decoded.trashed_at if decoded else "1970-01-01T00:00:00+00:00",
                "after_id": decoded.item_id if decoded else "",
            }
            rows = (
                (
                    await conn.execute(
                        text("""WITH trash AS (
                          SELECT id::text AS id,'folder' AS kind,name AS title,order_key,version,lifecycle,NULL::varchar AS file_state,trashed_at
                            FROM ima.folders
                           WHERE workspace_id=:workspace AND lifecycle='trashed' AND id=ANY(:folders)
                             AND NOT EXISTS (SELECT 1 FROM ima.folder_closure c JOIN ima.folders ancestor ON ancestor.id=c.ancestor_id
                                             WHERE c.workspace_id=:workspace AND c.descendant_id=ima.folders.id AND c.depth>0 AND ancestor.lifecycle='trashed')
                          UNION ALL
                          SELECT id::text,kind,title,order_key,version,lifecycle,file_state,trashed_at FROM ima.documents
                           WHERE workspace_id=:workspace AND lifecycle='trashed' AND folder_id=ANY(:folders)
                        )
                        SELECT * FROM trash
                         WHERE NOT :has_after OR trashed_at < CAST(:after_trashed_at AS timestamptz)
                           OR (trashed_at = CAST(:after_trashed_at AS timestamptz) AND id > :after_id)
                         ORDER BY trashed_at DESC,id LIMIT :limit"""),
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
                next_cursor = TrashCursor(
                    workspace_id, last["trashed_at"].isoformat(), str(last["id"])
                ).encode()
            return {
                "items": [
                    {**row, "orderKey": row.pop("order_key"), "fileState": row.pop("file_state"), "trashedAt": row.pop("trashed_at")}
                    for row in payload
                ],
                "nextCursor": next_cursor,
            }

    async def delete_document(self, actor: str, document_id: UUID) -> None:
        async with self.engine.begin() as conn:
            row = await self._document(conn, document_id, for_update=True)
            folder = await self._folder(conn, str(row["folder_id"]))
            info = await self.workspace._require_member(conn, actor, str(row["workspace_id"]))
            if info["role"] != "workspace_admin":
                raise KnowledgeError(
                    403, "DELETE_FORBIDDEN", "Workspace administration is required"
                )
            await self._authorize_folder(
                conn, actor, folder, AclAction.DELETE, include_trashed=True
            )
            if row["lifecycle"] != "trashed":
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document must be trashed first")
            try:
                result = await conn.execute(
                    text("DELETE FROM ima.documents WHERE id=:id AND lifecycle='trashed'"),
                    {"id": document_id},
                )
            except Exception as exc:
                raise KnowledgeError(
                    409, "DEPENDENCY_EXISTS", "Document has dependent records"
                ) from exc
            if result.rowcount != 1:
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document has changed")
