from apc.worksheet_work_units import (
    iter_worksheet_work_units,
)


def test_1001_rows_produce_three_chunks(tmp_path):
    path = tmp_path / "sheet.csv"
    path.write_text(
        "synthetic,data\n" * 1001,
        encoding="utf-8",
        newline="\n",
    )

    units = list(iter_worksheet_work_units(path))

    assert len(units) == 3
    assert [unit.row_count for unit in units] == [
        500, 500, 1,
    ]
    assert [unit.start_row for unit in units] == [
        1, 501, 1001,
    ]
    assert [unit.unit_id for unit in units] == [
        "chunk-000001",
        "chunk-000002",
        "chunk-000003",
    ]


def test_offsets_preserve_original_text(tmp_path):
    path = tmp_path / "sheet.csv"
    original = "a,b\r\nc,d\r\ne,f\r\n"

    path.write_bytes(original.encode("utf-8"))

    units = list(
        iter_worksheet_work_units(
            path,
            max_rows=2,
        )
    )

    assert len(units) == 2

    for unit in units:
        assert original[
            unit.start_offset:unit.end_offset
        ] == unit.text


def test_chunk_identity_is_deterministic(tmp_path):
    path = tmp_path / "sheet.csv"
    path.write_text(
        "one,two\nthree,four\n",
        encoding="utf-8",
        newline="\n",
    )

    first = list(
        iter_worksheet_work_units(
            path,
            max_rows=1,
        )
    )

    second = list(
        iter_worksheet_work_units(
            path,
            max_rows=1,
        )
    )

    assert first == second
    assert first[0].text_sha256 != first[1].text_sha256


def test_character_boundary_and_empty_file(tmp_path):
    path = tmp_path / "sheet.csv"
    path.write_text(
        "abcd\n1234\n",
        encoding="utf-8",
        newline="\n",
    )

    units = list(
        iter_worksheet_work_units(
            path,
            max_chars=5,
        )
    )

    assert len(units) == 2
    assert units[0].end_offset == 5
    assert units[1].start_offset == 5

    path.write_text("", encoding="utf-8")

    assert list(iter_worksheet_work_units(path)) == []