"""Ask scope wiring on real PostgreSQL: folder/document filters and conversation scope.

The folder scope matches the whole subtree through ima.folder_closure, the
document scope pins one document, scope targets must exist inside the
knowledge base, and a conversation pins its scope at creation for follow-ups
and retries.
"""

# Fixture SQL keeps long statements intact for review.
# ruff: noqa: E501

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ima.application.model_governance import ModelGovernanceService
from ima.application.search import AskScope, SearchError, SearchService
from ima.config import Settings

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")
SYNC_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else None
ALEMBIC_URL = (
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://") if DATABASE_URL else None
)


def migrate() -> None:
    assert ALEMBIC_URL
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).parents[2],
        env={**os.environ, "IMA_DATABASE_URL": ALEMBIC_URL},
        check=True,
    )


def scope_services() -> tuple[SearchService, ModelGovernanceService, AsyncEngine]:
    assert DATABASE_URL
    engine = create_async_engine(DATABASE_URL)
    models = ModelGovernanceService(engine, Settings(environment="test"))
    return SearchService(engine, models), models, engine


def seed_actor(actor_id: str) -> None:
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.users(id,email,normalized_email,display_name,security_stamp,created_at,updated_at) VALUES (%s,%s,%s,%s,'scope-stamp',now(),now()) ON CONFLICT DO NOTHING",
            (actor_id, f"{actor_id}@scope.test", f"{actor_id}@scope.test", "Scope Actor"),
        )
        connection.commit()


def seed_folder(
    connection: psycopg.Connection,
    kb_id: str,
    folder_id: str,
    parent_id: str | None,
    name: str,
) -> None:
    connection.execute(
        "INSERT INTO ima.folders(id,kb_id,parent_id,name,normalized_name,order_key,lifecycle,version,is_root,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,0,'active',1,%s,now(),now())",
        (folder_id, kb_id, parent_id, name, name.casefold(), parent_id is None),
    )
    connection.execute(
        "INSERT INTO ima.folder_closure(kb_id,ancestor_id,descendant_id,depth) SELECT %s,ancestor_id,%s,depth+1 FROM ima.folder_closure WHERE kb_id=%s AND descendant_id=%s UNION ALL SELECT %s,%s,%s,0 ON CONFLICT DO NOTHING",
        (kb_id, folder_id, kb_id, parent_id, kb_id, folder_id, folder_id),
    )


def seed_document(
    connection: psycopg.Connection,
    kb_id: str,
    folder_id: str,
    document_id: Any,
    title: str,
    text_content: str,
    seed: int,
) -> None:
    """One file document with a single FTS-searchable chunk (no embedding)."""
    checksum = f"{seed:064x}"
    digest = f"{seed + 4096:064x}"
    connection.execute(
        "INSERT INTO ima.documents(id,kb_id,folder_id,kind,title,normalized_title,current_version,file_state,created_at,updated_at) VALUES (%s,%s,%s,'file',%s,%s,1,'ready',now(),now())",
        (document_id, kb_id, folder_id, title, title.casefold()),
    )
    connection.execute(
        "INSERT INTO ima.document_file_versions(document_id,version,kb_id,object_state,object_key,checksum,size_bytes,mime_type,original_filename,created_at) VALUES (%s,1,%s,'verified',%s,%s,11,'text/plain',%s,now())",
        (document_id, kb_id, f"it/{kb_id}/{document_id}", checksum, f"{title}.txt"),
    )
    connection.execute(
        "INSERT INTO ima.document_derived_text(document_id,version,generation,parser_name,parser_version,source_checksum,text_digest,text_content,status,created_at) VALUES (%s,1,1,'test','1',%s,%s,%s,'ready',now())",
        (document_id, checksum, digest, text_content),
    )
    connection.execute(
        "INSERT INTO ima.document_chunks(kb_id,document_id,version,generation,ordinal,text_content,content_digest,embedding_status,created_at,updated_at) VALUES (%s,%s,1,1,0,%s,%s,'pending',now(),now())",
        (kb_id, document_id, text_content, digest),
    )


