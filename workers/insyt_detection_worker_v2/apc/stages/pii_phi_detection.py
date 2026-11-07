from __future__ import annotations


from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from ..detection.engine import run_detection_engine
from ..detection.models import DetectionCandidate
from ..detection.rules import DetectionRule
from ..detection.capture_rules import (
    load_capture_rules_from_azure,
)
from ..detection.discovery_rules import (
    load_discovery_rules_from_azure,
)

from ..util import json_dumps, new_id, utc_now


DETECTOR_NAME = "insyt_detection_engine"
DETECTOR_VERSION = "v1"

WORKSHEET_TRIAGE_CHUNK_CHARS = 32_000
WORKSHEET_TRIAGE_CHUNK_ROWS = 500

FULL_DETECTION_MODE = "full"
WORKSHEET_TRIAGE_MODE = "worksheet_triage"
IAR_FULL_DETECTION_MODE = "iar_full"

NON_REPORTABLE_REPORTABILITY = {
    "NOT_REPORTABLE",
    "NON_REPORTABLE",
    "NFR",
    "EXCLUDED",
}


def _row_get(row: Any, *names: str):
    for name in names:
        try:
            value = row[name]
        except Exception:
            value = getattr(row, name, None)

        if value not in (None, ""):
            return value

    return None


def _get_stage_status(row: Any) -> dict:
    raw = _row_get(row, "stage_status_json")

    if not raw:
        return {}

    try:
        import json

        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _find_text_path(row: Any) -> str | None:
    explicit = _row_get(
        row,
        "text_output_path",
        "ocr_text_path",
        "extracted_text_path",
        "text_path",
        "review_text_path",
        "output_text_path",
    )

    if explicit:
        path = Path(str(explicit))

        if path.exists() and path.is_file():
            return str(path)

    stage_status = _get_stage_status(row)

    ocr_live = stage_status.get("ocr_live") or {}

    if isinstance(ocr_live, dict):
        ocr_text_path = ocr_live.get("text_path")

        if ocr_text_path:
            path = Path(str(ocr_text_path))

            if path.exists() and path.is_file():
                return str(path)

    original_path = _row_get(
        row,
        "original_path",
        "source_path",
        "file_path",
        "path",
    )

    doc_id = _row_get(
        row,
        "doc_id",
        "assigned_doc_id",
        "document_id",
    )

    if original_path and doc_id:
        source = Path(str(original_path))

        derived = (
            source.parent.parent
            / "text"
            / f"{doc_id}.txt"
        )

        if derived.exists() and derived.is_file():
            return str(derived)

    return None


def _mask_value(value: str) -> str:
    text = str(value or "")

    if len(text) <= 2:
        return "*" * len(text)

    if len(text) <= 6:
        return text[0] + ("*" * (len(text) - 2)) + text[-1]

    return text[:2] + ("*" * (len(text) - 4)) + text[-2:]


