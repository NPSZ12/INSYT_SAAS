import unittest

from .native_json_handoff_execution import register_verified_native_json

DOC = "INSYT000000019"
BASE = "INSYT_Demo/capture/Project_Payroll_Dedupe_Test"
JOB = "JOB-ABF3927B981B47CA"
DATA = b'{"person":{"email":"jane@example.com"}}'
STAGED = f"{BASE}/processing_center/staged/{JOB}/native/{DOC}.json"
FINAL = f"{BASE}/source/native/{DOC}.json"


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.blobs = {STAGED: DATA, FINAL: DATA}
        self.indexes = {}
        self.writes = 0

    def read_staged(self, path):
        return self.blobs.get(path)

    def read_final(self, path):
        return self.blobs.get(path)

    def read_index(self, path):
        return self.indexes.get(path)

    def create_index(self, path, payload):
        if path in self.indexes:
            raise FileExistsError(path)
        self.writes += 1
        self.indexes[path] = dict(payload)

    def register(self, **overrides):
        arguments = dict(
            workspace="capture",
            client="INSYT_Demo",
            project="Project_Payroll_Dedupe_Test",
            project_base=BASE,
            doc_id=DOC,
            original_filename="INSYT_JSON_NATIVE_TEST.json",
            source_row={
                "doc_id": DOC,
                "classification": "HIT",
                "source_job_id": JOB,
                "detection_job_id": "DET-96D7C8D3ABC942C9",
            },
            staged_path=STAGED,
            final_path=FINAL,
            read_staged=self.read_staged,
            read_final=self.read_final,
            read_index=self.read_index,
            create_index=self.create_index,
        )
        arguments.update(overrides)
        return register_verified_native_json(**arguments)

    def test_creates_only_intake_record(self):
        result = self.register()
        self.assertEqual(result["status"], "registered_verified")
        self.assertEqual(result["source_profile"], "custom_api")
        self.assertFalse(result["csv_generated"])
        self.assertEqual(self.writes, 1)
        self.assertEqual(self.blobs[STAGED], DATA)
        self.assertEqual(self.blobs[FINAL], DATA)

    def test_repeat_is_idempotent(self):
        self.register()
        result = self.register()
        self.assertEqual(result["status"], "already_registered_verified")
        self.assertEqual(self.writes, 1)

    def test_reject_changed_files_bytes(self):
        self.blobs[FINAL] = b'{"modified":true}'
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(self.writes, 0)

    def test_reject_missing_original(self):
        del self.blobs[STAGED]
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(self.writes, 0)

    def test_reject_missing_files_native(self):
        del self.blobs[FINAL]
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(self.writes, 0)

    def test_reject_wrong_staging_job(self):
        with self.assertRaises(ValueError):
            self.register(
                staged_path=STAGED.replace(JOB, "JOB-OTHER")
            )
        self.assertEqual(self.writes, 0)

    def test_reject_conflicting_index(self):
        self.register()
        path = next(iter(self.indexes))
        self.indexes[path]["source_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.register()
        self.assertEqual(self.writes, 1)

    def test_no_csv_created(self):
        self.register()
        record = next(iter(self.indexes.values()))
        self.assertIsNone(record["source_csv_path"])
        self.assertEqual(record["csv_generation_status"], "not_started")


if __name__ == "__main__":
    unittest.main()
