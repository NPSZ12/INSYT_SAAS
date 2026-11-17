import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parent


def load_module(filename, name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract_module = load_module(
    "json_native_promotion_contract.py",
    "json_contract_test",
)
execution_module = load_module(
    "json_native_promotion_execution.py",
    "json_execution_test",
)

BASE = "INSYT_Demo/capture/Project_Payroll_Dedupe_Test"
DOC = "INSYT000000018"
JOB = "JOB-TEST507"


def make_row(ext="json", **overrides):
    row = {
        "doc_id": DOC,
        "source_job_id": JOB,
        "extension": ext,
        "classification": "HIT",
        "destination": "cyber2",
        "cyber2_sent": False,
    }
    row.update(overrides)
    return row


def prepare(row=None, status="completed"):
    return contract_module.prepare_json_native_promotion(
        row=make_row() if row is None else row,
        base_path=BASE,
        source_job_status=status,
    )


@pytest.mark.parametrize("ext", ["json", "jsonl", "ndjson"])
def test_plain_native_json_without_legacy_metadata(ext):
    result = prepare(make_row(ext=ext))
    assert result["staged_native_path"] == (
        f"{BASE}/processing_center/staged/"
        f"{JOB}/native/{DOC}.{ext}"
    )
    assert result["final_native_path"] == (
        f"{BASE}/source/native/{DOC}.{ext}"
    )
    assert result["generate_csv"] is False


def test_explicit_legacy_path_remains_supported():
    legacy = (
        f"{BASE}/processing_center/staged/"
        f"{JOB}/structured/native/{DOC}.json"
    )
    result = prepare(
        make_row(native_staged_blob_path=legacy)
    )
    assert result["staged_native_path"] == legacy


def test_arbitrary_staging_path_is_rejected():
    with pytest.raises(
        contract_module.JsonPromotionNotEligible
    ):
        prepare(
            make_row(
                native_staged_blob_path=(
                    "other-client/other-project/"
                    "processing_center/staged/"
                    f"{JOB}/native/{DOC}.json"
                )
            )
        )


@pytest.mark.parametrize(
    "row,status",
    [
        (make_row(classification="NO_HIT"), "completed"),
        (make_row(destination="review"), "completed"),
        (make_row(cyber2_sent=True), "completed"),
        (make_row(extension="pdf"), "completed"),
        (make_row(), "queued"),
        (make_row(doc_id="../bad"), "completed"),
    ],
)
def test_existing_eligibility_guards_remain(row, status):
    with pytest.raises(
        contract_module.JsonPromotionNotEligible
    ):
        prepare(row, status)


def test_standard_native_promotion_preserves_exact_bytes():
    promotion = prepare()
    original = (
        b'{"name":"Taylor Morgan",'
        b'"ssn":"123-45-6789"}\n'
    )
    stored = {}

    def read_staged(path):
        assert path == promotion["staged_native_path"]
        return original

    def read_final(path):
        return stored.get(path)

    def write_final(path, data):
        assert path == promotion["final_native_path"]
        assert path not in stored
        stored[path] = data

    result = execution_module.promote_json_native_verified(
        contract=promotion,
        read_staged=read_staged,
        read_final=read_final,
        write_final=write_final,
    )

    assert result["verified"] is True
    assert result["status"] == "promoted"
    assert result["generate_csv"] is False
    assert result["sha256"] == hashlib.sha256(
        original
    ).hexdigest()
    assert stored[promotion["final_native_path"]] == original

    # Repeated promotion must verify, not overwrite.
    repeated = execution_module.promote_json_native_verified(
        contract=promotion,
        read_staged=read_staged,
        read_final=read_final,
        write_final=lambda path, data: pytest.fail(
            "Existing native must never be overwritten"
        ),
    )
    assert repeated["status"] == "already_promoted_verified"


def test_different_existing_native_is_rejected():
    promotion = prepare()

    with pytest.raises(
        execution_module.JsonNativePromotionFailed
    ):
        execution_module.promote_json_native_verified(
            contract=promotion,
            read_staged=lambda path: b'{"valid":true}',
            read_final=lambda path: b'{"changed":true}',
            write_final=lambda path, data: pytest.fail(
                "Must not overwrite conflicting native"
            ),
        )


def test_missing_staged_native_fails_closed():
    promotion = prepare()

    with pytest.raises(
        execution_module.JsonNativePromotionFailed
    ):
        execution_module.promote_json_native_verified(
            contract=promotion,
            read_staged=lambda path: None,
            read_final=lambda path: None,
            write_final=lambda path, data: pytest.fail(
                "Must not promote missing bytes"
            ),
        )
