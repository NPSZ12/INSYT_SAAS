from pathlib import Path
import pytest

from apc.detection.models import DetectionCandidate
from apc.stages import pii_phi_detection as stage


def _candidate(
    entity_type,
    start,
    end,
    *,
    entity_subtype=None,
):
    return DetectionCandidate(
        entity_type=entity_type,
        detected_value="synthetic-test-value",
        start_offset=start,
        end_offset=end,
        entity_subtype=entity_subtype or "",
        confidence=1.0,
        reportability="REPORTABLE",
        metadata={},
    )


def test_worksheet_triage_retains_first_per_type_and_scans_to_eof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worksheet = tmp_path / "worksheet.csv"
    worksheet.write_text(
        "Email: first@example.test\n"
        "Email: second@example.test\n"
        "Other: none\n"
        "SSN: 464-12-1234\n",
        encoding="utf-8",
        newline="\n",
    )

    seen_chunks = []

    def fake_engine(text, **kwargs):
        seen_chunks.append(text)
        candidates = []

        for value, kind in (
            ("first@example.test", "Email"),
            ("second@example.test", "Email"),
            ("464-12-1234", "USSocialSecurityNumber"),
        ):
            start = text.find(value)

            if start >= 0:
                candidates.append(
                    _candidate(
                        kind,
                        start,
                        start + len(value),
                    )
                )

        return {
            "candidates": candidates,
            "azure_candidate_count": 0,
            "structured_candidate_count": len(candidates),
            "merged_candidate_count": len(candidates),
        }

    monkeypatch.setattr(
        stage,
        "run_detection_engine",
        fake_engine,
    )
    monkeypatch.setattr(
        stage,
        "WORKSHEET_TRIAGE_CHUNK_ROWS",
        2,
    )

    result = stage._run_worksheet_triage_engine(
        path=worksheet,
        include_phi=True,
        protocol_name="test",
        protocol_version="1",
        enable_azure=False,
        structured_rules=[],
    )

    assert result["rows_scanned"] == 4
    assert result["scan_complete"] is True
    assert result["type_profile_complete"] is True
    assert result["entity_counts_complete"] is False
    assert result["triage_stopped_early"] is False

    assert len(seen_chunks) == 2

    candidates = result["candidates"]

    assert len(candidates) == 2

    by_type = {
        candidate.entity_type: candidate
        for candidate in candidates
    }

    assert by_type["Email"].start_offset == worksheet.read_text(
        encoding="utf-8"
    ).find("first@example.test")

    assert (
        by_type["USSocialSecurityNumber"].start_offset
        == worksheet.read_text(
            encoding="utf-8"
        ).find("464-12-1234")
    )

def test_worksheet_triage_1001_rows_late_hit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    worksheet = tmp_path / "large_worksheet.csv"

    rows = ["No sensitive data\n"] * 1000
    rows.append("SSN: 464-12-1234\n")

    worksheet.write_text(
        "".join(rows),
        encoding="utf-8",
        newline="\n",
    )

    chunks = []

    def fake_engine(text, **kwargs):
        chunks.append(text)

        value = "464-12-1234"
        start = text.find(value)

        candidates = []

        if start >= 0:
            candidates.append(
                _candidate(
                    "USSocialSecurityNumber",
                    start,
                    start + len(value),
                )
            )

        return {
            "candidates": candidates,
            "azure_candidate_count": 0,
            "structured_candidate_count": len(candidates),
            "merged_candidate_count": len(candidates),
        }

    monkeypatch.setattr(
        stage,
        "run_detection_engine",
        fake_engine,
    )

    monkeypatch.setattr(
        stage,
        "WORKSHEET_TRIAGE_CHUNK_ROWS",
        500,
    )

    monkeypatch.setattr(
        stage,
        "WORKSHEET_TRIAGE_CHUNK_CHARS",
        1_000_000,
    )

    result = stage._run_worksheet_triage_engine(
        path=worksheet,
        include_phi=True,
        protocol_name="test",
        protocol_version="1",
        enable_azure=False,
        structured_rules=[],
    )

    assert result["rows_scanned"] == 1001
    assert len(chunks) == 3
    assert result["scan_complete"] is True
    assert result["type_profile_complete"] is True
    assert result["entity_counts_complete"] is False

    candidates = result["candidates"]

    assert len(candidates) == 1
    assert candidates[0].entity_type == "USSocialSecurityNumber"

    assert (
        candidates[0].metadata["profile_first_hit_row"]
        == 1001
    )

