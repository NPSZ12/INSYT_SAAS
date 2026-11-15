import unittest

from json_native_detection_gate import (
    JsonDetectionNotComplete,
    require_completed_json_detection,
)


DOC = "INSYT000000001"
APC = "JOB-APC-123"
DET = "DET-123"


def verify(index=None, status=None):
    if index is None:
        index = {
            "doc_id": DOC,
            "source_job_id": APC,
            "latest_detection_job_id": DET,
            "classification": "HIT",
        }
    if status is None:
        status = {
            "detection_job_id": DET,
            "status": "completed",
        }
    return require_completed_json_detection(
        doc_id=DOC,
        source_job_id=APC,
        detection_job_id=DET,
        document_index=index,
        detection_status=status,
    )


class DetectionGateTests(unittest.TestCase):

    def test_completed_hit(self):
        self.assertTrue(verify()["verified"])

    def test_incomplete_statuses_rejected(self):
        for value in (
            "queued", "processing", "failed",
            "completed_with_exceptions", "",
        ):
            with self.subTest(value=value):
                with self.assertRaises(JsonDetectionNotComplete):
                    verify(status={
                        "detection_job_id": DET,
                        "status": value,
                    })

    def test_wrong_doc_id_rejected(self):
        with self.assertRaises(JsonDetectionNotComplete):
            verify(index={
                "doc_id": "OTHER",
                "source_job_id": APC,
                "latest_detection_job_id": DET,
                "classification": "HIT",
            })

    def test_wrong_source_job_rejected(self):
        with self.assertRaises(JsonDetectionNotComplete):
            verify(index={
                "doc_id": DOC,
                "source_job_id": "OTHER",
                "latest_detection_job_id": DET,
                "classification": "HIT",
            })

    def test_stale_detection_rejected(self):
        with self.assertRaises(JsonDetectionNotComplete):
            verify(index={
                "doc_id": DOC,
                "source_job_id": APC,
                "latest_detection_job_id": "DET-OLD",
                "classification": "HIT",
            })

    def test_no_hit_and_nfr_rejected(self):
        for classification in ("NO_HIT", "NFR", "EXCEPTION"):
            with self.subTest(classification=classification):
                with self.assertRaises(JsonDetectionNotComplete):
                    verify(index={
                        "doc_id": DOC,
                        "source_job_id": APC,
                        "latest_detection_job_id": DET,
                        "classification": classification,
                    })

    def test_status_identity_mismatch_rejected(self):
        with self.assertRaises(JsonDetectionNotComplete):
            verify(status={
                "detection_job_id": "DET-WRONG",
                "status": "completed",
            })

    def test_unavailable_records_rejected(self):
        with self.assertRaises(JsonDetectionNotComplete):
            require_completed_json_detection(
                doc_id=DOC,
                source_job_id=APC,
                detection_job_id=DET,
                document_index=None,
                detection_status=None,
            )


if __name__ == "__main__":
    unittest.main()