def seed_corpus(kb_id: str, actor_id: str) -> dict[str, Any]:
    """Folder A with child B plus sibling C, one searchable chunk per folder."""
    ids: dict[str, Any] = {
        "folder_a": f"{kb_id}-fa",
        "folder_b": f"{kb_id}-fb",
        "folder_c": f"{kb_id}-fc",
        "doc_a": uuid4(),
        "doc_b": uuid4(),
        "doc_c": uuid4(),
    }
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.knowledge_bases(id,name,is_active,created_at,updated_at) VALUES (%s,'Scope KB',true,now(),now())",
            (kb_id,),
        )
        connection.execute(
            "INSERT INTO ima.kb_members(kb_id,user_id,role,joined_at) VALUES (%s,%s,'owner',now())",
            (kb_id, actor_id),
        )
        seed_folder(connection, kb_id, kb_id, None, "Root")
        seed_folder(connection, kb_id, ids["folder_a"], kb_id, "Folder A")
        seed_folder(connection, kb_id, ids["folder_b"], ids["folder_a"], "Folder B")
        seed_folder(connection, kb_id, ids["folder_c"], kb_id, "Folder C")
        seed_document(
            connection, kb_id, ids["folder_a"], ids["doc_a"], "Doc A", "hello scope alpha", 1
        )
        seed_document(
            connection, kb_id, ids["folder_b"], ids["doc_b"], "Doc B", "hello scope beta", 2
        )
        seed_document(
            connection, kb_id, ids["folder_c"], ids["doc_c"], "Doc C", "hello scope gamma", 3
        )
        connection.commit()
    return ids


def seed_keyword_chat_scene(actor_id: str) -> Any:
    """Grounded-Ask scene default pinned to keyword retrieval.

    Published profile versions are immutable, so the whole chain is inserted
    directly with retrievalMode already in the config.
    """
    gateway_id, model_id, profile_id = uuid4(), uuid4(), uuid4()
    config = json.dumps(
        {
            "chatModelId": str(model_id),
            "systemPrompt": "You are a helpful assistant.",
            "contextLimit": 32768,
            "outputLimit": 2048,
            "retrievalMode": "keyword",
        }
    )
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        # Idempotent on shared dev databases: replace any prior grounded-Ask default.
        connection.execute("DELETE FROM ima.scene_defaults WHERE workflow='grounded_ask'")
        connection.execute(
            "DELETE FROM ima.capability_profile_versions WHERE profile_id IN (SELECT id FROM ima.capability_profiles WHERE workflow='grounded_ask' AND business_alias='场景默认')"
        )
        connection.execute(
            "DELETE FROM ima.capability_profiles WHERE workflow='grounded_ask' AND business_alias='场景默认'"
        )
        connection.execute(
            "INSERT INTO ima.model_gateways(id,name,normalized_base_url,allowed_capabilities,tls_mode,enabled,connect_timeout_ms,read_timeout_ms,write_timeout_ms,pool_timeout_ms,max_response_bytes,created_at,updated_at) VALUES (%s,%s,'https://gateway.internal',ARRAY['chat'],'required',true,1000,10000,10000,1000,1048576,now(),now())",
            (gateway_id, f"pg-scope-{uuid4().hex[:12]}"),
        )
        connection.execute(
            "INSERT INTO ima.governed_models(id,gateway_id,remote_name,capability,business_label,enabled,validated,created_at,updated_at) VALUES (%s,%s,'chat-model','chat','Chat',true,true,now(),now())",
            (model_id, gateway_id),
        )
        connection.execute(
            "INSERT INTO ima.model_gateway_health(gateway_id,capability,state,checked_at) VALUES (%s,'chat','healthy',now())",
            (gateway_id,),
        )
        connection.execute(
            "INSERT INTO ima.capability_profiles(id,workflow,business_alias,description,lifecycle,current_version,created_by,created_at,updated_at) VALUES (%s,'grounded_ask','场景默认','scope integration','active',1,%s,now(),now())",
            (profile_id, actor_id),
        )
        connection.execute(
            "INSERT INTO ima.capability_profile_versions(profile_id,version,state,config,config_digest,published_at,published_by,created_at,updated_at) VALUES (%s,1,'published',%s,'scope-digest',now(),%s,now(),now())",
            (profile_id, config, actor_id),
        )
        connection.execute(
            "INSERT INTO ima.scene_defaults(workflow,profile_id,updated_at,updated_by) VALUES ('grounded_ask',%s,now(),%s) ON CONFLICT (workflow) DO UPDATE SET profile_id=EXCLUDED.profile_id,updated_at=now(),updated_by=EXCLUDED.updated_by",
            (profile_id, actor_id),
        )
        connection.commit()
    return gateway_id


