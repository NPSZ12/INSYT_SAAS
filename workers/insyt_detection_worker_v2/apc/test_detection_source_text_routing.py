from pathlib import Path

import pytest

from apc import detection_job_runner as runner


class FakeDownload:
    def chunks(self):
        yield b"synthetic worksheet text"


class FakeBlob:
    def download_blob(self):
        return FakeDownload()


class FakeContainer:
    def __init__(self):
        self.requested_paths = []

    def get_blob_client(self, path):
        self.requested_paths.append(path)
        return FakeBlob()


class FakeService:
    def __init__(self, container):
        self.container = container
        self.requested_containers = []

    def get_container_client(self, name):
        self.requested_containers.append(name)
        return self.container


def test_capture_review_staged_text_routes_to_review(
    monkeypatch, tmp_path
):
    review = FakeService(FakeContainer())

    monkeypatch.setattr(
        runner, "_review_blob_service", lambda: review
    )
    monkeypatch.setattr(
        runner, "_review_container",
        lambda workspace: f"insyt-{workspace}",
    )
    monkeypatch.setattr(
        runner, "_processing_blob_service",
        lambda: pytest.fail(
            "Review-staged text must not use processing storage"
        ),
    )

    path = (
        "client/capture/project/processing_center/"
        "staged/JOB-SYNTHETIC/text/DOC-A.txt"
    )

    destination = tmp_path / "capture.txt"

    runner._download_detection_text(
        workspace="capture",
        blob_path=path,
        destination=destination,
    )

    assert review.requested_containers == ["insyt-capture"]
    assert review.container.requested_paths == [path]
    assert destination.read_bytes() == b"synthetic worksheet text"


def test_processing_source_routing_is_preserved(
    monkeypatch, tmp_path
):
    processing = FakeService(FakeContainer())

    monkeypatch.setattr(
        runner, "_processing_blob_service",
        lambda: processing,
    )
    monkeypatch.setattr(
        runner, "_processing_container",
        lambda: "insyt-processing",
    )
    monkeypatch.setattr(
        runner, "_review_blob_service",
        lambda: pytest.fail(
            "Processing source must not use review storage"
        ),
    )

    path = (
        "client/capture/project/source/text/DOC-A.txt"
    )

    destination = tmp_path / "processing.txt"

    runner._download_detection_text(
        workspace="capture",
        blob_path=path,
        destination=destination,
    )

    assert processing.requested_containers == [
        "insyt-processing"
    ]
    assert processing.container.requested_paths == [path]
    assert destination.read_bytes() == b"synthetic worksheet text"