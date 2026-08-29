"""Real PostgreSQL coverage for the legacy cutover work items (G2/G4/G5).

These tests drive the cutover CLI helpers and the maintenance freeze service
against the project database image. Legacy ``public.*`` tables never exist in
the rehearsal database, so the exercises run against disposable ``ima.*``
checkpoint/pipeline rows only; object storage is replaced by a scripted fake
because no object store ships with the test image.
"""

# ruff: noqa: E501,ASYNC221

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy import text

import ima.cli as cli
from ima.application.authorization import WorkspaceService
from ima.application.knowledge import KnowledgeService
from ima.application.maintenance import (
    MAINTENANCE_WRITE_FREEZE,
    MaintenanceFreezeError,
    MaintenanceService,
)
from ima.config import Settings
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.storage import StorageClientError

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")
SYNC_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else None
ALEMBIC_URL = (
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://") if DATABASE_URL else None
)

requires_database = pytest.mark.skipif(
    not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured"
)

REINGEST_CORRELATION = "legacy-migration-reingest"


def migrate() -> None:
    assert ALEMBIC_URL
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).parents[2],
        env={**os.environ, "IMA_DATABASE_URL": ALEMBIC_URL},
        check=True,
    )


def cutover_settings() -> Settings:
    assert DATABASE_URL
    return Settings(
        environment="test",
        database_url=DATABASE_URL,
        session_pepper="cutover-integration-session",
        token_pepper="cutover-integration-token",
        totp_encryption_key="cutover-integration-totp-key",
        bridge_token="cutover-integration-bridge",
        smtp_host=None,
        smtp_from=None,
        storage_endpoint="https://storage.cutover-rehearsal.test",
        storage_bucket="cutover-rehearsal",
        storage_access_key_id="cutover-rehearsal-access",
        storage_secret_access_key="cutover-rehearsal-secret",
    )


def seed_user(connection: Any, user_id: str, *, super_admin: bool = False) -> None:
    stamp = datetime.now(UTC)
    connection.execute(
        """INSERT INTO ima.users
        (id,email,normalized_email,display_name,is_active,password_reset_required,
         security_stamp,created_at,updated_at)
        VALUES (%s,%s,%s,%s,true,false,%s,%s,%s)
        ON CONFLICT (id) DO UPDATE SET is_active=true,disabled_at=NULL""",
        (user_id, f"{user_id}@example.test", user_id, user_id, user_id, stamp, stamp),
    )
    if super_admin:
        connection.execute(
            "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) "
            "VALUES (%s,'super_admin',%s) ON CONFLICT DO NOTHING",
            (user_id, stamp),
        )


def seed_file_document(
    connection: Any,
    *,
    workspace_id: str,
    actor: str,
    title: str,
    mime_type: str,
    file_state: str = "pending",
    object_state: str = "verified",
) -> tuple[UUID, str]:
    """Insert one file document with a single verified file version."""
    document_id = uuid4()
    object_key = f"documents/{document_id}/{uuid4().hex}"
    connection.execute(
        """INSERT INTO ima.documents
        (id,workspace_id,folder_id,kind,title,normalized_title,current_version,
         file_state,mime_type,created_by,updated_by,created_at,updated_at)
        VALUES (%s,%s,%s,'file',%s,%s,1,%s,%s,%s,%s,now(),now())""",
        (
            document_id,
            workspace_id,
            workspace_id,
            title,
            title.lower(),
            file_state,
            mime_type,
            actor,
            actor,
        ),
    )
    connection.execute(
        """INSERT INTO ima.document_file_versions
        (document_id,version,workspace_id,generation,object_state,object_key,checksum,
         size_bytes,mime_type,original_filename,created_by,created_at,verified_at)
        VALUES (%s,1,%s,1,%s,%s,%s,%s,%s,%s,%s,now(),now())""",
        (
            document_id,
            workspace_id,
            object_state,
            object_key,
            hashlib.sha256(object_key.encode()).hexdigest(),
            16,
            mime_type,
            f"{title.lower()}.txt",
            actor,
        ),
    )
    return document_id, object_key