def _insert_detection_candidate(
    db,
    *,
    detection_run_id: str,
    detection_document_id: str,
    matter_id: str,
    file_id: str,
    doc_id: str,
    candidate: DetectionCandidate,
    source_text_type: str,
):
    entity_text = str(
        candidate.detected_value
        or ""
    )

    normalized_value = str(
        candidate.normalized_value
        or entity_text.strip()
    )

    masked_value = str(
        candidate.masked_value
        or _mask_value(entity_text)
    )

    db.execute(
        """
        INSERT INTO processing_detection_entity (
            detection_entity_id,
            detection_run_id,
            detection_document_id,
            matter_id,
            file_id,
            doc_id,
            entity_type,
            entity_subtype,
            detected_value,
            normalized_value,
            masked_value,
            confidence,
            start_offset,
            end_offset,
            page_number,
            detector_name,
            detector_version,
            detection_rule,
            protocol_name,
            protocol_version,
            reportability,
            source_text_type,
            metadata_json,
            created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            new_id("DETENT"),
            detection_run_id,
            detection_document_id,
            matter_id,
            file_id,
            doc_id,
            candidate.entity_type or "Unknown",
            candidate.entity_subtype or None,
            entity_text,
            normalized_value,
            masked_value,
            float(
                candidate.confidence
                or 0.0
            ),
            int(
                candidate.start_offset
            ),
            int(
                candidate.end_offset
            ),
            candidate.page_number,
            candidate.detector_name
            or DETECTOR_NAME,
            candidate.detector_version
            or DETECTOR_VERSION,
            candidate.detection_rule
            or "",
            candidate.protocol_name
            or None,
            candidate.protocol_version
            or None,
            candidate.reportability
            or "UNCLASSIFIED",
            source_text_type,
            json_dumps(
                {
                    "methods": list(
                        candidate.methods
                    ),
                    "context_terms": list(
                        candidate.context_terms
                    ),
                    "validation_status": (
                        candidate.validation_status
                    ),
                    "validation_method": (
                        candidate.validation_method
                    ),
                    **dict(
                        candidate.metadata
                        or {}
                    ),
                }
            ),
            utc_now(),
        ),
    )

def _normalized_entity_type(
    candidate: DetectionCandidate,
) -> str:
    return (
        str(
            candidate.entity_type
            or ""
        )
        .strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


def _candidate_is_responsive(
    candidate: DetectionCandidate,
) -> bool:
    """
    Determine whether an entity type is sufficient to make a
    worksheet responsive.

    Person/PersonType are retained in the worksheet profile,
    but a name by itself does not make the worksheet responsive.
    """

    reportability = str(
        candidate.reportability
        or "UNCLASSIFIED"
    ).strip().upper()

    if (
        reportability
        in NON_REPORTABLE_REPORTABILITY
    ):
        return False

    entity_type = (
        _normalized_entity_type(
            candidate
        )
    )

    if entity_type in {
        "person",
        "persontype",
    }:
        return False

    return True


def _normalized_detection_mode(
    value: Any,
) -> str:
    mode = str(
        value
        or FULL_DETECTION_MODE
    ).strip().lower()

    if mode in {
        FULL_DETECTION_MODE,
        WORKSHEET_TRIAGE_MODE,
        IAR_FULL_DETECTION_MODE,
    }:
        return mode

    return FULL_DETECTION_MODE


def _run_full_detection_engine(
    *,
    path: Path,
    include_phi: bool,
    protocol_name: str | None,
    protocol_version: str | None,
    enable_azure: bool = True,
    structured_rules: Iterable[
        DetectionRule
    ] | None = None,
) -> dict[str, Any]:
    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    if not text.strip():
        raise RuntimeError(
            "Detection text file is empty."
        )

    result = run_detection_engine(
        text,
        include_phi=include_phi,
        protocol_name=protocol_name,
        protocol_version=protocol_version,
        enable_azure=enable_azure,
        enable_structured_rules=True,
        structured_rules=structured_rules,
    )

    return {
        **result,
        "detection_mode":
            FULL_DETECTION_MODE,
        "scan_complete": True,
        "entity_counts_complete": True,
        "triage_stopped_early": False,
        "rows_scanned": None,
        "characters_scanned": len(
            text
        ),
        "first_hit_row": None,
    }


def _run_worksheet_triage_engine(
    *,
    path: Path,
    include_phi: bool,
    protocol_name: str | None,
    protocol_version: str | None,
    enable_azure: bool = True,
    structured_rules: Iterable[
        DetectionRule
    ] | None = None,
    chunk_executor=None,
    max_chunks: int | None = None,
) -> dict[str, Any]:
    """
    Profile a worksheet-derived CSV/text representation.

    The worksheet is scanned to EOF.

    Only the FIRST validated occurrence of each entity type is
    retained. Repeated occurrences of an already-discovered type
    are ignored for this pass.

    This provides data-type coverage without performing an
    exhaustive occurrence-counting IAR.

    Example:

        Person       -> retain first
        Person       -> ignore repeat
        SSN          -> retain first
        SSN          -> ignore repeat
        DOB          -> retain first
        Email        -> retain first

    Person/PersonType are profiled but do not independently make
    a worksheet responsive.
    """

    if max_chunks is not None:
        if type(max_chunks) is not int or max_chunks < 0:
            raise ValueError(
                "max_chunks must be positive."
            )
        if chunk_executor is None:
            raise ValueError(
                "Bounded execution requires an executor."
            )
        if max_chunks == 0 and not callable(
            getattr(chunk_executor, "load_completed", None)
        ):
            raise ValueError(
                "Zero budget requires checkpoint restoration."
            )

    chunks_processed = 0
    scan_complete = True
    rows_scanned = 0
    characters_scanned = 0

    chunk_parts: list[str] = []
    chunk_char_count = 0
    chunk_row_count = 0

    chunk_start_offset = 0
    chunk_start_row = 1

    azure_candidate_count = 0
    structured_candidate_count = 0
    merged_candidate_count = 0

    first_candidates_by_type: dict[
        str,
        DetectionCandidate,
    ] = {}

    first_rows_by_type: dict[
        str,
        int,
    ] = {}

    responsive_entity_types: set[str] = set()

    first_responsive_hit_row: int | None = None

    def scan_chunk(restored_result=None) -> None:
        nonlocal azure_candidate_count
        nonlocal structured_candidate_count
        nonlocal merged_candidate_count
        nonlocal first_responsive_hit_row

        if not chunk_parts:
            return

        chunk_text = "".join(
            chunk_parts
        )

        if not chunk_text.strip():
            return

        if restored_result is not None:
            engine_result = restored_result
        elif chunk_executor is None:
            engine_result = run_detection_engine(
                chunk_text,
                include_phi=include_phi,
                protocol_name=protocol_name,
                protocol_version=protocol_version,
                enable_azure=enable_azure,
                enable_structured_rules=True,
                structured_rules=structured_rules,
            )
        else:
            # The executor receives the deterministic work
            # unit and may return a verified cached result.
            # It must preserve chunk-local candidate offsets.
            engine_result = chunk_executor(unit)

        if not isinstance(engine_result, dict):
            raise TypeError(
                "Worksheet chunk executor must return a dictionary."
            )

        azure_candidate_count += int(
            engine_result.get(
                "azure_candidate_count",
                0,
            )
            or 0
        )

        structured_candidate_count += int(
            engine_result.get(
                "structured_candidate_count",
                0,
            )
            or 0
        )

        candidates = (
            engine_result.get(
                "candidates"
            )
            or []
        )

        merged_candidate_count += int(
            engine_result.get(
                "merged_candidate_count",
                len(candidates),
            )
            or 0
        )

        for candidate in candidates:
            entity_type = (
                _normalized_entity_type(
                    candidate
                )
            )

            if not entity_type:
                continue

            entity_subtype = (
                str(
                    candidate.entity_subtype
                    or ""
                )
                .strip()
                .lower()
                .replace("_", "")
                .replace("-", "")
                .replace(" ", "")
            )

            #
            # Profile by entity type + subtype when a subtype exists.
            #
            # Examples:
            #
            #   Person
            #       -> person
            #
            #   IdentificationNumber / SSN
            #       -> identificationnumber:ssn
            #
            #   IdentificationNumber / Passport
            #       -> identificationnumber:passport
            #
            # This prevents distinct subtypes under the same parent
            # entity type from being collapsed into a single profile hit.
            #
            profile_key = (
                f"{entity_type}:{entity_subtype}"
                if entity_subtype
                else entity_type
            )

            #
            # Coverage pass:
            # once we have one validated example of this type/subtype,
            # additional occurrences are unnecessary.
            #
            if (
                profile_key
                in first_candidates_by_type
            ):
                continue

            local_start = int(
                candidate.start_offset
            )

            local_end = int(
                candidate.end_offset
            )

            before_candidate = (
                chunk_text[
                    :local_start
                ]
            )

            row_offset = (
                before_candidate.count(
                    "\n"
                )
            )

            candidate_row = (
                chunk_start_row
                + row_offset
            )

            adjusted_candidate = replace(
                candidate,
                start_offset=(
                    chunk_start_offset
                    + local_start
                ),
                end_offset=(
                    chunk_start_offset
                    + local_end
                ),
                metadata={
                    **dict(
                        candidate.metadata
                        or {}
                    ),
                    "worksheet_triage": True,
                    "worksheet_profile": True,
                    "profile_strategy": (
                        "first_per_entity_type_subtype"
                    ),
                    "profile_chunk_start_offset": (
                        chunk_start_offset
                    ),
                    "profile_chunk_start_row": (
                        chunk_start_row
                    ),
                    "profile_first_hit_row": (
                        candidate_row
                    ),
                },
            )

            first_candidates_by_type[
                profile_key
            ] = adjusted_candidate

            first_rows_by_type[
                profile_key
            ] = candidate_row

            if _candidate_is_responsive(
                adjusted_candidate
            ):
                responsive_entity_types.add(
                    profile_key
                )

                if (
                    first_responsive_hit_row
                    is None
                ):
                    first_responsive_hit_row = (
                        candidate_row
                    )

    # Shared deterministic worksheet boundaries.
    # Existing scan_chunk() retains all detection,
    # first-occurrence, offset and responsiveness logic.
    from ..worksheet_work_units import (
        iter_worksheet_work_units,
    )

    for unit in iter_worksheet_work_units(
        path,
        max_chars=WORKSHEET_TRIAGE_CHUNK_CHARS,
        max_rows=WORKSHEET_TRIAGE_CHUNK_ROWS,
    ):
        restored = None

        if max_chunks is not None:
            load_completed = getattr(
                chunk_executor, "load_completed", None
            )

            if callable(load_completed):
                restored = load_completed(unit)

                if (
                    restored is not None
                    and not isinstance(restored, dict)
                ):
                    raise TypeError(
                        "Invalid restored chunk result."
                    )

            if (
                restored is None
                and chunks_processed >= max_chunks
            ):
                scan_complete = False
                break

        chunk_parts = [unit.text]
        chunk_start_offset = unit.start_offset
        chunk_start_row = unit.start_row

        rows_scanned = unit.end_row
        characters_scanned = unit.end_offset

        scan_chunk(restored_result=restored)
        if restored is None:
            chunks_processed += 1

        chunk_parts = []
    profiled_candidates = sorted(
        first_candidates_by_type.values(),
        key=lambda candidate: (
            int(
                candidate.start_offset
            ),
            int(
                candidate.end_offset
            ),
        ),
    )

    profiled_entity_types = [
        (
            f"{candidate.entity_type}:{candidate.entity_subtype}"
            if candidate.entity_subtype
            else str(
                candidate.entity_type
                or "Unknown"
            )
        )
        for candidate
        in profiled_candidates
    ]

    return {
        "new_chunks_processed": chunks_processed,
        "candidates": (
            profiled_candidates
        ),
        "azure_candidate_count": (
            azure_candidate_count
        ),
        "structured_candidate_count": (
            structured_candidate_count
        ),
        "merged_candidate_count": (
            merged_candidate_count
        ),
        "detectors": [
            "azure_language",
            "insyt_structured_rules",
        ],

        #
        # Keep the existing mode identifier so the API/worker
        # contract remains backward compatible.
        #
        "detection_mode": (
            WORKSHEET_TRIAGE_MODE
        ),

        "profile_strategy": (
            "first_per_entity_type_subtype"
        ),

        #
        # EOF was reached, so we know which entity TYPES are
        # present even though occurrence counts are incomplete.
        #
        "scan_complete": scan_complete,
        "entity_counts_complete": False,
        "type_profile_complete": True,

        #
        # This mode no longer stops on first hit.
        #
        "triage_stopped_early": False,

        "rows_scanned": (
            rows_scanned
        ),
        "characters_scanned": (
            characters_scanned
        ),

        "first_hit_row": (
            first_responsive_hit_row
        ),

        "profiled_entity_type_count": (
            len(
                profiled_candidates
            )
        ),

        "profiled_entity_types": (
            profiled_entity_types
        ),

        "responsive_entity_type_count": (
            len(
                responsive_entity_types
            )
        ),

        "responsive_entity_types": (
            sorted(
                responsive_entity_types
            )
        ),

        "responsive_hit_count": (
            len(
                responsive_entity_types
            )
        ),

        "first_rows_by_entity_type": {
            (
                (
                    f"{first_candidates_by_type[profile_key].entity_type}:"
                    f"{first_candidates_by_type[profile_key].entity_subtype}"
                )
                if first_candidates_by_type[
                    profile_key
                ].entity_subtype
                else str(
                    first_candidates_by_type[
                        profile_key
                    ].entity_type
                    or profile_key
                )
            ): first_rows_by_type[
                profile_key
            ]
            for profile_key
            in first_candidates_by_type
        },
    }

def _verify_selected_worksheet_progress(
    *,
    rows,
    document_options,
    workspace_key,
    structured_rules,
    rule_workbook_blob,
    selected_rule_sheets,
    include_phi,
    enable_azure_detection,
    protocol_name,
    protocol_version,
    worksheet_executor_factory,
    selected_doc_ids,
):
    """Verify the exact selected worksheet population."""
    from ..detection_checkpoint_progress import (
        verify_detection_checkpoint_progress,
    )

    if not callable(worksheet_executor_factory):
        raise RuntimeError(
            "Checkpoint executor factory unavailable."
        )

    worksheets = []
    seen = set()

    for row in rows:
        doc_id = str(_row_get(row, "doc_id") or "").strip()

        if not doc_id or doc_id in seen:
            raise ValueError(
                "Missing or duplicate selected document ID."
            )

        seen.add(doc_id)

        options = document_options.get(doc_id) or {}

        if (
            _normalized_detection_mode(
                options.get("detection_mode")
            ) != WORKSHEET_TRIAGE_MODE
        ):
            raise ValueError(
                "Bounded checkpoint verification requires "
                "worksheet-triage documents."
            )

        path_value = _find_text_path(row)

        if not path_value:
            raise RuntimeError(
                "Selected worksheet text path missing."
            )

        executor = worksheet_executor_factory(
            doc_id=doc_id,
            workspace=workspace_key,
            structured_rules=structured_rules,
            rule_source=rule_workbook_blob,
            selected_sheets=selected_rule_sheets,
            include_phi=include_phi,
            enable_azure=enable_azure_detection,
            protocol_name=protocol_name,
            protocol_version=protocol_version,
        )

        worksheets.append({
            "doc_id": doc_id,
            "path": path_value,
            "executor": executor,
        })

    if selected_doc_ids and seen != selected_doc_ids:
        raise ValueError(
            "Verified worksheet population does not match "
            "the selected document IDs."
        )

    return verify_detection_checkpoint_progress(
        worksheets=worksheets,
        max_chars=WORKSHEET_TRIAGE_CHUNK_CHARS,
        max_rows=WORKSHEET_TRIAGE_CHUNK_ROWS,
    )


class IncompleteWorksheetDetection(RuntimeError):
    """Incomplete worksheet; do not classify or finalize."""


def run_pii_phi_detection(
    db,
    *,
    source_job_id: str,
    matter_id: str,
    client_id: str,
    project: str,
    workspace: str = "capture",
    protocol_name: str | None = None,
    protocol_version: str | None = None,
    include_phi: bool = True,
    search_rule_sheets: (
        list[str]
        | tuple[str, ...]
        | None
    ) = None,
    selected_doc_ids: (
        set[str] | None
    ) = None,
    document_options: (
        dict[str, dict[str, Any]]
        | None
    ) = None,
    worksheet_executor_factory=None,
    max_chunks_per_document: int | None = None,
) -> dict:
    """
    Scan ingestion-complete documents with the unified INSYT
    Data Element Detection engine.

    Current detector stack:
    - Azure AI Language PII / PHI NER
    - INSYT structured regex/context/validator rules
    - merge/deduplication

    This stage is intentionally separate from Initial Ingestion. It is called
    by the Data Element Detection workflow after Doc ID assignment, native
    text extraction, and any required OCR have completed.
    """
    
    selected_doc_ids = {
        str(doc_id).strip()
        for doc_id in (
            selected_doc_ids
            or set()
        )
        if str(doc_id).strip()
    }

    document_options = (
        document_options
        or {}
    )

    workspace_key = str(
        workspace
        or "capture"
    ).strip().lower()

    selected_rule_sheets = tuple(
        str(sheet_name).strip()
        for sheet_name in (
            search_rule_sheets
            or []
        )
        if str(
            sheet_name
            or ""
        ).strip()
    )

    structured_rules: (
        list[DetectionRule]
        | None
    ) = None

    rule_workbook_blob = ""

    enable_azure_detection = True

    if workspace_key == "discovery":
        #
        # Discovery responsiveness is driven only
        # by Discovery Search Rules.
        #
        # Capture-style Azure PII/PHI detection
        # must not make Discovery documents
        # responsive.
        #
        (
            structured_rules,
            rule_workbook_blob,
        ) = load_discovery_rules_from_azure(
            client=client_id,
            project=project,
            sheet_names=(
                selected_rule_sheets
                or None
            ),
        )

        enable_azure_detection = False
        include_phi = False

    elif workspace_key == "capture":
        #
        # Capture now prefers the Excel rule
        # workbook.
        #
        # During migration, if the workbook
        # cannot be loaded, structured_rules
        # remains None, which preserves the
        # existing built-in rules as a fallback.
        #
        try:
            (
                structured_rules,
                rule_workbook_blob,
            ) = load_capture_rules_from_azure(
                client=client_id,
                project=project,
                sheet_names=(
                    selected_rule_sheets
                    or None
                ),
            )

        except Exception:
            structured_rules = None
            rule_workbook_blob = (
                "built_in_rules_fallback"
            )

        enable_azure_detection = True

    detection_run_id = new_id("DETRUN")
    now = utc_now()

    db.execute(
        """
        INSERT INTO processing_detection_run (
            detection_run_id,
            matter_id,
            client_id,
            workspace,
            source_job_id,
            protocol_name,
            protocol_version,
            detector_name,
            detector_version,
            created_at,
            started_at,
            status,
            metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            detection_run_id,
            matter_id,
            client_id,
            workspace,
            source_job_id,
            protocol_name,
            protocol_version,
            DETECTOR_NAME,
            DETECTOR_VERSION,
            now,
            now,
            "running",
            json_dumps(
                {
                    "include_phi": include_phi,
                    "engine": "INSYT Data Element Detection",
                    "azure_ner_enabled": True,
                    "structured_rules_enabled": True,
                    "merge_enabled": True,
                    "service_logs_disabled": True,
                }
            ),
        ),
    )

    if max_chunks_per_document is not None:
        if (
            type(max_chunks_per_document) is not int
            or max_chunks_per_document < 1
        ):
            raise ValueError(
                "Invalid shared detection budget."
            )
        if worksheet_executor_factory is None:
            raise ValueError(
                "Bounded detection requires checkpoints."
            )

    remaining_chunks = max_chunks_per_document
    rows = db.query(
        """
        SELECT *
        FROM file_processing_metrics
        WHERE job_id=?
          AND is_container=0
          AND is_denisted=0
          AND is_duplicate=0
          AND doc_id IS NOT NULL
        ORDER BY doc_id
        """,
        (source_job_id,),
    )
    
    if selected_doc_ids:
        rows = [
            row
            for row in rows
            if str(
                _row_get(
                    row,
                    "doc_id",
                )
                or ""
            ).strip()
            in selected_doc_ids
        ]

    documents_total = len(rows)
    documents_scanned = 0
    documents_with_hits = 0
    documents_no_hits = 0
    documents_exception = 0
    entity_hit_count = 0
    
    azure_candidate_count = 0
    structured_candidate_count = 0
    merged_candidate_count = 0

    for row in rows:
        file_id = str(_row_get(row, "file_id") or "")
        doc_id = str(_row_get(row, "doc_id") or "")
        
        doc_options = (
            document_options.get(
                doc_id
            )
            or {}
        )

        detection_mode = (
            _normalized_detection_mode(
                doc_options.get(
                    "detection_mode"
                )
            )
        )

        is_workbook_sheet = bool(
            doc_options.get(
                "is_workbook_sheet"
            )
            or detection_mode
            == WORKSHEET_TRIAGE_MODE
        )

        detection_document_id = new_id("DETDOC")

        text_path = _find_text_path(row)

        text_source = "unknown"

        stage_status = _get_stage_status(row)

        ocr_live = stage_status.get("ocr_live") or {}

        if isinstance(ocr_live, dict) and ocr_live.get("status") == "completed":
            text_source = "azure_document_intelligence_read"
        elif int(_row_get(row, "has_native_text") or 0):
            text_source = "native_text"

        db.execute(
            """
            INSERT INTO processing_detection_document (
                detection_document_id,
                detection_run_id,
                matter_id,
                source_job_id,
                file_id,
                doc_id,
                text_source,
                text_path,
                detection_status,
                classification,
                hit_count,
                protocol_name,
                protocol_version,
                exception_json,
                metadata_json,
                created_at,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                detection_document_id,
                detection_run_id,
                matter_id,
                source_job_id,
                file_id,
                doc_id,
                text_source,
                text_path,
                "running",
                "PENDING",
                0,
                protocol_name,
                protocol_version,
                "[]",
                json_dumps(
                    {
                        "detection_mode": (
                            detection_mode
                        ),
                        "is_workbook_sheet": (
                            is_workbook_sheet
                        ),
                        "source_type": (
                            doc_options.get(
                                "source_type"
                            )
                        ),
                        "original_workbook_file_id": (
                            doc_options.get(
                                "original_workbook_file_id"
                            )
                        ),
                        "original_workbook_name": (
                            doc_options.get(
                                "original_workbook_name"
                            )
                        ),
                        "sheet_name": (
                            doc_options.get(
                                "sheet_name"
                            )
                        ),
                        "sheet_index": (
                            doc_options.get(
                                "sheet_index"
                            )
                        ),
                        "sheet_visibility": (
                            doc_options.get(
                                "sheet_visibility"
                            )
                        ),
                    }
                ),
                utc_now(),
                utc_now(),
            ),
        )

        try:
            if not text_path:
                raise RuntimeError(
                    "No extracted/OCR text path available for detection."
                )

            path = Path(text_path)

            if not path.exists() or not path.is_file():
                raise RuntimeError(
                    f"Detection text file does not exist: {text_path}"
                )

            if (
                detection_mode
                == WORKSHEET_TRIAGE_MODE
            ):
                engine_result = (
                    _run_worksheet_triage_engine(
                        path=path,
                        include_phi=include_phi,
                        protocol_name=protocol_name,
                        protocol_version=protocol_version,
                        enable_azure=(
                            enable_azure_detection
                        ),
                        structured_rules=(
                            structured_rules
                        ),
                        max_chunks=(
                            remaining_chunks
                        ),
                        chunk_executor=(
                            worksheet_executor_factory(
                                doc_id=doc_id,
                                workspace=workspace_key,
                                structured_rules=structured_rules,
                                rule_source=rule_workbook_blob,
                                selected_sheets=selected_rule_sheets,
                                include_phi=include_phi,
                                enable_azure=enable_azure_detection,
                                protocol_name=protocol_name,
                                protocol_version=protocol_version,
                            )
                            if worksheet_executor_factory is not None
                            else None
                        ),
                    )
                )

            else:
                #
                # Both normal full detection and IAR full
                # currently use the exhaustive engine path.
                #
                engine_result = (
                    _run_full_detection_engine(
                        path=path,
                        include_phi=include_phi,
                        protocol_name=protocol_name,
                        protocol_version=protocol_version,
                        enable_azure=(
                            enable_azure_detection
                        ),
                        structured_rules=(
                            structured_rules
                        ),
                    )
                )

                if (
                    detection_mode
                    == IAR_FULL_DETECTION_MODE
                ):
                    engine_result[
                        "detection_mode"
                    ] = (
                        IAR_FULL_DETECTION_MODE
                    )

            if (
                remaining_chunks is not None
                and detection_mode == WORKSHEET_TRIAGE_MODE
            ):
                consumed = engine_result.get(
                    "new_chunks_processed"
                )
                if (
                    type(consumed) is not int
                    or not 0 <= consumed <= remaining_chunks
                ):
                    raise IncompleteWorksheetDetection(
                        "Invalid bounded work accounting."
                    )
                remaining_chunks -= consumed
            # Do not classify an incomplete checkpoint-enabled worksheet.
            if (
                worksheet_executor_factory is not None
                and detection_mode == WORKSHEET_TRIAGE_MODE
                and engine_result.get('scan_complete') is not True
            ):
                raise IncompleteWorksheetDetection(
                    'Worksheet detection is incomplete; '
                    'final classification is prohibited.'
                )

            candidates = (
                engine_result.get("candidates")
                or []
            )

            azure_candidate_count += int(
                engine_result.get(
                    "azure_candidate_count",
                    0,
                )
                or 0
            )

            structured_candidate_count += int(
                engine_result.get(
                    "structured_candidate_count",
                    0,
                )
                or 0
            )

            merged_candidate_count += int(
                engine_result.get(
                    "merged_candidate_count",
                    len(candidates),
                )
                or 0
            )

            confidences: list[float] = []

            for candidate in candidates:
                confidence = float(
                    candidate.confidence
                    or 0.0
                )

                confidences.append(
                    confidence
                )

                _insert_detection_candidate(
                    db,
                    detection_run_id=detection_run_id,
                    detection_document_id=detection_document_id,
                    matter_id=matter_id,
                    file_id=file_id,
                    doc_id=doc_id,
                    candidate=candidate,
                    source_text_type=text_source,
                )

            profiled_entity_type_count = (
                len(
                    candidates
                )
            )

            responsive_hit_count = int(
                engine_result.get(
                    "responsive_hit_count",
                    profiled_entity_type_count,
                )
                or 0
            )

            #
            # For worksheet profiling, Person-only sheets remain
            # NO_HIT even though Person is retained in the profile.
            #
            if (
                detection_mode
                == WORKSHEET_TRIAGE_MODE
            ):
                hit_count = (
                    responsive_hit_count
                )

            else:
                hit_count = (
                    profiled_entity_type_count
                )

            highest_confidence = (
                max(confidences)
                if confidences
                else None
            )

            average_confidence = (
                sum(confidences)
                / len(confidences)
                if confidences
                else None
            )

            classification = (
                "HIT"
                if hit_count > 0
                else "NO_HIT"
            )

            db.execute(
                """
                UPDATE processing_detection_document
                SET detection_status=?,
                    classification=?,
                    hit_count=?,
                    highest_confidence=?,
                    average_confidence=?,
                    metadata_json=?,
                    updated_at=?
                WHERE detection_document_id=?
                """,
                (
                    "completed",
                    classification,
                    hit_count,
                    highest_confidence,
                    average_confidence,
                    json_dumps(
                        {
                            "general_pii_enabled": True,
                            "phi_enabled": include_phi,
                            "detection_mode": (
                                engine_result.get(
                                    "detection_mode",
                                    detection_mode,
                                )
                            ),
                            "is_workbook_sheet": (
                                is_workbook_sheet
                            ),
                            "scan_complete": (
                                engine_result.get(
                                    "scan_complete",
                                    True,
                                )
                            ),
                            "entity_counts_complete": (
                                engine_result.get(
                                    "entity_counts_complete",
                                    detection_mode
                                    != WORKSHEET_TRIAGE_MODE,
                                )
                            ),
                            "type_profile_complete": (
                                engine_result.get(
                                    "type_profile_complete"
                                )
                            ),

                            "profile_strategy": (
                                engine_result.get(
                                    "profile_strategy"
                                )
                            ),

                            "profiled_entity_type_count": (
                                engine_result.get(
                                    "profiled_entity_type_count",
                                    len(
                                        candidates
                                    ),
                                )
                            ),

                            "profiled_entity_types": (
                                engine_result.get(
                                    "profiled_entity_types",
                                    [],
                                )
                            ),

                            "responsive_entity_type_count": (
                                engine_result.get(
                                    "responsive_entity_type_count",
                                    hit_count,
                                )
                            ),

                            "responsive_entity_types": (
                                engine_result.get(
                                    "responsive_entity_types",
                                    [],
                                )
                            ),

                            "first_rows_by_entity_type": (
                                engine_result.get(
                                    "first_rows_by_entity_type",
                                    {},
                                )
                            ),
                            "triage_stopped_early": (
                                engine_result.get(
                                    "triage_stopped_early",
                                    False,
                                )
                            ),
                            "rows_scanned": (
                                engine_result.get(
                                    "rows_scanned"
                                )
                            ),
                            "characters_scanned": (
                                engine_result.get(
                                    "characters_scanned"
                                )
                            ),
                            "first_hit_row": (
                                engine_result.get(
                                    "first_hit_row"
                                )
                            ),
                            "original_workbook_file_id": (
                                doc_options.get(
                                    "original_workbook_file_id"
                                )
                            ),
                            "original_workbook_name": (
                                doc_options.get(
                                    "original_workbook_name"
                                )
                            ),
                            "sheet_name": (
                                doc_options.get(
                                    "sheet_name"
                                )
                            ),
                            "sheet_index": (
                                doc_options.get(
                                    "sheet_index"
                                )
                            ),
                            "sheet_visibility": (
                                doc_options.get(
                                    "sheet_visibility"
                                )
                            ),
                            "azure_ner_enabled": True,
                            "structured_rules_enabled": True,
                            "merge_enabled": True,
                            "azure_candidate_count": (
                                engine_result.get(
                                    "azure_candidate_count",
                                    0,
                                )
                            ),
                            "structured_candidate_count": (
                                engine_result.get(
                                    "structured_candidate_count",
                                    0,
                                )
                            ),
                            "merged_candidate_count": (
                                engine_result.get(
                                    "merged_candidate_count",
                                    hit_count,
                                )
                            ),
                            "detectors": (
                                engine_result.get(
                                    "detectors",
                                    [],
                                )
                            ),
                        }
                    ),
                    utc_now(),
                    detection_document_id,
                ),
            )

            documents_scanned += 1
            entity_hit_count += hit_count

            if classification == "HIT":
                documents_with_hits += 1
            else:
                documents_no_hits += 1

        except IncompleteWorksheetDetection as exc:
            # Only an incomplete scan is resumable.
            # Invalid accounting remains a hard failure.
            if (
                remaining_chunks is not None
                and str(exc) == (
                    "Worksheet detection is incomplete; "
                    "final classification is prohibited."
                )
            ):
                exc.checkpoint_progress = (
                    _verify_selected_worksheet_progress(
                        rows=rows,
                        document_options=document_options,
                        workspace_key=workspace_key,
                        structured_rules=structured_rules,
                        rule_workbook_blob=rule_workbook_blob,
                        selected_rule_sheets=selected_rule_sheets,
                        include_phi=include_phi,
                        enable_azure_detection=enable_azure_detection,
                        protocol_name=protocol_name,
                        protocol_version=protocol_version,
                        worksheet_executor_factory=worksheet_executor_factory,
                        selected_doc_ids=selected_doc_ids,
                    )
                )
            raise

        except Exception as exc:
            documents_exception += 1

            db.execute(
                """
                UPDATE processing_detection_document
                SET detection_status=?,
                    classification=?,
                    exception_json=?,
                    updated_at=?
                WHERE detection_document_id=?
                """,
                (
                    "failed",
                    "EXCEPTION",
                    json_dumps(
                        [
                            {
                                "error": (
                                    f"{type(exc).__name__}: {exc}"
                                )
                            }
                        ]
                    ),
                    utc_now(),
                    detection_document_id,
                ),
            )

    # Final bounded checkpoint verification.
    # Never finalize from local SQLite results alone.
    if remaining_chunks is not None:
        progress = _verify_selected_worksheet_progress(
            rows=rows,
            document_options=document_options,
            workspace_key=workspace_key,
            structured_rules=structured_rules,
            rule_workbook_blob=rule_workbook_blob,
            selected_rule_sheets=selected_rule_sheets,
            include_phi=include_phi,
            enable_azure_detection=enable_azure_detection,
            protocol_name=protocol_name,
            protocol_version=protocol_version,
            worksheet_executor_factory=worksheet_executor_factory,
            selected_doc_ids=selected_doc_ids,
        )

        if (
            progress.get("checkpoint_verified") is not True
            or progress.get("job_complete") is not True
            or type(progress.get("completed_units")) is not int
            or type(progress.get("total_units")) is not int
            or progress["total_units"] < 1
            or progress["completed_units"] != progress["total_units"]
        ):
            raise RuntimeError(
                "Final checkpoint verification incomplete; "
                "publication prohibited."
            )

    db.execute(
        """
        UPDATE processing_detection_run
        SET completed_at=?,
            status=?,
            documents_total=?,
            documents_scanned=?,
            documents_with_hits=?,
            documents_no_hits=?,
            documents_nfr=?,
            documents_exception=?,
            entity_hit_count=?,
            metadata_json=?
        WHERE detection_run_id=?
        """,
        (
            utc_now(),
            (
                "completed"
                if documents_exception == 0
                else "completed_with_exceptions"
            ),
            documents_total,
            documents_scanned,
            documents_with_hits,
            documents_no_hits,
            0,
            documents_exception,
            entity_hit_count,
            json_dumps(
                {
                    "general_pii_enabled": True,
                    "phi_enabled": include_phi,
                    "azure_ner_enabled": True,
                    "structured_rules_enabled": True,
                    "merge_enabled": True,
                    "service_logs_disabled": True,
                    "azure_candidate_count": (
                        azure_candidate_count
                    ),
                    "structured_candidate_count": (
                        structured_candidate_count
                    ),
                    "merged_candidate_count": (
                        merged_candidate_count
                    ),
                }
            ),
            detection_run_id,
        ),
    )

    return {
        "detection_run_id": detection_run_id,
        "status": (
            "completed"
            if documents_exception == 0
            else "completed_with_exceptions"
        ),
        "documents_total": documents_total,
        "documents_scanned": documents_scanned,
        "documents_with_hits": documents_with_hits,
        "documents_no_hits": documents_no_hits,
        "documents_nfr": 0,
        "documents_exception": documents_exception,
        "entity_hit_count": entity_hit_count,
        "azure_candidate_count": azure_candidate_count,
        "structured_candidate_count": structured_candidate_count,
        "merged_candidate_count": merged_candidate_count,
    }