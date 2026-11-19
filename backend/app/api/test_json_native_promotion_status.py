import unittest

from json_native_promotion_status import (
    matches_native_json_intake_identity,
)


BASE = "SyntheticClient/capture/SyntheticProject"
DOC = "INSYT000009999"


def make_index():
    return {
        "workspace": "capture",
        "client": "SyntheticClient",
        "project": "SyntheticProject",
        "doc_id": DOC,
        "source_kind": "native_json",
        "source_type": "json_structured",
        "classification": "HIT",
        "source_job_id": "JOB-SYNTHETIC",
        "detection_job_id": "DET-SYNTHETIC",
        "source_native_path": f"{BASE}/source/native/{DOC}.json",
        "source_profile": "plain",
        "source_sha256": "a" * 64,
        "source_bytes": 100,
    }


def check(index):
    return matches_native_json_intake_identity(
        index,
        workspace="capture",
        client="SyntheticClient",
        project="SyntheticProject",
        project_base=BASE,
        doc_id=DOC,
        extension="json",
        source_job_id="JOB-SYNTHETIC",
        detection_job_id="DET-SYNTHETIC",
    )


class NativeJsonPromotionStatusTests(unittest.TestCase):

    def test_valid_six_profiles(self):
        for profile in (
            "plain", "slack", "teams",
            "salesforce", "google", "custom_api"
        ):
            with self.subTest(profile=profile):
                index = make_index()
                index["source_profile"] = profile
                self.assertTrue(check(index))

    def test_missing_index(self):
        self.assertFalse(check(None))

    def test_wrong_doc_id(self):
        index = make_index()
        index["doc_id"] = "OTHER"
        self.assertFalse(check(index))

    def test_wrong_project(self):
        index = make_index()
        index["project"] = "OtherProject"
        self.assertFalse(check(index))

    def test_wrong_source_job(self):
        index = make_index()
        index["source_job_id"] = "OTHER"
        self.assertFalse(check(index))

    def test_wrong_detection_job(self):
        index = make_index()
        index["detection_job_id"] = "OTHER"
        self.assertFalse(check(index))

    def test_wrong_native_path(self):
        index = make_index()
        index["source_native_path"] = "Other/native.json"
        self.assertFalse(check(index))

    def test_wrong_source_kind(self):
        index = make_index()
        index["source_kind"] = "csv"
        self.assertFalse(check(index))

    def test_unknown_profile(self):
        index = make_index()
        index["source_profile"] = "unknown"
        self.assertFalse(check(index))

    def test_missing_hash(self):
        index = make_index()
        index.pop("source_sha256")
        self.assertFalse(check(index))

    def test_empty_source(self):
        index = make_index()
        index["source_bytes"] = 0
        self.assertFalse(check(index))

    def test_plain_csv_index_rejected(self):
        index = make_index()
        index["source_type"] = "csv"
        self.assertFalse(check(index))


if __name__ == "__main__":
    unittest.main()
