"""Unit tests for the cutover migration rules (reconcile, blob report, readiness)."""

from __future__ import annotations

import pytest

from ima.application.conversation_archive import (
    CONVERSATION_TABLES,
    build_conversation_archive_report,
)
from ima.application.maintenance import (
    MAINTENANCE_WRITE_FREEZE,
    MUTATING_ACTIONS,
    MaintenanceFreezeError,
)
from ima.application.migration_blob_verify import (
    CORRUPT,
    MISSING,
    VERIFIED,
    BlobVerifyRecord,
    build_blob_verify_report,
)
from ima.application.migration_reconcile import (
    DELETE_AND_REIMPORT_SUBTREE,
    LEGACY_ABSENT_IN_TARGET,
    OPERATOR_REVIEW,
    PROPAGATE_TRASH,
    RECONCILE_TRASH_PLACEMENT,
    REIMPORT,
    REPARENTED_FOLDER,
    SOURCE_CHANGED,
    TARGET_ABSENT_IN_LEGACY,
    TRASH_MOVED,
    classify_entity_delta,
    compare_row_sets,
)
from ima.application.migration_reingest import (
    DEGRADED,
    FAILED,
    PENDING,
    READY,
    classify_readiness,
    enqueue_budget,
    mime_supported,
)
from ima.domain.authorization import AclAction


def test_compare_row_sets_flags_missing_rows_both_directions() -> None:
    findings = compare_row_sets(
        scope="identity",
        legacy_ids=["u1", "u2", "u4"],
        checkpoints={"u1": "complete", "u2": "review", "u3": "complete"},
    )
    by_rule = {(finding.rule, finding.source_id): finding for finding in findings}
    assert by_rule[(TARGET_ABSENT_IN_LEGACY, "u3")].decision == OPERATOR_REVIEW
    assert by_rule[(LEGACY_ABSENT_IN_TARGET, "u2")].decision == OPERATOR_REVIEW
    assert by_rule[(LEGACY_ABSENT_IN_TARGET, "u4")].decision == REIMPORT
    assert len(findings) == 3


def test_compare_row_sets_is_idempotent_and_clean_when_aligned() -> None:
    kwargs = {
        "scope": "identity",
        "legacy_ids": ["u1"],
        "checkpoints": {"u1": "complete"},
    }
    assert compare_row_sets(**kwargs) == []
    assert compare_row_sets(**kwargs) == []


def test_compare_row_sets_honors_deletion_decision() -> None:
    findings = compare_row_sets(
        scope="knowledge",
        legacy_ids=[],
        checkpoints={"e1": "complete"},
        deletion_decision=PROPAGATE_TRASH,
    )
    assert [finding.decision for finding in findings] == [PROPAGATE_TRASH]


def test_classify_entity_delta_legacy_deleted_reimports() -> None:
    rule, decision = classify_entity_delta(
        target_kind="note",
        target_lifecycle=None,
        in_trash=False,
        original_parent_provable=True,
        current_parent="root",
        target_parent="root",
    )
    assert (rule, decision) == (LEGACY_ABSENT_IN_TARGET, REIMPORT)


def test_classify_entity_delta_trash_moves() -> None:
    provable = classify_entity_delta(
        target_kind="note",
        target_lifecycle="active",
        in_trash=True,
        original_parent_provable=True,
        current_parent="folder-a",
        target_parent="folder-a",
    )
    assert provable == (TRASH_MOVED, RECONCILE_TRASH_PLACEMENT)
    unprovable = classify_entity_delta(
        target_kind="note",
        target_lifecycle="active",
        in_trash=True,
        original_parent_provable=False,
        current_parent="folder-a",
        target_parent="folder-a",
    )
    assert unprovable == (TRASH_MOVED, OPERATOR_REVIEW)
    restored = classify_entity_delta(
        target_kind="note",
        target_lifecycle="trashed",
        in_trash=False,
        original_parent_provable=True,
        current_parent="folder-a",
        target_parent="folder-a",
    )
    assert restored == (TRASH_MOVED, RECONCILE_TRASH_PLACEMENT)


def test_classify_entity_delta_reparented_folder_reimports_subtree() -> None:
    folder = classify_entity_delta(
        target_kind="folder",
        target_lifecycle="active",
        in_trash=False,
        original_parent_provable=True,
        current_parent="folder-b",
        target_parent="folder-a",
    )
    assert folder == (REPARENTED_FOLDER, DELETE_AND_REIMPORT_SUBTREE)
    file_move = classify_entity_delta(
        target_kind="note",
        target_lifecycle="active",
        in_trash=False,
        original_parent_provable=True,
        current_parent="folder-b",
        target_parent="folder-a",
    )
    assert file_move == (SOURCE_CHANGED, OPERATOR_REVIEW)


