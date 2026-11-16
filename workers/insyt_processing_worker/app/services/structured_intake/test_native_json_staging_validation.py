import pytest

from app.services.structured_intake.staging_validation import (
    NativeJsonStagingIncomplete,
    validate_native_json_staging,
)


def uploaded_row():
    return {
        "doc_id": "INSYT000000010",
        "extension": "json",
        "status": "uploaded",
        "native_staged_blob_path": (
            "Client/capture/Project/"
            "processing_center/staged/JOB-1/"
            "structured/native/INSYT000000010.json"
        ),
        "text_staged_blob_path": (
            "Client/capture/Project/"
            "processing_center/staged/JOB-1/"
            "structured/text/INSYT000000010.txt"
        ),
    }


def result(rows=None, planned=1, failed=0):
    if rows is None:
        rows = [uploaded_row()]
    return {
        "planned_count": planned,
        "uploaded_count": len(rows),
        "failed_count": failed,
        "uploaded": rows,
    }


def test_successful_native_staging():
    validate_native_json_staging(result())


def test_no_json_documents_is_valid():
    validate_native_json_staging(result([], planned=0))


@pytest.mark.parametrize("planned,failed", [
    (2, 0),
    (1, 1),
])
def test_incomplete_staging_rejected(planned, failed):
    with pytest.raises(NativeJsonStagingIncomplete):
        validate_native_json_staging(
            result(planned=planned, failed=failed)
        )


@pytest.mark.parametrize("field,value", [
    ("native_staged_blob_path", ""),
    ("text_staged_blob_path", ""),
    ("extension", "csv"),
    ("doc_id", ""),
    ("status", "failed"),
])
def test_invalid_staging_record_rejected(field, value):
    row = uploaded_row()
    row[field] = value

    with pytest.raises(NativeJsonStagingIncomplete):
        validate_native_json_staging(result([row]))


def test_duplicate_doc_id_rejected():
    row = uploaded_row()
    with pytest.raises(NativeJsonStagingIncomplete):
        validate_native_json_staging(
            result([row, dict(row)], planned=2)
        )


def test_missing_result_rejected():
    with pytest.raises(NativeJsonStagingIncomplete):
        validate_native_json_staging(None)


def test_expected_inventory_matches_uploaded():
    validate_native_json_staging(
        result(),
        expected_doc_ids={"INSYT000000010"},
    )


def test_expected_json_missing_from_staging():
    with pytest.raises(NativeJsonStagingIncomplete):
        validate_native_json_staging(
            result([], planned=0),
            expected_doc_ids={"INSYT000000010"},
        )


def test_unexpected_uploaded_document_rejected():
    with pytest.raises(NativeJsonStagingIncomplete):
        validate_native_json_staging(
            result(),
            expected_doc_ids=set(),
        )


def test_three_expected_one_staged_rejected():
    with pytest.raises(NativeJsonStagingIncomplete):
        validate_native_json_staging(
            result(),
            expected_doc_ids={
                "INSYT000000010",
                "INSYT000000011",
                "INSYT000000012",
            },
        )


def test_empty_inventory_and_staging_matches():
    validate_native_json_staging(
        result([], planned=0),
        expected_doc_ids=set(),
    )


def test_loader_uses_unfiltered_source_inventory():
    from app.services.structured_intake.staging_validation import (
        load_expected_native_json_doc_ids,
    )

    class FakeDB:
        def query(self, sql, params):
            assert params == ("JOB-JSON-1",)
            assert "file_processing_metrics" in sql
            assert "structured_source" not in sql
            assert "json_extract" not in sql
            return [
                {"doc_id": "INSYT000000010"},
                {"doc_id": "INSYT000000011"},
                {"doc_id": "INSYT000000012"},
            ]

    actual = load_expected_native_json_doc_ids(
        db=FakeDB(),
        job_id="JOB-JSON-1",
    )

    assert actual == {
        "INSYT000000010",
        "INSYT000000011",
        "INSYT000000012",
    }


def test_loader_rejects_missing_document_id():
    from app.services.structured_intake.staging_validation import (
        load_expected_native_json_doc_ids,
    )

    class FakeDB:
        def query(self, sql, params):
            return [{"doc_id": None}]

    with pytest.raises(NativeJsonStagingIncomplete):
        load_expected_native_json_doc_ids(
            db=FakeDB(),
            job_id="JOB-JSON-1",
        )


def test_loader_rejects_duplicate_document_ids():
    from app.services.structured_intake.staging_validation import (
        load_expected_native_json_doc_ids,
    )

    class FakeDB:
        def query(self, sql, params):
            return [
                {"doc_id": "INSYT000000010"},
                {"doc_id": "INSYT000000010"},
            ]

    with pytest.raises(NativeJsonStagingIncomplete):
        load_expected_native_json_doc_ids(
            db=FakeDB(),
            job_id="JOB-JSON-1",
        )
