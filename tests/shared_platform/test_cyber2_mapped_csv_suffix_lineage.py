"""Permanent regression tests for Cyber2 mapped CSV header suffixes and lineage."""

import ast
import copy
import csv
import io
import re
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "backend/app/api/cyber2/schema_mapping.py"


def load_transform():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))

    required = {
        "_normalize_header",
        "_generate_mapped_document_rows",
    }

    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in required
    ]

    assert {node.name for node in nodes} == required

    namespace = {
        "Any": Any,
        "csv": csv,
        "io": io,
        "re": re,
    }

    module = ast.Module(body=nodes, type_ignores=[])
    exec(compile(module, str(SOURCE), "exec"), namespace)

    return namespace["_generate_mapped_document_rows"]


TRANSFORM = load_transform()


def make_result(headers, values, protocol=(), dispositions=None):
    columns = [
        {
            "column_index": i,
            "source_header": header,
            "final_header": header,
            "mapped_to_protocol": (
                header in protocol
                if dispositions is None
                else dispositions[i]
            ),
            "delete_column": False,
        }
        for i, header in enumerate(headers)
    ]

    original = copy.deepcopy(columns)

    result = TRANSFORM(
        source_rows=[list(headers), list(values)],
        approved_document={
            "header_status": "HEADER",
            "columns": columns,
        },
        protocol_headers=list(protocol),
    )

    assert columns == original, "Approved mappings were mutated"
    return result


class MappedCsvSuffixLineageTests(unittest.TestCase):

    def test_two_duplicate_headers(self):
        result = make_result(
            ["Policy", "Policy"],
            ["A", "B"],
            ["Policy"],
        )
        self.assertEqual(
            result["output_headers"],
            ["Policy", "Policy_2"],
        )
        self.assertEqual(result["rows"][1], ["A", "B"])

    def test_three_duplicates(self):
        result = make_result(
            ["Policy", "Policy", "Policy"],
            ["A", "B", "C"],
        )
        self.assertEqual(
            result["output_headers"],
            ["Policy", "Policy_2", "Policy_3"],
        )

    def test_existing_suffix_collision(self):
        result = make_result(
            ["Policy", "Policy", "Policy_2"],
            ["A", "B", "C"],
        )
        self.assertEqual(
            result["output_headers"],
            ["Policy", "Policy_3", "Policy_2"],
        )
        self.assertEqual(result["rows"][1], ["A", "B", "C"])

    def test_distinct_values_preserved(self):
        result = make_result(
            ["Health Insurance Policy Number"] * 2,
            ["BCBS12345", "AET99881"],
            ["Health Insurance Policy Number"],
        )
        self.assertEqual(
            result["rows"][1],
            ["BCBS12345", "AET99881"],
        )
        self.assertEqual(result["mapped_column_count"], 2)

    def test_identical_values_not_prematurely_deduplicated(self):
        result = make_result(
            ["Policy", "Policy"],
            ["UHC56789", "UHC56789"],
        )
        self.assertEqual(
            result["rows"][1],
            ["UHC56789", "UHC56789"],
        )

    def test_blank_value_preserved(self):
        result = make_result(
            ["Policy", "Policy"],
            ["MED11111", ""],
        )
        self.assertEqual(result["rows"][1], ["MED11111", ""])

    def test_column_lineage(self):
        result = make_result(
            ["Policy", "Policy"],
            ["A", "B"],
            ["Policy"],
        )
        lineage = result["column_lineage"]

        self.assertEqual(len(lineage), 2)
        self.assertEqual(
            [x["source_column_index"] for x in lineage],
            [0, 1],
        )
        self.assertEqual(
            [x["output_column_index"] for x in lineage],
            [0, 1],
        )
        self.assertEqual(
            [x["canonical_header"] for x in lineage],
            ["Policy", "Policy"],
        )
        self.assertEqual(
            [x["output_header"] for x in lineage],
            ["Policy", "Policy_2"],
        )

    def test_protocol_classification_of_suffix(self):
        result = make_result(
            ["Policy", "Policy"],
            ["A", "B"],
            ["Policy"],
        )
        self.assertEqual(
            result["protocol_headers_present"],
            ["Policy", "Policy_2"],
        )
        self.assertEqual(result["custom_headers_retained"], [])

    def test_protocol_order_and_value_alignment(self):
        result = make_result(
            ["Other", "Policy", "First Name", "Policy"],
            ["X", "A", "Jane", "B"],
            ["First Name", "Policy"],
        )

        self.assertEqual(
            result["output_headers"],
            ["First Name", "Policy", "Policy_2", "Other"],
        )
        self.assertEqual(
            result["rows"][1],
            ["Jane", "A", "B", "X"],
        )
        self.assertEqual(
            [
                x["source_column_index"]
                for x in result["column_lineage"]
            ],
            [2, 1, 3, 0],
        )

    def test_no_duplicate_names_for_unique_columns(self):
        result = make_result(
            ["First Name", "Last Name", "Policy"],
            ["Jane", "Doe", "P123"],
        )
        self.assertEqual(
            result["output_headers"],
            ["First Name", "Last Name", "Policy"],
        )
        self.assertEqual(
            result["rows"][1],
            ["Jane", "Doe", "P123"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