def cleanup_scope_fixtures(
    kb_ids: tuple[str, ...],
    *,
    gateway_ids: tuple[Any, ...] = (),
    actor_ids: tuple[str, ...] = (),
    scene: bool = False,
) -> None:
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        for kb_id in kb_ids:
            connection.execute(
                "DELETE FROM ima.message_citations WHERE message_id IN (SELECT id FROM ima.conversation_messages WHERE kb_id=%s)",
                (kb_id,),
            )
            connection.execute("DELETE FROM ima.conversation_messages WHERE kb_id=%s", (kb_id,))
            connection.execute("DELETE FROM ima.conversations WHERE kb_id=%s", (kb_id,))
            connection.execute("DELETE FROM ima.document_chunks WHERE kb_id=%s", (kb_id,))
            connection.execute(
                "DELETE FROM ima.document_derived_text WHERE document_id IN (SELECT id FROM ima.documents WHERE kb_id=%s)",
                (kb_id,),
            )
            connection.execute("DELETE FROM ima.document_file_versions WHERE kb_id=%s", (kb_id,))
            connection.execute("DELETE FROM ima.documents WHERE kb_id=%s", (kb_id,))
            connection.execute("DELETE FROM ima.folder_closure WHERE kb_id=%s", (kb_id,))
            connection.execute("DELETE FROM ima.folders WHERE kb_id=%s", (kb_id,))
            connection.execute("DELETE FROM ima.kb_members WHERE kb_id=%s", (kb_id,))
            connection.execute("DELETE FROM ima.knowledge_bases WHERE id=%s", (kb_id,))
        if scene:
            connection.execute("DELETE FROM ima.scene_defaults WHERE workflow='grounded_ask'")
            connection.execute(
                "DELETE FROM ima.capability_profile_versions WHERE profile_id IN (SELECT id FROM ima.capability_profiles WHERE workflow='grounded_ask' AND business_alias='场景默认')"
            )
            connection.execute(
                "DELETE FROM ima.capability_profiles WHERE workflow='grounded_ask' AND business_alias='场景默认'"
            )
        for gateway_id in gateway_ids:
            connection.execute("DELETE FROM ima.governed_models WHERE gateway_id=%s", (gateway_id,))
            connection.execute("DELETE FROM ima.model_gateways WHERE id=%s", (gateway_id,))
        for actor_id in actor_ids:
            connection.execute("DELETE FROM ima.audit_events WHERE actor_id=%s", (actor_id,))
            connection.execute("DELETE FROM ima.users WHERE id=%s", (actor_id,))
        connection.commit()


