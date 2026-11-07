from types import SimpleNamespace

import pytest
from azure.core import MatchConditions
from azure.core.exceptions import (
    ResourceExistsError,
    ResourceModifiedError,
    ResourceNotFoundError,
)

from apc.detection_shared_index import (
    write_shared_detection_index,
)


class Blob:
    def __init__(self):
        self.data = None
        self.version = 0
        self.updates = 0
        self.inject_race = False

    def get_blob_properties(self):
        if self.data is None:
            raise ResourceNotFoundError("Missing")
        return SimpleNamespace(etag=str(self.version))

    def download_blob(self):
        return self

    def readall(self):
        return self.data

    def upload_blob(
        self,
        data,
        *,
        overwrite,
        content_settings,
        etag=None,
        match_condition=None,
    ):
        if self.inject_race:
            self.inject_race = False
            self.version += 1
            raise ResourceModifiedError("Synthetic race")

        if not overwrite and self.data is not None:
            raise ResourceExistsError("Already exists")

        if overwrite:
            assert match_condition == MatchConditions.IfNotModified
            if etag != str(self.version):
                raise ResourceModifiedError("ETag mismatch")

        self.data = bytes(data)
        self.version += 1
        self.updates += 1


class Container:
    def __init__(self):
        self.blob = Blob()

    def get_blob_client(self, path):
        return self.blob


def record(job, time):
    return {
        "doc_id": "DOC-A",
        "latest_detection_job_id": job,
        "detected_at": time,
    }


OLD = "2026-11-07T12:00:00+00:00"
NEW = "2026-11-07T13:00:00+00:00"


def write(container, job, time):
    return write_shared_detection_index(
        container=container,
        blob_path="synthetic/detection/documents/DOC-A.json",
        payload=record(job, time),
        storage_account="synthetic-account",
        container_name="synthetic-container",
    )


def test_newer_replaces_older_and_older_cannot_revert():
    container = Container()

    write(container, "DET-OLD", OLD)
    write(container, "DET-NEW", NEW)

    original = container.blob.data
    assert container.blob.updates == 2

    skipped = write(container, "DET-OLD", OLD)

    assert skipped["skipped"] is True
    assert container.blob.data == original
    assert container.blob.updates == 2


def test_same_job_duplicate_is_idempotent():
    container = Container()

    write(container, "DET-OLD", OLD)
    receipt = write(container, "DET-OLD", OLD)

    assert receipt["skipped"] is True
    assert container.blob.updates == 1


def test_etag_race_retries_safely():
    container = Container()

    write(container, "DET-OLD", OLD)
    container.blob.inject_race = True

    write(container, "DET-NEW", NEW)

    assert container.blob.updates == 2


def test_equal_timestamp_different_job_fails_closed():
    container = Container()
    write(container, "DET-OLD", OLD)

    with pytest.raises(RuntimeError, match="ambiguous"):
        write(container, "DET-OTHER", OLD)

    assert container.blob.updates == 1


def test_invalid_timestamp_rejected():
    container = Container()

    with pytest.raises(ValueError, match="timezone"):
        write(container, "DET-OLD", "2026-11-07T12:00:00")

    assert container.blob.updates == 0