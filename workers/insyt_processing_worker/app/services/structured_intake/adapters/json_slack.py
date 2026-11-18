from __future__ import annotations

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
