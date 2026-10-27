from __future__ import annotations

from pathlib import Path

from ..base import AdapterContext, AdapterResult, PreparedChild
from .workbook_engine import (
    _iter_workbook_sheets,
    _safe_sheet_filename,
    _write_sheet_rows_to_csv,
)


class SpreadsheetAdapter:
    """Prepare workbook sheets; APC remains owner of child IDs and lineage.

    CSV files already traverse the proven flat-file ingestion route and are
    intentionally not expanded into sheets by this adapter.
    """
    name = "workbook"
    extensions = (".xlsx", ".xlsm", ".xltx", ".xltm", ".xls", ".xlsb")

    def process(self, context: AdapterContext) -> AdapterResult:
        source = Path(context.source_path)
        destination = Path(context.work_dir or (source.parent / ".workbook_prepared")) / "workbook_sheets"
        destination.mkdir(parents=True, exist_ok=True)

        manifest = {
            "schema_version": 1,
            "source_type": "workbook",
            "workbook_file_id": context.file_id,
            "workbook_name": source.name,
            "workbook_normalized_path": context.normalized_path,
            "workbook_format": context.extension.lstrip(".").lower(),
            "derivation_method": "workbook_sheet_to_csv",
            "triage_detection_mode": "first_reportable_hit",
            "sheet_count": 0,
            "nonblank_sheet_count": 0,
            "blank_sheet_count": 0,
            "generated_child_count": 0,
            "sheets": [],
        }
        children: list[PreparedChild] = []
        errors: list[dict] = []
        try:
            for sheet in _iter_workbook_sheets(source, context.extension):
                index = int(sheet["sheet_index"])
                name = str(sheet.get("sheet_name") or f"Sheet{index}")
                visibility = str(sheet.get("sheet_visibility") or "unknown")
                manifest["sheet_count"] += 1
                csv_name = _safe_sheet_filename(name, index)
                csv_path = destination / csv_name
                try:
                    metrics = _write_sheet_rows_to_csv(sheet["rows"], csv_path)
                except Exception as exc:
                    failure = {"sheet_index": index, "sheet_name": name, "visibility": visibility,
                               "status": "failed", "error": repr(exc)}
                    manifest["sheets"].append(failure)
                    errors.append(failure)
                    continue
                if metrics["is_blank"]:
                    manifest["blank_sheet_count"] += 1
                    manifest["sheets"].append({
                        "sheet_index": index, "sheet_name": name, "visibility": visibility,
                        "status": "blank", "child_file_id": None, "child_doc_id": None,
                        "rows_seen": metrics["rows_seen"], "nonblank_row_count": 0,
                        "max_column_count": 0, "nonblank_cell_count": 0,
                        "triage_status": "not_required_blank", "counts_complete": True,
                    })
                    continue
                manifest["nonblank_sheet_count"] += 1
                manifest["generated_child_count"] += 1
                logical_path = f"{context.normalized_path}!/workbook/{csv_name}"
                sheet_details = {
                    "sheet_index": index, "sheet_name": name, "visibility": visibility,
                    "status": "converted", "child_file_id": None, "child_doc_id": None,
                    "csv_name": csv_name, "csv_path": str(csv_path),
                    "logical_path": logical_path, "csv_bytes": int(metrics["csv_bytes"]),
                    "rows_seen": metrics["rows_seen"],
                    "nonblank_row_count": metrics["nonblank_row_count"],
                    "max_column_count": metrics["max_column_count"],
                    "nonblank_cell_count": metrics["nonblank_cell_count"],
                    "triage_status": "pending", "triage_detection_mode": "first_reportable_hit",
                    "counts_complete": False,
                }
                manifest["sheets"].append(sheet_details)
                children.append(PreparedChild(
                    source_path=csv_path, normalized_path=logical_path,
                    relationship="workbook_sheet", original_name=csv_name,
                    extension=".csv", metadata={
                        "workbook_sheet": {
                            "schema_version": 1, "source_type": "workbook_sheet",
                            "derived_from": "workbook_sheet",
                            "derivation_method": "workbook_sheet_to_csv",
                            "original_workbook_file_id": context.file_id,
                            "original_workbook_name": source.name,
                            "original_workbook_path": str(source),
                            "original_workbook_normalized_path": context.normalized_path,
                            "workbook_format": context.extension.lstrip(".").lower(),
                            "sheet_name": name, "sheet_index": index,
                            "sheet_visibility": visibility,
                            "sheet_rows_seen": metrics["rows_seen"],
                            "sheet_nonblank_row_count": metrics["nonblank_row_count"],
                            "sheet_column_count": metrics["max_column_count"],
                            "sheet_nonblank_cell_count": metrics["nonblank_cell_count"],
                            "triage_status": "pending",
                            "triage_detection_mode": "first_reportable_hit",
                            "counts_complete": False, "full_iar_status": "pending_if_hit",
                        },
                    },
                ))
        except Exception as exc:
            errors.append({"error": repr(exc)})
        status = "completed"
        if errors:
            status = "completed_with_warnings" if (children or manifest["blank_sheet_count"]) else "failed"
        return AdapterResult(
            adapter_name=self.name, handled=True, status=status,
            source_file_id=context.file_id, children=children,
            metadata={"workbook_manifest": manifest, "sheet_errors": errors},
            error="; ".join(str(item.get("error", "")) for item in errors) or None,
        )


SPREADSHEET_ADAPTER = SpreadsheetAdapter()
