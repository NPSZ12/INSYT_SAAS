import unittest

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from apc.azure_blob_adapter import (
    azure_upload_xl_files_outputs,
)


class CommonCsvUploadFailureTests(unittest.TestCase):

    def test_failure_isolation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            parent = root / "source.json"
            parent.write_bytes(b'{"records":[]}')

            good_one = root / "child1.csv"
            good_one.write_text(
                "id,name\n1,Alpha\n",
                encoding="utf-8",
            )

            good_two = root / "child3.csv"
            good_two.write_text(
                "id,name\n3,Gamma\n",
                encoding="utf-8",
            )

            missing = root / "child2.csv"

            def artifact(
                file_id,
                path,
                native_blob,
                text_blob,
                is_child,
            ):
                return {
                    "file_id": file_id,
                    "doc_id": file_id,
                    "original_path": str(path),
                    "staged_blob_path": native_blob,
                    "text_staged_blob_path": text_blob,
                    "is_csv_child": is_child,
                }

            plan = [
                artifact(
                    "PARENT",
                    parent,
                    "native/source.json",
                    "",
                    False,
                ),
                artifact(
                    "CHILD1",
                    good_one,
                    "native/child1.csv",
                    "text/child1.txt",
                    True,
                ),
                artifact(
                    "CHILD2",
                    missing,
                    "native/child2.csv",
                    "text/child2.txt",
                    True,
                ),
                artifact(
                    "CHILD3",
                    good_two,
                    "native/child3.csv",
                    "text/child3.txt",
                    True,
                ),
            ]

            adapter = MagicMock()
            adapter._content_settings_cls.side_effect = (
                lambda **kwargs: kwargs
            )

            attempted = []

            def get_blob_client(blob_path):
                attempted.append(blob_path)

                if blob_path == "native/source.json":
                    raise RuntimeError(
                        "Synthetic native upload failure"
                    )

                return MagicMock()

            adapter.review_container.get_blob_client.side_effect = (
                get_blob_client
            )

            with patch(
                "apc.azure_blob_adapter."
                "build_xl_files_staging_plan",
                return_value=plan,
            ), patch(
                "apc.azure_blob_adapter."
                "DualStorageBlobAdapter",
                return_value=adapter,
            ):
                result = azure_upload_xl_files_outputs(
                    db=MagicMock(),
                    routing=MagicMock(),
                    job_id="TEST-COMMON-CSV-FAILURES",
                    azure_write=True,
                    overwrite=True,
                )

            self.assertEqual(
                result["planned_count"], 4
            )
            self.assertEqual(
                result["uploaded_count"], 2
            )
            self.assertEqual(
                result["failed_count"], 2
            )

            uploaded = {
                str(row["file_id"]): row
                for row in result["uploaded"]
            }

            failed = {
                str(row["doc_id"]): row
                for row in result["failed"]
            }

            self.assertEqual(
                set(uploaded),
                {"CHILD1", "CHILD3"},
            )
            self.assertEqual(
                set(failed),
                {"PARENT", "CHILD2"},
            )

            self.assertTrue(
                uploaded["CHILD1"]["detection_ready"]
            )
            self.assertTrue(
                uploaded["CHILD3"]["detection_ready"]
            )

            self.assertEqual(
                failed["CHILD2"]["status"],
                "missing_local_file",
            )
            self.assertEqual(
                failed["PARENT"]["status"],
                "failed",
            )

            self.assertIn(
                "native/child3.csv",
                attempted,
            )
            self.assertIn(
                "text/child3.txt",
                attempted,
            )

            self.assertNotIn(
                "native/child2.csv",
                attempted,
            )

            self.assertEqual(
                len(attempted),
                len(set(attempted)),
            )


if __name__ == "__main__":
    unittest.main()
