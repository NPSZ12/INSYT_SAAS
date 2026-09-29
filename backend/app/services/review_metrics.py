import json
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

from app.services.batch_service import get_container_client
from app.services.storage_paths import build_project_base_path

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.authorization import (
    has_scoped_project_access,
    normalize_role,
)

VALID_PERIODS = {
    "day",
    "week",
    "month",
    "project",
}

def display_metric_role(
    role: str,
) -> str:
    normalized = normalize_role(
        role
    )

    if normalized == "Reviewer":
        return "Reviewer"

    if normalized == "QC":
        return "QC"

    if normalized == "TL":
        return "TL"

    if normalized == "INSYT Manager":
        return "INSYT Manager"

    if normalized == "Client Admin":
        return "Client Admin"

    if normalized == "Client":
        return "Client"

    return normalized or str(
        role or ""
    ).strip()

def parse_metric_date(
    value: str | None,
) -> date:
    if not value:
        return datetime.now(
            timezone.utc
        ).date()

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=(
                "Metric date must use "
                "YYYY-MM-DD format."
            ),
        )


def resolve_metric_period(
    period: str,
    selected_date: str | None,
):
    clean_period = str(
        period or "project"
    ).strip().lower()

    if clean_period not in VALID_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Period must be day, week, "
                "month, or project."
            ),
        )

    if clean_period == "project":
        return {
            "period": "project",
            "period_start": None,
            "period_end": None,
        }

    active_date = parse_metric_date(
        selected_date
    )

    if clean_period == "day":
        start_date = active_date
        end_date = active_date

    elif clean_period == "week":
        start_date = (
            active_date
            - timedelta(
                days=active_date.weekday()
            )
        )

        end_date = (
            start_date
            + timedelta(days=6)
        )

    else:
        start_date = active_date.replace(
            day=1
        )

        if start_date.month == 12:
            next_month = start_date.replace(
                year=start_date.year + 1,
                month=1,
            )
        else:
            next_month = start_date.replace(
                month=start_date.month + 1
            )

        end_date = (
            next_month
            - timedelta(days=1)
        )

    return {
        "period": clean_period,
        "period_start": (
            start_date.isoformat()
        ),
        "period_end": (
            end_date.isoformat()
        ),
    }


def event_in_period(
    reviewed_at: str,
    period_start: str | None,
    period_end: str | None,
) -> bool:
    if not reviewed_at:
        return False

    try:
        parsed = datetime.fromisoformat(
            reviewed_at.replace(
                "Z",
                "+00:00",
            )
        )
    except Exception:
        return False

    if (
        period_start is None
        or period_end is None
    ):
        return True

    event_date = parsed.date()

    return (
        date.fromisoformat(
            period_start
        )
        <= event_date
        <= date.fromisoformat(
            period_end
        )
    )


def empty_reviewer_metrics(
    username: str,
    display_name: str = "",
    role: str = "Reviewer",
):
    return {
        "username": username,
        "display_name": (
            display_name
            or username
        ),
        "role": display_metric_role(
            role
        ),

        "review_hours": 0.0,

        "documents_reviewed": 0,
        "documents_coded": 0,
        "documents_per_hour": 0.0,

        "responsive": 0,
        "not_responsive": 0,
        "further_review": 0,

        "qc_reviewed": 0,
        "qc_no_change": 0,
        "qc_changes": 0,
        "qc_nfr": 0,

        "batches_touched": 0,

        "first_activity": "",
        "last_activity": "",

        "_reviewed_docs": set(),
        "_coded_docs": set(),
        "_responsive_docs": set(),
        "_not_responsive_docs": set(),
        "_further_review_docs": set(),
        "_qc_reviewed_docs": set(),
        "_qc_no_change_docs": set(),
        "_qc_change_docs": set(),
        "_qc_nfr_docs": set(),
        "_batches": set(),
        "_activity_times": [],
    }

def load_assigned_project_users(
    db: Session,
    workspace: str,
    client: str,
    project: str,
):
    users = (
        db.query(User)
        .filter(User.status == "Active")
        .all()
    )

    assigned = []

    for user in users:
        if not has_scoped_project_access(
            user,
            workspace,
            client,
            project,
        ):
            continue

        assigned.append(user)

    assigned.sort(
        key=lambda user: (
            user.display_name
            or user.username
            or ""
        ).lower()
    )

    return assigned

