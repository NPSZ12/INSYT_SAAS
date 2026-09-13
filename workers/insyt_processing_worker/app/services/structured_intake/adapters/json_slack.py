from __future__ import annotations

import csv
import json
import zipfile

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..models import (
    StructuredNormalizationResult,
    StructuredPackageInfo,
)


SLACK_COLUMNS = [
    "INSYT_Source_Record_ID",
    "INSYT_Record_Type",

    "INSYT_Slack_Workspace_ID",
    "INSYT_Slack_Workspace_Name",

    "INSYT_Slack_Channel_ID",
    "INSYT_Slack_Channel_Name",
    "INSYT_Slack_Channel_Is_Private",

    "INSYT_Slack_Message_TS",
    "INSYT_Slack_Message_DateTime_UTC",

    "INSYT_Slack_Thread_TS",
    "INSYT_Slack_Parent_Message_TS",
    "INSYT_Slack_Is_Thread_Reply",

    "INSYT_Slack_User_ID",
    "INSYT_Slack_User_Name",
    "INSYT_Slack_User_Real_Name",
    "INSYT_Slack_User_Display_Name",

    "INSYT_Slack_Message_Text",
    "INSYT_Slack_Message_Subtype",

    "INSYT_Slack_Reply_Count",

    "INSYT_Slack_Reactions_JSON",
    "INSYT_Slack_Files_JSON",
    "INSYT_Slack_Attachments_JSON",
    "INSYT_Slack_Edited_JSON",

    "INSYT_Slack_Raw_Message_JSON",
]


def _json_cell(
    value: Any,
) -> str:
    if value is None:
        return ""

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _bool_cell(
    value: Any,
) -> str:
    return (
        "true"
        if bool(value)
        else "false"
    )


def _timestamp_to_iso(
    value: Any,
) -> str:
    raw = str(
        value or ""
    ).strip()

    if not raw:
        return ""

    try:
        seconds = float(
            raw
        )

        return (
            datetime
            .fromtimestamp(
                seconds,
                tz=timezone.utc,
            )
            .isoformat()
        )

    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return ""


def _user_profile(
    user: dict[str, Any],
) -> dict[str, str]:
    profile = (
        user.get("profile")
        or {}
    )

    if not isinstance(
        profile,
        dict,
    ):
        profile = {}

    return {
        "user_id":
            str(
                user.get("id")
                or ""
            ),

        "user_name":
            str(
                user.get("name")
                or ""
            ),

        "real_name":
            str(
                profile.get(
                    "real_name"
                )
                or user.get(
                    "real_name"
                )
                or ""
            ),

        "display_name":
            str(
                profile.get(
                    "display_name"
                )
                or ""
            ),
    }


def _channel_info(
    channel: dict[str, Any],
) -> dict[str, Any]:
    return {
        "channel_id":
            str(
                channel.get("id")
                or ""
            ),

        "channel_name":
            str(
                channel.get("name")
                or ""
            ),

        "is_private":
            bool(
                channel.get(
                    "is_private"
                )
                or channel.get(
                    "is_group"
                )
            ),
    }


def _workspace_info(
    payload: dict[str, Any],
) -> tuple[str, str]:
    team = (
        payload.get("team")
        or payload.get("workspace")
        or {}
    )

    if not isinstance(
        team,
        dict,
    ):
        team = {}

    workspace_id = str(
        team.get("id")
        or payload.get("team_id")
        or payload.get("workspace_id")
        or ""
    )

    workspace_name = str(
        team.get("name")
        or payload.get("team_name")
        or payload.get("workspace_name")
        or ""
    )

    return (
        workspace_id,
        workspace_name,
    )

def _slack_source_record_id(
    *,
    workspace_id: str,
    channel_id: str,
    channel_name: str,
    message_ts: str,
    fallback: str,
) -> str:
    """
    Build a durable Slack source-record identity.

    Slack message ts is normally the message identifier,
    but including workspace/channel lineage avoids ambiguity
    across imported Slack populations.
    """

    workspace_key = str(
        workspace_id
        or "workspace"
    ).strip()

    channel_key = str(
        channel_id
        or channel_name
        or "channel"
    ).strip()

    message_key = str(
        message_ts
        or fallback
        or ""
    ).strip()

    return (
        f"SLACK:"
        f"{workspace_key}:"
        f"{channel_key}:"
        f"{message_key}"
    )

