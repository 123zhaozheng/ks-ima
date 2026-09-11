"""PostgreSQL coverage for ingestion terminal states and cancellation semantics."""

# Real PostgreSQL constraints and transactions; no mocks.
# ruff: noqa: E501, ASYNC221

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy import text

from ima.application.storage import StorageService
from ima.config import Settings
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.tasks.app import create_task_app
from ima.infrastructure.tasks.ingestion import (
    finalize_cancel_requested,
    mark_document_terminal,
    register_ingestion_tasks,
)
from ima.infrastructure.tasks.service import JobService
from ima.workers.main import reconcile_once

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")
SYNC_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else None


def settings_for(digest: str) -> Settings:
    assert DATABASE_URL
    return Settings(
        environment="test",
        database_url=DATABASE_URL,
        session_pepper="ingestion-state-session",
        token_pepper="ingestion-state-token",
        totp_encryption_key="ingestion-state-totp-key",
        smtp_host=None,
        smtp_from=None,
        ingestion_queue=f"it-{digest}",
    )


def remove(queue_name: str, kb_id: str, actor: str) -> None:
    """Delete every row this test's deterministic actor/kb created."""
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "DELETE FROM ima_jobs.procrastinate_jobs WHERE queue_name=%s", (queue_name,)
        )
        connection.execute(
            "DELETE FROM ima.ingestion_jobs WHERE document_id IN (SELECT id FROM ima.documents WHERE kb_id=%s)",
            (kb_id,),
        )
        connection.execute(
            "DELETE FROM ima.document_derived_text WHERE document_id IN (SELECT id FROM ima.documents WHERE kb_id=%s)",
            (kb_id,),
        )
        connection.execute(
            "DELETE FROM ima.document_chunks WHERE document_id IN (SELECT id FROM ima.documents WHERE kb_id=%s)",
            (kb_id,),
        )
        connection.execute("DELETE FROM ima.document_file_versions WHERE kb_id=%s", (kb_id,))
        connection.execute("DELETE FROM ima.knowledge_bases WHERE id=%s", (kb_id,))
        connection.execute("DELETE FROM ima.audit_events WHERE actor_id=%s", (actor,))
        connection.execute("DELETE FROM ima.users WHERE id=%s", (actor,))
        connection.commit()


