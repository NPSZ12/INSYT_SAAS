import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


SOURCE = Path(__file__).with_name("mapped_processing_set.py")


def load_consumer():
    spec = importlib.util.spec_from_file_location(
        "_insyt_test_mapped_consumer",
        SOURCE,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeJsonProcessingLoaderTests(unittest.TestCase):

    def setUp(self):
        self.consumer = load_consumer()

        self.scope = {
            "workspace": "capture",
            "client": "SyntheticClient",
            "project": "SyntheticProject",
            "header_set_id": "HDRSET-SYNTHETIC",
        }

        self.doc_id = "INSYT000000077"

        self.source_path = (
            "synthetic/source/native/"
            "INSYT000000077.json"
        )

        self.mapped_path = (
            "synthetic/mapped_csv/"
            "INSYT000000077.csv"
        )

        self.headers = [
            "First Name (or Initial)",
            "First Name (or Initial)_2",
            "Secondary Email",
        ]

        self.rows = [
            self.headers,
            ["Avery", "A", "avery@example.invalid"],
            ["Jordan", "J", "jordan@example.invalid"],
        ]

        self.lineage = [
            {
                "output_column_index": index,
                "source_column_index": index,
                "output_header": header,
                "json_pointer": pointer,
            }
            for index, (header, pointer) in enumerate(zip(
                self.headers,
                [
                    "/collection/people/[]/first_name",
                    "/collection/people/[]/fname",
                    "/collection/people/[]/email",
                ],
            ))
        ]

        self.approved_document = {
            "doc_id": self.doc_id,
            "source_kind": "native_json",
            "source_native_path": self.source_path,
            "source_sha256": "a" * 64,
        }

        self.approved_mapping = {
            **self.scope,
            "status": "approved",
            "documents": [self.approved_document],
        }

        self.document = {
            "doc_id": self.doc_id,
            "status": "generated",
            "source_kind": "native_json",
            "source_native_path": self.source_path,
            "source_sha256": "a" * 64,
            "source_csv_path": "",
            "mapped_csv_path": self.mapped_path,
            "original_filename": "synthetic.json",
            "header_status": "HEADER",
            "output_headers": self.headers,
            "column_lineage": self.lineage,
            "mapped_row_count": 2,
            "record_array_path": "/collection/people",
            "row_source_pointers": [
                "/collection/people/0",
                "/collection/people/1",
            ],
        }

        self.manifest = {
            **self.scope,
            "status": "completed",
            "document_count": 1,
            "generated_document_count": 1,
            "failed_document_count": 0,
            "total_mapped_rows": 2,
            "documents": [self.document],
            "failed_documents": [],
        }

        self.read_csv = Mock(
            return_value=(self.rows, ",")
        )

        self.schema_module = ModuleType(
            "app.api.cyber2.schema_mapping"
        )

        self.schema_module._load_required_json = (
            lambda path, *, description: self.manifest
        )

        self.schema_module._mapped_csv_manifest_path = (
            lambda **kwargs: "synthetic/mapped_manifest.json"
        )

        self.schema_module._mapped_csv_path = (
            lambda **kwargs: self.mapped_path
        )

        self.schema_module._read_csv_blob_rows = self.read_csv

        self.processing_module = ModuleType(
            "app.api.processing_center_azure"
        )

        self.processing_module._processing_container_client = (
            lambda: "mock-processing-container"
        )

    def run_loader(self):
        with patch.dict(sys.modules, {
            "app.api.cyber2.schema_mapping": self.schema_module,
            "app.api.processing_center_azure": self.processing_module,
        }):
            return self.consumer.load_cyber2_mapped_processing_set(
                **self.scope,
                approved_mapping=self.approved_mapping,
            )

    def test_real_loader_preserves_native_row_provenance(self):
        result = self.run_loader()

        self.assertEqual(result["record_count"], 2)
        self.assertEqual(len(result["records"]), 2)

        for index, record in enumerate(result["records"]):
            provenance = record["provenance"]

            self.assertEqual(record["doc_id"], self.doc_id)

            self.assertEqual(
                provenance["capture_source"],
                "cyber2_mapped_csv",
            )

            self.assertEqual(
                provenance["source_kind"],
                "native_json",
            )

            self.assertEqual(
                provenance["source_native_path"],
                self.source_path,
            )

            self.assertEqual(
                provenance["source_sha256"],
                "a" * 64,
            )

            self.assertEqual(
                provenance["native_record_pointer"],
                f"/collection/people/{index}",
            )

            self.assertEqual(
                provenance["column_lineage"],
                self.lineage,
            )

            self.assertEqual(
                record["metadata"],
                dict(zip(self.headers, self.rows[index + 1])),
            )

        self.assertNotEqual(
            result["records"][0]["ucid"],
            result["records"][1]["ucid"],
        )

        self.read_csv.assert_called_once()

    def test_missing_native_pointer_blocks_processing(self):
        self.document["row_source_pointers"].pop()

        with self.assertRaises(
            self.consumer.MappedProcessingSetError
        ):
            self.run_loader()

    def test_native_hash_mismatch_blocks_processing(self):
        self.document["source_sha256"] = "b" * 64

        with self.assertRaises(
            self.consumer.MappedProcessingSetError
        ):
            self.run_loader()

    def test_existing_csv_source_remains_compatible(self):
        self.approved_document["source_kind"] = "csv"

        for key in (
            "source_native_path",
            "source_sha256",
        ):
            self.approved_document.pop(key, None)

        for key in (
            "source_native_path",
            "source_sha256",
            "record_array_path",
            "row_source_pointers",
        ):
            self.document.pop(key, None)

        self.document["source_kind"] = "csv"
        self.document["source_csv_path"] = (
            "synthetic/source/source.csv"
        )

        result = self.run_loader()

        self.assertEqual(result["record_count"], 2)

        for record in result["records"]:
            self.assertEqual(
                record["provenance"]["capture_source"],
                "cyber2_mapped_csv",
            )
            self.assertNotIn(
                "native_record_pointer",
                record["provenance"],
            )



class RootJsonProcessingLoaderTests(unittest.TestCase):

    def verify_loader(self, data, extension, names, pointers):

        import hashlib
        from copy import deepcopy

        from app.api.cyber2.json_header_evidence import (
            discover_json_header_evidence,
        )

        from app.api.cyber2.json_mapped_preview import (
            construct_approved_json_csv_rows,
        )

        fixture = NativeJsonProcessingLoaderTests(
            "test_real_loader_preserves_native_row_provenance"
        )

        fixture.setUp()

        source_hash = hashlib.sha256(data).hexdigest()

        evidence = discover_json_header_evidence(
            data,
            extension,
        )

        columns = [
            {
                "column_index": index,
                "json_pointer": field["json_pointer"],
                "json_kind": "scalar",
                "source_header": "first_name",
                "final_header": "First Name (or Initial)",
                "disposition": "map",
                "delete_column": False,
                "mapped_to_protocol": True,
            }
            for index, field in enumerate(evidence["fields"])
            if field["kind"] == "scalar"
        ]

        fixture.approved_document.update({
            "source_native_path": (
                f"synthetic/source/native/{fixture.doc_id}.{extension}"
            ),
            "source_sha256": source_hash,
            "source_format": extension,
            "source_bytes": len(data),
            "columns": columns,
        })

        original_approval = deepcopy(fixture.approved_mapping)

        converted = construct_approved_json_csv_rows(
            data,
            extension,
            fixture.approved_document,
            ["First Name (or Initial)"],
            source_hash,
            record_array_path=None,
        )

        fixture.document.update({
            key: value
            for key, value in converted.items()
            if key != "rows"
        })

        fixture.document["status"] = "generated"

        fixture.manifest["total_mapped_rows"] = len(names)
        fixture.manifest["total_source_rows"] = len(names)

        fixture.read_csv.return_value = (
            converted["rows"],
            ",",
        )

        result = fixture.run_loader()

        self.assertEqual(
            result["record_count"],
            len(names),
        )

        self.assertEqual(
            len(result["records"]),
            len(names),
        )

        for index, record in enumerate(result["records"]):

            provenance = record["provenance"]

            self.assertEqual(
                record["metadata"]["First Name (or Initial)"],
                names[index],
            )

            self.assertEqual(
                provenance["native_record_pointer"],
                pointers[index],
            )

            self.assertEqual(
                provenance["source_sha256"],
                source_hash,
            )

            self.assertEqual(
                provenance["source_native_path"],
                fixture.approved_document["source_native_path"],
            )

            self.assertEqual(
                provenance["column_lineage"],
                converted["column_lineage"],
            )

            self.assertEqual(
                provenance["capture_source"],
                "cyber2_mapped_csv",
            )

        self.assertEqual(
            len({record["ucid"] for record in result["records"]}),
            len(names),
        )

        self.assertEqual(
            fixture.approved_mapping,
            original_approval,
        )

        fixture.read_csv.assert_called_once()

    def test_root_object_loader(self):
        self.verify_loader(
            b'{"first_name":"Avery"}',
            "json",
            ["Avery"],
            ["/0"],
        )

    def test_root_array_loader(self):
        self.verify_loader(
            b'[{"first_name":"Avery"},{"first_name":"Jordan"}]',
            "json",
            ["Avery", "Jordan"],
            ["/0", "/1"],
        )

    def test_records_container_loader(self):
        self.verify_loader(
            b'{"records":[{"first_name":"Avery"},{"first_name":"Jordan"}]}',
            "json",
            ["Avery", "Jordan"],
            ["/records/0", "/records/1"],
        )

    def test_jsonl_loader(self):
        self.verify_loader(
            b'{"first_name":"Avery"}\n{"first_name":"Jordan"}\n',
            "jsonl",
            ["Avery", "Jordan"],
            ["/0", "/1"],
        )

    def test_ndjson_loader(self):
        self.verify_loader(
            b'{"first_name":"Avery"}\n{"first_name":"Jordan"}\n',
            "ndjson",
            ["Avery", "Jordan"],
            ["/0", "/1"],
        )


if __name__ == "__main__":
    unittest.main()
