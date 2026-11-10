"""C2 transfer-readiness route structure and security regressions."""

import ast
from pathlib import Path

import pytest


SOURCE = Path("backend/app/api/cyber2/membership_api.py")


def route():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    matches = [
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "inspect_cyber2_c2_transfer_readiness"
    ]
    assert len(matches) == 1
    return matches[0]


def names_and_calls(fn):
    return [
        node.func.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
    ]


def test_requires_all_existing_security_gates():
    calls = names_and_calls(route())

    assert "require_scoped_project_access" in calls
    assert "require_permission" in calls
    assert "require_admin" in calls

    assert calls.index("require_scoped_project_access") < (
        calls.index("_cyber2_merge_store_for")
    )


def test_uses_existing_verified_source_services():
    calls = names_and_calls(route())
    assert "_cyber2_merge_store_for" in calls
    assert "_approved_mapping_path" in calls
    assert "_load_required_json" in calls
    assert "_load_cyber2_merge_processing_set" in calls
    assert "validate_c2_merge_population" in calls


def test_route_contains_no_transfer_write():
    calls = names_and_calls(route())
    assert "build_c2_projection" not in calls
    assert "Cyber2C2TransferStore" not in calls
    assert "upload_blob" not in calls


def test_readiness_cannot_authorize_transfer():
    fn = route()
    results = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Dict)
    ]
    assert len(results) == 1

    entries = dict(zip(
        [
            key.value
            for key in results[0].value.keys
            if isinstance(key, ast.Constant)
        ],
        results[0].value.values,
    ))

    for key in ("origin_authorized", "transfer_authorized"):
        assert isinstance(entries[key], ast.Constant)
        assert entries[key].value is False


def test_latest_completed_merge_set_is_required():
    source = ast.unparse(route())
    assert "require_complete_c2_lineage" in source
    assert "header_set_id=header_set_id" in source
    assert "merge_set_id=merge_set_id" in source


def test_readiness_still_requires_independent_source_validation():
    source = ast.unparse(route())
    assert "validate_c2_merge_population" in source
    assert "store.load(merge_set_id)" in source
    assert "origin_authorized" in source
    assert "transfer_authorized" in source


def test_complete_lineage_accepts_two_valid_passes():
    from app.services.cyber2.c2_merge_lineage import (
        require_complete_c2_lineage,
    )

    sets = [
        {
            "merge_set_id": "MSET-FIRST",
            "header_set_id": "HDR-TEST",
            "status": "completed",
        },
        {
            "merge_set_id": "MSET-SECOND",
            "header_set_id": "HDR-TEST",
            "status": "completed",
            "parent_merge_set_id": "MSET-FIRST",
        },
    ]
    result = require_complete_c2_lineage(
        sets,
        header_set_id="HDR-TEST",
        merge_set_id="MSET-SECOND",
    )
    assert result["lineage_verified"] is True
    assert result["pass_count"] == 2


@pytest.mark.parametrize(
    "problem",
    ["missing_parent", "wrong_parent_header", "fork",
     "cycle", "old_pass", "disconnected", "duplicate"],
)
def test_complete_lineage_rejects_unsafe_cases(problem):
    from app.services.cyber2.c2_merge_lineage import (
        C2MergeLineageError,
        require_complete_c2_lineage,
    )

    sets = [
        {
            "merge_set_id": "MSET-FIRST",
            "header_set_id": "HDR-TEST",
            "status": "completed",
        },
        {
            "merge_set_id": "MSET-SECOND",
            "header_set_id": "HDR-TEST",
            "status": "completed",
            "parent_merge_set_id": "MSET-FIRST",
        },
    ]
    selected = "MSET-SECOND"

    if problem == "missing_parent":
        sets[1]["parent_merge_set_id"] = "MSET-UNKNOWN"
    elif problem == "wrong_parent_header":
        sets[0]["header_set_id"] = "HDR-OTHER"
    elif problem == "fork":
        sets.append({
            "merge_set_id": "MSET-THIRD",
            "header_set_id": "HDR-TEST",
            "status": "completed",
            "parent_merge_set_id": "MSET-FIRST",
        })
    elif problem == "cycle":
        sets[0]["parent_merge_set_id"] = "MSET-SECOND"
    elif problem == "old_pass":
        selected = "MSET-FIRST"
    elif problem == "disconnected":
        sets.append({
            "merge_set_id": "MSET-THIRD",
            "header_set_id": "HDR-TEST",
            "status": "completed",
        })
    elif problem == "duplicate":
        sets.append(dict(sets[0]))

    with pytest.raises(C2MergeLineageError):
        require_complete_c2_lineage(
            sets,
            header_set_id="HDR-TEST",
            merge_set_id=selected,
        )


def test_bounded_inventory_fails_closed():
    from app.services.cyber2.c2_merge_lineage import (
        C2MergeLineageError,
        require_complete_c2_lineage,
    )

    sets = [
        {
            "merge_set_id": f"MSET-{i:032X}",
            "header_set_id": "HDR-TEST",
            "status": "completed",
        }
        for i in range(1000)
    ]

    with pytest.raises(C2MergeLineageError):
        require_complete_c2_lineage(
            sets,
            header_set_id="HDR-TEST",
            merge_set_id=sets[-1]["merge_set_id"],
        )


def test_response_disables_http_caching():
    source = ast.unparse(route())
    assert "Cache-Control" in source
    assert "no-store, private" in source