def load_review_hours_for_period(
    workspace: str,
    client: str,
    project: str,
    period_start: str | None,
    period_end: str | None,
):
    container = get_container_client(
        workspace
    )

    blob_name = (
        f"{client.strip('/')}/"
        f"{workspace.strip('/')}/"
        f"{project.strip('/')}/"
        "ReviewHours/time_entries.json"
    )

    blob_client = (
        container.get_blob_client(
            blob_name
        )
    )

    if not blob_client.exists():
        return {}

    try:
        entries = json.loads(
            blob_client
            .download_blob()
            .readall()
            .decode("utf-8")
        )
    except Exception:
        return {}

    if not isinstance(entries, list):
        return {}

    totals: dict[str, float] = {}

    for entry in entries:
        username = str(
            entry.get("username")
            or ""
        ).strip()

        entry_date_raw = str(
            entry.get("date")
            or ""
        ).strip()

        if (
            not username
            or not entry_date_raw
        ):
            continue

        try:
            entry_date = date.fromisoformat(
                entry_date_raw
            )
        except Exception:
            continue

        if (
            period_start is not None
            and entry_date
            < date.fromisoformat(
                period_start
            )
        ):
            continue

        if (
            period_end is not None
            and entry_date
            > date.fromisoformat(
                period_end
            )
        ):
            continue

        totals[username] = (
            totals.get(
                username,
                0.0,
            )
            + float(
                entry.get("hours")
                or 0
            )
        )

    return totals


def finalize_reviewer_metrics(
    row: dict,
):
    row["documents_reviewed"] = len(
        row["_reviewed_docs"]
    )

    row["documents_coded"] = len(
        row["_coded_docs"]
    )

    row["responsive"] = len(
        row["_responsive_docs"]
    )

    row["not_responsive"] = len(
        row["_not_responsive_docs"]
    )

    row["further_review"] = len(
        row["_further_review_docs"]
    )

    row["qc_reviewed"] = len(
        row["_qc_reviewed_docs"]
    )

    row["qc_no_change"] = len(
        row["_qc_no_change_docs"]
    )

    row["qc_changes"] = len(
        row["_qc_change_docs"]
    )

    row["qc_nfr"] = len(
        row["_qc_nfr_docs"]
    )

    row["batches_touched"] = len(
        row["_batches"]
    )

    row["review_hours"] = round(
        float(
            row["review_hours"]
            or 0
        ),
        2,
    )

    if row["review_hours"] > 0:
        row["documents_per_hour"] = round(
            (
                row["documents_reviewed"]
                / row["review_hours"]
            ),
            2,
        )
    else:
        row["documents_per_hour"] = 0.0

    times = sorted(
        row["_activity_times"]
    )

    if times:
        row["first_activity"] = times[0]
        row["last_activity"] = times[-1]

    for key in [
        "_reviewed_docs",
        "_coded_docs",
        "_responsive_docs",
        "_not_responsive_docs",
        "_further_review_docs",
        "_qc_reviewed_docs",
        "_qc_no_change_docs",
        "_qc_change_docs",
        "_qc_nfr_docs",
        "_batches",
        "_activity_times",
    ]:
        row.pop(
            key,
            None,
        )

    return row


