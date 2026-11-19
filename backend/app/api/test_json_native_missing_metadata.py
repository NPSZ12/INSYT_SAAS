"""Manual native JSON promotion must not require pre-Promotion source profiles."""

import unittest

from json_native_promotion_contract import (
    JsonPromotionNotEligible,
    prepare_json_native_promotion,
)

BASE = "clients/SyntheticClient/projects/SyntheticProject"
DOC = "INSYTSYNTHETIC22"
JOB = "JOB-SYNTHETIC"


def row(extension="json"):
    return {
        "doc_id": DOC,
        "source_job_id": JOB,
        "extension": extension,
        "classification": "HIT",
        "destination": "json_cyber2",
        "cyber2_sent": False,
        "native_staged_blob_path": (
            f"{BASE}/processing_center/staged/"
            f"{JOB}/native/{DOC}.{extension}"
        ),
    }


def prepare(source):
    return prepare_json_native_promotion(
        row=source,
        base_path=BASE,
        source_job_status="completed",
    )


class DeferredJsonClassificationTests(unittest.TestCase):

    def test_json_without_source_metadata(self):
        result = prepare(row())
        self.assertEqual(result["source_kind"], "native_json")
        self.assertFalse(result["generate_csv"])

    def test_jsonl_without_source_metadata(self):
        self.assertEqual(prepare(row("jsonl"))["extension"], "jsonl")

    def test_ndjson_without_source_metadata(self):
        self.assertEqual(prepare(row("ndjson"))["extension"], "ndjson")

    def test_source_profile_not_required(self):
        source = row()
        source["source_type"] = ""
        source["source_format"] = None
        self.assertFalse(prepare(source)["generate_csv"])

    def test_reject_explicit_csv_type(self):
        source = row()
        source["source_type"] = "csv"
        with self.assertRaises(JsonPromotionNotEligible):
            prepare(source)

    def test_reject_explicit_pdf_type(self):
        source = row()
        source["source_type"] = "pdf"
        with self.assertRaises(JsonPromotionNotEligible):
            prepare(source)

    def test_reject_explicit_excel_format(self):
        source = row()
        source["source_format"] = "xlsx"
        with self.assertRaises(JsonPromotionNotEligible):
            prepare(source)

    def test_reject_no_hit(self):
        source = row()
        source["classification"] = "NO_HIT"
        with self.assertRaises(JsonPromotionNotEligible):
            prepare(source)

    def test_reject_wrong_destination(self):
        source = row()
        source["destination"] = "review"
        with self.assertRaises(JsonPromotionNotEligible):
            prepare(source)

    def test_reject_wrong_staged_path(self):
        source = row()
        source["native_staged_blob_path"] = "wrong/path.json"
        with self.assertRaises(JsonPromotionNotEligible):
            prepare(source)

    def test_reject_already_registered(self):
        source = row()
        source["cyber2_sent"] = True
        with self.assertRaises(JsonPromotionNotEligible):
            prepare(source)


if __name__ == "__main__":
    unittest.main()