def test_blob_verify_report_ok_requires_everything_verified_and_no_orphans() -> None:
    verified = BlobVerifyRecord("doc-1", 1, "documents/doc-1/1/source", VERIFIED, "")
    missing = BlobVerifyRecord("doc-2", 1, "documents/doc-2/1/source", MISSING, "OBJECT_MISSING")
    corrupt = BlobVerifyRecord(
        "doc-3", 1, "documents/doc-3/1/source", CORRUPT, "OBJECT_VERIFICATION_FAILED"
    )
    clean = build_blob_verify_report(records=[verified], orphan_keys=[], legacy_blob_rows=1)
    assert clean["ok"] is True
    assert clean["checked"] == 1 and clean["verified"] == 1
    assert clean["secretValues"] is False
    broken = build_blob_verify_report(
        records=[verified, missing, corrupt],
        orphan_keys=["documents/orphan/1/source"],
        legacy_blob_rows=4,
    )
    assert broken["ok"] is False
    assert [record["documentId"] for record in broken["missing"]] == ["doc-2"]  # type: ignore[index]
    assert [record["documentId"] for record in broken["corrupt"]] == ["doc-3"]  # type: ignore[index]
    assert broken["orphans"] == ["documents/orphan/1/source"]
    assert broken["legacyBlobRows"] == 4
    unconfigured = build_blob_verify_report(
        records=[verified], orphan_keys=[], legacy_blob_rows=1, storage_configured=False
    )
    assert unconfigured["ok"] is False


def test_readiness_classification_by_state_and_mime() -> None:
    assert classify_readiness(file_state="ready", mime_type="text/plain") == READY
    assert classify_readiness(file_state="failed", mime_type="text/plain") == FAILED
    assert (
        classify_readiness(file_state="processing", parse_status="failed", mime_type="text/plain")
        == FAILED
    )
    assert (
        classify_readiness(
            file_state="processing",
            parse_status="succeeded",
            embed_status="dead_letter",
            mime_type="text/plain",
        )
        == DEGRADED
    )
    assert classify_readiness(file_state="processing", mime_type="application/x-legacy") == DEGRADED
    assert classify_readiness(file_state="pending", mime_type="text/plain") == PENDING
    assert mime_supported("text/plain")
    assert not mime_supported("application/x-legacy")
    assert not mime_supported(None)


def test_enqueue_budget_is_bounded_by_capacity_limit_and_candidates() -> None:
    assert enqueue_budget(max_active=8, active_jobs=6, limit=50, candidates=10) == 2
    assert enqueue_budget(max_active=8, active_jobs=8, limit=50, candidates=10) == 0
    assert enqueue_budget(max_active=8, active_jobs=0, limit=3, candidates=10) == 3
    assert enqueue_budget(max_active=8, active_jobs=0, limit=50, candidates=4) == 4
    assert enqueue_budget(max_active=0, active_jobs=0, limit=50, candidates=10) == 0
    assert enqueue_budget(max_active=8, active_jobs=0, limit=0, candidates=10) == 0


def test_conversation_archive_report_is_counts_only() -> None:
    report = build_conversation_archive_report(
        {"chat": 2, "message": 5, "messageEntity": None, "toolCall": 1, "unrelated": 9}
    )
    assert report == {
        "canonicalResource": "/conversations",
        "migrated": False,
        "decision": "counts_only_archive",
        "tables": {"chat": 2, "message": 5, "toolCall": 1},
        "totalRows": 8,
        "secretValues": False,
    }
    assert CONVERSATION_TABLES == ("chat", "message", "messageEntity", "toolCall")


def test_freeze_error_is_safe_and_mutation_set_covers_only_writes() -> None:
    error = MaintenanceFreezeError()
    assert error.status_code == 503
    assert error.code == MAINTENANCE_WRITE_FREEZE
    assert "secret" not in error.detail.lower()
    assert MUTATING_ACTIONS == frozenset(
        {
            AclAction.CREATE_CHILD,
            AclAction.EDIT,
            AclAction.MOVE,
            AclAction.DELETE,
            AclAction.MANAGE_ACL,
        }
    )
    assert AclAction.VIEW_METADATA not in MUTATING_ACTIONS
    assert AclAction.VIEW_CONTENT not in MUTATING_ACTIONS


@pytest.mark.parametrize("action", sorted(MUTATING_ACTIONS, key=lambda item: item.value))
def test_every_mutating_action_is_a_known_acl_action(action: AclAction) -> None:
    assert isinstance(action, AclAction)
