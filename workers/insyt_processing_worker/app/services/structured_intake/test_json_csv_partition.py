import csv
import tempfile
import unittest
from pathlib import Path

from .json_csv_partition import partition_normalized_json_csv


class TestJsonCsvPartition(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "normalized.csv"
        self.parts = self.root / "parts"

    def write_rows(self, count, value="example"):
        with self.source.open(
            "w", encoding="utf-8-sig", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(["ID", "Name"])
            for index in range(count):
                writer.writerow([index + 1, value])

    def read_parts(self, parts):
        headers = []
        rows = []
        for part in parts:
            with Path(part["path"]).open(
                "r", encoding="utf-8-sig", newline=""
            ) as handle:
                reader = csv.reader(handle)
                headers.append(next(reader))
                rows.extend(list(reader))
        return headers, rows

    def test_single_child(self):
        self.write_rows(2)
        parts = partition_normalized_json_csv(
            source_csv=self.source,
            output_dir=self.parts,
            max_records=3,
        )
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["record_count"], 2)

    def test_multiple_children_and_lineage(self):
        self.write_rows(7)
        parts = partition_normalized_json_csv(
            source_csv=self.source,
            output_dir=self.parts,
            max_records=3,
        )
        self.assertEqual(
            [p["record_count"] for p in parts],
            [3, 3, 1],
        )
        self.assertEqual(
            [p["first_record"] for p in parts],
            [1, 4, 7],
        )
        self.assertEqual(
            [p["last_record"] for p in parts],
            [3, 6, 7],
        )
        headers, rows = self.read_parts(parts)
        self.assertEqual(headers, [["ID", "Name"]] * 3)
        self.assertEqual(
            [row[0] for row in rows],
            [str(i) for i in range(1, 8)],
        )

    def test_byte_limit(self):
        self.write_rows(4, value="X" * 30)
        parts = partition_normalized_json_csv(
            source_csv=self.source,
            output_dir=self.parts,
            max_records=100,
            max_bytes=75,
        )
        self.assertEqual(len(parts), 4)
        self.assertTrue(
            all(p["bytes"] <= 75 for p in parts)
        )

    def test_oversized_record_cleans_up(self):
        self.write_rows(2, value="X" * 200)
        with self.assertRaises(ValueError):
            partition_normalized_json_csv(
                source_csv=self.source,
                output_dir=self.parts,
                max_bytes=100,
            )
        self.assertFalse(list(self.parts.glob("*.csv")))

    def test_empty_population_has_header_only(self):
        self.write_rows(0)
        parts = partition_normalized_json_csv(
            source_csv=self.source,
            output_dir=self.parts,
        )
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["record_count"], 0)

    def test_native_source_unchanged(self):
        self.write_rows(5)
        before = self.source.read_bytes()
        partition_normalized_json_csv(
            source_csv=self.source,
            output_dir=self.parts,
            max_records=2,
        )
        self.assertEqual(self.source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
