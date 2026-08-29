"""Reconciliation rules for resumable legacy migration reruns (G4).

Pure, transport-neutral rules shared by all importer families. The CLI layer
reads legacy rows and checkpoint rows, then consumes the findings produced
here. Nothing in this module touches the database, so the rules are unit
testable without PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# Rule names used in reports and checkpoint last_error values.
LEGACY_ABSENT_IN_TARGET = "legacy_absent_in_target"
TARGET_ABSENT_IN_LEGACY = "target_absent_in_legacy"
LEGACY_DELETED = "legacy_deleted"
TRASH_MOVED = "trash_moved"
REPARENTED_FOLDER = "reparented_folder"
SOURCE_CHANGED = "source_changed"

# Decisions attached to findings.
REIMPORT = "reimport"
PROPAGATE_TRASH = "propagate_trash"
RECONCILE_TRASH_PLACEMENT = "reconcile_trash_placement"
DELETE_AND_REIMPORT_SUBTREE = "delete_and_reimport_subtree"
OPERATOR_REVIEW = "operator_review"


@dataclass(frozen=True, slots=True)
class ReconcileFinding:
    scope: str
    rule: str
    source_id: str
    decision: str
    detail: str


def compare_row_sets(
    *,
    scope: str,
    legacy_ids: Iterable[str],
    checkpoints: Mapping[str, str],
    deletion_decision: str = OPERATOR_REVIEW,
) -> list[ReconcileFinding]:
    """Compare a legacy key set against checkpoint rows for one scope.

    ``checkpoints`` maps source id to checkpoint status. Findings list
    legacy rows without a complete checkpoint (legacy-absent-in-target) and
    complete checkpoints whose legacy row no longer exists
    (target-absent-in-legacy).
    """
    legacy = {str(source_id) for source_id in legacy_ids}
    findings: list[ReconcileFinding] = []
    for source_id in sorted(checkpoints):
        if source_id not in legacy and checkpoints[source_id] == "complete":
            findings.append(
                ReconcileFinding(
                    scope=scope,
                    rule=TARGET_ABSENT_IN_LEGACY,
                    source_id=source_id,
                    decision=deletion_decision,
                    detail="complete checkpoint without legacy row",
                )
            )
    for source_id in sorted(legacy):
        status = checkpoints.get(source_id)
        if status == "complete":
            continue
        findings.append(
            ReconcileFinding(
                scope=scope,
                rule=LEGACY_ABSENT_IN_TARGET,
                source_id=source_id,
                decision=REIMPORT if status is None else OPERATOR_REVIEW,
                detail="no checkpoint" if status is None else f"checkpoint status {status}",
            )
        )
    return findings


def classify_entity_delta(
    *,
    target_kind: str,
    target_lifecycle: str | None,
    in_trash: bool,
    original_parent_provable: bool,
    current_parent: str,
    target_parent: str | None,
) -> tuple[str, str]:
    """Classify a changed knowledge checkpoint against current legacy state.

    Returns ``(rule, decision)``. Callers only invoke this when the source
    fingerprint differs from the completed checkpoint or the target row
    needs placement reconciliation.
    """
    if target_lifecycle is None:
        return LEGACY_ABSENT_IN_TARGET, REIMPORT
    target_trashed = target_lifecycle == "trashed"
    if in_trash and not target_trashed:
        if not original_parent_provable:
            return TRASH_MOVED, OPERATOR_REVIEW
        return TRASH_MOVED, RECONCILE_TRASH_PLACEMENT
    if not in_trash and target_trashed:
        return TRASH_MOVED, RECONCILE_TRASH_PLACEMENT
    if target_parent is not None and current_parent != target_parent:
        if target_kind == "folder":
            return REPARENTED_FOLDER, DELETE_AND_REIMPORT_SUBTREE
        return SOURCE_CHANGED, OPERATOR_REVIEW
    return SOURCE_CHANGED, OPERATOR_REVIEW