def sse_events(frames: list[bytes]) -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for frame in frames:
        decoded = frame.decode()
        name = next(
            (
                line.removeprefix("event: ")
                for line in decoded.splitlines()
                if line.startswith("event: ")
            ),
            "",
        )
        data = next((line for line in decoded.splitlines() if line.startswith("data: ")), "")
        if name and data:
            events[name] = json.loads(data[6:])
    return events


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_search_scope_filters_folder_subtree_and_document() -> None:
    migrate()
    actor = "scope-it-actor-1"
    kb_id, other_kb = f"pg-kb-{uuid4().hex[:20]}", f"pg-kb-{uuid4().hex[:20]}"
    seed_actor(actor)
    ids = seed_corpus(kb_id, actor)
    search, _models, engine = scope_services()
    gateway_id = seed_keyword_chat_scene(actor)
    try:
        everything = await search.search(actor, kb_id, "hello", mode="keyword")
        assert {item["title"] for item in everything["items"]} == {"Doc A", "Doc B", "Doc C"}

        folder = await search.search(
            actor, kb_id, "hello", mode="keyword", folder_id=ids["folder_a"]
        )
        assert {item["title"] for item in folder["items"]} == {"Doc A", "Doc B"}

        document = await search.search(
            actor, kb_id, "hello", mode="keyword", document_id=ids["doc_b"]
        )
        assert [item["title"] for item in document["items"]] == ["Doc B"]

        with pytest.raises(SearchError) as invalid:
            await search.search(
                actor,
                kb_id,
                "hello",
                mode="keyword",
                folder_id=ids["folder_a"],
                document_id=ids["doc_a"],
            )
        assert (invalid.value.status_code, invalid.value.code) == (422, "INVALID_SCOPE")

        # A scope target outside the knowledge base is a clean 404, never a 500.
        with pytest.raises(SearchError) as missing_document:
            await search.search(actor, kb_id, "hello", mode="keyword", document_id=uuid4())
        assert (missing_document.value.status_code, missing_document.value.code) == (
            404,
            "DOCUMENT_NOT_FOUND",
        )
        seed_corpus(other_kb, actor)
        with pytest.raises(SearchError) as cross_kb:
            await search.search(actor, other_kb, "hello", mode="keyword", folder_id=ids["folder_a"])
        assert (cross_kb.value.status_code, cross_kb.value.code) == (404, "FOLDER_NOT_FOUND")
    finally:
        await engine.dispose()
        cleanup_scope_fixtures(
            (kb_id, other_kb),
            gateway_ids=(gateway_id,),
            actor_ids=(actor,),
            scene=True,
        )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_ask_scope_persists_filters_and_reports_scoped_gap() -> None:
    migrate()
    actor = "scope-it-actor-2"
    kb_id = f"pg-kb-{uuid4().hex[:20]}"
    seed_actor(actor)
    ids = seed_corpus(kb_id, actor)
    search, _models, engine = scope_services()
    gateway_id = seed_keyword_chat_scene(actor)
    try:
        scope = AskScope(folder_id=ids["folder_a"])
        # The question matches nothing, so the run ends in a scoped knowledge gap.
        frames = [
            frame
            async for frame in await search.ask(actor, kb_id, "nomatch zzz scope", None, scope)
        ]
        events = sse_events(frames)
        conversation = events["conversation"]["conversation"]
        assert conversation["scope"] == {"folderId": ids["folder_a"], "title": "Folder A"}
        assert isinstance(conversation["id"], str)
        assert events["knowledge_gap"]["answer"] == "该范围下未找到相关内容。"
        conversation_id = UUID(conversation["id"])

        assert SYNC_URL
        with psycopg.connect(SYNC_URL) as connection:
            row = connection.execute(
                "SELECT scope FROM ima.conversations WHERE id=%s", (conversation_id,)
            ).fetchone()
            # psycopg decodes jsonb to dict; tolerate a raw string too.
            persisted_scope = json.loads(row[0]) if row and isinstance(row[0], str) else row[0]
            assert persisted_scope == {"folderId": ids["folder_a"]}
            gap_message = connection.execute(
                "SELECT status,content FROM ima.conversation_messages WHERE conversation_id=%s AND role='assistant'",
                (conversation_id,),
            ).fetchone()
            assert gap_message == ("knowledge_gap", "该范围下未找到相关内容。")

        # Follow-ups inherit the pinned scope automatically (no scope argument).
        follow_up = [
            frame
            async for frame in await search.ask(
                actor, kb_id, "nomatch zzz scope again", conversation_id
            )
        ]
        assert sse_events(follow_up)["knowledge_gap"]["answer"] == "该范围下未找到相关内容。"

        # A matching echo is accepted; a different scope conflicts before writes.
        echo = [
            frame
            async for frame in await search.ask(
                actor, kb_id, "nomatch zzz scope echo", conversation_id, scope
            )
        ]
        assert "knowledge_gap" in sse_events(echo)
        with pytest.raises(SearchError) as mismatch:
            await search.ask(
                actor,
                kb_id,
                "nomatch zzz scope other",
                conversation_id,
                AskScope(document_id=ids["doc_a"]),
            )
        assert (mismatch.value.status_code, mismatch.value.code) == (409, "SCOPE_MISMATCH")

        # Retry inherits the pinned scope as well.
        with psycopg.connect(SYNC_URL) as connection:
            user_message = connection.execute(
                "SELECT id,version FROM ima.conversation_messages WHERE conversation_id=%s AND role='user' ORDER BY sequence LIMIT 1",
                (conversation_id,),
            ).fetchone()
        assert user_message
        retry_frames = [
            frame
            async for frame in await search.retry(
                actor, kb_id, conversation_id, user_message[0], int(user_message[1])
            )
        ]
        assert sse_events(retry_frames)["knowledge_gap"]["answer"] == "该范围下未找到相关内容。"
    finally:
        await engine.dispose()
        cleanup_scope_fixtures((kb_id,), gateway_ids=(gateway_id,), actor_ids=(actor,), scene=True)