def cleanup_documents(connection: Any, workspace_id: str, actor_ids: tuple[str, ...]) -> None:
    connection.execute(
        "UPDATE ima.system_settings SET maintenance_write_freeze=false,"
        "maintenance_freeze_reason=NULL,maintenance_freeze_entered_at=NULL,"
        "maintenance_freeze_entered_by=NULL,updated_by=NULL"
    )
    connection.execute(
        "DELETE FROM ima.ingestion_jobs WHERE document_id IN "
        "(SELECT id FROM ima.documents WHERE workspace_id=%s)",
        (workspace_id,),
    )
    connection.execute(
        "DELETE FROM ima.storage_cleanup_jobs WHERE document_id IN "
        "(SELECT id FROM ima.documents WHERE workspace_id=%s)",
        (workspace_id,),
    )
    connection.execute(
        "DELETE FROM ima.document_file_versions WHERE workspace_id=%s", (workspace_id,)
    )
    connection.execute(
        "DELETE FROM ima.document_versions WHERE document_id IN "
        "(SELECT id FROM ima.documents WHERE workspace_id=%s)",
        (workspace_id,),
    )
    connection.execute(
        "DELETE FROM ima.document_tags WHERE document_id IN "
        "(SELECT id FROM ima.documents WHERE workspace_id=%s)",
        (workspace_id,),
    )
    connection.execute("DELETE FROM ima.documents WHERE workspace_id=%s", (workspace_id,))
    connection.execute("DELETE FROM ima.workspaces WHERE id=%s", (workspace_id,))
    for actor_id in actor_ids:
        connection.execute("DELETE FROM ima.audit_events WHERE actor_id=%s", (actor_id,))
        connection.execute(
            "DELETE FROM ima.platform_role_assignments WHERE user_id=%s", (actor_id,)
        )
        connection.execute("DELETE FROM ima.users WHERE id=%s", (actor_id,))


async def create_workspace_context(label: str) -> tuple[Any, str, str]:
    """Create engine + disposable workspace; returns (engine, workspace_id, actor)."""
    engine = create_engine(cutover_settings())
    workspace_service = WorkspaceService(engine, cutover_settings())
    digest = hashlib.sha256(label.encode()).hexdigest()[:16]
    actor = f"cutover-{digest}-actor"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """DELETE FROM ima.ingestion_jobs WHERE document_id IN
                (SELECT id FROM ima.documents WHERE workspace_id IN
                 (SELECT id FROM ima.workspaces WHERE created_by=:actor))"""
            ),
            {"actor": actor},
        )
        await conn.execute(
            text(
                """DELETE FROM ima.document_file_versions WHERE workspace_id IN
                (SELECT id FROM ima.workspaces WHERE created_by=:actor)"""
            ),
            {"actor": actor},
        )
        await conn.execute(
            text(
                """DELETE FROM ima.document_versions WHERE document_id IN
                (SELECT id FROM ima.documents WHERE workspace_id IN
                 (SELECT id FROM ima.workspaces WHERE created_by=:actor))"""
            ),
            {"actor": actor},
        )
        await conn.execute(
            text(
                """DELETE FROM ima.documents WHERE workspace_id IN
                (SELECT id FROM ima.workspaces WHERE created_by=:actor)"""
            ),
            {"actor": actor},
        )
        await conn.execute(
            text("DELETE FROM ima.workspaces WHERE created_by=:actor"), {"actor": actor}
        )
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id=:actor"), {"actor": actor}
        )
        await conn.execute(
            text("DELETE FROM ima.platform_role_assignments WHERE user_id=:actor"),
            {"actor": actor},
        )
        await conn.execute(text("DELETE FROM ima.users WHERE id=:actor"), {"actor": actor})
        stamp = datetime.now(UTC)
        await conn.execute(
            text(
                """INSERT INTO ima.users
                (id,email,normalized_email,display_name,is_active,password_reset_required,
                 security_stamp,created_at,updated_at)
                VALUES (:id,:email,:email,:id,true,false,:stamp,:now,:now)"""
            ),
            {"id": actor, "email": f"{actor}@example.test", "stamp": actor, "now": stamp},
        )
        await conn.execute(
            text(
                "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) "
                "VALUES (:id,'platform_admin',:now)"
            ),
            {"id": actor, "now": stamp},
        )
    workspace = await workspace_service.create_workspace(actor, f"Cutover {label}", actor)
    return engine, str(workspace["id"]), actor