def _message_row(
    *,
    message: dict[str, Any],
    source_record_id: str,
    workspace_id: str,
    workspace_name: str,
    channel_id: str,
    channel_name: str,
    channel_is_private: bool,
    users_by_id: dict[
        str,
        dict[str, str],
    ],
) -> dict[str, Any]:

    ts = str(
        message.get("ts")
        or ""
    ).strip()

    thread_ts = str(
        message.get(
            "thread_ts"
        )
        or ""
    ).strip()

    is_thread_reply = bool(
        thread_ts
        and ts
        and thread_ts != ts
    )

    parent_message_ts = (
        thread_ts
        if is_thread_reply
        else ""
    )

    user_id = str(
        message.get("user")
        or message.get(
            "user_id"
        )
        or ""
    ).strip()

    user_info = (
        users_by_id.get(
            user_id
        )
        or {}
    )

    reply_count = (
        message.get(
            "reply_count"
        )
    )

    if reply_count is None:
        replies = (
            message.get(
                "replies"
            )
            or []
        )

        reply_count = (
            len(replies)
            if isinstance(
                replies,
                list,
            )
            else 0
        )

    return {
        "INSYT_Source_Record_ID":
            source_record_id,

        "INSYT_Record_Type":
            "slack_message",

        "INSYT_Slack_Workspace_ID":
            workspace_id,

        "INSYT_Slack_Workspace_Name":
            workspace_name,

        "INSYT_Slack_Channel_ID":
            channel_id,

        "INSYT_Slack_Channel_Name":
            channel_name,

        "INSYT_Slack_Channel_Is_Private":
            _bool_cell(
                channel_is_private
            ),

        "INSYT_Slack_Message_TS":
            ts,

        "INSYT_Slack_Message_DateTime_UTC":
            _timestamp_to_iso(
                ts
            ),

        "INSYT_Slack_Thread_TS":
            thread_ts,

        "INSYT_Slack_Parent_Message_TS":
            parent_message_ts,

        "INSYT_Slack_Is_Thread_Reply":
            _bool_cell(
                is_thread_reply
            ),

        "INSYT_Slack_User_ID":
            user_id,

        "INSYT_Slack_User_Name":
            user_info.get(
                "user_name",
                "",
            ),

        "INSYT_Slack_User_Real_Name":
            user_info.get(
                "real_name",
                "",
            ),

        "INSYT_Slack_User_Display_Name":
            user_info.get(
                "display_name",
                "",
            ),

        "INSYT_Slack_Message_Text":
            str(
                message.get("text")
                or ""
            ),

        "INSYT_Slack_Message_Subtype":
            str(
                message.get(
                    "subtype"
                )
                or ""
            ),

        "INSYT_Slack_Reply_Count":
            int(
                reply_count
                or 0
            ),

        "INSYT_Slack_Reactions_JSON":
            _json_cell(
                message.get(
                    "reactions"
                )
            ),

        "INSYT_Slack_Files_JSON":
            _json_cell(
                message.get(
                    "files"
                )
            ),

        "INSYT_Slack_Attachments_JSON":
            _json_cell(
                message.get(
                    "attachments"
                )
            ),

        "INSYT_Slack_Edited_JSON":
            _json_cell(
                message.get(
                    "edited"
                )
            ),

        "INSYT_Slack_Raw_Message_JSON":
            _json_cell(
                message
            ),
    }


def _write_rows(
    *,
    rows: Iterable[
        dict[str, Any]
    ],
    output_path: Path,
) -> tuple[
    int,
    dict[str, int],
]:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    record_count = 0

    group_counts: dict[
        str,
        int,
    ] = defaultdict(int)

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=(
                SLACK_COLUMNS
            ),
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in rows:

            writer.writerow(
                row
            )

            record_count += 1

            channel_name = str(
                row.get(
                    "INSYT_Slack_Channel_Name"
                )
                or ""
            ).strip()

            channel_id = str(
                row.get(
                    "INSYT_Slack_Channel_ID"
                )
                or ""
            ).strip()

            group_key = (
                channel_name
                or channel_id
                or "Unknown Channel"
            )

            group_counts[
                group_key
            ] += 1

    return (
        record_count,
        dict(
            group_counts
        ),
    )


