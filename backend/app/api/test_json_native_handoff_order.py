import unittest

from json_native_promotion_contract import (
    prepare_json_native_promotion,
)
from json_native_promotion_execution import (
    JsonNativePromotionFailed,
    promote_json_native_verified,
)


class JsonNativeHandoffOrderTests(unittest.TestCase):

    def setUp(self):
        self.original = b'{"Email":"jane@example.com"}'
        self.files = {}
        self.cyber2 = {}
        self.events = []

        self.contract = prepare_json_native_promotion(
            row={
                "doc_id": "INSYT000000001",
                "source_job_id": "JOB-JSON-1",
                "extension": "json",
                "native_staged_blob_path": (
                    "Client/capture/Project/processing_center/staged/"
                    "JOB-JSON-1/native/INSYT000000001.json"
                ),
                "source_type": "json_structured",
                "classification": "HIT",
                "destination": "json_cyber2",
                "cyber2_sent": False,
            },
            base_path="Client/capture/Project",
            source_job_status="completed",
        )

    def handoff(self, fail_write=False, fail_register=False):
        def read_staged(path):
            self.events.append("read_staged")
            return self.original

        def read_final(path):
            self.events.append("read_final")
            return self.files.get(path)

        def write_final(path, data):
            self.events.append("write_files")
            if fail_write:
                raise RuntimeError("Simulated Azure failure")
            if path in self.files:
                raise RuntimeError("Overwrite prohibited")
            self.files[path] = data

        result = promote_json_native_verified(
            contract=self.contract,
            read_staged=read_staged,
            read_final=read_final,
            write_final=write_final,
        )

        if not result["verified"]:
            raise JsonNativePromotionFailed(
                "Files promotion not verified."
            )

        self.events.append("register_cyber2")

        if fail_register:
            raise RuntimeError("Simulated Cyber2 failure")

        index_path = self.contract["cyber2_intake_path"]

        self.cyber2.setdefault(
            index_path,
            {
                "doc_id": result["doc_id"],
                "source_native_path": result["source_native_path"],
                "source_kind": "native_json",
                "sha256": result["sha256"],
            },
        )

        return result

    def test_files_before_cyber2(self):
        result = self.handoff()

        self.assertLess(
            self.events.index("write_files"),
            self.events.index("register_cyber2"),
        )
        self.assertTrue(result["verified"])
        self.assertEqual(len(self.cyber2), 1)

    def test_files_failure_blocks_registration(self):
        with self.assertRaises(JsonNativePromotionFailed):
            self.handoff(fail_write=True)

        self.assertNotIn("register_cyber2", self.events)
        self.assertEqual(self.cyber2, {})

    def test_missing_source_blocks_registration(self):
        self.original = None

        with self.assertRaises(JsonNativePromotionFailed):
            self.handoff()

        self.assertEqual(self.cyber2, {})

    def test_registration_failure_preserves_native(self):
        with self.assertRaises(RuntimeError):
            self.handoff(fail_register=True)

        self.assertEqual(len(self.files), 2)
        self.assertEqual(self.cyber2, {})

        self.events.clear()
        result = self.handoff()

        self.assertEqual(
            result["status"],
            "already_promoted_verified",
        )
        self.assertEqual(len(self.files), 2)
        self.assertEqual(len(self.cyber2), 1)
        self.assertNotIn("write_files", self.events)

    def test_repeat_handoff_does_not_overwrite(self):
        self.handoff()
        self.events.clear()

        result = self.handoff()

        self.assertEqual(
            result["status"],
            "already_promoted_verified",
        )
        self.assertNotIn("write_files", self.events)
        self.assertEqual(len(self.cyber2), 1)


if __name__ == "__main__":
    unittest.main()