@pytest.mark.postgres
@requires_database
def test_reconcile_report_maps_review_decisions_and_reruns_idempotently(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert SYNC_URL
    digest = uuid4().hex[:12]
    deleted = f"cutover-{digest}-deleted"
    reparented = f"cutover-{digest}-reparented"
    changed = f"cutover-{digest}-changed"
    with psycopg.connect(SYNC_URL) as connection:
        for source_id, last_error in (
            (deleted, "legacy_deleted"),
            (reparented, "reparented_folder"),
            (changed, "source_changed"),
        ):
            connection.execute(
                "INSERT INTO ima.legacy_knowledge_migration"
                "(source_kind,source_id,source_fingerprint,status,last_error,updated_at) "
                "VALUES ('entity',%s,%s,'review',%s,now())",
                (source_id, f"fingerprint-{source_id}", last_error),
            )
    monkeypatch.setattr(cli, "get_settings", cutover_settings)
    try:
        payloads = []
        for _ in range(2):
            with pytest.raises(SystemExit) as exit_code:
                cli._legacy_reconcile_report("knowledge")
            assert exit_code.value.code == 4
            payloads.append(json.loads(capsys.readouterr().out))
        # Rerun idempotence: same findings, checkpoints untouched.
        assert payloads[0] == payloads[1]
        findings = {finding["sourceId"]: finding for finding in payloads[0]["findings"]}
        assert findings[deleted]["rule"] == "legacy_deleted"
        assert findings[deleted]["decision"] == "propagate_trash"
        assert findings[reparented]["rule"] == "reparented_folder"
        assert findings[reparented]["decision"] == "delete_and_reimport_subtree"
        assert findings[changed]["rule"] == "source_changed"
        assert findings[changed]["decision"] == "operator_review"
        assert payloads[0]["secretValues"] is False
        with psycopg.connect(SYNC_URL) as connection:
            statuses = dict(
                connection.execute(
                    "SELECT source_id,status FROM ima.legacy_knowledge_migration "
                    "WHERE source_kind='entity' AND source_id LIKE %s",
                    (f"cutover-{digest}%",),
                ).fetchall()
            )
        assert statuses == {deleted: "review", reparented: "review", changed: "review"}
    finally:
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "DELETE FROM ima.legacy_knowledge_migration "
                "WHERE source_kind='entity' AND source_id LIKE %s",
                (f"cutover-{digest}%",),
            )


@pytest.mark.postgres
@requires_database
def test_reconcile_report_is_clean_once_reviews_resolved(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert SYNC_URL
    digest = uuid4().hex[:12]
    source_id = f"cutover-{digest}-resolved"
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.legacy_knowledge_migration"
            "(source_kind,source_id,source_fingerprint,status,last_error,updated_at) "
            "VALUES ('entity',%s,%s,'review','legacy_deleted',now())",
            (source_id, f"fingerprint-{source_id}"),
        )
    monkeypatch.setattr(cli, "get_settings", cutover_settings)
    try:
        with pytest.raises(SystemExit):
            cli._legacy_reconcile_report("knowledge")
        capsys.readouterr()
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "DELETE FROM ima.legacy_knowledge_migration "
                "WHERE source_kind='entity' AND source_id=%s",
                (source_id,),
            )
        cli._legacy_reconcile_report("knowledge")
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["findings"] == []
        assert payload["scope"] == "knowledge"
    finally:
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "DELETE FROM ima.legacy_knowledge_migration "
                "WHERE source_kind='entity' AND source_id LIKE %s",
                (f"cutover-{digest}%",),
            )


