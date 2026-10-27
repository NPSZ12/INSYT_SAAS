import ast
import json
import unittest
from pathlib import Path
from textwrap import dedent

from apc.detection_text_routing import (
    resolve_detection_text_route,
)
from apc.pdf_detection_guard import validate_pdf_documents


class DetectionRegression(unittest.TestCase):

    def route(self, workspace, folder, doc_id, job="JOB-TEST"):
        path = (
            f"CLIENT/{workspace}/PROJECT/"
            f"processing_center/staged/{job}/"
            f"{folder}/{doc_id}.txt"
        )

        args = {
            "workspace": workspace,
            "blob_path": path,
            "processing_container": "insyt-processing",
            "review_container": f"insyt-{workspace}",
            "client": "CLIENT",
            "project": "PROJECT",
            "source_job_id": "JOB-TEST",
            "doc_id": doc_id,
        }

        return resolve_detection_text_route(**args)

    def test_all_shared_staging_routes(self):
        for workspace in ("capture", "discovery"):
            for folder in (
                "text",
                "xl/text",
                "structured/text",
            ):
                with self.subTest(
                    workspace=workspace,
                    folder=folder,
                ):
                    route = self.route(
                        workspace,
                        folder,
                        "INSYT000000001",
                    )
                    self.assertEqual(
                        route.storage_source, "review"
                    )
                    self.assertEqual(
                        route.container,
                        f"insyt-{workspace}",
                    )

    def test_cross_job_isolation(self):
        for workspace in ("capture", "discovery"):
            with self.assertRaises(ValueError):
                self.route(
                    workspace,
                    "text",
                    "INSYT000000001",
                    job="JOB-OTHER",
                )

    def test_doc_id_isolation(self):
        for workspace in ("capture", "discovery"):
            path = (
                f"CLIENT/{workspace}/PROJECT/"
                "processing_center/staged/JOB-TEST/"
                "text/INSYT000000001.txt"
            )
            with self.assertRaises(ValueError):
                resolve_detection_text_route(
                    workspace=workspace,
                    blob_path=path,
                    processing_container="insyt-processing",
                    review_container=f"insyt-{workspace}",
                    client="CLIENT",
                    project="PROJECT",
                    source_job_id="JOB-TEST",
                    doc_id="INSYT000000999",
                )

    def test_cross_workspace_isolation(self):
        for workspace in ("capture", "discovery"):
            other = (
                "discovery" if workspace == "capture"
                else "capture"
            )
            path = (
                f"CLIENT/{other}/PROJECT/"
                "processing_center/staged/JOB-TEST/"
                "text/INSYT000000001.txt"
            )
            with self.assertRaises(ValueError):
                resolve_detection_text_route(
                    workspace=workspace,
                    blob_path=path,
                    processing_container="insyt-processing",
                    review_container=f"insyt-{workspace}",
                    client="CLIENT",
                    project="PROJECT",
                    source_job_id="JOB-TEST",
                    doc_id="INSYT000000001",
                )

    def source_report(self, doc_id, extension="pdf",
                      remediation=False):
        record = {
            "doc_id": doc_id,
            "file_id": "FILE-001",
            "extension": extension,
        }

        if extension == "pdf":
            record["stage_status_json"] = json.dumps({
                "pdf_adapter_inspection": {
                    "status": "completed",
                    "remediation_required": remediation,
                    "metadata": {
                        "structural_status": "validated",
                        "remediation_reason": (
                            "TEST_REMEDIATION"
                            if remediation else None
                        ),
                    },
                }
            })

        return {"files": [record]}

    def validate(self, workspace, document, report):
        return validate_pdf_documents(
            [document],
            report,
            workspace=workspace,
            client="CLIENT",
            project="PROJECT",
            source_job_id="JOB-TEST",
        )

    def test_pdf_extension_bypass_blocked(self):
        doc_id = "INSYT000000001"

        for workspace in ("capture", "discovery"):
            path = (
                f"CLIENT/{workspace}/PROJECT/"
                "processing_center/staged/JOB-TEST/"
                f"text/{doc_id}.txt"
            )

            report = self.source_report(
                doc_id,
                remediation=True,
            )

            for extension in (None, "txt", "pdf"):
                doc = {
                    "doc_id": doc_id,
                    "file_id": "FILE-001",
                    "text_staged_blob_path": path,
                }

                if extension is not None:
                    doc["extension"] = extension

                accepted, rejected = self.validate(
                    workspace, doc, report
                )

                self.assertFalse(accepted)
                self.assertEqual(len(rejected), 1)
                self.assertEqual(
                    rejected[0]["reason_code"],
                    "PDF_INSPECTION_REMEDIATION_REQUIRED",
                )

    def test_known_non_pdf_compatibility(self):
        for workspace in ("capture", "discovery"):
            for extension in (
                "txt", "csv", "docx", "msg", "eml", "xlsx"
            ):
                doc_id = "INSYT000000001"
                doc = {
                    "doc_id": doc_id,
                    "file_id": "FILE-001",
                    "text_staged_blob_path": (
                        f"CLIENT/{workspace}/PROJECT/"
                        "processing_center/staged/JOB-TEST/"
                        f"text/{doc_id}.txt"
                    ),
                }

                accepted, rejected = self.validate(
                    workspace,
                    doc,
                    self.source_report(
                        doc_id, extension=extension
                    ),
                )

                self.assertEqual(len(accepted), 1)
                self.assertFalse(rejected)

    def test_missing_report_fails_closed(self):
        for workspace in ("capture", "discovery"):
            with self.assertRaises(ValueError):
                self.validate(
                    workspace,
                    {"doc_id": "INSYT000000001"},
                    None,
                )

    def test_unknown_source_record_rejected(self):
        for workspace in ("capture", "discovery"):
            accepted, rejected = self.validate(
                workspace,
                {
                    "doc_id": "INSYT000000999",
                    "extension": "txt",
                },
                self.source_report("INSYT000000001"),
            )
            self.assertFalse(accepted)
            self.assertEqual(
                rejected[0]["reason_code"],
                "SOURCE_RECORD_MISSING_OR_AMBIGUOUS",
            )

    def test_all_rejected_result_accounting(self):
        runner = (
            Path(__file__).resolve().parents[2]
            / "workers"
            / "insyt_detection_worker_v2"
            / "apc"
            / "detection_job_runner.py"
        )

        source = runner.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        lines = source.splitlines()

        matches = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and isinstance(node.test.operand, ast.Name)
            and node.test.operand.id == "documents"
            and "ALL_REJECTED_REMEDIATION_V1"
            in "\n".join(
                lines[node.lineno - 1:node.end_lineno]
            )
        ]

        self.assertEqual(len(matches), 1)

        branch = matches[0]
        fragment = "\n".join(
            lines[branch.lineno - 1:branch.end_lineno]
        )

        wrapper = (
            "def execute(documents, rejected_pdfs, client_id, "
            "workspace, project, detection_job_id, source_job_id, "
            "payload, _write_processing_json, utc_now):\n"
            + "\n".join(
                "    " + line
                for line in fragment.splitlines()
            )
            + "\n"
        )

        namespace = {}
        exec(compile(wrapper, str(runner), "exec"), namespace)

        for workspace in ("capture", "discovery"):
            uploads = {}

            def write_json(path, payload):
                uploads[path] = payload
                return {"blob_path": path}

            rejected = [
                {
                    "doc_id": f"INSYT{i:09d}",
                    "reason_code": (
                        "PDF_INSPECTION_REMEDIATION_REQUIRED"
                    ),
                }
                for i in range(1, 4)
            ]

            result = namespace["execute"](
                [],
                rejected,
                "CLIENT",
                workspace,
                "PROJECT",
                "DET-TEST",
                "JOB-TEST",
                {},
                write_json,
                lambda: "2026-10-26T00:00:00Z",
            )

            self.assertEqual(
                result["status"],
                "completed_with_exceptions",
            )
            self.assertEqual(result["documents_total"], 3)
            self.assertEqual(result["documents_scanned"], 0)
            self.assertEqual(result["documents_no_hits"], 0)
            self.assertEqual(result["documents_nfr"], 0)
            self.assertEqual(result["documents_exception"], 3)
            self.assertEqual(len(uploads), 4)


if __name__ == "__main__":
    unittest.main()
