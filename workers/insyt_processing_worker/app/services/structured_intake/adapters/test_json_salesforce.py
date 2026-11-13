import csv
import json
import unittest

from pathlib import Path
from tempfile import TemporaryDirectory

from .json_salesforce import (
    normalize_salesforce_json_to_csv,
)


class SalesforceJsonConversionTests(unittest.TestCase):

    def test_nested_contacts_and_field_discovery(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "salesforce.json"
            target = root / "output.csv"

            payload = {
                "totalSize": 2,
                "done": True,
                "records": [
                    {
                        "attributes": {"type": "Account"},
                        "Id": "001A",
                        "Name": "Acme",
                        "Contacts": {
                            "totalSize": 2,
                            "done": True,
                            "records": [
                                {
                                    "attributes": {
                                        "type": "Contact"
                                    },
                                    "Id": "003A",
                                    "FirstName": "Jane",
                                },
                                {
                                    "attributes": {
                                        "type": "Contact"
                                    },
                                    "Id": "003B",
                                    "LastName": "Smith",
                                },
                            ],
                        },
                    },
                    {
                        "attributes": {"type": "Account"},
                        "Id": "001B",
                        "Name": "Beta",
                        "NewField": "Appears Later",
                        "Tags": ["A", "B"],
                    },
                ],
            }

            source.write_text(
                json.dumps(payload), encoding="utf-8"
            )
            original = source.read_bytes()

            result = normalize_salesforce_json_to_csv(
                source_path=source,
                output_path=target,
                package_id="PKG-1",
            )

            self.assertEqual(result.package.record_count, 4)
            self.assertEqual(source.read_bytes(), original)

            with target.open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 4)
            self.assertEqual(
                rows[0]["INSYT_SF_Object_Type"], "Account"
            )
            self.assertEqual(
                rows[1]["INSYT_SF_Parent_Record_ID"], "001A"
            )
            self.assertEqual(
                rows[2]["INSYT_SF_Parent_Record_ID"], "001A"
            )
            self.assertEqual(
                rows[3]["SF__NewField"], "Appears Later"
            )
            self.assertEqual(
                rows[3]["SF__Tags"], '["A","B"]'
            )
            self.assertEqual(
                rows[0]["SF__Contacts.__related_count"],
                "2",
            )
            self.assertIn("SF__LastName", rows[1])

    def test_non_salesforce_rejected(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "ordinary.json"
            target = Path(tmp) / "output.csv"
            source.write_text(
                '{"records":[{"name":"Alice"}]}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                normalize_salesforce_json_to_csv(
                    source_path=source,
                    output_path=target,
                )
            self.assertFalse(target.exists())


    def test_incomplete_salesforce_page_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "page1.json"
            target = root / "result.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 2000,
                    "done": False,
                    "nextRecordsUrl": (
                        "/services/data/v60.0/query/next"
                    ),
                    "records": [{
                        "attributes": {"type": "Contact"},
                        "Id": "003PAGE1",
                        "Name": "Partial",
                    }],
                }),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError, "Incomplete Salesforce query page"
            ):
                normalize_salesforce_json_to_csv(
                    source_path=source,
                    output_path=target,
                )

            self.assertFalse(target.exists())

    def test_complete_salesforce_page_accepted(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "complete.json"
            target = root / "result.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 1,
                    "done": True,
                    "records": [{
                        "attributes": {"type": "Contact"},
                        "Id": "003COMPLETE",
                        "Name": "Complete",
                    }],
                }),
                encoding="utf-8",
            )

            result = normalize_salesforce_json_to_csv(
                source_path=source,
                output_path=target,
            )

            self.assertEqual(result.package.record_count, 1)
            self.assertTrue(target.is_file())

    def test_incomplete_nested_relationship_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "nested.json"
            target = root / "result.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 1,
                    "done": True,
                    "records": [{
                        "attributes": {"type": "Account"},
                        "Id": "001PARENT",
                        "Contacts": {
                            "totalSize": 100,
                            "done": False,
                            "nextRecordsUrl": "/query/contacts-next",
                            "records": [{
                                "attributes": {
                                    "type": "Contact"
                                },
                                "Id": "003PARTIAL",
                            }],
                        },
                    }],
                }),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Incomplete Salesforce related-record page",
            ):
                normalize_salesforce_json_to_csv(
                    source_path=source,
                    output_path=target,
                )

            self.assertFalse(target.exists())


    def test_streaming_does_not_call_json_load(self):
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "streaming.json"
            target = root / "result.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 2,
                    "done": True,
                    "records": [
                        {
                            "attributes": {"type": "Contact"},
                            "Id": "003ONE",
                            "Name": "One",
                        },
                        {
                            "attributes": {"type": "Contact"},
                            "Id": "003TWO",
                            "Name": "Two",
                        },
                    ],
                }),
                encoding="utf-8",
            )

            with patch(
                "app.services.structured_intake."
                "adapters.json_salesforce.json.load",
                side_effect=AssertionError(
                    "Full-document json.load prohibited"
                ),
            ):
                result = normalize_salesforce_json_to_csv(
                    source_path=source,
                    output_path=target,
                )

            self.assertEqual(result.package.record_count, 2)
            self.assertTrue(target.is_file())


    def test_salesforce_bom_full_conversion(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bom.json"
            target = root / "result.csv"

            payload = {
                "totalSize": 1,
                "done": True,
                "records": [{
                    "attributes": {"type": "Account"},
                    "Id": "001BOM",
                    "Name": "Synthetic BOM Account",
                }],
            }

            source.write_bytes(
                bytes((0xEF, 0xBB, 0xBF))
                + json.dumps(payload).encode("utf-8")
            )

            original = source.read_bytes()

            result = normalize_salesforce_json_to_csv(
                source_path=source,
                output_path=target,
            )

            self.assertEqual(result.package.record_count, 1)
            self.assertEqual(source.read_bytes(), original)

            with target.open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 1)
            self.assertEqual(
                rows[0]["INSYT_SF_Record_ID"],
                "001BOM",
            )
            self.assertEqual(
                rows[0]["SF__Name"],
                "Synthetic BOM Account",
            )

    def test_oversized_record_rejected(self):
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "large.json"
            target = root / "result.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 1,
                    "done": True,
                    "records": [{
                        "attributes": {"type": "Contact"},
                        "Id": "003LARGE",
                        "Description": "X" * 1000,
                    }],
                }),
                encoding="utf-8",
            )

            with patch(
                "app.services.structured_intake."
                "adapters.json_salesforce."
                "MAX_SALESFORCE_RECORD_EVENT_BYTES",
                256,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Salesforce record size budget exceeded",
                ):
                    normalize_salesforce_json_to_csv(
                        source_path=source,
                        output_path=target,
                    )

            self.assertFalse(target.exists())

    def test_deeply_nested_record_rejected(self):
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "deep.json"
            target = root / "result.csv"

            nested = {"value": "test"}
            for _ in range(8):
                nested = {"child": nested}

            source.write_text(
                json.dumps({
                    "records": [{
                        "attributes": {"type": "Account"},
                        "Id": "001DEEP",
                        "Details": nested,
                    }],
                    "done": True,
                }),
                encoding="utf-8",
            )

            with patch(
                "app.services.structured_intake."
                "adapters.json_salesforce."
                "MAX_SALESFORCE_RECORD_DEPTH",
                5,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Salesforce record nesting-depth "
                    "budget exceeded",
                ):
                    normalize_salesforce_json_to_csv(
                        source_path=source,
                        output_path=target,
                    )

            self.assertFalse(target.exists())


    def test_query_record_count_mismatch_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "incomplete.json"
            target = root / "output.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 3,
                    "done": True,
                    "records": [{
                        "attributes": {"type": "Contact"},
                        "Id": "003ONLYONE",
                    }],
                }),
                encoding="utf-8",
            )

            original = source.read_bytes()

            with self.assertRaisesRegex(
                ValueError,
                "Salesforce query record-count mismatch",
            ):
                normalize_salesforce_json_to_csv(
                    source_path=source,
                    output_path=target,
                )

            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), original)

    def test_empty_complete_salesforce_query(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "empty.json"
            target = root / "output.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 0,
                    "done": True,
                    "records": [],
                }),
                encoding="utf-8",
            )

            result = normalize_salesforce_json_to_csv(
                source_path=source,
                output_path=target,
            )

            self.assertEqual(result.package.record_count, 0)

            with target.open(
                encoding="utf-8-sig",
                newline="",
            ) as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(rows, [])


    def test_nested_relationship_count_mismatch_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "nested_mismatch.json"
            target = root / "result.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 1,
                    "done": True,
                    "records": [{
                        "attributes": {"type": "Account"},
                        "Id": "001PARENT",
                        "Contacts": {
                            "totalSize": 3,
                            "done": True,
                            "records": [{
                                "attributes": {"type": "Contact"},
                                "Id": "003ONLYONE",
                            }],
                        },
                    }],
                }),
                encoding="utf-8",
            )

            original = source.read_bytes()

            with self.assertRaisesRegex(
                ValueError,
                "Salesforce related-record count mismatch",
            ):
                normalize_salesforce_json_to_csv(
                    source_path=source,
                    output_path=target,
                )

            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), original)

    def test_complete_nested_relationship_preserved(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "nested_complete.json"
            target = root / "result.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 1,
                    "done": True,
                    "records": [{
                        "attributes": {"type": "Account"},
                        "Id": "001PARENT",
                        "Contacts": {
                            "totalSize": 2,
                            "done": True,
                            "records": [
                                {
                                    "attributes": {"type": "Contact"},
                                    "Id": "003FIRST",
                                },
                                {
                                    "attributes": {"type": "Contact"},
                                    "Id": "003SECOND",
                                },
                            ],
                        },
                    }],
                }),
                encoding="utf-8",
            )

            result = normalize_salesforce_json_to_csv(
                source_path=source,
                output_path=target,
            )

            self.assertEqual(result.package.record_count, 3)

            with target.open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 3)
            self.assertEqual(
                rows[0]["SF__Contacts.__related_count"],
                "2",
            )
            self.assertEqual(
                [
                    row["INSYT_SF_Record_ID"]
                    for row in rows[1:]
                ],
                ["003FIRST", "003SECOND"],
            )

            for row in rows[1:]:
                self.assertEqual(
                    row["INSYT_SF_Parent_Record_ID"],
                    "001PARENT",
                )
                self.assertEqual(
                    row["INSYT_SF_Parent_Source_Record_ID"],
                    rows[0]["INSYT_Source_Record_ID"],
                )


    def test_mixed_salesforce_records_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "mixed.json"
            target = root / "result.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 2,
                    "done": True,
                    "records": [
                        {
                            "attributes": {"type": "Contact"},
                            "Id": "003VALID",
                        },
                        {
                            "name": "Unrecognized record",
                        },
                    ],
                }),
                encoding="utf-8",
            )

            original = source.read_bytes()

            with self.assertRaisesRegex(
                ValueError,
                "Unrecognized Salesforce record at index 1",
            ):
                normalize_salesforce_json_to_csv(
                    source_path=source,
                    output_path=target,
                )

            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), original)

    def test_valid_salesforce_records_remain_accepted(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "valid.json"
            target = root / "result.csv"

            source.write_text(
                json.dumps({
                    "totalSize": 2,
                    "done": True,
                    "records": [
                        {
                            "attributes": {"type": "Account"},
                            "Id": "001VALID",
                        },
                        {
                            "attributes": {"type": "Contact"},
                            "Id": "003VALID",
                        },
                    ],
                }),
                encoding="utf-8",
            )

            result = normalize_salesforce_json_to_csv(
                source_path=source,
                output_path=target,
            )

            self.assertEqual(result.package.record_count, 2)

            with target.open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 2)
            self.assertEqual(
                [row["INSYT_SF_Record_ID"] for row in rows],
                ["001VALID", "003VALID"],
            )


    def test_standalone_record_size_budget(self):
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "account.json"
            target = Path(tmp) / "result.csv"

            source.write_text(
                json.dumps({
                    "attributes": {"type": "Account"},
                    "Id": "001LARGE",
                    "Description": "X" * 1000,
                }),
                encoding="utf-8",
            )

            original = source.read_bytes()

            with patch(
                "app.services.structured_intake."
                "adapters.json_salesforce."
                "MAX_SALESFORCE_RECORD_EVENT_BYTES",
                256,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Salesforce record size budget exceeded",
                ):
                    normalize_salesforce_json_to_csv(
                        source_path=source,
                        output_path=target,
                    )

            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), original)

    def test_standalone_record_depth_budget(self):
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "account.json"
            target = Path(tmp) / "result.csv"

            nested = {"value": "synthetic"}
            for _ in range(8):
                nested = {"child": nested}

            source.write_text(
                json.dumps({
                    "attributes": {"type": "Account"},
                    "Id": "001DEEP",
                    "Details": nested,
                }),
                encoding="utf-8",
            )

            with patch(
                "app.services.structured_intake."
                "adapters.json_salesforce."
                "MAX_SALESFORCE_RECORD_DEPTH",
                5,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "Salesforce record nesting-depth "
                    "budget exceeded",
                ):
                    normalize_salesforce_json_to_csv(
                        source_path=source,
                        output_path=target,
                    )

            self.assertFalse(target.exists())

if __name__ == "__main__":
    unittest.main()