@pytest.mark.postgres
@requires_database
async def test_blob_verify_flags_missing_corrupt_and_orphan_objects(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine, workspace_id, actor = await create_workspace_context("blob-verify-bad")
    digest = uuid4().hex[:12]
    try:
        with psycopg.connect(SYNC_URL) as connection:
            ok_document, ok_key = seed_file_document(
                connection,
                workspace_id=workspace_id,
                actor=actor,
                title=f"Verified {digest}",
                mime_type="text/plain",
            )
            missing_document, missing_key = seed_file_document(
                connection,
                workspace_id=workspace_id,
                actor=actor,
                title=f"Missing {digest}",
                mime_type="text/plain",
            )
            corrupt_document, corrupt_key = seed_file_document(
                connection,
                workspace_id=workspace_id,
                actor=actor,
                title=f"Corrupt {digest}",
                mime_type="text/plain",
            )
            orphan_key = f"documents/orphan-{digest}"

        class FakeStorageClient:
            def __init__(self, settings: Settings) -> None:
                assert settings.storage_bucket == "cutover-rehearsal"

            def verify(self, key: str, checksum: str, size_bytes: int, mime_type: str) -> None:
                if key == missing_key:
                    raise StorageClientError("OBJECT_MISSING")
                if key == corrupt_key:
                    raise StorageClientError("OBJECT_VERIFICATION_FAILED")

            def list_keys(self, prefix: str, *, max_keys: int = 10000) -> list[str]:
                assert prefix == "documents/"
                return [ok_key, missing_key, corrupt_key, orphan_key]

        monkeypatch.setattr(cli, "get_settings", cutover_settings)
        monkeypatch.setattr(cli, "ObjectStorageClient", FakeStorageClient)
        with pytest.raises(SystemExit) as exit_code:
            cli._legacy_blob_verify()
        assert exit_code.value.code == 4
        report = json.loads(capsys.readouterr().out)
        assert report["ok"] is False
        assert report["storageConfigured"] is True
        assert report["checked"] == 3
        assert report["verified"] == 1
        missing_entries = {entry["objectKey"]: entry for entry in report["missing"]}
        assert set(missing_entries) == {missing_key}
        assert missing_entries[missing_key]["detail"] == "OBJECT_MISSING"
        assert missing_entries[missing_key]["documentId"] == str(missing_document)
        corrupt_entries = {entry["objectKey"]: entry for entry in report["corrupt"]}
        assert set(corrupt_entries) == {corrupt_key}
        assert corrupt_entries[corrupt_key]["detail"] == "OBJECT_VERIFICATION_FAILED"
        assert corrupt_entries[corrupt_key]["documentId"] == str(corrupt_document)
        assert report["orphans"] == [orphan_key]
        assert report["secretValues"] is False
        assert ok_document is not None
    finally:
        with psycopg.connect(SYNC_URL) as connection:
            cleanup_documents(connection, workspace_id, (actor,))
        await engine.dispose()


@pytest.mark.postgres
@requires_database
async def test_blob_verify_passes_when_all_objects_verify(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine, workspace_id, actor = await create_workspace_context("blob-verify-ok")
    digest = uuid4().hex[:12]
    try:
        with psycopg.connect(SYNC_URL) as connection:
            _document, verified_key = seed_file_document(
                connection,
                workspace_id=workspace_id,
                actor=actor,
                title=f"Sound {digest}",
                mime_type="text/plain",
            )

        class FakeStorageClient:
            def __init__(self, settings: Settings) -> None:
                assert settings.storage_bucket == "cutover-rehearsal"

            def verify(self, key: str, checksum: str, size_bytes: int, mime_type: str) -> None:
                assert checksum == hashlib.sha256(key.encode()).hexdigest()

            def list_keys(self, prefix: str, *, max_keys: int = 10000) -> list[str]:
                return [verified_key]

        monkeypatch.setattr(cli, "get_settings", cutover_settings)
        monkeypatch.setattr(cli, "ObjectStorageClient", FakeStorageClient)
        cli._legacy_blob_verify()
        report = json.loads(capsys.readouterr().out)
        assert report["ok"] is True
        assert report["checked"] == 1
        assert report["verified"] == 1
        assert report["missing"] == []
        assert report["corrupt"] == []
        assert report["orphans"] == []
    finally:
        with psycopg.connect(SYNC_URL) as connection:
            cleanup_documents(connection, workspace_id, (actor,))
        await engine.dispose()


class _FakeParseTask:
    def __init__(self) -> None:
        self.deferred: list[dict[str, Any]] = []

    def defer(self, **kwargs: Any) -> None:
        self.deferred.append(kwargs)


class _FakeTaskApp:
    def __init__(self) -> None:
        self.schema_manager = self

    def apply_schema(self) -> None:
        return None

    def open(self) -> nullcontext[None]:
        return nullcontext()


def _patch_reingest_tasks(monkeypatch: pytest.MonkeyPatch) -> _FakeParseTask:
    parse_task = _FakeParseTask()
    monkeypatch.setattr(cli, "get_settings", cutover_settings)
    monkeypatch.setattr(cli, "create_task_app", lambda settings: _FakeTaskApp())
    monkeypatch.setattr(
        cli, "register_ingestion_tasks", lambda task_app, settings: {"parse": parse_task}
    )
    return parse_task


@pytest.mark.postgres
@requires_database
async def test_reingest_enqueue_is_bounded_resumable_mime_gated_then_report_classifies(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine, workspace_id, actor = await create_workspace_context("reingest")
    digest = uuid4().hex[:12]
    try:
        with psycopg.connect(SYNC_URL) as connection:
            ready_document, _ = seed_file_document(
                connection,
                workspace_id=workspace_id,
                actor=actor,
                title=f"Reingest A {digest}",
                mime_type="text/plain",
            )
            failed_document, _ = seed_file_document(
                connection,
                workspace_id=workspace_id,
                actor=actor,
                title=f"Reingest B {digest}",
                mime_type="application/pdf",
            )
            unsupported_document, _ = seed_file_document(
                connection,
                workspace_id=workspace_id,
                actor=actor,
                title=f"Reingest C {digest}",
                mime_type="application/x-legacy-unsupported",
            )
            resumed_document, _ = seed_file_document(
                connection,
                workspace_id=workspace_id,
                actor=actor,
                title=f"Reingest D {digest}",
                mime_type="text/plain",
            )
            capacity_document, _ = seed_file_document(
                connection,
                workspace_id=workspace_id,
                actor=actor,
                title=f"Reingest E {digest}",
                mime_type="text/markdown",
            )
            for stage in ("parse", "chunk", "embed"):
                connection.execute(
                    "INSERT INTO ima.ingestion_jobs"
                    "(id,idempotency_key,document_id,version,generation,stage,status,"
                    " correlation_id,created_at,updated_at) "
                    "VALUES (%s,%s,%s,1,1,%s,'succeeded','prior-pipeline',now(),now())",
                    (uuid4(), f"{resumed_document}:1:1:{stage}", resumed_document, stage),
                )

        parse_task = _patch_reingest_tasks(monkeypatch)

        # Boundedness: the operator limit admits one job although three are eligible.
        cli._legacy_reingest_enqueue(limit=1, max_active=10)
        first = json.loads(capsys.readouterr().out)
        assert first["candidates"] == 3
        assert first["enqueued"] == 1
        assert first["activeParseJobs"] == 0
        assert len(parse_task.deferred) == 1

        # Boundedness by worker capacity: one active parse job fills max_active=1.
        cli._legacy_reingest_enqueue(limit=10, max_active=1)
        second = json.loads(capsys.readouterr().out)
        assert second["candidates"] == 2
        assert second["enqueued"] == 0
        assert second["activeParseJobs"] == 1
        assert len(parse_task.deferred) == 1

        # Resumability: the rerun admits the remaining eligible versions only.
        cli._legacy_reingest_enqueue(limit=10, max_active=10)
        third = json.loads(capsys.readouterr().out)
        assert third["candidates"] == 2
        assert third["enqueued"] == 2
        assert len(parse_task.deferred) == 3

        with psycopg.connect(SYNC_URL) as connection:
            # Unsupported MIME and already-pipelined versions get no reingest jobs.
            assert (
                connection.execute(
                    "SELECT count(*) FROM ima.ingestion_jobs WHERE document_id IN (%s,%s) "
                    "AND correlation_id=%s",
                    (unsupported_document, resumed_document, REINGEST_CORRELATION),
                ).fetchone()[0]
                == 0
            )
            jobs = connection.execute(
                "SELECT document_id,stage,status,idempotency_key,generation "
                "FROM ima.ingestion_jobs WHERE correlation_id=%s ORDER BY document_id,stage",
                (REINGEST_CORRELATION,),
            ).fetchall()
            assert len(jobs) == 9
            by_document: dict[str, dict[str, str]] = {}
            for document_id, stage, status, idempotency_key, generation in jobs:
                by_document.setdefault(str(document_id), {})[stage] = status
                assert idempotency_key == f"{document_id}:1:{generation}:{stage}"
            assert set(by_document) == {
                str(ready_document),
                str(failed_document),
                str(capacity_document),
            }
            for stages in by_document.values():
                assert stages["parse"] in {"queued", "running", "retryable"}
                assert stages["chunk"] == "blocked"
                assert stages["embed"] == "blocked"

            # Readiness report: drive every classification bucket.
            connection.execute(
                "UPDATE ima.documents SET file_state='ready' WHERE id=%s", (ready_document,)
            )
            connection.execute(
                "UPDATE ima.ingestion_jobs SET status='failed' "
                "WHERE document_id=%s AND stage='parse'",
                (failed_document,),
            )
            connection.execute(
                "UPDATE ima.ingestion_jobs SET status='succeeded' "
                "WHERE document_id=%s AND stage='parse'",
                (capacity_document,),
            )
            connection.execute(
                "UPDATE ima.ingestion_jobs SET status='dead_letter' "
                "WHERE document_id=%s AND stage='chunk'",
                (capacity_document,),
            )

        with pytest.raises(SystemExit) as exit_code:
            cli._legacy_reingest_report()
        assert exit_code.value.code == 4
        report = json.loads(capsys.readouterr().out)
        assert report["byMimeType"]["text/plain"] == {
            "ready": 1,
            "degraded": 0,
            "failed": 0,
            "pending": 1,
        }
        assert report["byMimeType"]["application/pdf"]["failed"] == 1
        assert report["byMimeType"]["text/markdown"]["degraded"] == 1
        assert report["byMimeType"]["application/x-legacy-unsupported"]["degraded"] == 1
        assert report["totals"] == {"ready": 1, "degraded": 2, "failed": 1, "pending": 1}
        assert report["unsupportedMimeDocuments"] == [str(unsupported_document)]
        assert report["ok"] is False
        assert report["secretValues"] is False
    finally:
        with psycopg.connect(SYNC_URL) as connection:
            cleanup_documents(connection, workspace_id, (actor,))
        await engine.dispose()


@pytest.mark.postgres
@requires_database
def test_conversations_archive_reports_counts_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "get_settings", cutover_settings)
    cli._legacy_conversations_archive()
    report = json.loads(capsys.readouterr().out)
    assert report["canonicalResource"] == "/conversations"
    assert report["migrated"] is False
    assert report["decision"] == "counts_only_archive"
    assert report["totalRows"] == sum(report["tables"].values())
    assert set(report["tables"]) <= {"chat", "message", "messageEntity", "toolCall"}
    assert report["secretValues"] is False


@pytest.mark.postgres
@requires_database
async def test_freeze_guard_blocks_bridge_mutations_and_allows_migration_writes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert SYNC_URL
    engine, workspace_id, actor = await create_workspace_context("freeze")
    digest = uuid4().hex[:12]
    admin = f"cutover-{digest}-admin"
    service = MaintenanceService(engine)
    knowledge = KnowledgeService(engine, WorkspaceService(engine, cutover_settings()))
    try:
        with psycopg.connect(SYNC_URL) as connection:
            seed_user(connection, admin, super_admin=True)

        # Only active super-admins may operate the freeze.
        with pytest.raises(PermissionError):
            await service.enter_freeze(actor, "not authorized")

        entered = await service.enter_freeze(admin, f"cutover rehearsal {digest}")
        assert entered["frozen"] is True
        assert entered["enteredBy"] == admin
        assert entered["reason"] == f"cutover rehearsal {digest}"
        assert entered["secretValues"] is False

        # Bridge-served mutations are refused with the typed RFC 9457 problem.
        with pytest.raises(MaintenanceFreezeError) as refusal:
            await knowledge.create_note(actor, workspace_id, f"Frozen {digest}", "text")
        assert refusal.value.status_code == 503
        assert refusal.value.code == MAINTENANCE_WRITE_FREEZE

        # Migration-tagged writers keep working through the freeze.
        with psycopg.connect(SYNC_URL) as connection:
            migration_document, _ = seed_file_document(
                connection,
                workspace_id=workspace_id,
                actor=actor,
                title=f"Migration write {digest}",
                mime_type="text/plain",
            )
        parse_task = _patch_reingest_tasks(monkeypatch)
        cli._legacy_reingest_enqueue(limit=5, max_active=5)
        enqueue_report = json.loads(capsys.readouterr().out)
        assert enqueue_report["enqueued"] == 1
        assert len(parse_task.deferred) == 1
        with psycopg.connect(SYNC_URL) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM ima.ingestion_jobs "
                    "WHERE document_id=%s AND correlation_id=%s",
                    (migration_document, REINGEST_CORRELATION),
                ).fetchone()[0]
                == 3
            )

        status = await service.freeze_status()
        assert status["frozen"] is True
        with psycopg.connect(SYNC_URL) as connection:
            actions = {
                row[0]
                for row in connection.execute(
                    "SELECT action FROM ima.audit_events WHERE actor_id=%s", (admin,)
                ).fetchall()
            }
            assert actions == {"maintenance.freeze.enter"}
            metadata = json.loads(
                connection.execute(
                    "SELECT metadata::text FROM ima.audit_events "
                    "WHERE actor_id=%s AND action='maintenance.freeze.enter'",
                    (admin,),
                ).fetchone()[0]
            )
            assert metadata == {"reason": f"cutover rehearsal {digest}", "secretValues": False}

        exited = await service.exit_freeze(admin)
        assert exited["frozen"] is False
        assert exited["enteredBy"] is None

        # Mutations succeed again after the freeze exits.
        note = await knowledge.create_note(actor, workspace_id, f"After freeze {digest}", "text")
        assert note["id"] is not None
        with psycopg.connect(SYNC_URL) as connection:
            actions = {
                row[0]
                for row in connection.execute(
                    "SELECT action FROM ima.audit_events WHERE actor_id=%s", (admin,)
                ).fetchall()
            }
            assert actions == {"maintenance.freeze.enter", "maintenance.freeze.exit"}
    finally:
        with psycopg.connect(SYNC_URL) as connection:
            cleanup_documents(connection, workspace_id, (actor, admin))
        await engine.dispose()


