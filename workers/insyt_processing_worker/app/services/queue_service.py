import json
import os

from azure.storage.queue import QueueClient


QUEUE_NAME = os.getenv("AZURE_QUEUE_NAME", "insyt-jobs")
STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")


def get_queue_client() -> QueueClient:
    if not STORAGE_CONNECTION_STRING:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")

    return QueueClient.from_connection_string(
        conn_str=STORAGE_CONNECTION_STRING,
        queue_name=QUEUE_NAME,
    )


def enqueue_job(job_id: int, job_type: str, project_id: str | None = None):
    queue_client = get_queue_client()

    message = {
        "job_id": job_id,
        "job_type": job_type,
        "project_id": project_id,
    }

    queue_client.send_message(json.dumps(message))