def test_chunk_executor_receives_deterministic_units(tmp_path):
    from apc.stages.pii_phi_detection import (
        _run_worksheet_triage_engine,
    )

    path = tmp_path / "worksheet.csv"
    path.write_text(
        "synthetic,data\n" * 1001,
        encoding="utf-8",
        newline="\n",
    )

    seen = []

    def executor(unit):
        seen.append(
            (
                unit.unit_id,
                unit.start_row,
                unit.end_row,
                unit.start_offset,
                unit.end_offset,
            )
        )
        return {
            "candidates": [],
            "azure_candidate_count": 0,
            "structured_candidate_count": 0,
            "merged_candidate_count": 0,
        }

    result = _run_worksheet_triage_engine(
        path=path,
        include_phi=True,
        protocol_name=None,
        protocol_version=None,
        enable_azure=False,
        structured_rules=[],
        chunk_executor=executor,
    )

    assert len(seen) == 3

    assert [item[0] for item in seen] == [
        "chunk-000001",
        "chunk-000002",
        "chunk-000003",
    ]

    assert [item[1] for item in seen] == [
        1, 501, 1001,
    ]

    assert result["rows_scanned"] == 1001
    assert result["scan_complete"] is True
    assert result["candidates"] == []

def test_restored_chunks_match_fresh_profile(tmp_path, monkeypatch):
    from dataclasses import asdict

    from apc.detection.models import DetectionCandidate
    from apc.detection_candidate_codec import (
        serialize_candidate_batch,
        deserialize_candidate_batch,
    )
    from apc.stages import pii_phi_detection as stage

    path = tmp_path / "restoration.csv"

    lines = ["ordinary,data\n"] * 1001
    lines[0] = "email,first@example.test\n"
    lines[1000] = "ssn,123-45-6789\n"

    path.write_text(
        "".join(lines),
        encoding="utf-8",
        newline="\n",
    )

    calls = {"count": 0}

    def synthetic_engine(text, **kwargs):
        calls["count"] += 1
        candidates = []

        for marker, entity_type, subtype in (
            ("first@example.test", "Email", ""),
            ("123-45-6789", "IdentificationNumber", "SSN"),
        ):
            offset = text.find(marker)

            if offset >= 0:
                candidates.append(
                    DetectionCandidate(
                        entity_type=entity_type,
                        entity_subtype=subtype,
                        detected_value=marker,
                        start_offset=offset,
                        end_offset=offset + len(marker),
                        confidence=0.99,
                        detector_name="synthetic",
                        reportability="REPORTABLE",
                    )
                )

        return {
            "candidates": candidates,
            "azure_candidate_count": len(candidates),
            "structured_candidate_count": 0,
            "merged_candidate_count": len(candidates),
        }

    monkeypatch.setattr(
        stage,
        "run_detection_engine",
        synthetic_engine,
    )

    options = {
        "path": path,
        "include_phi": True,
        "protocol_name": None,
        "protocol_version": None,
        "enable_azure": False,
        "structured_rules": [],
    }

    fresh = stage._run_worksheet_triage_engine(**options)

    fresh_calls = calls["count"]

    assert fresh_calls == 3
    assert fresh["rows_scanned"] == 1001
    assert fresh["scan_complete"] is True
    assert len(fresh["candidates"]) == 2

    # Simulate checkpoint artifacts: serialize each
    # chunk's actual engine output in JSON form.
    cache = {}

    def persist_executor(unit):
        output = synthetic_engine(unit.text)
        cache[unit.unit_id] = {
            "candidates": serialize_candidate_batch(
                output["candidates"],
                chunk_length=len(unit.text),
            ),
            "azure_candidate_count": output[
                "azure_candidate_count"
            ],
            "structured_candidate_count": output[
                "structured_candidate_count"
            ],
            "merged_candidate_count": output[
                "merged_candidate_count"
            ],
        }
        return output

    staged = stage._run_worksheet_triage_engine(
        **options,
        chunk_executor=persist_executor,
    )

    assert len(cache) == 3

    calls_before_restore = calls["count"]

    def restored_executor(unit):
        record = cache[unit.unit_id]

        return {
            "candidates": deserialize_candidate_batch(
                record["candidates"],
                chunk_length=len(unit.text),
            ),
            "azure_candidate_count": record[
                "azure_candidate_count"
            ],
            "structured_candidate_count": record[
                "structured_candidate_count"
            ],
            "merged_candidate_count": record[
                "merged_candidate_count"
            ],
        }

    restored = stage._run_worksheet_triage_engine(
        **options,
        chunk_executor=restored_executor,
    )

    # Restoration must not invoke the detection engine.
    assert calls["count"] == calls_before_restore

    for key in (
        "rows_scanned",
        "characters_scanned",
        "scan_complete",
        "profiled_entity_types",
        "responsive_entity_types",
        "first_hit_row",
        "azure_candidate_count",
        "merged_candidate_count",
    ):
        assert fresh[key] == staged[key] == restored[key]

    assert [
        asdict(candidate)
        for candidate in fresh["candidates"]
    ] == [
        asdict(candidate)
        for candidate in restored["candidates"]
    ]