def _normalize_consolidated_payload(
    payload: Any,
) -> Iterable[
    dict[str, Any]
]:

    if isinstance(
        payload,
        list,
    ):
        messages = payload

        users_by_id: dict[
            str,
            dict[str, str],
        ] = {}

        workspace_id = ""
        workspace_name = ""
        channel_id = ""
        channel_name = ""
        channel_is_private = False

    elif isinstance(
        payload,
        dict,
    ):
        users = (
            payload.get("users")
            or []
        )

        users_by_id = {}

        if isinstance(
            users,
            list,
        ):
            for user in users:

                if not isinstance(
                    user,
                    dict,
                ):
                    continue

                info = (
                    _user_profile(
                        user
                    )
                )

                user_id = (
                    info[
                        "user_id"
                    ]
                )

                if user_id:
                    users_by_id[
                        user_id
                    ] = info

        workspace_id, workspace_name = (
            _workspace_info(
                payload
            )
        )

        messages = (
            payload.get(
                "messages"
            )
            or []
        )

        channel = (
            payload.get(
                "channel"
            )
            or {}
        )

        if isinstance(
            channel,
            dict,
        ):
            info = (
                _channel_info(
                    channel
                )
            )

            channel_id = str(
                info[
                    "channel_id"
                ]
            )

            channel_name = str(
                info[
                    "channel_name"
                ]
            )

            channel_is_private = bool(
                info[
                    "is_private"
                ]
            )

        else:
            channel_id = ""
            channel_name = ""
            channel_is_private = False

    else:
        messages = []
        users_by_id = {}

        workspace_id = ""
        workspace_name = ""

        channel_id = ""
        channel_name = ""
        channel_is_private = False


    if not isinstance(
        messages,
        list,
    ):
        return


    for index, message in enumerate(
        messages,
        start=1,
    ):

        if not isinstance(
            message,
            dict,
        ):
            continue

        yield _message_row(
            message=message,

            source_record_id=(
                _slack_source_record_id(
                    workspace_id=(
                        workspace_id
                    ),
                    channel_id=(
                        channel_id
                    ),
                    channel_name=(
                        channel_name
                    ),
                    message_ts=str(
                        message.get(
                            "ts"
                        )
                        or ""
                    ),
                    fallback=str(
                        index
                    ),
                )
            ),

            workspace_id=(
                workspace_id
            ),

            workspace_name=(
                workspace_name
            ),

            channel_id=(
                channel_id
            ),

            channel_name=(
                channel_name
            ),

            channel_is_private=(
                channel_is_private
            ),

            users_by_id=(
                users_by_id
            ),
        )


def normalize_slack_json_to_csv(
    *,
    source_path: Path,
    output_path: Path,
    package_id: str | None = None,
) -> StructuredNormalizationResult:

    source_path = (
        source_path.resolve()
    )

    output_path = (
        output_path.resolve()
    )

    with source_path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
    ) as handle:

        payload = json.load(
            handle
        )

    (
        record_count,
        group_counts,
    ) = _write_rows(
        rows=(
            _normalize_consolidated_payload(
                payload
            )
        ),

        output_path=(
            output_path
        ),
    )

    package = (
        StructuredPackageInfo(
            source_family=(
                "structured"
            ),

            source_format=(
                "json"
            ),

            source_profile=(
                "slack"
            ),

            source_path=(
                source_path
            ),

            source_filename=(
                source_path.name
            ),

            package_id=(
                package_id
            ),

            package_count=1,

            record_count=(
                record_count
            ),

            normalized_format=(
                "csv"
            ),

            normalized_csv_path=(
                output_path
            ),

            metadata={
                "adapter":
                    "json_slack",

                "original_source_preserved":
                    True,

                "record_boundary":
                    "slack_message",

                "group_boundary":
                    "slack_channel",

                "column_count":
                    len(
                        SLACK_COLUMNS
                    ),
            },
        )
    )

    return StructuredNormalizationResult(
        package=package,

        normalized_csv_paths=[
            output_path
        ],

        group_counts=(
            group_counts
        ),

        metadata={
            "columns":
                SLACK_COLUMNS,

            "record_count":
                record_count,

            "channel_counts":
                group_counts,
        },
    )


def is_slack_export_zip(
    source_path: Path,
) -> bool:

    if (
        source_path.suffix
        .strip()
        .lower()
        != ".zip"
    ):
        return False

    try:
        with zipfile.ZipFile(
            source_path,
            "r",
        ) as archive:

            names = {
                name
                .replace("\\", "/")
                .strip("/")
                .lower()
                for name
                in archive.namelist()
            }

    except Exception:
        return False

    has_users = (
        "users.json"
        in names
    )

    has_channels = (
        "channels.json"
        in names
        or "groups.json"
        in names
    )

    has_channel_messages = any(
        name.endswith(
            ".json"
        )
        and "/" in name
        and name.rsplit(
            "/",
            1,
        )[-1]
        not in {
            "users.json",
            "channels.json",
            "groups.json",
        }
        for name in names
    )

    return bool(
        has_users
        and has_channels
        and has_channel_messages
    )


