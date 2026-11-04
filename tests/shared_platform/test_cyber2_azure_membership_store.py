"""Offline tests of exact Azure SDK conditional-write call semantics."""
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.services.cyber2.azure_membership_store import AzureBlobMembershipStore
from app.services.cyber2.membership_persistence import MembershipConflict


@pytest.fixture(autouse=True)
def fake_azure(monkeypatch):
    class HttpResponseError(Exception):
        def __init__(self, status_code=None):
            self.status_code = status_code
    class ResourceExistsError(HttpResponseError): pass
    class ResourceModifiedError(HttpResponseError): pass
    class ResourceNotFoundError(HttpResponseError): pass
    class MatchConditions:
        IfNotModified = "IfNotModified"
    class ContentSettings:
        def __init__(self, content_type): self.content_type = content_type
    azure = types.ModuleType("azure")
    core = types.ModuleType("azure.core")
    exceptions = types.ModuleType("azure.core.exceptions")
    storage = types.ModuleType("azure.storage")
    blob = types.ModuleType("azure.storage.blob")
    core.MatchConditions = MatchConditions
    for cls in (HttpResponseError, ResourceExistsError, ResourceModifiedError, ResourceNotFoundError):
        setattr(exceptions, cls.__name__, cls)
    blob.ContentSettings = ContentSettings
    for name, mod in {"azure": azure, "azure.core": core,
                      "azure.core.exceptions": exceptions,
                      "azure.storage": storage, "azure.storage.blob": blob}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return SimpleNamespace(HttpResponseError=HttpResponseError,
                           ResourceExistsError=ResourceExistsError,
                           ResourceModifiedError=ResourceModifiedError,
                           ResourceNotFoundError=ResourceNotFoundError)


class FakeBlob:
    def __init__(self, errors):
        self.errors = errors
        self.version = 0
        self.data = None
        self.race_on_download = False
        self.last_upload = None
    def get_blob_properties(self):
        if self.data is None:
            raise self.errors.ResourceNotFoundError(status_code=404)
        return SimpleNamespace(etag=f'"v{self.version}"')
    def download_blob(self, *, etag, match_condition):
        assert match_condition == "IfNotModified"
        if self.race_on_download or etag != f'"v{self.version}"':
            raise self.errors.ResourceModifiedError(status_code=412)
        return SimpleNamespace(readall=lambda: self.data)
    def upload_blob(self, data, **kwargs):
        self.last_upload = kwargs
        if kwargs["overwrite"] is False:
            if self.data is not None:
                raise self.errors.ResourceExistsError(status_code=409)
        else:
            assert kwargs["match_condition"] == "IfNotModified"
            if self.data is None or kwargs["etag"] != f'"v{self.version}"':
                raise self.errors.ResourceModifiedError(status_code=412)
        self.version += 1
        self.data = data
        return {"etag": f'"v{self.version}"'}

class FakeContainer:
    def __init__(self, err):
        self.blob = FakeBlob(err)
        self.paths = []
    def get_blob_client(self, path):
        self.paths.append(path)
        return self.blob


def make_store(err):
    container = FakeContainer(err)
    return AzureBlobMembershipStore(container), container


def test_missing_reads_absent(fake_azure):
    store, _ = make_store(fake_azure)
    assert store.read("some/registry.json").payload is None
    assert store.read("some/registry.json").version is None


def test_create_only_and_read_version(fake_azure):
    store, container = make_store(fake_azure)
    assert store.write("a", {"revision": 0}, expected_version=None) == '"v1"'
    assert container.blob.last_upload["overwrite"] is False
    assert container.blob.last_upload["content_settings"].content_type == "application/json"
    snap = store.read("a")
    assert snap.payload == {"revision": 0} and snap.version == '"v1"'


def test_create_race_rejected(fake_azure):
    store, container = make_store(fake_azure)
    store.write("a", {"revision": 0}, expected_version=None)
    with pytest.raises(MembershipConflict):
        store.write("a", {"revision": 1}, expected_version=None)
    assert json.loads(container.blob.data) == {"revision": 0}


def test_cas_update(fake_azure):
    store, container = make_store(fake_azure)
    store.write("a", {"revision": 0}, expected_version=None)
    assert store.write("a", {"revision": 1}, expected_version='"v1"') == '"v2"'
    assert container.blob.last_upload["etag"] == '"v1"'
    assert json.loads(container.blob.data) == {"revision": 1}


def test_stale_cas_rejected_and_no_mutation(fake_azure):
    store, container = make_store(fake_azure)
    store.write("a", {"revision": 0}, expected_version=None)
    store.write("a", {"revision": 1}, expected_version='"v1"')
    with pytest.raises(MembershipConflict):
        store.write("a", {"revision": 2}, expected_version='"v1"')
    assert json.loads(container.blob.data) == {"revision": 1}


def test_changed_during_read_rejected(fake_azure):
    store, container = make_store(fake_azure)
    store.write("a", {"revision": 0}, expected_version=None)
    container.blob.race_on_download = True
    with pytest.raises(MembershipConflict):
        store.read("a")


def test_invalid_etag_and_unexpected_errors(fake_azure):
    store, container = make_store(fake_azure)
    with pytest.raises(ValueError):
        store.write("a", {}, expected_version="")
    def fail(*args, **kwargs):
        raise fake_azure.HttpResponseError(status_code=500)
    container.blob.upload_blob = fail
    with pytest.raises(fake_azure.HttpResponseError):
        store.write("a", {}, expected_version=None)


def test_bad_json_fails_closed(fake_azure):
    store, container = make_store(fake_azure)
    store.write("a", {"revision": 0}, expected_version=None)
    container.blob.data = b'not-json'
    with pytest.raises(json.JSONDecodeError):
        store.read("a")
