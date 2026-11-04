"""Regression tests exercising the actual RAW reconciliation statements."""

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "backend/app/api/cyber2/schema_mapping.py"
)


@pytest.fixture
def reconcile():
    text = SOURCE.read_text(encoding="utf-8")
    lines = text.splitlines()

    start = next(
        i + 1 for i, line in enumerate(lines)
        if "# Preserve immutable source-row identities" in line
    )

    end = next(
        i + 1 for i in range(start, len(lines))
        if lines[i] == "    payload = {"
    )

    module = ast.parse(text)
    writer = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "generate_cyber2_raw_capture"
    )

    statements = [
        node for node in writer.body
        if start < node.lineno < end
    ]

    assert statements, "Actual RAW reconciliation not found"
    assert any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "combined_records"
            for target in node.targets
        )
        for node in statements
    ), "combined_records assignment missing"

    wrapper = ast.parse(
        "def run(existing_records, new_records, "
        "header_set_id, failed_documents=None):\n"
        "    pass\n"
    )

    function = wrapper.body[0]
    function.body = statements + [
        ast.Return(value=ast.Name(
            id="combined_records",
            ctx=ast.Load(),
        ))
    ]

    ast.fix_missing_locations(wrapper)

    namespace = {"HTTPException": HTTPException}
    exec(compile(wrapper, str(SOURCE), "exec"), namespace)

    return namespace["run"]


def record(index, header="HDRSET-TEST", ucid=None):
    if ucid is None:
        ucid = f"UCID-ORIGINAL-{index:04d}"

    return {
        "ucid": ucid,
        "doc_id": "INSYT-SYNTHETIC-001",
        "metadata": {
            "First Name": "Synthetic",
            "Row Marker": str(index),
            "UCID": ucid,
        },
        "provenance": {
            "header_set_id": header,
            "source_row_number": index + 1,
            "sheet_index": 0,
            "source_csv_path": "synthetic/source.csv",
            "generated_at": "2026-01-01T00:00:00Z",
        },
    }


def baseline():
    return [record(i) for i in range(64)]


def regenerated(rows):
    return [
        {
            **r,
            "ucid": f"UCID-NEW-{i:04d}",
            "metadata": {
                **r["metadata"],
                "UCID": f"UCID-NEW-{i:04d}",
            },
        }
        for i, r in enumerate(rows)
    ]


def test_all_64_original_ucids_survive_regeneration(reconcile):
    old = baseline()
    result = reconcile(old, regenerated(old), "HDRSET-TEST")

    assert len(result) == 64
    assert result == old
    assert [r["ucid"] for r in result] == [
        r["ucid"] for r in old
    ]


def test_repeating_generation_does_not_duplicate(reconcile):
    old = baseline()
    first = reconcile(old, regenerated(old), "HDRSET-TEST")
    second = reconcile(first, regenerated(old), "HDRSET-TEST")

    assert len(first) == len(second) == 64
    assert second == old


def test_new_source_row_is_appended(reconcile):
    old = baseline()
    incoming = regenerated(old + [record(64)])

    result = reconcile(old, incoming, "HDRSET-TEST")

    assert len(result) == 65
    assert result[:64] == old
    assert result[-1]["ucid"] == incoming[-1]["ucid"]


def test_changed_existing_value_is_rejected(reconcile):
    old = baseline()
    incoming = regenerated(old)
    incoming[0]["metadata"]["First Name"] = "Changed"

    with pytest.raises(HTTPException) as exc:
        reconcile(old, incoming, "HDRSET-TEST")

    assert exc.value.status_code == 409
    assert len(old) == 64


def test_missing_existing_source_row_is_rejected(reconcile):
    old = baseline()

    with pytest.raises(HTTPException) as exc:
        reconcile(old, regenerated(old[:-1]), "HDRSET-TEST")

    assert exc.value.status_code == 409


def test_failed_document_prevents_reconciliation(reconcile):
    old = baseline()

    with pytest.raises(HTTPException) as exc:
        reconcile(
            old,
            regenerated(old),
            "HDRSET-TEST",
            [{"doc_id": "SYNTHETIC", "error": "failed"}],
        )

    assert exc.value.status_code == 409


def test_other_header_set_records_remain_unchanged(reconcile):
    old = baseline()
    new = record(200, header="HDRSET-NEW")

    result = reconcile(
        old,
        regenerated([new]),
        "HDRSET-NEW",
    )

    assert len(result) == 65
    assert result[:64] == old


def test_duplicate_source_identity_is_rejected(reconcile):
    old = baseline()
    incoming = regenerated(old)
    incoming.append(incoming[0])

    with pytest.raises(HTTPException) as exc:
        reconcile(old, incoming, "HDRSET-TEST")

    assert exc.value.status_code == 409


def test_duplicate_existing_ucid_is_rejected(reconcile):
    old = baseline()
    old[1]["ucid"] = old[0]["ucid"]

    with pytest.raises(HTTPException) as exc:
        reconcile(old, regenerated(old), "HDRSET-TEST")

    assert exc.value.status_code == 409


def test_source_value_change_does_not_mutate_existing(reconcile):
    old = baseline()
    original_ucid = old[0]["ucid"]
    original_value = old[0]["metadata"]["First Name"]

    incoming = regenerated(old)
    incoming[0]["metadata"]["First Name"] = "Different"

    with pytest.raises(HTTPException):
        reconcile(old, incoming, "HDRSET-TEST")

    assert old[0]["ucid"] == original_ucid
    assert old[0]["metadata"]["First Name"] == original_value