@pytest.mark.postgres
@requires_database
async def test_cutover_rehearsal_records_gate_results(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Disposable rehearsal: apply → verify → freeze → delta → routing configs.

    The routing JSON derivation itself is pinned in the Bun drill
    (``bun run test:caddy-routing``); here the rehearsal records that both
    artifacts stay contractually wired into the drill and the runbook.
    """
    assert SYNC_URL
    gates: dict[str, bool] = {}

    # Sanitize the shared rehearsal database: sibling importer suites leave
    # checkpoints whose legacy rows were deleted plus legacy fixtures, which
    # reconcile would legitimately flag. The rehearsal gates run on a clean
    # dataset, so clear migration bookkeeping and legacy fixtures first.
    with psycopg.connect(SYNC_URL) as connection:
        for table in (
            "ima.legacy_identity_migration",
            "ima.workspace_authorization_migration",
            "ima.legacy_knowledge_migration",
            "ima.legacy_model_governance_migration",
        ):
            connection.execute(f"DELETE FROM {table}")
        if connection.execute("SELECT to_regclass('public.\"workspace\"')").fetchone()[0]:
            connection.execute('DELETE FROM public."workspace"')
        if connection.execute("SELECT to_regclass('public.\"user\"')").fetchone()[0]:
            if connection.execute("SELECT to_regclass('public.\"userData\"')").fetchone()[0]:
                connection.execute('DELETE FROM public."userData"')
            connection.execute('DELETE FROM public."user"')

    # apply: the schema is at the maintenance-freeze head, additive only.
    migrate()
    with psycopg.connect(SYNC_URL) as connection:
        head = connection.execute("SELECT version_num FROM ima.alembic_version").fetchone()[0]
        freeze_columns = {
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='ima' AND table_name='system_settings'"
            ).fetchall()
        }
    gates["apply"] = (
        head == "20260828_0010"
        and {
            "maintenance_write_freeze",
            "maintenance_freeze_reason",
            "maintenance_freeze_entered_at",
            "maintenance_freeze_entered_by",
        }
        <= freeze_columns
    )

    monkeypatch.setattr(cli, "get_settings", cutover_settings)

    # verify: read-only inventory gate with no pending connectors.
    cli._legacy_report_all()
    inventory = json.loads(capsys.readouterr().out)
    gates["verify"] = inventory["complete"] is True and inventory["secretValues"] is False

    # delta: reconcile over all scopes is clean on the sanitized dataset.
    cli._legacy_reconcile_report("all")
    delta = json.loads(capsys.readouterr().out)
    gates["delta"] = delta["ok"] is True and delta["findings"] == []

    # freeze: enter → status → exit with audit rows, on a disposable operator.
    digest = uuid4().hex[:12]
    admin = f"cutover-{digest}-rehearsal"
    with psycopg.connect(SYNC_URL) as connection:
        seed_user(connection, admin, super_admin=True)
    try:
        engine = create_engine(cutover_settings())
        service = MaintenanceService(engine)
        entered = await service.enter_freeze(admin, f"rehearsal {digest}")
        status = await service.freeze_status()
        exited = await service.exit_freeze(admin)
        await engine.dispose()
        with psycopg.connect(SYNC_URL) as connection:
            actions = {
                row[0]
                for row in connection.execute(
                    "SELECT action FROM ima.audit_events WHERE actor_id=%s", (admin,)
                ).fetchall()
            }
        gates["freeze"] = (
            entered["frozen"] is True
            and status["frozen"] is True
            and exited["frozen"] is False
            and actions == {"maintenance.freeze.enter", "maintenance.freeze.exit"}
        )
    finally:
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "UPDATE ima.system_settings SET maintenance_write_freeze=false,"
                "maintenance_freeze_reason=NULL,maintenance_freeze_entered_at=NULL,"
                "maintenance_freeze_entered_by=NULL,updated_by=NULL"
            )
            connection.execute("DELETE FROM ima.audit_events WHERE actor_id=%s", (admin,))
            connection.execute(
                "DELETE FROM ima.platform_role_assignments WHERE user_id=%s", (admin,)
            )
            connection.execute("DELETE FROM ima.users WHERE id=%s", (admin,))

    # cutover-config / rollback-config: pinned derivation artifacts.
    root = Path(__file__).parents[3]
    drill = (root / "scripts/caddy-routing-drill.ts").read_text(encoding="utf-8")
    runbook = (root / "docs/legacy-cutover-runbook.md").read_text(encoding="utf-8")
    gates["cutover-config"] = (
        all(token in drill for token in ("buildCutoverConfig", "cutover.json", "'cutover'"))
        and "`cutover.json`" in runbook
    )
    gates["rollback-config"] = (
        all(
            token in drill
            for token in ("buildRollbackConfig", "rollback.json", "pre_sunset_rollback")
        )
        and "`rollback.json`" in runbook
    )

    assert gates == {
        "apply": True,
        "verify": True,
        "delta": True,
        "freeze": True,
        "cutover-config": True,
        "rollback-config": True,
    }
