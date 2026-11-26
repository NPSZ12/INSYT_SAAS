import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


SOURCE = Path(__file__).with_name("schema_mapping.py")


class MockHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def load_generator(namespace):
    """Execute the actual endpoint function with mocked dependencies."""
    tree = ast.parse(
        SOURCE.read_text(encoding="utf-8-sig")
    )

    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "generate_cyber2_mapped_csvs"
    ]

    if len(matches) != 1:
        raise AssertionError(
            "Generator function not found exactly once."
        )

    function = matches[0]
    function.decorator_list = []

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            function,
        ],
        type_ignores=[],
    )

    exec(
        compile(
            ast.fix_missing_locations(module),
            str(SOURCE),
            "exec",
        ),
        namespace,
    )

    return namespace["generate_cyber2_mapped_csvs"]


class JsonGeneratorIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.doc_id = "INSYT000000077"

        self.identification = {
            "documents": [{
                "doc_id": self.doc_id,
                "source_kind": "native_json",
            }]
        }

        self.approved_document = {
            "doc_id": self.doc_id,
            "source_kind": "native_json",
            "source_native_path": (
                "synthetic/capture/source/native/"
                "INSYT000000077.json"
            ),
            "source_sha256": "a" * 64,
            "source_format": "json",
            "source_csv_path": "",
            "original_filename": "synthetic.json",
            "header_status": "HEADER",
            "source_origin": "structured_native",
            "columns": [
                {
                    "column_index": 0,
                    "source_header": "first_name",
                    "json_pointer": "/collection/people/[]/first_name",
                    "json_kind": "scalar",
                    "final_header": "First Name (or Initial)",
                    "delete_column": False,
                },
                {
                    "column_index": 1,
                    "source_header": "batch_key",
                    "json_pointer": "/collection/people/[]/batch_key",
                    "json_kind": "scalar",
                    "final_header": "",
                    "delete_column": True,
                },
            ],
        }

        self.identification["documents"][0].update({
            "source_sha256": self.approved_document["source_sha256"],
            "source_native_path": self.approved_document["source_native_path"],
            "source_format": self.approved_document["source_format"],
            "identification_status": "COMPLETED",
            "columns": [
                dict(column)
                for column in self.approved_document["columns"]
            ],
            "structural_fields": [
                {
                    "json_pointer": "/collection",
                    "json_kind": "object",
                },
                {
                    "json_pointer": "/collection/people",
                    "json_kind": "array",
                },
                {
                    "json_pointer": "/collection/people/[]",
                    "json_kind": "object",
                },
            ],
        })

        self.approved = {
            "status": "approved",
            "documents": [self.approved_document],
            "canonical_column_order": [
                "First Name (or Initial)"
            ],
        }

        self.header_set = {
            "header_set_id": "HDRSET-SYNTHETIC",
            "status": "mapping_approved",
        }

        self.read_source = Mock(
            return_value=b'{"collection":{"people":[]}}'
        )

        self.transform = Mock(return_value={
            "doc_id": self.doc_id,
            "source_native_path": (
                self.approved_document["source_native_path"]
            ),
            "source_sha256": "a" * 64,
            "source_format": "json",
            "record_array_path": "/collection/people",
            "rows": [
                ["First Name (or Initial)"],
                ["Avery"],
                ["Jordan"],
            ],
            "output_headers": [
                "First Name (or Initial)"
            ],
            "column_lineage": [{
                "output_column_index": 0,
                "source_column_index": 0,
                "source_header": "first_name",
                "canonical_header": "First Name (or Initial)",
                "output_header": "First Name (or Initial)",
                "mapped_to_protocol": True,
                "json_pointer": (
                    "/collection/people/[]/first_name"
                ),
            }],
            "row_source_pointers": [
                "/collection/people/0",
                "/collection/people/1",
            ],
            "source_row_count": 2,
            "mapped_row_count": 2,
            "source_column_count": 2,
            "mapped_column_count": 1,
        })

        self.write_csv = Mock()
        self.write_json = Mock()
        self.csv_guard = Mock()
        self.authorize = Mock()

        def load_json(path, *, description):
            if description == "Header Identification result":
                return self.identification
            if description == "Approved Header Mapping":
                return self.approved
            if description == "Header Set manifest":
                return dict(self.header_set)
            raise AssertionError(
                f"Unexpected JSON read: {description}"
            )

        self.namespace = {
            "HTTPException": MockHTTPException,
            "Depends": lambda dependency: None,
            "require_admin": object(),
            "require_scoped_project_access": self.authorize,
            "_identification_path": (
                lambda **kwargs: "synthetic/identification.json"
            ),
            "_approved_mapping_path": (
                lambda **kwargs: "synthetic/approved.json"
            ),
            "_mapped_csv_manifest_path": (
                lambda **kwargs: "synthetic/mapped_manifest.json"
            ),
            "_header_set_manifest_path": (
                lambda **kwargs: "synthetic/header_set.json"
            ),
            "_mapped_csv_path": (
                lambda **kwargs: (
                    "synthetic/mapped_csv/"
                    + kwargs["doc_id"]
                    + ".csv"
                )
            ),
            "_load_required_json": load_json,
            "_require_csv_sources_for_legacy_generation":
                self.csv_guard,
            "_processing_container_client": (
                lambda: "mock-processing-container"
            ),
            "_review_container": (
                lambda workspace: "mock-review-container"
            ),
            "_utc_now": (
                lambda: "2026-11-23T00:00:00+00:00"
            ),
            "_read_verified_native_json_for_mapping":
                self.read_source,
            "construct_approved_json_csv_rows": self.transform,
            "_write_csv_blob_rows": self.write_csv,
            "_write_processing_json_blob": self.write_json,
        }

        self.generator = load_generator(self.namespace)

        self.request = SimpleNamespace(
            client="SyntheticClient",
            project="SyntheticProject",
            generated_by="synthetic-test",
            overwrite_existing=True,
            record_array_paths={
                self.doc_id: "/collection/people",
            },
        )

    def generate(self):
        return self.generator(
            workspace="capture",
            header_set_id="HDRSET-SYNTHETIC",
            request=self.request,
            admin=object(),
        )

    def manifest(self):
        matches = [
            call.kwargs["payload"]
            for call in self.write_json.call_args_list
            if call.kwargs.get("blob_path")
            == "synthetic/mapped_manifest.json"
        ]

        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_native_json_reuses_writer_and_manifest(self):
        result = self.generate()

        self.assertEqual(result["status"], "completed")

        self.authorize.assert_called_once()
        self.csv_guard.assert_not_called()
        self.read_source.assert_called_once()
        self.transform.assert_called_once()
        self.write_csv.assert_called_once()

        written = self.write_csv.call_args.kwargs

        self.assertEqual(
            written["rows"],
            [
                ["First Name (or Initial)"],
                ["Avery"],
                ["Jordan"],
            ],
        )

        self.assertEqual(
            written["blob_path"],
            "synthetic/mapped_csv/"
            "INSYT000000077.csv",
        )

        manifest = self.manifest()

        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(
            manifest["generated_document_count"], 1
        )
        self.assertEqual(
            manifest["failed_document_count"], 0
        )
        self.assertEqual(
            manifest["total_mapped_rows"], 2
        )

        document = manifest["documents"][0]

        self.assertEqual(
            document["source_kind"], "native_json"
        )
        self.assertEqual(
            document["record_array_path"],
            "/collection/people",
        )
        self.assertEqual(
            document["row_source_pointers"],
            [
                "/collection/people/0",
                "/collection/people/1",
            ],
        )
        self.assertEqual(
            document["output_headers"],
            ["First Name (or Initial)"],
        )
        self.assertEqual(
            document["column_lineage"][0]["json_pointer"],
            "/collection/people/[]/first_name",
        )

    def test_missing_record_boundary_cannot_write_csv(self):
        self.request.record_array_paths = {}

        result = self.generate()

        self.assertNotEqual(result["status"], "completed")
        self.read_source.assert_not_called()
        self.transform.assert_not_called()
        self.write_csv.assert_not_called()

        manifest = self.manifest()

        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(
            manifest["failed_document_count"], 1
        )

    def test_native_integrity_failure_cannot_write_csv(self):
        self.read_source.side_effect = MockHTTPException(
            409, "Native source integrity verification failed."
        )

        result = self.generate()

        self.assertNotEqual(result["status"], "completed")
        self.transform.assert_not_called()
        self.write_csv.assert_not_called()

        manifest = self.manifest()

        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(
            manifest["failed_document_count"], 1
        )

    def test_duplicate_approved_native_document_fails_before_write(self):
        self.approved["documents"] = [
            self.approved_document,
            dict(self.approved_document),
        ]

        with self.assertRaises(MockHTTPException) as caught:
            self.generate()

        self.assertEqual(caught.exception.status_code, 409)
        self.read_source.assert_not_called()
        self.transform.assert_not_called()
        self.write_csv.assert_not_called()
        self.write_json.assert_not_called()

    def test_missing_identified_native_document_fails_before_write(self):
        self.identification["documents"].append({
            "doc_id": "INSYT000000078",
            "source_kind": "native_json",
        })

        with self.assertRaises(MockHTTPException) as caught:
            self.generate()

        self.assertEqual(caught.exception.status_code, 409)
        self.read_source.assert_not_called()
        self.transform.assert_not_called()
        self.write_csv.assert_not_called()
        self.write_json.assert_not_called()

    def test_legacy_csv_still_uses_csv_source_guard(self):
        self.identification = {
            "documents": [{
                "doc_id": self.doc_id,
                "source_kind": "csv",
            }]
        }

        self.csv_guard.side_effect = MockHTTPException(
            409, "Synthetic CSV guard rejection."
        )

        with self.assertRaises(MockHTTPException) as caught:
            self.generate()

        self.assertEqual(caught.exception.status_code, 409)
        self.csv_guard.assert_called_once()
        self.read_source.assert_not_called()
        self.transform.assert_not_called()
        self.write_csv.assert_not_called()
        self.write_json.assert_not_called()


    def test_real_converter_preserves_doc077_population(self):
        import hashlib
        import json

        from json_header_evidence import discover_json_header_evidence
        from json_mapped_preview import construct_approved_json_csv_rows

        people = [
            {
                "first_name": "Avery",
                "fname": "A",
                "last_name": "Example",
                "lname": "Example",
                "dob": "1990-01-02",
                "ssn": "111-22-3333",
                "email": "avery@example.invalid",
                "full_name": "Avery Example",
                "phone": "555-0101",
                "social_last_four": "3333",
                "test_only_unknown_field": "KEEP-A",
                "batch_key": "DELETE-A",
            },
            {
                "first_name": "Jordan",
                "fname": "J",
                "last_name": "Sample",
                "lname": "Sample",
                "dob": "1991-02-03",
                "ssn": "444-55-6666",
                "email": "jordan@example.invalid",
                "full_name": "Jordan Sample",
                "phone": "555-0102",
                "social_last_four": "6666",
                "test_only_unknown_field": "KEEP-B",
                "batch_key": "DELETE-B",
            },
        ]

        fixture = {
            "__insyt_synthetic_fixture": {
                "mapping_purpose": "DELETE",
                "profile": "DELETE",
                "record_granularity": "DELETE",
                "synthetic_only": "DELETE",
            },
            "collection": {
                "batch_key": "DELETE",
                "people": people,
            },
        }

        data = json.dumps(
            fixture, separators=(",", ":")
        ).encode("utf-8")

        original_hash = hashlib.sha256(data).hexdigest()
        evidence = discover_json_header_evidence(data, "json")

        protocol_mapping = {
            "first_name": "First Name (or Initial)",
            "fname": "First Name (or Initial)",
            "last_name": "Last Name (FULL)",
            "lname": "Last Name (FULL)",
            "dob": "Date of Birth (DOB)",
            "ssn": "Social Security number (SSN)",
        }

        keep_fields = {
            "email",
            "full_name",
            "phone",
            "social_last_four",
            "test_only_unknown_field",
        }

        deleted_fields = {
            "__insyt_synthetic_fixture.mapping_purpose",
            "__insyt_synthetic_fixture.profile",
            "__insyt_synthetic_fixture.record_granularity",
            "__insyt_synthetic_fixture.synthetic_only",
            "collection.batch_key",
            "collection.people.[].batch_key",
        }

        columns = []
        deleted_seen = set()

        scalar_fields = [
            field for field in evidence["fields"]
            if field["kind"] == "scalar"
        ]

        for index, field in enumerate(scalar_fields):
            pointer = field["json_pointer"]

            dotted = (
                pointer.lstrip("/")
                .replace("/[]/", ".[].")
                .replace("/", ".")
            )

            leaf = pointer.rsplit("/", 1)[-1]

            if dotted in deleted_fields:
                disposition = "delete"
                header = ""
                deleted_seen.add(dotted)

            elif (
                pointer.startswith("/collection/people/[]/")
                and leaf in protocol_mapping
            ):
                disposition = "map"
                header = protocol_mapping[leaf]

            elif (
                pointer.startswith("/collection/people/[]/")
                and leaf in keep_fields
            ):
                disposition = "keep"
                header = "collection.people.[]." + leaf

            else:
                self.fail(
                    "Unexpected synthetic scalar field: " + pointer
                )

            columns.append({
                "column_index": index,
                "json_pointer": pointer,
                "json_kind": "scalar",
                "source_header": dotted,
                "disposition": disposition,
                "final_header": header,
                "delete_column": disposition == "delete",
                "mapped_to_protocol": disposition == "map",
            })

        self.assertEqual(deleted_seen, deleted_fields)

        self.approved_document.update({
            "source_sha256": original_hash,
            "source_bytes": len(data),
            "columns": columns,
        })

        self.identification["documents"][0].update({
            "source_sha256": original_hash,
            "source_native_path": self.approved_document["source_native_path"],
            "source_format": self.approved_document["source_format"],
            "identification_status": "COMPLETED",
            "columns": [
                dict(column)
                for column in columns
            ],
            "structural_fields": [
                {
                    "json_pointer": field["json_pointer"],
                    "json_kind": field["kind"],
                }
                for field in discover_json_header_evidence(
                    data, "json"
                )["fields"]
                if field["kind"] != "scalar"
            ],
        })

        self.approved["canonical_column_order"] = [
            "First Name (or Initial)",
            "Last Name (FULL)",
            "Date of Birth (DOB)",
            "Social Security number (SSN)",
        ]

        self.read_source.return_value = data

        # Execute the genuine converter inside the existing
        # endpoint. Only Azure storage operations remain mocked.
        self.transform.side_effect = construct_approved_json_csv_rows

        result = self.generate()

        self.assertEqual(result["status"], "completed")
        self.read_source.assert_called_once()
        self.transform.assert_called_once()
        self.write_csv.assert_called_once()

        written_rows = self.write_csv.call_args.kwargs["rows"]

        self.assertEqual(len(written_rows), 3)

        headers = written_rows[0]

        self.assertEqual(len(headers), 11)
        self.assertEqual(len(set(headers)), 11)

        self.assertIn("First Name (or Initial)", headers)
        self.assertIn("First Name (or Initial)_2", headers)
        self.assertIn("Last Name (FULL)", headers)
        self.assertIn("Last Name (FULL)_2", headers)

        for field in keep_fields:
            self.assertIn(
                "collection.people.[]." + field,
                headers,
            )

        for row_index, person in enumerate(people, start=1):
            values = dict(zip(headers, written_rows[row_index]))

            self.assertEqual(
                values["First Name (or Initial)"],
                person["first_name"],
            )
            self.assertEqual(
                values["First Name (or Initial)_2"],
                person["fname"],
            )
            self.assertEqual(
                values["Last Name (FULL)"],
                person["last_name"],
            )
            self.assertEqual(
                values["Last Name (FULL)_2"],
                person["lname"],
            )
            self.assertEqual(
                values["Date of Birth (DOB)"],
                person["dob"],
            )
            self.assertEqual(
                values["Social Security number (SSN)"],
                person["ssn"],
            )

            for field in keep_fields:
                self.assertEqual(
                    values["collection.people.[]." + field],
                    person[field],
                )

            self.assertEqual(
                len(written_rows[row_index]),
                len(headers),
            )

            self.assertNotIn(
                "DELETE", str(written_rows[row_index])
            )

        manifest = self.manifest()

        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["total_mapped_rows"], 2)

        document = manifest["documents"][0]

        self.assertEqual(document["mapped_row_count"], 2)
        self.assertEqual(document["output_headers"], headers)
        self.assertEqual(
            document["source_sha256"], original_hash
        )
        self.assertEqual(
            document["record_array_path"],
            "/collection/people",
        )
        self.assertEqual(
            document["row_source_pointers"],
            [
                "/collection/people/0",
                "/collection/people/1",
            ],
        )

        lineage = document["column_lineage"]

        self.assertEqual(
            [column["output_header"] for column in lineage],
            headers,
        )
        self.assertEqual(
            [
                column["output_column_index"]
                for column in lineage
            ],
            list(range(len(headers))),
        )

        self.assertEqual(
            len(document["deleted_headers"]), 6
        )

        self.assertEqual(
            len(document["custom_headers_retained"]), 5
        )

        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            original_hash,
        )

        self.assertEqual(self.read_source.return_value, data)


if __name__ == "__main__":
    unittest.main()
