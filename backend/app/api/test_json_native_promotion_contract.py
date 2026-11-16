import unittest

from json_native_promotion_contract import (
    JsonPromotionNotEligible,
    prepare_json_native_promotion,
)


BASE = "TestClient/capture/TestProject"


def eligible_row():
    return {
        "doc_id": "INSYT000000001",
        "source_job_id": "JOB-JSON-1",
        "extension": "json",
        "source_type": "json_structured",
        "classification": "HIT",
        "destination": "cyber2",
        "cyber2_sent": False,
    }


def prepare(row=None, status="completed"):
    return prepare_json_native_promotion(
        row=eligible_row() if row is None else row,
        base_path=BASE,
        source_job_status=status,
    )


class JsonNativePromotionContractTests(unittest.TestCase):

    def test_valid_native_promotion_paths(self):
        result = prepare()

        self.assertEqual(
            result["staged_native_path"],
            BASE + "/processing_center/staged/"
            "JOB-JSON-1/structured/native/INSYT000000001.json",
        )
        self.assertEqual(
            result["final_native_path"],
            BASE + "/source/native/INSYT000000001.json",
        )
        self.assertFalse(result["generate_csv"])
        self.assertTrue(result["requires_manual_promotion"])

    def test_incomplete_job_rejected(self):
        for status in ("processing", "failed", ""):
            with self.subTest(status=status):
                with self.assertRaises(JsonPromotionNotEligible):
                    prepare(status=status)

    def test_no_hit_and_nfr_rejected(self):
        for classification in ("NO_HIT", "NFR", ""):
            row = eligible_row()
            row["classification"] = classification
            with self.assertRaises(JsonPromotionNotEligible):
                prepare(row)

    def test_existing_registration_rejected(self):
        row = eligible_row()
        row["cyber2_sent"] = True
        with self.assertRaises(JsonPromotionNotEligible):
            prepare(row)

    def test_csv_rejected(self):
        row = eligible_row()
        row["extension"] = "csv"
        with self.assertRaises(JsonPromotionNotEligible):
            prepare(row)

    def test_wrong_destination_rejected(self):
        row = eligible_row()
        row["destination"] = "review"
        with self.assertRaises(JsonPromotionNotEligible):
            prepare(row)

    def test_path_traversal_rejected(self):
        for doc_id in ("../bad", "a/b", "a.b", ""):
            row = eligible_row()
            row["doc_id"] = doc_id
            with self.subTest(doc_id=doc_id):
                with self.assertRaises(JsonPromotionNotEligible):
                    prepare(row)

    def test_jsonl_and_ndjson_supported(self):
        for extension in ("jsonl", "ndjson"):
            row = eligible_row()
            row["extension"] = extension
            result = prepare(row)
            self.assertTrue(
                result["staged_native_path"].endswith(
                    "." + extension
                )
            )


if __name__ == "__main__":
    unittest.main()