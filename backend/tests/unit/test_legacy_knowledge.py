from __future__ import annotations

import pytest

from ima.application.legacy_knowledge import (
    LegacyKnowledgeIssue,
    classify_page_patches,
    hierarchy_issues,
    normalize_legacy_tags,
    source_fingerprint,
)


def test_legacy_tags_are_nfkc_casefolded_and_deduplicated() -> None:
    assert normalize_legacy_tags(["  Café  ", "CAFE\u0301", "work"]) == (
        ("café", "Café"),
        ("work", "work"),
    )


@pytest.mark.parametrize("value", ["not-a-list", [3], [" "]])
def test_malformed_tags_are_reviewable_not_guessed(value: object) -> None:
    with pytest.raises(LegacyKnowledgeIssue):
        normalize_legacy_tags(value)


def test_hierarchy_detects_cycle_dangling_and_cross_workspace_parent() -> None:
    rows = [
        {"id": "root-a", "root_id": "root-a", "parent_id": None},
        {"id": "cycle-a", "root_id": "root-a", "parent_id": "cycle-b"},
        {"id": "cycle-b", "root_id": "root-a", "parent_id": "cycle-a"},
        {"id": "dangling", "root_id": "root-a", "parent_id": "missing"},
        {"id": "root-b", "root_id": "root-b", "parent_id": None},
        {"id": "cross", "root_id": "root-a", "parent_id": "root-b"},
    ]
    assert hierarchy_issues(rows) == {
        "cycle-a": "hierarchy_cycle",
        "cycle-b": "hierarchy_cycle",
        "dangling": "dangling_parent",
        "cross": "cross_workspace_parent",
    }


def test_only_complete_text_snapshots_become_immutable_versions() -> None:
    result = classify_page_patches(
        [{"patch": '{"text":"first"}'}, {"patch": '[{"text":"second"}]'}]
    )
    assert result.snapshots == ("first", "second")
    assert result.reason is None


@pytest.mark.parametrize("patch", ["replace /text", '{"op":"replace","path":"/text"}'])
def test_patch_only_or_json_patch_history_is_reviewed(patch: str) -> None:
    result = classify_page_patches([{"patch": patch}])
    assert result.snapshots == ()
    assert result.reason == "unsupported_patch_history"


def test_fingerprint_changes_when_patch_or_hierarchy_changes() -> None:
    base = {"root": "w", "parent": "w", "type": "item", "patches": ["a"]}
    assert source_fingerprint(base) == source_fingerprint(dict(base))
    assert source_fingerprint(base) != source_fingerprint({**base, "patches": ["b"]})
