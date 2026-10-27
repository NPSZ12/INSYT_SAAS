"""INSYT Discovery: offline adapter and failure-isolation regressions.

Tests use only generated synthetic content. They do not call Azure/OCR or
assert that database-backed lineage has already been verified.
"""
import tempfile
import unittest
import zipfile
from email.message import EmailMessage
from pathlib import Path

from openpyxl import Workbook
from apc.adapters.base import AdapterContext
from apc.adapters.builtin import register_builtin_adapters
from apc.adapters.dispatcher import dispatch_to_adapter
from apc.routing.file_type_registry import resolve_file_route


class DiscoveryMixedFormatsRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        register_builtin_adapters()

    def _dispatch(self, root: Path, name: str, extension: str, file_id: str):
        return dispatch_to_adapter(AdapterContext(
            job_id="JOB-DISCOVERY-SYNTHETIC",
            matter_id="MATTER-DISCOVERY-SYNTHETIC",
            file_id=file_id,
            source_path=root / name,
            normalized_path=name,
            extension=extension,
            work_dir=root / f"output_{file_id}",
        ))

    def test_eml_attachments_and_zip_failure_isolation(self):
        with tempfile.TemporaryDirectory(prefix="insyt_discovery_eml_zip_") as td:
            root = Path(td)
            email = EmailMessage()
            email["From"] = "sender@example.test"
            email["To"] = "recipient@example.test"
            email["Subject"] = "Synthetic two attachment test"
            email.set_content("Synthetic message body")
            for index in (1, 2):
                email.add_attachment(
                    f"Synthetic attachment {index}".encode(),
                    maintype="application", subtype="octet-stream",
                    filename=f"attachment{index}.txt",
                )
            (root / "with_attachments.eml").write_bytes(email.as_bytes())
            (root / "corrupt.zip").write_bytes(b"CORRUPT_ZIP_DATA")
            with zipfile.ZipFile(root / "valid.zip", "w") as archive:
                archive.writestr("valid.txt", "Synthetic content")

            eml = self._dispatch(root, "with_attachments.eml", ".eml", "EML1")
            self.assertIsNotNone(eml)
            self.assertIn(eml.status, {"completed", "completed_with_warnings"}, eml.error)
            self.assertEqual(len(eml.children), 2)
            for child in eml.children:
                self.assertTrue(child.source_path.is_file())
                self.assertEqual(child.relationship, "email_attachment")

            bad_zip = self._dispatch(root, "corrupt.zip", ".zip", "BADZIP")
            self.assertIsNotNone(bad_zip)
            self.assertEqual(bad_zip.status, "failed")
            self.assertTrue(bad_zip.error)

            good_zip = self._dispatch(root, "valid.zip", ".zip", "GOODZIP")
            self.assertIsNotNone(good_zip)
            self.assertIn(good_zip.status, {"completed", "completed_with_warnings"}, good_zip.error)
            self.assertEqual(len(good_zip.children), 1)
            self.assertTrue(good_zip.children[0].source_path.is_file())

    def test_workbook_child_and_corrupt_workbook_isolation(self):
        with tempfile.TemporaryDirectory(prefix="insyt_discovery_excel_") as td:
            root = Path(td)
            workbook = Workbook()
            workbook.active.append(["Name", "Value"])
            workbook.active.append(["Test", "123"])
            workbook.save(root / "valid.xlsx")
            (root / "corrupt.xlsx").write_bytes(b"not an excel workbook")

            good = self._dispatch(root, "valid.xlsx", ".xlsx", "XLSX1")
            self.assertIsNotNone(good)
            self.assertEqual(good.status, "completed", good.error)
            self.assertGreaterEqual(len(good.children), 1)
            self.assertTrue(all(c.source_path.is_file() for c in good.children))

            bad = self._dispatch(root, "corrupt.xlsx", ".xlsx", "XLSX2")
            self.assertIsNotNone(bad)
            self.assertEqual(bad.status, "failed")

            again = self._dispatch(root, "valid.xlsx", ".xlsx", "XLSX3")
            self.assertEqual(again.status, "completed", again.error)

    def test_txt_and_unsupported_routes_are_not_claimed_processed(self):
        # These are routing assertions ONLY. Durable unsupported NFR is a
        # separate database/API release gate and is NOT asserted here.
        txt = resolve_file_route(extension=".txt", original_path="sample.txt")
        self.assertEqual(txt["status"], "continue")
        unknown = resolve_file_route(
            extension=".unknownformat", original_path="sample.unknownformat"
        )
        self.assertEqual(unknown["status"], "train_station")


if __name__ == "__main__":
    unittest.main()
