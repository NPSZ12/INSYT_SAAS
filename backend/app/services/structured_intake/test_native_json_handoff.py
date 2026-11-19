import hashlib
import unittest

from .native_json_handoff import (
    build_native_json_intake_record,
    verify_existing_native_json_intake,
)

DATA = b'{"person":{"email":"jane@example.com"},"record_id":"TEST"}'
DOC = "INSYT000000019"
BASE = "INSYT_Demo/capture/Project_Payroll_Dedupe_Test"


def make_record(**overrides):
    params = dict(
        workspace="capture",
        client="INSYT_Demo",
        project="Project_Payroll_Dedupe_Test",
        project_base=BASE,
        doc_id=DOC,
        native_path=f"{BASE}/source/native/{DOC}.json",
        native_bytes=DATA,
        expected_source_sha256=hashlib.sha256(DATA).hexdigest(),
        original_filename="INSYT_JSON_NATIVE_TEST.json",
        source_row={
            "doc_id": DOC,
            "classification": "HIT",
            "source_job_id": "JOB-ABF3927B981B47CA",
            "detection_job_id": "DET-96D7C8D3ABC942C9",
        },
    )
    params.update(overrides)
    return build_native_json_intake_record(**params)


class NativeJsonHandoffTests(unittest.TestCase):
    def test_valid_native_json(self):
        record = make_record()
        self.assertEqual(record["doc_id"], DOC)
        self.assertEqual(record["source_profile"], "plain")
        self.assertEqual(record["source_kind"], "native_json")
        self.assertIsNone(record["source_csv_path"])
        self.assertEqual(record["csv_generation_status"], "not_started")

    def test_repeated_valid_registration(self):
        record = make_record()
        self.assertTrue(
            verify_existing_native_json_intake(dict(record), record)
        )

    def test_conflicting_existing_registration(self):
        record = make_record()
        different = {**record, "source_sha256": "0" * 64}
        with self.assertRaises(ValueError):
            verify_existing_native_json_intake(different, record)

    def test_assigned_header_set_preserves_native_registration(self):
        expected = make_record()
        existing = {
            **expected,
            "header_set_id": "HDRSET-TEST123456",
            "cyber2_stage": "header_schema_mapping",
            "header_set_status": "assigned",
            "sent_to_header_mapping_at": "2026-11-18T12:00:00Z",
        }
        original_copy = dict(existing)
        self.assertTrue(
            verify_existing_native_json_intake(existing, expected)
        )
        self.assertEqual(existing, original_copy)
        self.assertEqual(
            existing["header_set_id"], "HDRSET-TEST123456"
        )
        self.assertIsNone(existing["source_csv_path"])

    def test_unapproved_csv_reference_remains_rejected(self):
        expected = make_record()
        existing = {
            **expected,
            "source_csv_path": (
                "unapproved/derived/INSYT000000019.csv"
            ),
            "csv_generation_status": "completed",
        }
        with self.assertRaises(ValueError):
            verify_existing_native_json_intake(existing, expected)

    def test_reject_wrong_original_hash(self):
        with self.assertRaises(ValueError):
            make_record(expected_source_sha256="0" * 64)

    def test_reject_cross_project_path(self):
        with self.assertRaises(ValueError):
            make_record(
                native_path=f"OTHER/source/native/{DOC}.json"
            )

    def test_reject_wrong_doc_id(self):
        with self.assertRaises(ValueError):
            make_record(doc_id="INSYT000000999")

    def test_reject_non_hit(self):
        with self.assertRaises(ValueError):
            make_record(source_row={
                "doc_id": DOC,
                "classification": "EXCEPTION",
                "source_job_id": "JOB-TEST",
                "detection_job_id": "DET-TEST",
            })

    def test_reject_non_json(self):
        with self.assertRaises(ValueError):
            make_record(
                native_path=f"{BASE}/source/native/{DOC}.csv"
            )

    def test_never_overwrite_original(self):
        original = bytes(DATA)
        make_record()
        self.assertEqual(DATA, original)


if __name__ == "__main__":
    unittest.main()
