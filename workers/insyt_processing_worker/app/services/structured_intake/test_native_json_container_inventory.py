import sqlite3

import pytest

from app.services.structured_intake.staging_validation import (
    NativeJsonStagingIncomplete,
    load_expected_native_json_doc_ids,
)


class TestLedger:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE file_processing_metrics (
                job_id TEXT,
                doc_id TEXT,
                extension TEXT,
                is_container INTEGER,
                is_denisted INTEGER,
                is_duplicate INTEGER
            )
            """
        )

    def add(self, doc_id, extension="json", container=1,
            denisted=0, duplicate=0):
        self.connection.execute(
            """
            INSERT INTO file_processing_metrics
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("JOB-NATIVE", doc_id, extension, container,
             denisted, duplicate),
        )

    def query(self, statement, params):
        return self.connection.execute(statement, params).fetchall()


def test_native_container_is_detection_eligible():
    db = TestLedger()
    db.add("DOC-JSON-001", "json", container=1)
    assert load_expected_native_json_doc_ids(
        db=db, job_id="JOB-NATIVE"
    ) == {"DOC-JSON-001"}


def test_jsonl_ndjson_and_leaf_documents():
    db = TestLedger()
    db.add("DOC-JSONL", "jsonl", container=1)
    db.add("DOC-NDJSON", "ndjson", container=1)
    db.add("DOC-LEAF", "JSON", container=0)
    assert load_expected_native_json_doc_ids(
        db=db, job_id="JOB-NATIVE"
    ) == {"DOC-JSONL", "DOC-NDJSON", "DOC-LEAF"}


def test_unrelated_formats_and_suppressed_docs_excluded():
    db = TestLedger()
    db.add("DOC-CSV", "csv")
    db.add("DOC-PDF", "pdf", container=0)
    db.add("DOC-DENIST", denisted=1)
    db.add("DOC-DUPLICATE", duplicate=1)
    assert load_expected_native_json_doc_ids(
        db=db, job_id="JOB-NATIVE"
    ) == set()


def test_missing_native_doc_id_fails_closed():
    db = TestLedger()
    db.add(None, "json", container=1)
    with pytest.raises(NativeJsonStagingIncomplete):
        load_expected_native_json_doc_ids(
            db=db, job_id="JOB-NATIVE"
        )


def test_duplicate_native_doc_id_fails_closed():
    db = TestLedger()
    db.add("DOC-REPEATED")
    db.add("DOC-REPEATED")
    with pytest.raises(NativeJsonStagingIncomplete):
        load_expected_native_json_doc_ids(
            db=db, job_id="JOB-NATIVE"
        )
