import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter

from apc.adapters.base import AdapterContext
from apc.adapters.documents.pdf_adapter import PDF_ADAPTER


class ProcessingRegression(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_pdf(self, name, encrypted=False):
        path = self.root / name
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        if encrypted:
            writer.encrypt("synthetic-password")
        writer.write(str(path))
        return path

    def inspect(self, path, file_id):
        return PDF_ADAPTER.process(
            AdapterContext(
                job_id="JOB-REGRESSION",
                matter_id="MATTER-TEST",
                file_id=file_id,
                source_path=str(path),
                normalized_path=path.name,
                extension=".pdf",
            )
        )

    def test_valid_pdf(self):
        path = self.make_pdf("valid.pdf")
        result = self.inspect(path, "FILE-001")
        self.assertEqual(result.status, "completed")
        self.assertEqual(
            result.metadata["structural_status"],
            "validated",
        )
        self.assertTrue(path.exists())

    def test_encrypted_pdf(self):
        path = self.make_pdf(
            "encrypted.pdf", encrypted=True
        )
        result = self.inspect(path, "FILE-002")
        self.assertEqual(
            result.status, "completed_with_warnings"
        )
        self.assertEqual(
            result.metadata["remediation_reason"],
            "PDF_ENCRYPTION_REVIEW_REQUIRED",
        )

    def test_corrupt_pdf(self):
        path = self.root / "corrupt.pdf"
        path.write_bytes(b"%PDF-1.7\ninvalid PDF structure")

        result = self.inspect(path, "FILE-003")
        self.assertEqual(result.status, "failed")
        self.assertEqual(
            result.metadata["remediation_reason"],
            "PDF_STRUCTURAL_VALIDATION_FAILED",
        )
        self.assertTrue(path.exists())

    def test_empty_pdf(self):
        path = self.root / "empty.pdf"
        path.write_bytes(b"")
        result = self.inspect(path, "FILE-004")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "PDF_EMPTY_FILE")

    def test_timeout_does_not_block_next_document(self):
        first = self.make_pdf("timeout.pdf")
        second = self.make_pdf("next.pdf")

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(
                cmd="synthetic-probe",
                timeout=1,
            ),
        ):
            failed = self.inspect(first, "FILE-005")

        self.assertEqual(
            failed.error,
            "PDF_STRUCTURAL_INSPECTION_TIMEOUT",
        )

        self.assertEqual(
            failed.metadata["remediation_reason"],
            "PDF_STRUCTURAL_INSPECTION_TIMEOUT",
        )

        successful = self.inspect(second, "FILE-006")

        self.assertEqual(successful.status, "completed")
        self.assertEqual(
            successful.metadata["structural_status"],
            "validated",
        )
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())


if __name__ == "__main__":
    unittest.main()