def normalize_slack_zip_to_csv(
    *,
    source_path: Path,
    output_path: Path,
    package_id: str | None = None,
) -> StructuredNormalizationResult:

    source_path = (
        source_path.resolve()
    )

    output_path = (
        output_path.resolve()
    )

    users_by_id: dict[
        str,
        dict[str, str],
    ] = {}

    channels_by_name: dict[
        str,
        dict[str, Any],
    ] = {}

    workspace_id = ""
    workspace_name = ""


    def rows():
        nonlocal workspace_id
        nonlocal workspace_name

        with zipfile.ZipFile(
            source_path,
            "r",
        ) as archive:

            names = {
                name
                .replace("\\", "/")
                .strip("/"):
                name
                for name
                in archive.namelist()
                if not name.endswith(
                    "/"
                )
            }


            if "users.json" in names:

                users_payload = json.loads(
                    archive.read(
                        names[
                            "users.json"
                        ]
                    ).decode(
                        "utf-8-sig",
                        errors="replace",
                    )
                )

                if isinstance(
                    users_payload,
                    list,
                ):
                    for user in (
                        users_payload
                    ):

                        if not isinstance(
                            user,
                            dict,
                        ):
                            continue

                        info = (
                            _user_profile(
                                user
                            )
                        )

                        user_id = (
                            info[
                                "user_id"
                            ]
                        )

                        if user_id:
                            users_by_id[
                                user_id
                            ] = info


            for metadata_name in (
                "channels.json",
                "groups.json",
            ):

                if (
                    metadata_name
                    not in names
                ):
                    continue

                channel_payload = (
                    json.loads(
                        archive.read(
                            names[
                                metadata_name
                            ]
                        ).decode(
                            "utf-8-sig",
                            errors="replace",
                        )
                    )
                )

                if not isinstance(
                    channel_payload,
                    list,
                ):
                    continue

                for channel in (
                    channel_payload
                ):

                    if not isinstance(
                        channel,
                        dict,
                    ):
                        continue

                    info = (
                        _channel_info(
                            channel
                        )
                    )

                    channel_name = (
                        str(
                            info[
                                "channel_name"
                            ]
                        )
                    )

                    if channel_name:
                        channels_by_name[
                            channel_name
                        ] = info


            message_files = sorted(
                (
                    normalized_name,
                    actual_name,
                )
                for (
                    normalized_name,
                    actual_name,
                )
                in names.items()
                if (
                    normalized_name.endswith(
                        ".json"
                    )
                    and "/" in (
                        normalized_name
                    )
                )
            )


            record_number = 0

            for (
                normalized_name,
                actual_name,
            ) in message_files:

                parts = (
                    normalized_name
                    .split("/")
                )

                if len(parts) < 2:
                    continue

                channel_name = (
                    parts[-2]
                )

                channel_info = (
                    channels_by_name.get(
                        channel_name
                    )
                    or {}
                )

                channel_id = str(
                    channel_info.get(
                        "channel_id"
                    )
                    or ""
                )

                channel_is_private = bool(
                    channel_info.get(
                        "is_private"
                    )
                )

                try:
                    message_payload = (
                        json.loads(
                            archive.read(
                                actual_name
                            ).decode(
                                "utf-8-sig",
                                errors="replace",
                            )
                        )
                    )

                except Exception:
                    continue

                if not isinstance(
                    message_payload,
                    list,
                ):
                    continue

                for message in (
                    message_payload
                ):

                    if not isinstance(
                        message,
                        dict,
                    ):
                        continue

                    record_number += 1

                    yield _message_row(
                        message=message,

                        source_record_id=(
                            _slack_source_record_id(
                                workspace_id=(
                                    workspace_id
                                ),
                                channel_id=(
                                    channel_id
                                ),
                                channel_name=(
                                    channel_name
                                ),
                                message_ts=str(
                                    message.get(
                                        "ts"
                                    )
                                    or ""
                                ),
                                fallback=str(
                                    record_number
                                ),
                            )
                        ),

                        workspace_id=(
                            workspace_id
                        ),

                        workspace_name=(
                            workspace_name
                        ),

                        channel_id=(
                            channel_id
                        ),

                        channel_name=(
                            channel_name
                        ),

                        channel_is_private=(
                            channel_is_private
                        ),

                        users_by_id=(
                            users_by_id
                        ),
                    )


    (
        record_count,
        group_counts,
    ) = _write_rows(
        rows=rows(),

        output_path=(
            output_path
        ),
    )

    package = (
        StructuredPackageInfo(
            source_family=(
                "structured"
            ),

            source_format=(
                "json"
            ),

            source_profile=(
                "slack"
            ),

            source_path=(
                source_path
            ),

            source_filename=(
                source_path.name
            ),

            package_id=(
                package_id
            ),

            package_count=1,

            record_count=(
                record_count
            ),

            normalized_format=(
                "csv"
            ),

            normalized_csv_path=(
                output_path
            ),

            metadata={
                "adapter":
                    "json_slack",

                "original_source_preserved":
                    True,

                "record_boundary":
                    "slack_message",

                "group_boundary":
                    "slack_channel",

                "source_package_type":
                    "slack_export_zip",

                "column_count":
                    len(
                        SLACK_COLUMNS
                    ),
            },
        )
    )

    return StructuredNormalizationResult(
        package=package,

        normalized_csv_paths=[
            output_path
        ],

        group_counts=(
            group_counts
        ),

        metadata={
            "columns":
                SLACK_COLUMNS,

            "record_count":
                record_count,

            "channel_counts":
                group_counts,
        },
    )