def test_main_detection_stage_exposes_executor_factory():
    import ast
    import inspect

    from apc.stages.pii_phi_detection import (
        run_pii_phi_detection,
    )

    signature = inspect.signature(run_pii_phi_detection)

    assert "worksheet_executor_factory" in signature.parameters
    assert (
        signature.parameters[
            "worksheet_executor_factory"
        ].default is None
    )

    source = inspect.getsource(run_pii_phi_detection)
    tree = ast.parse(source)

    factory_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "worksheet_executor_factory"
    ]

    assert len(factory_calls) == 1

    supplied = {
        keyword.arg
        for keyword in factory_calls[0].keywords
    }

    assert supplied == {
        "doc_id",
        "workspace",
        "structured_rules",
        "rule_source",
        "selected_sheets",
        "include_phi",
        "enable_azure",
        "protocol_name",
        "protocol_version",
    }

    triage_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_run_worksheet_triage_engine"
    ]

    assert len(triage_calls) == 1

    assert "chunk_executor" in {
        keyword.arg
        for keyword in triage_calls[0].keywords
    }

def test_incomplete_worksheet_bypasses_exception_and_finalization():
    import ast
    import inspect

    from apc.stages import pii_phi_detection as stage

    assert issubclass(
        stage.IncompleteWorksheetDetection,
        RuntimeError,
    )

    tree = ast.parse(
        inspect.getsource(stage.run_pii_phi_detection)
    )

    raises = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "IncompleteWorksheetDetection"
        and any(
            isinstance(arg, ast.Constant)
            and isinstance(arg.value, str)
            and "Worksheet detection is incomplete;" in arg.value
            for arg in node.exc.args
        )
    ]

    assert len(raises) == 1

    matching_handlers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and isinstance(node.type, ast.Name)
        and node.type.id == "IncompleteWorksheetDetection"
    ]

    assert len(matching_handlers) == 1

    handler = matching_handlers[0]

    assert len(handler.body) >= 1

    assert any(
        isinstance(node, ast.Raise)
        and node.exc is None
        for node in handler.body
    )

    try_blocks = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        and handler in node.handlers
    ]

    assert len(try_blocks) == 1

    document_try = try_blocks[0]

    # The incomplete-work exception must be handled
    # before the broad document exception handler.
    assert document_try.handlers[0] is handler

    assert any(
        isinstance(node, ast.ExceptHandler)
        and node.type is None or (
            isinstance(node, ast.ExceptHandler)
            and isinstance(node.type, ast.Name)
            and node.type.id == "Exception"
        )
        for node in document_try.handlers[1:]
    )

    # The completion gate must execute within the
    # document-processing try block.
    assert any(
        node is raises[0]
        for statement in document_try.body
        for node in ast.walk(statement)
    )
