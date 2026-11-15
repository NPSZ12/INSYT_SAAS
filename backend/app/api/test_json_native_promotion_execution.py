import unittest

from json_native_promotion_contract import (
    prepare_json_native_promotion,
)
from json_native_promotion_execution import (
    JsonNativePromotionFailed,
    promote_json_native_verified,
)


def build_contract():
    row = {
        "doc_id": "INSYT000000001",
        "source_job_id": "JOB-JSON-1",
        "extension": "json",
        "source_type": "json_structured",
        "classification": "HIT",
        "destination": "cyber2",
        "cyber2_sent": False,
    }

    return prepare_json_native_promotion(
        row=row,
        base_path="Client/capture/Project",
        source_job_status="completed",
    )


class PromotionTests(unittest.TestCase):

    def setUp(self):
        self.contract = build_contract()
        self.original = b'{"Email":"jane@example.com"}'
        self.store = {}
        self.writes = 0

    def execute(self):
        def read_staged(path):
            if path == self.contract["staged_native_path"]:
                return self.original
            return None

        def read_final(path):
            return self.store.get(path)

        def write_final(path, data):
            self.writes += 1
            if path in self.store:
                raise RuntimeError("Overwrite prohibited")
            self.store[path] = data

        return promote_json_native_verified(
            contract=self.contract,
            read_staged=read_staged,
            read_final=read_final,
            write_final=write_final,
        )

    def test_valid_native_promoted(self):
        result = self.execute()
        self.assertEqual(result["status"], "promoted")
        self.assertTrue(result["verified"])
        self.assertFalse(result["generate_csv"])
        self.assertEqual(self.writes, 1)
        self.assertEqual(
            self.store[self.contract["final_native_path"]],
            self.original,
        )

    def test_repeat_is_idempotent(self):
        self.execute()
        result = self.execute()
        self.assertEqual(
            result["status"], "already_promoted_verified"
        )
        self.assertEqual(self.writes, 1)

    def test_existing_different_native_rejected(self):
        self.store[self.contract["final_native_path"]] = b"different"
        with self.assertRaises(JsonNativePromotionFailed):
            self.execute()
        self.assertEqual(self.writes, 0)

    def test_missing_staged_native_rejected(self):
        self.original = None
        with self.assertRaises(JsonNativePromotionFailed):
            self.execute()
        self.assertEqual(self.writes, 0)

    def test_unauthorized_contract_rejected(self):
        self.contract["requires_manual_promotion"] = False
        with self.assertRaises(JsonNativePromotionFailed):
            self.execute()
        self.assertEqual(self.writes, 0)

    def test_wrong_source_kind_rejected(self):
        self.contract["source_kind"] = "csv"
        with self.assertRaises(JsonNativePromotionFailed):
            self.execute()
        self.assertEqual(self.writes, 0)


if __name__ == "__main__":
    unittest.main()