def build_project_review_metrics(
    db: Session,
    workspace: str,
    client: str,
    project: str,
    period: str = "project",
    selected_date: str | None = None,
):
    period_info = resolve_metric_period(
        period,
        selected_date,
    )

    period_start = (
        period_info["period_start"]
    )

    period_end = (
        period_info["period_end"]
    )

    container = get_container_client(
        workspace
    )

    base_path = (
        build_project_base_path(
            workspace,
            client,
            project,
        )
    )

    document_prefix = (
        f"{base_path}/"
        "Review/documents/"
    )

    reviewers: dict[str, dict] = {}

    assigned_users = load_assigned_project_users(
        db=db,
        workspace=workspace,
        client=client,
        project=project,
    )

    for user in assigned_users:
        username = str(
            user.username or ""
        ).strip()

        if not username:
            continue

        reviewers[username] = (
            empty_reviewer_metrics(
                username=username,
                display_name=(
                    user.display_name
                    or username
                ),
                role=user.role,
            )
        )

    for blob in container.list_blobs(
        name_starts_with=document_prefix
    ):
        if not blob.name.endswith(
            ".json"
        ):
            continue

        try:
            state = json.loads(
                container
                .get_blob_client(
                    blob.name
                )
                .download_blob()
                .readall()
                .decode("utf-8")
            )
        except Exception:
            continue

        doc_id = str(
            state.get("doc_id")
            or ""
        ).strip()

        if not doc_id:
            continue

        history = state.get(
            "review_history",
            [],
        )

        if not isinstance(
            history,
            list,
        ):
            continue

        for event in history:
            username = str(
                event.get(
                    "reviewed_by"
                )
                or ""
            ).strip()

            reviewed_at = str(
                event.get(
                    "reviewed_at"
                )
                or ""
            ).strip()

            if not username:
                continue

            if not event_in_period(
                reviewed_at,
                period_start,
                period_end,
            ):
                continue

            if username not in reviewers:
                reviewers[username] = (
                    empty_reviewer_metrics(
                        username=username,
                    )
                )

            row = reviewers[
                username
            ]

            row[
                "_reviewed_docs"
            ].add(doc_id)

            document_coding = str(
                event.get(
                    "document_coding"
                )
                or ""
            ).strip()

            if document_coding:
                row[
                    "_coded_docs"
                ].add(doc_id)

            if (
                document_coding
                == "Responsive"
            ):
                row[
                    "_responsive_docs"
                ].add(doc_id)

            elif (
                document_coding
                == "Not Responsive"
            ):
                row[
                    "_not_responsive_docs"
                ].add(doc_id)

            further_review_reason = str(
                event.get(
                    "further_review_reason"
                )
                or ""
            ).strip()

            if further_review_reason:
                row[
                    "_further_review_docs"
                ].add(doc_id)

            qc_coding = str(
                event.get(
                    "qc_coding"
                )
                or ""
            ).strip()

            if qc_coding:
                row[
                    "_qc_reviewed_docs"
                ].add(doc_id)

            if (
                qc_coding
                == "QC - No Change"
            ):
                row[
                    "_qc_no_change_docs"
                ].add(doc_id)

            elif (
                qc_coding
                == "QC - Change"
            ):
                row[
                    "_qc_change_docs"
                ].add(doc_id)

            elif (
                qc_coding
                == "QC-NFR"
            ):
                row[
                    "_qc_nfr_docs"
                ].add(doc_id)

            batch_id = str(
                event.get(
                    "batch_id"
                )
                or ""
            ).strip()

            if batch_id:
                row[
                    "_batches"
                ].add(batch_id)

            if reviewed_at:
                row[
                    "_activity_times"
                ].append(
                    reviewed_at
                )

    hour_totals = (
        load_review_hours_for_period(
            workspace=workspace,
            client=client,
            project=project,
            period_start=period_start,
            period_end=period_end,
        )
    )

    for username, hours in (
        hour_totals.items()
    ):
        if username not in reviewers:
            reviewers[username] = (
                empty_reviewer_metrics(
                    username
                )
            )

        reviewers[
            username
        ]["review_hours"] = hours

    project_batches_touched = {
        batch_id
        for row in reviewers.values()
        for batch_id in row.get(
            "_batches",
            set(),
        )
    }

    finalized = [
        finalize_reviewer_metrics(
            row
        )
        for row in reviewers.values()
    ]

    finalized.sort(
        key=lambda row: (
            row.get(
                "display_name"
            )
            or row.get(
                "username"
            )
            or ""
        ).lower()
    )

    project_summary = {
        "assigned_reviewers": len(
            assigned_users
        ),
        "active_reviewers": sum(
            1
            for row in finalized
            if (
                row[
                    "documents_reviewed"
                ]
                > 0
                or row[
                    "review_hours"
                ]
                > 0
            )
        ),
        "review_hours": round(
            sum(
                row["review_hours"]
                for row in finalized
            ),
            2,
        ),
        "documents_reviewed": sum(
            row["documents_reviewed"]
            for row in finalized
        ),
        "documents_coded": sum(
            row["documents_coded"]
            for row in finalized
        ),
        "responsive": sum(
            row["responsive"]
            for row in finalized
        ),
        "not_responsive": sum(
            row["not_responsive"]
            for row in finalized
        ),
        "further_review": sum(
            row["further_review"]
            for row in finalized
        ),
        "qc_reviewed": sum(
            row["qc_reviewed"]
            for row in finalized
        ),
        "qc_no_change": sum(
            row["qc_no_change"]
            for row in finalized
        ),
        "qc_changes": sum(
            row["qc_changes"]
            for row in finalized
        ),
        "qc_nfr": sum(
            row["qc_nfr"]
            for row in finalized
        ),
        "batches_touched": len(
            project_batches_touched
        ),
        "first_activity": "",
        "last_activity": "",
    }

    if (
        project_summary[
            "review_hours"
        ]
        > 0
    ):
        project_summary[
            "documents_per_hour"
        ] = round(
            (
                project_summary[
                    "documents_reviewed"
                ]
                / project_summary[
                    "review_hours"
                ]
            ),
            2,
        )
    else:
        project_summary[
            "documents_per_hour"
        ] = 0.0

    activities = sorted(
        [
            value
            for row in finalized
            for value in [
                row.get(
                    "first_activity"
                ),
                row.get(
                    "last_activity"
                ),
            ]
            if value
        ]
    )

    if activities:
        project_summary[
            "first_activity"
        ] = activities[0]

        project_summary[
            "last_activity"
        ] = activities[-1]

    return {
        "workspace": workspace,
        "client": client,
        "project": project,
        **period_info,
        "project_summary": (
            project_summary
        ),
        "reviewers": finalized,
    }