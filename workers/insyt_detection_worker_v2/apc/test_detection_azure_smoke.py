import pytest

from azure.core.exceptions import (
    ResourceExistsError,
    ResourceNotFoundError,
)

from apc.detection_azure_smoke import run_checkpoint_smoke


class FakeBlob:
    def __init__(self, data, path):
        self.data = data
        self.path = path

    def upload_blob(self, content, *, overwrite=False):
        if self.path in self.data and not overwrite:
            raise ResourceExistsError("Already exists.")
        self.data[self.path] = content

    def download_blob(self):
        if self.path not in self.data:
            raise ResourceNotFoundError("Missing.")
        return self

    def readall(self):
        return self.data[self.path]

    def get_blob_properties(self):
        if self.path not in self.data:
            raise ResourceNotFoundError("Missing.")
        return {"size": len(self.data[self.path])}


class FakeContainer:
    def __init__(self):
        self.data = {}

    def get_blob_client(self, path):
        return FakeBlob(self.data, path)


def test_smoke_writes_and_reuses_checkpoint():
    container = FakeContainer()
    calls = []

    def engine(text, **kwargs):
        calls.append((text, kwargs))
        return {
            "candidates": [],
            "azure_candidate_count": 0,
            "structured_candidate_count": 0,
            "merged_candidate_count": 0,
        }

    first = run_checkpoint_smoke(
        container_client=container,
        smoke_id="SMOKE-TEST0001",
        engine=engine,
    )

    second = run_checkpoint_smoke(
        container_client=container,
        smoke_id="SMOKE-TEST0001",
        engine=engine,
    )

    assert first.reused_checkpoint is False
    assert second.reused_checkpoint is True
    assert len(calls) == 1
    assert calls[0][1]["enable_azure"] is False
    assert first.checkpoint_path in container.data
    assert first.result_path in container.data


def test_smoke_rejects_invalid_identifier():
    with pytest.raises(ValueError):
        run_checkpoint_smoke(
            container_client=FakeContainer(),
            smoke_id="../client",
        )