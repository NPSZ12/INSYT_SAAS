"""C2 transfer API security, dataflow and routing contracts."""

import ast
from pathlib import Path

import pytest


SOURCE = Path(
    "backend/app/api/cyber2/membership_api.py"
)


def transfer_function():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    matches = [
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "transfer_cyber2_merge_set_to_c2"
    ]
    assert len(matches) == 1
    return matches[0]


def transfer_source():
    return ast.unparse(transfer_function())


def test_uses_existing_authentication_gates():
    source = transfer_source()
    assert "require_scoped_project_access" in source
    assert "require_permission" in source
    assert "require_admin" in source
    assert "_cyber2_execution_actor" in source

    assert source.index("require_admin(") < (
        source.index("inspect_cyber2_c2_transfer_readiness(")
    )


def test_reloads_integrity_checked_merge_set():
    source = transfer_source()
    assert "_cyber2_merge_store_for" in source
    assert "merge_store.load(body.merge_set_id)" in source


def test_requires_independent_server_readiness():
    source = transfer_source()
    assert source.count(
        "inspect_cyber2_c2_transfer_readiness("
    ) == 2


def test_requires_existing_verified_origin_receipt():
    source = transfer_source()
    assert "origin_receipt_path" in source
    assert "load_origin_blob" in source
    assert "require_c2_origin_authorization" in source
    assert "if receipt is None:" in source

    assert source.index("load_origin_blob(") < (
        source.index("snapshot_store.save(")
    )


def test_validates_original_mapped_records():
    source = transfer_source()

    assert "_load_cyber2_merge_processing_set" in source
    assert "validate_c2_merge_population" in source
    assert "build_c2_projection" in source

    assert source.index("validate_c2_merge_population(") < (
        source.index("build_c2_projection(")
    )


def test_only_c2_snapshot_is_written():
    source = transfer_source()

    assert "Cyber2C2TransferStore" in source
    assert "snapshot_store.save(" in source

    for forbidden in (
        "save_c2_origin_approval(",
        "upload_blob(",
        "load_cyber2_raw_capture_records(",
        "Entity Normalization",
    ):
        assert forbidden not in source


def test_no_raw_ai_final_mutation():
    source = transfer_source()

    assert "CAPTURED_ENTITIES.append(" not in source
    assert "_write_processing_json_blob(" not in source
    assert "overlay_view=" not in source


def test_client_cannot_submit_records_or_approval_flags():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))

    models = [
        item for item in tree.body
        if isinstance(item, ast.ClassDef)
        and item.name == "C2TransferBody"
    ]

    assert len(models) == 1

    fields = {
        item.target.id
        for item in models[0].body
        if isinstance(item, ast.AnnAssign)
        and isinstance(item.target, ast.Name)
    }

    assert fields == {
        "client",
        "project",
        "merge_set_id",
    }


def test_response_omits_original_provenance():
    fn = transfer_function()

    returns = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Return)
    ]

    assert len(returns) == 1

    result = returns[0].value
    assert isinstance(result, ast.Dict)

    fields = {
        key.value: value
        for key, value in zip(result.keys, result.values)
        if isinstance(key, ast.Constant)
        and isinstance(key.value, str)
    }

    for field in (
        "origin_approval_verified",
        "source_conservation_verified",
    ):
        assert field in fields
        assert isinstance(fields[field], ast.Constant)
        assert fields[field].value is True

    assert "field_provenance" not in fields
    assert "source_ucids" not in fields

    # The response may include the safe snapshot save receipt,
    # but must not directly return the full projection or source.
    source = ast.unparse(fn)
    assert "return projection" not in source
    assert "return merge_set" not in source
    assert "return processing_set" not in source


def test_api_is_post_not_get():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
    fn = transfer_function()

    assert len(fn.decorator_list) == 1
    decorator = ast.unparse(fn.decorator_list[0])

    assert "router.post" in decorator
    assert "/cyber2/c2/transfer" in decorator
