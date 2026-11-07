from __future__ import annotations

import json
import os
from typing import Any


def enqueue_detection_continuation(
    payload: dict[str, Any],
    *,
    queue_client=None,
) -> None:
    """
    Enqueue continuation using the existing INSYT
    Detection V2 Storage Queue.

    host.json specifies messageEncoding='none',
    so messages are plain JSON, not Base64.

    Scheduling and checkpoint verification remain
    responsibilities of the bounded coordinator.
    """
    if not isinstance(payload, dict):
        raise TypeError(
            "Continuation payload must be a dictionary."
        )

    job_id = str(
        payload.get("detection_job_id")
        or payload.get("job_id")
        or ""
    ).strip()

    if not job_id:
        raise ValueError(
            "Detection continuation requires a job ID."
        )

    continuation = dict(payload)
    continuation["detection_continuation"] = True

    message = json.dumps(
        continuation,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

    if len(message.encode("utf-8")) > 65536:
        raise ValueError(
            "Detection continuation exceeds the "
            "Azure Storage Queue 64 KiB limit."
        )

    if queue_client is None:
        from azure.storage.queue import QueueClient

        connection = str(
            os.getenv(
                "INSYT_PROCESSING_STORAGE_CONNECTION_STRING"
            ) or ""
        ).strip()

        queue_name = str(
            os.getenv(
                "APC_DETECTION_QUEUE_NAME"
            ) or ""
        ).strip()

        if not connection:
            raise RuntimeError(
                "Processing storage connection missing."
            )

        if not queue_name:
            raise RuntimeError(
                "Detection queue name missing."
            )

        queue_client = QueueClient.from_connection_string(
            connection,
            queue_name,
        )

    # Do not suppress failures: the coordinator must
    # know if continuation could not be queued.
    queue_client.send_message(message)