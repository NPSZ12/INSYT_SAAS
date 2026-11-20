import hashlib
import unittest

from json_native_text_recovery_22 import (
    DOC, JOB, DETECTION, BASE,
    STAGED_NATIVE, STAGED_TEXT, FINAL_NATIVE, FINAL_TEXT,
    JsonTextRecoveryRejected,
    recover_doc22_text_verified,
)

NATIVE = b'{"records":[{"name":"Synthetic Person"}]}'
TEXT = b"X" * 1336


class RecoveryTests(unittest.TestCase):

    def setUp(self):
        self.staged = {
            STAGED_NATIVE: NATIVE,
            STAGED_TEXT: TEXT,
        }
        self.final = {FINAL_NATIVE: NATIVE}
        self.writes = []
        self.intake = {
            "workspace": "capture",
            "client": "INSYT_Demo",
            "project": "Project_Payroll_Dedupe_Test",
            "doc_id": DOC,
            "source_job_id": JOB,
            "detection_job_id": DETECTION,
            "source_kind": "native_json",
            "classification": "HIT",
            "source_native_path": FINAL_NATIVE,
            "source_sha256": hashlib.sha256(NATIVE).hexdigest(),
            "source_bytes": len(NATIVE),
            "source_csv_path": None,
            "csv_generation_status": "not_started",
        }

    def write(self, path, data):
        if path in self.final:
            raise RuntimeError("Overwrite prohibited.")
        self.writes.append(path)
        self.final[path] = data

    def execute(self, **changes):
        args = dict(
            workspace="capture",
            client="INSYT_Demo",
            project="Project_Payroll_Dedupe_Test",
            doc_ids=[DOC],
            intake=self.intake,
            read_staged=self.staged.get,
            read_final=self.final.get,
            write_final=self.write,
        )
        args.update(changes)
        return recover_doc22_text_verified(**args)

    def test_creates_only_missing_text(self):
        result = self.execute()
        self.assertEqual(self.writes, [FINAL_TEXT])
        self.assertEqual(self.final[FINAL_NATIVE], NATIVE)
        self.assertEqual(self.final[FINAL_TEXT], TEXT)
        self.assertTrue(result["text_verified"])
        self.assertFalse(result["csv_generated"])

    def test_repeat_is_idempotent(self):
        self.execute()
        result = self.execute()
        self.assertEqual(self.writes, [FINAL_TEXT])
        self.assertEqual(
            result["text_status"],
            "already_promoted_verified",
        )

    def test_document_21_rejected(self):
        with self.assertRaises(JsonTextRecoveryRejected):
            self.execute(doc_ids=["INSYT000000021"])
        self.assertEqual(self.writes, [])

    def test_wrong_project_rejected(self):
        with self.assertRaises(JsonTextRecoveryRejected):
            self.execute(project="Other_Project")
        self.assertEqual(self.writes, [])

    def test_wrong_detection_rejected(self):
        self.intake["detection_job_id"] = "OTHER"
        with self.assertRaises(JsonTextRecoveryRejected):
            self.execute()
        self.assertEqual(self.writes, [])

    def test_changed_native_rejected(self):
        self.final[FINAL_NATIVE] = b"different"
        with self.assertRaises(JsonTextRecoveryRejected):
            self.execute()
        self.assertEqual(self.writes, [])

    def test_missing_staged_text_rejected(self):
        self.staged.pop(STAGED_TEXT)
        with self.assertRaises(JsonTextRecoveryRejected):
            self.execute()
        self.assertEqual(self.writes, [])

    def test_wrong_staged_text_size_rejected(self):
        self.staged[STAGED_TEXT] = b"incorrect"
        with self.assertRaises(JsonTextRecoveryRejected):
            self.execute()
        self.assertEqual(self.writes, [])

    def test_existing_conflicting_text_rejected(self):
        self.final[FINAL_TEXT] = b"conflict"
        with self.assertRaises(JsonTextRecoveryRejected):
            self.execute()
        self.assertEqual(self.writes, [])

    def test_csv_reference_rejected(self):
        self.intake["source_csv_path"] = "unexpected.csv"
        with self.assertRaises(JsonTextRecoveryRejected):
            self.execute()
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
