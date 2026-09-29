import csv
import io
from dataclasses import dataclass

from app.services.batch_service import get_container_client
from app.services.storage_paths import build_project_base_path


DEFAULT_WEIGHTS = {
    "Critical": 20.0,
    "Important": 7.0,
    "Minimal": 2.0,
    "Informational": 0.0,
}


@dataclass
class QcSeverity:
    severity: str
    weight: float
    description: str = ""


def default_qc_severities():
    return {
        severity: QcSeverity(
            severity=severity,
            weight=weight,
            description="",
        )
        for severity, weight in DEFAULT_WEIGHTS.items()
    }


def get_workspace_qc_scoring_blob_name(
    workspace: str,
):
    workspace_clean = str(
        workspace or ""
    ).strip().lower()

    if workspace_clean == "capture":
        return (
            "config/qc/"
            "INSYT_QC_Scoring_Capture.csv"
        )

    if workspace_clean == "discovery":
        return (
            "config/qc/"
            "INSYT_QC_Scoring_Discovery.csv"
        )

    # Summaries does not yet have its own
    # scoring model. Use Capture until a
    # Summaries-specific model is created.
    return (
        "config/qc/"
        "INSYT_QC_Scoring_Capture.csv"
    )


def load_qc_scoring_model(
    workspace: str,
    client: str,
    project: str,
):
    container = get_container_client(
        workspace
    )

    project_blob_name = (
        f"{build_project_base_path(
            workspace,
            client,
            project,
        )}/source/protocol/"
        f"{project}_QC_Scoring_Model.csv"
    )

    workspace_blob_name = (
        get_workspace_qc_scoring_blob_name(
            workspace
        )
    )

    blob_name = ""

    project_blob_client = (
        container.get_blob_client(
            project_blob_name
        )
    )

    if project_blob_client.exists():
        blob_name = project_blob_name
    else:
        workspace_blob_client = (
            container.get_blob_client(
                workspace_blob_name
            )
        )

        if workspace_blob_client.exists():
            blob_name = workspace_blob_name

    if not blob_name:
        return default_qc_severities()

    blob_client = container.get_blob_client(
        blob_name
    )

    try:
        raw = (
            blob_client.download_blob()
            .readall()
            .decode("utf-8-sig")
        )
    except Exception:
        return default_qc_severities()

    reader = csv.DictReader(
        io.StringIO(raw)
    )

    model = {}

    for row in reader:
        severity = str(
            row.get("Severity")
            or ""
        ).strip()

        if severity not in DEFAULT_WEIGHTS:
            continue

        active = str(
            row.get("Active")
            or "TRUE"
        ).strip().lower()

        if active not in {
            "true",
            "1",
            "yes",
            "y",
        }:
            continue

        try:
            weight = float(
                row.get("Weight")
                or DEFAULT_WEIGHTS[severity]
            )
        except Exception:
            weight = DEFAULT_WEIGHTS[
                severity
            ]

        model[severity] = QcSeverity(
            severity=severity,
            weight=weight,
            description=str(
                row.get("Description")
                or ""
            ).strip(),
        )

    for severity, weight in (
        DEFAULT_WEIGHTS.items()
    ):
        if severity not in model:
            model[severity] = QcSeverity(
                severity=severity,
                weight=weight,
                description="",
            )

    return model


def calculate_qc_score(
    counts: dict,
    scoring_model: dict,
):
    breakdown = {}
    total_deduction = 0.0

    for severity in [
        "Critical",
        "Important",
        "Minimal",
        "Informational",
    ]:
        raw_count = counts.get(
            severity,
            0,
        )

        try:
            count = max(
                int(raw_count or 0),
                0,
            )
        except Exception:
            count = 0

        weight = float(
            scoring_model[
                severity
            ].weight
        )

        points = round(
            count * weight,
            2,
        )

        total_deduction += points

        breakdown[severity] = {
            "count": count,
            "weight": weight,
            "points": points,
        }

    total_deduction = round(
        total_deduction,
        2,
    )

    weighted_score = round(
        max(
            0.0,
            100.0 - total_deduction,
        ),
        2,
    )

    return {
        "breakdown": breakdown,
        "weighted_error_points": (
            total_deduction
        ),
        "weighted_qc_score": (
            weighted_score
        ),
    }


def serialize_qc_scoring_model(
    workspace: str,
    client: str,
    project: str,
):
    model = load_qc_scoring_model(
        workspace=workspace,
        client=client,
        project=project,
    )

    return {
        severity: {
            "severity": item.severity,
            "weight": item.weight,
            "description": item.description,
        }
        for severity, item in model.items()
    }


def load_qc_scoring_guide(
    workspace: str,
    client: str,
    project: str,
):
    container = get_container_client(
        workspace
    )

    project_blob_name = (
        f"{build_project_base_path(
            workspace,
            client,
            project,
        )}/source/protocol/"
        f"{project}_QC_Scoring_Model.csv"
    )

    workspace_blob_name = (
        get_workspace_qc_scoring_blob_name(
            workspace
        )
    )

    blob_name = ""

    project_blob_client = (
        container.get_blob_client(
            project_blob_name
        )
    )

    if project_blob_client.exists():
        blob_name = project_blob_name
    else:
        workspace_blob_client = (
            container.get_blob_client(
                workspace_blob_name
            )
        )

        if workspace_blob_client.exists():
            blob_name = workspace_blob_name

    if not blob_name:
        return []

    try:
        raw = (
            container
            .get_blob_client(blob_name)
            .download_blob()
            .readall()
            .decode("utf-8-sig")
        )
    except Exception:
        return []

    reader = csv.DictReader(
        io.StringIO(raw)
    )

    guide = []

    for row in reader:
        severity = str(
            row.get("Severity")
            or ""
        ).strip()

        if severity not in DEFAULT_WEIGHTS:
            continue

        active = str(
            row.get("Active")
            or "TRUE"
        ).strip().lower()

        if active not in {
            "true",
            "1",
            "yes",
            "y",
        }:
            continue

        try:
            weight = float(
                row.get("Weight")
                or DEFAULT_WEIGHTS[severity]
            )
        except Exception:
            weight = DEFAULT_WEIGHTS[
                severity
            ]

        guide.append(
            {
                "severity": severity,
                "weight": weight,
                "category": str(
                    row.get("Category")
                    or ""
                ).strip(),
                "error_type": str(
                    row.get("Error_Type")
                    or ""
                ).strip(),
                "description": str(
                    row.get("Description")
                    or ""
                ).strip(),
            }
        )

    return guide
