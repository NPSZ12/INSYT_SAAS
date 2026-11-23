import json
import unittest
from unittest.mock import Mock

from app.services.cyber2.c2_origin_receipt import (
    C2OriginReceiptError,
    save_c2_origin_approval,
)


class JsonOriginReceiptTests(unittest.TestCase):

    def setUp(self):
        self.scope = {
            "workspace": "capture",
            "client": "SyntheticClient",
            "project": "SyntheticProject",
            "header_set_id": "HDRSET-SYNTHETIC",
        }

        self.merge = {
            **self.scope,
            "status": "completed",
            "merge_set_id": "MSET-" + "A" * 32,
            "integrity_sha256": "b" * 64,
        }

        self.path = (
            "synthetic/project/source/native/"
            "INSYT000000077.json"
        )

        self.document = {
            "doc_id": "INSYT000000077",
            "source_kind": "native_json",
            "source_native_path": self.path,
            "source_sha256": "a" * 64,
            "source_csv_path": "",
        }

        self.mapping = {
            **self.scope,
            "status": "approved",
            "documents": [self.document],
        }

        self.container = Mock()

    def save(self):
        return save_c2_origin_approval(
            container=self.container,
            project_base_path="synthetic/project",
            merge_set=self.merge,
            approved_mapping=self.mapping,
            reviewed_doc_ids=["INSYT000000077"],
            reviewer="SyntheticAdministrator",
            attested_non_ai=True,
            content_settings_factory=lambda: object(),
        )

    def stored(self):
        blob = self.container.get_blob_client.return_value
        return json.loads(blob.upload_blob.call_args.args[0])

    def test_json_receipt_uses_verified_native_identity(self):
        self.assertEqual(self.save()["status"], "approved")

        document = self.stored()["documents"][0]

        self.assertEqual(document["source_kind"], "native_json")
        self.assertEqual(document["source_native_path"], self.path)
        self.assertEqual(document["source_json_path"], self.path)
        self.assertEqual(document["source_sha256"], "a" * 64)
        self.assertNotIn("source_csv_path", document)

    def test_legacy_csv_receipt_structure_unchanged(self):
        self.mapping["documents"] = [{
            "doc_id": "INSYT000000077",
            "source_csv_path": "synthetic/source/CSV001.csv",
        }]

        self.save()
        document = self.stored()["documents"][0]

        self.assertEqual(document, {
            "doc_id": "INSYT000000077",
            "source_csv_path": "synthetic/source/CSV001.csv",
            "capture_method": "non_ai_structured_source",
        })

    def test_json_alias_mismatch_rejected_without_write(self):
        self.document["source_json_path"] = (
            "different/project/source/native/OTHER.json"
        )

        with self.assertRaises(C2OriginReceiptError):
            self.save()

        self.container.get_blob_client.assert_not_called()

    def test_missing_json_hash_rejected_without_write(self):
        self.document.pop("source_sha256")

        with self.assertRaises(C2OriginReceiptError):
            self.save()

        self.container.get_blob_client.assert_not_called()

    def test_non_ai_attestation_remains_mandatory(self):
        with self.assertRaises(C2OriginReceiptError):
            save_c2_origin_approval(
                container=self.container,
                project_base_path="synthetic/project",
                merge_set=self.merge,
                approved_mapping=self.mapping,
                reviewed_doc_ids=["INSYT000000077"],
                reviewer="SyntheticAdministrator",
                attested_non_ai=False,
                content_settings_factory=lambda: object(),
            )

        self.container.get_blob_client.assert_not_called()

    def test_known_ai_json_source_is_rejected_before_write(self):
        self.document["source_origin"] = "ai_extracted"

        with self.assertRaises(C2OriginReceiptError):
            self.save()

        self.container.get_blob_client.assert_not_called()

    def test_known_ai_csv_source_is_rejected_before_write(self):
        self.mapping["documents"] = [{
            "doc_id": "INSYT000000077",
            "source_csv_path": "synthetic/source/CSV001.csv",
            "capture_method": "ai_generated",
        }]

        with self.assertRaises(C2OriginReceiptError):
            self.save()

        self.container.get_blob_client.assert_not_called()


    def test_mixed_csv_and_json_receipt(self):
        self.mapping["documents"].append({
            "doc_id": "CSV001",
            "source_csv_path": "synthetic/project/source/CSV001.csv",
        })

        result = save_c2_origin_approval(
            container=self.container,
            project_base_path="synthetic/project",
            merge_set=self.merge,
            approved_mapping=self.mapping,
            reviewed_doc_ids=["INSYT000000077", "CSV001"],
            reviewer="SyntheticAdministrator",
            attested_non_ai=True,
            content_settings_factory=lambda: object(),
        )

        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["reviewed_document_count"], 2)

        receipt = self.stored()
        by_id = {
            document["doc_id"]: document
            for document in receipt["documents"]
        }

        self.assertEqual(
            by_id["CSV001"],
            {
                "doc_id": "CSV001",
                "source_csv_path": "synthetic/project/source/CSV001.csv",
                "capture_method": "non_ai_structured_source",
            },
        )

        self.assertEqual(
            by_id["INSYT000000077"]["source_json_path"],
            self.path,
        )

        self.assertNotIn(
            "source_csv_path",
            by_id["INSYT000000077"],
        )

    def test_mixed_receipt_passes_existing_authorization(self):
        from app.services.cyber2.c2_origin_authorization import (
            require_c2_origin_authorization,
        )

        self.mapping["documents"].append({
            "doc_id": "CSV001",
            "source_csv_path": "synthetic/project/source/CSV001.csv",
        })

        save_c2_origin_approval(
            container=self.container,
            project_base_path="synthetic/project",
            merge_set=self.merge,
            approved_mapping=self.mapping,
            reviewed_doc_ids=["CSV001", "INSYT000000077"],
            reviewer="SyntheticAdministrator",
            attested_non_ai=True,
            content_settings_factory=lambda: object(),
        )

        authorization = require_c2_origin_authorization(
            self.merge,
            self.mapping,
            self.stored(),
        )

        self.assertTrue(authorization["origin_authorized"])
        self.assertEqual(
            authorization["authorized_document_count"], 2
        )

    def test_existing_json_receipt_cannot_change_reviewer(self):
        self.save()

        blob = self.container.get_blob_client.return_value
        saved_bytes = blob.upload_blob.call_args.args[0]

        class ConflictError(Exception):
            status_code = 409

        blob.upload_blob.side_effect = ConflictError()
        blob.download_blob.return_value.readall.return_value = saved_bytes

        repeated = self.save()
        self.assertEqual(repeated["status"], "already_approved")

        with self.assertRaises(C2OriginReceiptError):
            save_c2_origin_approval(
                container=self.container,
                project_base_path="synthetic/project",
                merge_set=self.merge,
                approved_mapping=self.mapping,
                reviewed_doc_ids=["INSYT000000077"],
                reviewer="DifferentAdministrator",
                attested_non_ai=True,
                content_settings_factory=lambda: object(),
            )


if __name__ == "__main__":
    unittest.main()