async def create_context(
    label: str,
    *,
    file_state: str = "pending",
    object_state: str = "pending",
    statuses: dict[str, str] | None = None,
) -> Any:
    """Seed one isolated file document plus its three ingestion stages."""
    digest = hashlib.sha256(label.encode()).hexdigest()[:16]
    cfg = settings_for(digest)
    actor, kb_id = f"ingest-{digest}", f"ikb-{digest}"
    # The root folder's id must equal its knowledge base id (folders_check).
    folder_id = kb_id
    document_id, ts = uuid4(), datetime.now(UTC)
    checksum = digest * 4
    object_key = f"it/{digest}/{document_id}"
    statuses = statuses or {"parse": "queued", "chunk": "blocked", "embed": "blocked"}
    remove(cfg.ingestion_queue, kb_id, actor)
    engine = create_engine(cfg)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """INSERT INTO ima.users
                (id,email,normalized_email,display_name,is_active,password_reset_required,
                 security_stamp,created_at,updated_at)
                VALUES (:id,:email,:email,:id,true,false,:id,:now,:now)"""
            ),
            {"id": actor, "email": f"{actor}@example.test", "now": ts},
        )
        await conn.execute(
            text(
                """INSERT INTO ima.knowledge_bases(id,name,is_active,created_by,created_at,updated_at)
                VALUES (:kb,:name,true,:actor,:now,:now)"""
            ),
            {"kb": kb_id, "name": f"Ingestion {label}", "actor": actor, "now": ts},
        )
        await conn.execute(
            text(
                """INSERT INTO ima.kb_members(kb_id,user_id,role,state,version,joined_at)
                VALUES (:kb,:actor,'owner','active',1,:now)"""
            ),
            {"kb": kb_id, "actor": actor, "now": ts},
        )
        await conn.execute(
            text(
                """INSERT INTO ima.folders
                (id,kb_id,parent_id,name,normalized_name,order_key,lifecycle,version,is_root,
                 created_by,created_at,updated_at)
                VALUES (:folder,:kb,NULL,'Root','root',0,'active',1,true,:actor,:now,:now)"""
            ),
            {"folder": folder_id, "kb": kb_id, "actor": actor, "now": ts},
        )
        await conn.execute(
            text(
                """INSERT INTO ima.documents
                (id,kb_id,folder_id,kind,title,normalized_title,current_version,file_state,
                 mime_type,size_bytes,checksum,storage_key,created_by,updated_by,created_at,updated_at)
                VALUES (:id,:kb,:folder,'file','doc.txt','doc.txt',1,:state,
                        'text/plain',5,:checksum,:key,:actor,:actor,:now,:now)"""
            ),
            {
                "id": document_id,
                "kb": kb_id,
                "folder": folder_id,
                "state": file_state,
                "checksum": checksum,
                "key": object_key,
                "actor": actor,
                "now": ts,
            },
        )
        await conn.execute(
            text(
                """INSERT INTO ima.document_file_versions
                (document_id,version,kb_id,object_state,object_key,checksum,size_bytes,mime_type,
                 original_filename,created_by,created_at)
                VALUES (:id,1,:kb,:state,:key,:checksum,5,'text/plain','doc.txt',:actor,:now)"""
            ),
            {
                "id": document_id,
                "kb": kb_id,
                "state": object_state,
                "key": object_key,
                "checksum": checksum,
                "actor": actor,
                "now": ts,
            },
        )
        for stage, status in statuses.items():
            await conn.execute(
                text(
                    """INSERT INTO ima.ingestion_jobs
                    (id,idempotency_key,document_id,version,generation,stage,status,created_by,
                     created_at,updated_at)
                    VALUES (:id,:key,:document,1,1,:stage,:status,:actor,:now,:now)"""
                ),
                {
                    "id": uuid4(),
                    "key": f"{document_id}:1:1:{stage}",
                    "document": document_id,
                    "stage": stage,
                    "status": status,
                    "actor": actor,
                    "now": ts,
                },
            )
    jobs: dict[str, UUID] = {}
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT stage,id FROM ima.ingestion_jobs WHERE document_id=:id"),
                {"id": document_id},
            )
        ).mappings()
        jobs = {str(row["stage"]): row["id"] for row in rows}
    return SimpleNamespace(
        engine=engine,
        cfg=cfg,
        storage=StorageService(cfg, engine, JobService(cfg, engine)),
        actor=actor,
        kb_id=kb_id,
        document_id=document_id,
        jobs=jobs,
    )


async def cleanup(ctx: Any) -> None:
    await ctx.engine.dispose()
    remove(ctx.cfg.ingestion_queue, ctx.kb_id, ctx.actor)


async def read_state(engine: Any, document_id: UUID, stage: str) -> tuple[str | None, str | None]:
    async with engine.connect() as conn:
        state = await conn.scalar(
            text("SELECT file_state FROM ima.documents WHERE id=:id"), {"id": document_id}
        )
        status = await conn.scalar(
            text("SELECT status FROM ima.ingestion_jobs WHERE document_id=:id AND stage=:stage"),
            {"id": document_id, "stage": stage},
        )
    return state, status


pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")


@pytest.mark.postgres
async def test_cancelling_a_queued_ingestion_is_immediate_and_terminal() -> None:
    ctx = await create_context("queued-cancel")
    try:
        await ctx.storage.cancel(ctx.actor, ctx.document_id)
        async with ctx.engine.connect() as conn:
            statuses = dict(
                (
                    await conn.execute(
                        text("SELECT stage,status FROM ima.ingestion_jobs WHERE document_id=:id"),
                        {"id": ctx.document_id},
                    )
                ).all()
            )
            state = await conn.scalar(
                text("SELECT file_state FROM ima.documents WHERE id=:id"),
                {"id": ctx.document_id},
            )
        # No worker is involved: queued/blocked stages reach cancelled directly
        # and the document leaves the pending state.
        assert set(statuses.values()) == {"cancelled"}
        assert "cancel_requested" not in statuses.values()
        assert state == "failed"
    finally:
        await cleanup(ctx)


