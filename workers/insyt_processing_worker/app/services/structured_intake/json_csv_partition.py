from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any


DEFAULT_MAX_RECORDS = 10_000
DEFAULT_MAX_BYTES = 16 * 1024 * 1024


def partition_normalized_json_csv(
    *,
    source_csv: Path,
    output_dir: Path,
    max_records: int = DEFAULT_MAX_RECORDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[dict[str, Any]]:
    """Partition normalized JSON CSV without splitting records."""

    if max_records < 1 or max_bytes < 1:
        raise ValueError("Partition limits must be positive.")

    source_csv = Path(source_csv).resolve()
    output_dir = Path(output_dir).resolve()

    if not source_csv.is_file():
        raise FileNotFoundError(source_csv)

    if output_dir == source_csv.parent:
        raise ValueError(
            "Output directory must differ from source directory."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = source_csv.stem
    if list(output_dir.glob(f"{prefix}.part*.csv")):
        raise FileExistsError(
            "Partition outputs already exist; refusing overwrite."
        )

    results: list[dict[str, Any]] = []
    created: list[Path] = []
    handle = None
    part_number = 0
    part_count = 0
    part_bytes = 0
    total_records = 0
    first_record = 0

    def encode_row(values: list[str]) -> bytes:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(values)
        return buffer.getvalue().encode("utf-8")

    def finish_part() -> None:
        nonlocal handle
        if handle is None:
            return
        handle.close()
        handle = None
        results.append(
            {
                "part_number": part_number,
                "path": str(created[-1]),
                "record_count": part_count,
                "first_record": first_record,
                "last_record": total_records,
                "bytes": part_bytes,
            }
        )

    try:
        with source_csv.open(
            "r", encoding="utf-8-sig", newline=""
        ) as source:
            reader = csv.reader(source)
            headers = next(reader, None)

            if not headers:
                raise ValueError("Normalized CSV has no headers.")

            header_bytes = encode_row(headers)
            minimum_bytes = 3 + len(header_bytes)

            if minimum_bytes > max_bytes:
                raise ValueError(
                    "CSV headers exceed the partition byte limit."
                )

            def start_part() -> None:
                nonlocal handle, part_number, part_count
                nonlocal part_bytes, first_record

                part_number += 1
                part_count = 0
                part_bytes = minimum_bytes
                first_record = total_records + 1

                path = (
                    output_dir
                    / f"{prefix}.part{part_number:04d}.csv"
                )

                handle = path.open("wb")
                created.append(path)
                handle.write(b"\xef\xbb\xbf")
                handle.write(header_bytes)

            start_part()

            for values in reader:
                if len(values) != len(headers):
                    raise ValueError(
                        "CSV row has a different column count."
                    )

                row_bytes = encode_row(values)

                if minimum_bytes + len(row_bytes) > max_bytes:
                    raise ValueError(
                        "Individual JSON record exceeds "
                        "the partition byte limit."
                    )

                if (
                    part_count >= max_records
                    or (
                        part_count > 0
                        and part_bytes + len(row_bytes) > max_bytes
                    )
                ):
                    finish_part()
                    start_part()

                handle.write(row_bytes)
                part_count += 1
                part_bytes += len(row_bytes)
                total_records += 1

            finish_part()

        if sum(
            result["record_count"] for result in results
        ) != total_records:
            raise RuntimeError("Partition record-count mismatch.")

        return results

    except Exception:
        if handle is not None:
            handle.close()
        for path in created:
            path.unlink(missing_ok=True)
        raise
