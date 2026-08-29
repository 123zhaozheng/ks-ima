"""Authorized file version upload, completion, and byte access."""

# ruff: noqa: E501

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ima.application.authorization import WorkspaceError, WorkspaceService
from ima.application.ingestion import ParseError, validate_upload_type
from ima.application.knowledge import KnowledgeError, now
from ima.application.maintenance import assert_mutation_allowed
from ima.application.mcp_contracts import McpActor
from ima.config import Settings
from ima.domain.authorization import AclAction
from ima.domain.knowledge import normalize_name
from ima.infrastructure.storage import ObjectStorageClient, StorageClientError
from ima.infrastructure.tasks.service import JobService


class StorageService:
    def __init__(
        self, settings: Settings, engine: AsyncEngine, workspace: WorkspaceService, jobs: JobService
    ) -> None:
        self.settings = settings
        self.engine = engine
        self.workspace = workspace
        self.jobs = jobs
        self.client = ObjectStorageClient(settings)

    async def capabilities(self, actor: str, workspace_id: str) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            await self.workspace._require_member(conn, actor, workspace_id)
        available = (
            {"status": "available"}
            if self.client.enabled
            else {"status": "unavailable", "reason": "STORAGE_UNAVAILABLE"}
        )
        return {"upload": available, "download": available, "preview": available}

    async def upload_ticket(
        self,
        actor: str,
        folder_id: str,
        title: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        checksum: str,
    ) -> dict[str, Any]:
        if not self.client.enabled:
            raise KnowledgeError(503, "STORAGE_UNAVAILABLE", "File storage is unavailable")
        self._validate_upload(filename, mime_type, size_bytes, checksum)
        try:
            display, normalized = normalize_name(title)
        except ValueError as exc:
            raise KnowledgeError(422, "INVALID_TITLE", "Title is invalid") from exc
        document_id, version, ts = uuid4(), 1, now()
        key = self.client.object_key(document_id, version)
        async with self.engine.begin() as conn:
            folder = await self._folder(conn, folder_id)
            await self._authorize(conn, actor, folder, AclAction.CREATE_CHILD)
            try:
                url = self.client.presigned_put(key, checksum, size_bytes, mime_type)
            except StorageClientError as exc:
                raise KnowledgeError(503, exc.code, "File storage is unavailable") from exc
            await conn.execute(
                text(
                    """INSERT INTO ima.documents(id,workspace_id,folder_id,kind,title,normalized_title,current_version,file_state,mime_type,size_bytes,checksum,storage_key,created_by,updated_by,created_at,updated_at) VALUES (:id,:workspace,:folder,'file',:title,:normalized,1,'pending',:mime,:size,:checksum,:key,:actor,:actor,:now,:now)"""
                ),
                {
                    "id": document_id,
                    "workspace": folder["workspace_id"],
                    "folder": folder_id,
                    "title": display,
                    "normalized": normalized,
                    "mime": mime_type,
                    "size": size_bytes,
                    "checksum": checksum,
                    "key": key,
                    "actor": actor,
                    "now": ts,
                },
            )
            await conn.execute(
                text(
                    """INSERT INTO ima.document_file_versions(document_id,version,workspace_id,object_state,object_key,checksum,size_bytes,mime_type,original_filename,created_by,created_at) VALUES (:document,1,:workspace,'pending',:key,:checksum,:size,:mime,:filename,:actor,:now)"""
                ),
                {
                    "document": document_id,
                    "workspace": folder["workspace_id"],
                    "key": key,
                    "checksum": checksum,
                    "size": size_bytes,
                    "mime": mime_type,
                    "filename": filename,
                    "actor": actor,
                    "now": ts,
                },
            )
        expiry = datetime.now(UTC) + timedelta(seconds=self.settings.storage_presign_seconds)
        return {
            "ticketId": self._ticket(document_id, version, expiry),
            "uploadUrl": url,
            "documentId": document_id,
            "version": version,
            "expiresAt": expiry,
            "requiredChecksum": checksum,
            "requiredSizeBytes": size_bytes,
            "requiredMimeType": mime_type,
        }

    async def replacement_ticket(
        self,
        actor: str,
        document_id: UUID,
        filename: str,
        mime_type: str,
        size_bytes: int,
        checksum: str,
        expected_version: int,
        expected_content_version: int,
    ) -> dict[str, Any]:
        if not self.client.enabled:
            raise KnowledgeError(503, "STORAGE_UNAVAILABLE", "File storage is unavailable")
        self._validate_upload(filename, mime_type, size_bytes, checksum)
        async with self.engine.begin() as conn:
            document = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.documents WHERE id=:id AND kind='file' AND lifecycle='active' FOR UPDATE"
                        ),
                        {"id": document_id},
                    )
                )
                .mappings()
                .first()
            )
            if not document:
                raise KnowledgeError(404, "DOCUMENT_NOT_FOUND", "Document not found")
            folder = await self._folder(conn, str(document["folder_id"]))
            await self._authorize(conn, actor, folder, AclAction.EDIT)
            if (
                int(document["version"]) != expected_version
                or int(document["current_version"] or 0) != expected_content_version
            ):
                raise KnowledgeError(409, "VERSION_CONFLICT", "Document has changed")
            pending = await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.document_file_versions WHERE document_id=:id AND object_state='pending')"
                ),
                {"id": document_id},
            )
            if pending:
                raise KnowledgeError(
                    409, "UPLOAD_IN_PROGRESS", "A file replacement is already pending"
                )
            version = int(document["current_version"] or 0) + 1
            key = self.client.object_key(document_id, version)
            try:
                url = self.client.presigned_put(key, checksum, size_bytes, mime_type)
            except StorageClientError as exc:
                raise KnowledgeError(503, exc.code, "File storage is unavailable") from exc
            ts = now()
            await conn.execute(
                text(
                    """INSERT INTO ima.document_file_versions(document_id,version,workspace_id,object_state,object_key,checksum,size_bytes,mime_type,original_filename,created_by,created_at) VALUES (:document,:version,:workspace,'pending',:key,:checksum,:size,:mime,:filename,:actor,:now)"""
                ),
                {
                    "document": document_id,
                    "version": version,
                    "workspace": document["workspace_id"],
                    "key": key,
                    "checksum": checksum,
                    "size": size_bytes,
                    "mime": mime_type,
                    "filename": filename,
                    "actor": actor,
                    "now": ts,
                },
            )
        expiry = datetime.now(UTC) + timedelta(seconds=self.settings.storage_presign_seconds)
        return {
            "ticketId": self._ticket(document_id, version, expiry),
            "uploadUrl": url,
            "documentId": document_id,
            "version": version,
            "expiresAt": expiry,
            "requiredChecksum": checksum,
            "requiredSizeBytes": size_bytes,
            "requiredMimeType": mime_type,
        }

    async def complete(self, actor: str, document_id: UUID, ticket: str) -> dict[str, Any]:
        version = self._verify_ticket(ticket, document_id)
        async with self.engine.begin() as conn:
            row = await self._file_row(conn, document_id, version, lock=True)
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize(conn, actor, folder, AclAction.EDIT)
            if row["object_state"] == "verified":
                return await self.status(actor, document_id)
            try:
                self.client.verify(
                    row["object_key"], row["checksum"], row["size_bytes"], row["mime_type"]
                )
            except StorageClientError as exc:
                await conn.execute(
                    text(
                        "UPDATE ima.document_file_versions SET object_state='failed' WHERE document_id=:id AND version=:version"
                    ),
                    {"id": document_id, "version": version},
                )
                raise KnowledgeError(
                    422, exc.code, "Uploaded object could not be verified"
                ) from exc
            await conn.execute(
                text(
                    "UPDATE ima.document_file_versions SET object_state='verified',verified_at=:now WHERE document_id=:id AND version=:version"
                ),
                {"id": document_id, "version": version, "now": now()},
            )
            await conn.execute(
                text(
                    "UPDATE ima.documents SET current_version=:version,file_state='pending',mime_type=:mime,size_bytes=:size,checksum=:checksum,storage_key=:key,version=version+1,updated_at=:now,updated_by=:actor WHERE id=:id"
                ),
                {
                    "id": document_id,
                    "version": version,
                    "mime": row["mime_type"],
                    "size": row["size_bytes"],
                    "checksum": row["checksum"],
                    "key": row["object_key"],
                    "now": now(),
                    "actor": actor,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.document_versions(document_id,version,kind,digest,created_by,created_at) VALUES (:document,:version,'file',:digest,:actor,:now)"
                ),
                {
                    "document": document_id,
                    "version": version,
                    "digest": row["checksum"],
                    "actor": actor,
                    "now": now(),
                },
            )
            await self.jobs.create_ingestion_jobs(conn, document_id, version, 1, actor)
        await self.jobs.defer_ingestion_parse(document_id, version, 1)
        return await self.status(actor, document_id)

    async def download(
        self, actor: str | McpActor, document_id: UUID, *, preview: bool = False
    ) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            row = await self._file_row(conn, document_id, None)
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize(
                conn, actor, folder, AclAction.VIEW_CONTENT if preview else AclAction.DOWNLOAD
            )
        if row["object_state"] != "verified":
            raise KnowledgeError(409, "FILE_NOT_READY", "File is not ready")
        if preview and row["mime_type"] not in {"text/plain", "text/markdown", "application/json"}:
            raise KnowledgeError(409, "PREVIEW_UNAVAILABLE", "Preview is unavailable")
        try:
            url = self.client.presigned_get(
                row["object_key"], row["original_filename"], row["mime_type"], inline=preview
            )
        except StorageClientError as exc:
            raise KnowledgeError(503, exc.code, "File storage is unavailable") from exc
        return {
            "url": url,
            "expiresAt": datetime.now(UTC)
            + timedelta(seconds=self.settings.storage_presign_seconds),
        }

    async def file_versions(self, actor: str, document_id: UUID) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            row = await self._file_row(conn, document_id, None)
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize(conn, actor, folder, AclAction.VIEW_METADATA)
            versions = (
                (
                    await conn.execute(
                        text(
                            "SELECT version,generation,object_state,original_filename,created_at FROM ima.document_file_versions WHERE document_id=:id ORDER BY version DESC"
                        ),
                        {"id": document_id},
                    )
                )
                .mappings()
                .all()
            )
        return {
            "items": [
                {
                    "version": item["version"],
                    "generation": item["generation"],
                    "objectState": item["object_state"],
                    "originalFilename": item["original_filename"],
                    "createdAt": item["created_at"],
                }
                for item in versions
            ]
        }

    async def retry(self, actor: str, document_id: UUID) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            row = await self._file_row(conn, document_id, None, lock=True)
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize(conn, actor, folder, AclAction.EDIT)
            stages = (
                (
                    await conn.execute(
                        text(
                            "SELECT stage,generation FROM ima.ingestion_jobs WHERE document_id=:id AND version=:version AND status IN ('failed','dead_letter','cancelled')"
                        ),
                        {"id": document_id, "version": row["version"]},
                    )
                )
                .mappings()
                .all()
            )
            if not stages:
                raise KnowledgeError(409, "INGESTION_NOT_RETRYABLE", "Ingestion is not retryable")
            generation = max(int(stage["generation"]) for stage in stages)
            await conn.execute(
                text(
                    "UPDATE ima.ingestion_jobs SET status='queued',attempts=0,retry_at=NULL,error_code=NULL,updated_at=:now WHERE document_id=:id AND version=:version AND generation=:generation AND stage='parse' AND status IN ('failed','dead_letter','cancelled')"
                ),
                {
                    "id": document_id,
                    "version": row["version"],
                    "generation": generation,
                    "now": now(),
                },
            )
            await conn.execute(
                text(
                    "UPDATE ima.ingestion_jobs SET status='blocked',attempts=0,retry_at=NULL,error_code=NULL,updated_at=:now WHERE document_id=:id AND version=:version AND generation=:generation AND stage IN ('chunk','embed')"
                ),
                {
                    "id": document_id,
                    "version": row["version"],
                    "generation": generation,
                    "now": now(),
                },
            )
        await self.jobs.defer_ingestion_stage(document_id, row["version"], generation, "parse")
        return await self.status(actor, document_id)

    async def cancel(self, actor: str, document_id: UUID) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            row = await self._file_row(conn, document_id, None, lock=True)
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize(conn, actor, folder, AclAction.EDIT)
            updated = await conn.scalar(
                text(
                    "UPDATE ima.ingestion_jobs SET status='cancel_requested',updated_at=:now WHERE document_id=:id AND version=:version AND status IN ('queued','running','retryable') RETURNING 1"
                ),
                {"id": document_id, "version": row["version"], "now": now()},
            )
            if not updated:
                raise KnowledgeError(409, "INGESTION_NOT_CANCELLABLE", "Ingestion is not running")
        return await self.status(actor, document_id)

    async def status(self, actor: str, document_id: UUID) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            row = await self._file_row(conn, document_id, None)
            folder = await self._folder(conn, str(row["folder_id"]))
            await self._authorize(conn, actor, folder, AclAction.VIEW_METADATA)
            jobs = (
                (
                    await conn.execute(
                        text(
                            "SELECT stage,status,completed_units,total_units,error_code,updated_at FROM ima.ingestion_jobs WHERE document_id=:id AND version=:version ORDER BY created_at"
                        ),
                        {"id": document_id, "version": row["version"]},
                    )
                )
                .mappings()
                .all()
            )
        return {
            "documentId": document_id,
            "version": row["version"],
            "objectState": row["object_state"],
            "jobs": [
                {
                    "stage": job["stage"],
                    "status": job["status"],
                    "completedUnits": job["completed_units"],
                    "totalUnits": job["total_units"],
                    "errorCode": job["error_code"],
                    "updatedAt": job["updated_at"],
                }
                for job in jobs
            ],
        }

    def _validate_upload(
        self, filename: str, mime_type: str, size_bytes: int, checksum: str
    ) -> None:
        if size_bytes < 1 or size_bytes > self.settings.storage_max_object_bytes:
            raise KnowledgeError(413, "OBJECT_TOO_LARGE", "File size is outside the allowed range")
        if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
            raise KnowledgeError(422, "INVALID_CHECKSUM", "Checksum is invalid")
        try:
            validate_upload_type(filename, mime_type)
        except ParseError as exc:
            raise KnowledgeError(422, exc.code, "File type is not supported") from exc

    async def _folder(self, conn: Any, folder_id: str) -> dict[str, Any]:
        row = (
            (
                await conn.execute(
                    text("SELECT id,workspace_id,lifecycle FROM ima.folders WHERE id=:id"),
                    {"id": folder_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise KnowledgeError(404, "FOLDER_NOT_FOUND", "Folder not found")
        return dict(row)

    async def _authorize(
        self, conn: Any, actor: str | McpActor, folder: dict[str, Any], action: AclAction
    ) -> None:
        await assert_mutation_allowed(conn, action)
        if isinstance(actor, McpActor):
            try:
                await self.workspace._require_delegated_action(
                    conn,
                    actor,
                    str(folder["workspace_id"]),
                    str(folder["id"]),
                    action,
                )
            except WorkspaceError as exc:
                raise KnowledgeError(exc.status_code, exc.code, exc.detail) from exc
            return
        info = await self.workspace._require_member(conn, actor, str(folder["workspace_id"]))
        try:
            await self.workspace._require_folder_action(
                conn, info["subject"], str(folder["workspace_id"]), str(folder["id"]), action
            )
        except Exception as exc:
            raise KnowledgeError(404, "DOCUMENT_NOT_FOUND", "Document not found") from exc

    async def _file_row(
        self, conn: Any, document_id: UUID, version: int | None, lock: bool = False
    ) -> dict[str, Any]:
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT d.id,d.folder_id,d.workspace_id,d.current_version,d.version AS document_version,
                        fv.version,fv.object_state,fv.object_key,fv.checksum,fv.size_bytes,fv.mime_type,fv.original_filename
                        FROM ima.documents d JOIN ima.document_file_versions fv ON fv.document_id=d.id
                        WHERE d.id=:id AND d.kind='file' AND d.lifecycle='active'
                        AND (:version IS NULL AND fv.version=d.current_version OR :version IS NOT NULL AND fv.version=:version)
                        LIMIT 1"""
                        + (" FOR UPDATE" if lock else "")
                    ),
                    {"id": document_id, "version": version},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise KnowledgeError(404, "DOCUMENT_NOT_FOUND", "Document not found")
        return dict(row)

    def _ticket(self, document_id: UUID, version: int, expiry: datetime) -> str:
        payload = json.dumps(
            {"document": str(document_id), "version": version, "expiry": int(expiry.timestamp())},
            separators=(",", ":"),
        ).encode()
        signature = hmac.new(
            self.settings.token_pepper.get_secret_value().encode(), payload, hashlib.sha256
        ).digest()
        return base64.urlsafe_b64encode(payload + signature).decode().rstrip("=")

    def _verify_ticket(self, value: str, document_id: UUID) -> int:
        try:
            raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            payload, signature = raw[:-32], raw[-32:]
            expected = hmac.new(
                self.settings.token_pepper.get_secret_value().encode(), payload, hashlib.sha256
            ).digest()
            data = json.loads(payload)
            if (
                not hmac.compare_digest(signature, expected)
                or data["document"] != str(document_id)
                or int(data["expiry"]) < int(datetime.now(UTC).timestamp())
            ):
                raise ValueError
            return int(data["version"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, binascii.Error) as exc:
            raise KnowledgeError(
                422, "INVALID_UPLOAD_TICKET", "Upload ticket is invalid or expired"
            ) from exc
