import json
import os
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


API = (
    Path(__file__).resolve().parents[2]
    / "backend/app/api/processing_center_azure.py"
)


def load_collector():
    source = API.read_text(encoding="utf-8-sig")
    start_marker = "# INGESTION_PDF_NFR_V1"
    end_marker = (
        '@router.get('
        '"/{workspace}/processing-center/data-element-detection/ready"'
        ')'
    )

    assert source.count(start_marker) == 1
    assert source.count(end_marker) == 1

    start = source.index(start_marker)
    end = source.index(end_marker, start)

    def extract_inspection(record):
        raw = record.get("stage_status_json") or {}
        if isinstance(raw, str):
            raw = json.loads(raw)
        return raw.get("pdf_adapter_inspection")

    namespace = {
        "Any": Any,
        "os": os,
        "_pdf_inspection_from_report_file": extract_inspection,
    }

    exec(
        compile(source[start:end], str(API), "exec"),
        namespace,
    )

    return namespace["_ingestion_pdf_nfr_from_report"]


def pdf_record(doc_id, reason=None, missing=False):
    record = {
        "doc_id": doc_id,
        "file_id": f"FILE-{doc_id}",
        "extension": "pdf",
        "normalized_path": f"{doc_id}.pdf",
    }

    if not missing:
        record["stage_status_json"] = json.dumps({
            "pdf_adapter_inspection": {
                "status": (
                    "completed_with_warnings" if reason
                    else "completed"
                ),
                "remediation_required": bool(reason),
                "metadata": {
                    "structural_status": "validated",
                    "remediation_reason": reason,
                },
            }
        })

    return record


class IngestionNfrRegression(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.collect = staticmethod(load_collector())

    def test_failed_pdf_without_staged_text(self):
        report = {
            "files": [
                pdf_record("INSYT000000001"),
                pdf_record(
                    "INSYT000000002",
                    "PDF_ENCRYPTION_REVIEW_REQUIRED",
                ),
                pdf_record(
                    "INSYT000000003",
                    "PDF_STRUCTURAL_VALIDATION_FAILED",
                ),
                {"doc_id": "INSYT000000004", "extension": "txt"},
            ]
        }

        with patch.dict(
            os.environ,
            {"INSYT_PDF_DETECTION_REQUIRE_INSPECTION": "0"},
        ):
            records = self.collect(report, "JOB-ONE", [])

        self.assertEqual(
            {item["doc_id"] for item in records},
            {"INSYT000000002", "INSYT000000003"},
        )
        self.assertTrue(all(
            item["detection_status"] == "NOT_SCANNED"
            and item["native_staged_blob_path"] is None
            for item in records
        ))

    def test_source_jobs_remain_distinct(self):
        report = {
            "files": [
                pdf_record(
                    "INSYT000000002",
                    "PDF_ENCRYPTION_REVIEW_REQUIRED",
                )
            ]
        }

        first = self.collect(report, "JOB-ONE", [])
        second = self.collect(report, "JOB-TWO", [])

        self.assertNotEqual(
            first[0]["source_job_id"],
            second[0]["source_job_id"],
        )
        self.assertEqual(first[0]["doc_id"], second[0]["doc_id"])

    def test_missing_inspection_strict_mode(self):
        report = {
            "files": [
                pdf_record("INSYT000000005", missing=True)
            ]
        }

        with patch.dict(
            os.environ,
            {"INSYT_PDF_DETECTION_REQUIRE_INSPECTION": "0"},
        ):
            self.assertEqual(
                self.collect(report, "JOB-ONE", []),
                [],
            )

        with patch.dict(
            os.environ,
            {"INSYT_PDF_DETECTION_REQUIRE_INSPECTION": "1"},
        ):
            records = self.collect(report, "JOB-ONE", [])

        self.assertEqual(len(records), 1)
        self.assertEqual(
            records[0]["reason_code"],
            "PDF_INSPECTION_MISSING",
        )


if __name__ == "__main__":
    unittest.main()