@pytest.mark.postgres
async def test_cancelling_a_running_stage_is_cooperative_and_worker_finalizes() -> None:
    ctx = await create_context(
        "running-cancel", statuses={"parse": "running", "chunk": "blocked", "embed": "blocked"}
    )
    try:
        async with ctx.engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.ingestion_jobs SET lease_expires_at=:lease WHERE id=:id"),
                {"lease": datetime.now(UTC) + timedelta(minutes=5), "id": ctx.jobs["parse"]},
            )
        await ctx.storage.cancel(ctx.actor, ctx.document_id)
        state, parse_status = await read_state(ctx.engine, ctx.document_id, "parse")
        assert parse_status == "cancel_requested"
        assert state == "failed"

        async with ctx.engine.begin() as conn:
            assert await finalize_cancel_requested(conn, ctx.jobs["parse"]) is True
        _, parse_status = await read_state(ctx.engine, ctx.document_id, "parse")
        assert parse_status == "cancelled"
    finally:
        await cleanup(ctx)


@pytest.mark.postgres
async def test_terminal_parse_failure_marks_the_document_failed() -> None:
    # A file row that is not verified makes the real parse task take its
    # terminal OBJECT_MISSING branch.
    ctx = await create_context("failure", object_state="pending")
    try:
        app = create_task_app(ctx.cfg)
        tasks = register_ingestion_tasks(app, ctx.cfg)
        await tasks["parse"].func(None, str(ctx.document_id), 1, 1)
        state, parse_status = await read_state(ctx.engine, ctx.document_id, "parse")
        assert parse_status == "failed"
        assert state == "failed"
    finally:
        await cleanup(ctx)


@pytest.mark.postgres
async def test_reconcile_reaps_orphaned_cancel_requested() -> None:
    ctx = await create_context(
        "orphan-cancel",
        statuses={"parse": "cancel_requested", "chunk": "blocked", "embed": "blocked"},
    )
    try:
        spies = {stage: _DeferSpy() for stage in ("parse", "chunk", "embed", "cleanup")}
        await reconcile_once(ctx.engine, spies, datetime.now(UTC))
        state, parse_status = await read_state(ctx.engine, ctx.document_id, "parse")
        assert parse_status == "cancelled"
        assert state == "failed"
        # A reaped cancellation is finalized in place, never redelivered.
        assert not any(spy.calls for spy in spies.values())
    finally:
        await cleanup(ctx)


@pytest.mark.postgres
async def test_ready_document_is_never_clobbered_by_a_terminal_write() -> None:
    ctx = await create_context(
        "ready-guard",
        file_state="ready",
        statuses={"parse": "running", "chunk": "blocked", "embed": "blocked"},
    )
    try:
        async with ctx.engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.ingestion_jobs SET lease_expires_at=:lease WHERE id=:id"),
                {"lease": datetime.now(UTC) + timedelta(minutes=5), "id": ctx.jobs["parse"]},
            )
        await ctx.storage.cancel(ctx.actor, ctx.document_id)
        async with ctx.engine.begin() as conn:
            await finalize_cancel_requested(conn, ctx.jobs["parse"])
            await mark_document_terminal(conn, ctx.document_id)
        state, _ = await read_state(ctx.engine, ctx.document_id, "parse")
        assert state == "ready"
    finally:
        await cleanup(ctx)


@pytest.mark.postgres
async def test_retry_resets_the_document_to_pending() -> None:
    ctx = await create_context(
        "retry-reset",
        file_state="failed",
        statuses={"parse": "failed", "chunk": "blocked", "embed": "blocked"},
    )
    try:
        await ctx.storage.jobs.start()
        try:
            await ctx.storage.retry(ctx.actor, ctx.document_id)
        finally:
            await ctx.storage.jobs.stop()
        state, parse_status = await read_state(ctx.engine, ctx.document_id, "parse")
        assert parse_status == "queued"
        assert state == "pending"
    finally:
        await cleanup(ctx)


@pytest.mark.postgres
async def test_retry_restarts_from_a_failed_chunk_without_downgrading_parse() -> None:
    # Parse succeeded before chunk failed: re-deferring parse would be a no-op,
    # so retry must restart chunk (and keep the succeeded parse) instead.
    ctx = await create_context(
        "retry-chunk",
        file_state="failed",
        statuses={"parse": "succeeded", "chunk": "failed", "embed": "blocked"},
    )
    try:
        await ctx.storage.jobs.start()
        try:
            await ctx.storage.retry(ctx.actor, ctx.document_id)
        finally:
            await ctx.storage.jobs.stop()
        state, parse_status = await read_state(ctx.engine, ctx.document_id, "parse")
        _, chunk_status = await read_state(ctx.engine, ctx.document_id, "chunk")
        assert parse_status == "succeeded"
        assert chunk_status == "queued"
        assert state == "pending"
    finally:
        await cleanup(ctx)


class _DeferSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def defer_async(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
