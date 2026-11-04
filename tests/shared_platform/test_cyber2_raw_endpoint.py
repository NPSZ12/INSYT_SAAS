"""Full RAW generator tests with in-memory Azure Blob CAS semantics."""

import ast
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "backend/app/api/cyber2/schema_mapping.py"
)


class AzureError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(str(status_code))


class HttpResponseError(AzureError):
    pass


class ResourceNotFoundError(HttpResponseError):
    pass


class ResourceModifiedError(HttpResponseError):
    pass


class ResourceExistsError(HttpResponseError):
    pass


class MatchConditions:
    IfNotModified = "IfNotModified"


class ContentSettings:
    def __init__(self, content_type):
        self.content_type = content_type


class FakeBlob:
    def __init__(self):
        self.data = None
        self.version = 0
        self.write_calls = 0
        self.race_on_write = False
        self.race_on_read = False

    def get_blob_properties(self):
        if self.data is None:
            raise ResourceNotFoundError(404)
        return SimpleNamespace(etag=f'"v{self.version}"')

    def download_blob(self, *, etag, match_condition):
        assert match_condition == MatchConditions.IfNotModified
        if self.race_on_read or etag != f'"v{self.version}"':
            raise ResourceModifiedError(412)
        return SimpleNamespace(readall=lambda: self.data)

    def upload_blob(self, data, **kwargs):
        self.write_calls += 1
        assert kwargs["content_settings"].content_type == "application/json"

        if kwargs["overwrite"] is False:
            if self.data is not None:
                raise ResourceExistsError(409)
        else:
            assert kwargs["match_condition"] == MatchConditions.IfNotModified
            if (
                self.race_on_write
                or self.data is None
                or kwargs["etag"] != f'"v{self.version}"'
            ):
                raise ResourceModifiedError(412)

        self.data = data
        self.version += 1
        return {"etag": f'"v{self.version}"'}

    def records(self):
        return json.loads(self.data)["records"]


class FakeContainer:
    def __init__(self):
        self.blob = FakeBlob()

    def get_blob_client(self, path):
        assert path.endswith("latest_raw_capture.json")
        return self.blob


@pytest.fixture
def environment(monkeypatch):
    # Only mock Azure SDK imports used by the real endpoint.
    azure = types.ModuleType("azure")
    core = types.ModuleType("azure.core")
    errors = types.ModuleType("azure.core.exceptions")
    storage = types.ModuleType("azure.storage")
    blob_module = types.ModuleType("azure.storage.blob")

    core.MatchConditions = MatchConditions
    blob_module.ContentSettings = ContentSettings

    for exception in (
        HttpResponseError,
        ResourceNotFoundError,
        ResourceModifiedError,
        ResourceExistsError,
    ):
        setattr(errors, exception.__name__, exception)

    for name, module in {
        "azure": azure,
        "azure.core": core,
        "azure.core.exceptions": errors,
        "azure.storage": storage,
        "azure.storage.blob": blob_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    # Compile the actual endpoint function, without starting FastAPI
    # or connecting to Azure.
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "generate_cyber2_raw_capture"
    )
    fn.decorator_list = []

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            fn,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)

    container = FakeContainer()
    state = SimpleNamespace(
        header="HDRSET-TEST",
        doc_id="INSYT-SYNTHETIC-001",
        rows=[
            ["First Name", "Row Marker"],
            *[
                ["Synthetic", str(i)]
                for i in range(64)
            ],
        ],
        uid_counter=0,
        manifest_writes=0,
    )

    def document():
        return {
            "doc_id": state.doc_id,
            "mapped_csv_path": "mapped/synthetic.csv",
            "source_csv_path": "source/synthetic.csv",
            "header_status": "HEADER",
            "sheet_index": 0,
            "original_filename": "synthetic.csv",
        }

    def load_required(path, **kwargs):
        if path == "mapped_manifest":
            return {"documents": [document()]}
        if path == "header_manifest":
            return {"status": "mapped"}
        raise AssertionError(f"Unexpected manifest path: {path}")

    def next_ucid():
        state.uid_counter += 1
        return f"UCID-SYNTHETIC-{state.uid_counter:08d}"

    def write_manifest(**kwargs):
        assert kwargs["blob_path"] == "header_manifest"
        state.manifest_writes += 1
        return {"status": "uploaded"}

    namespace = {
        "HTTPException": HTTPException,
        "_mapped_csv_manifest_path": lambda **kw: "mapped_manifest",
        "_header_set_manifest_path": lambda **kw: "header_manifest",
        "_raw_capture_path": lambda **kw: (
            "synthetic/cyber2/raw_capture/latest_raw_capture.json"
        ),
        "_load_required_json": load_required,
        "_processing_container_client": lambda: container,
        "_read_csv_blob_rows": lambda **kw: (state.rows, ","),
        "_utc_now": lambda: "2026-11-04T00:00:00Z",
        "_generate_cyber2_ucid": next_ucid,
        "_write_processing_json_blob": write_manifest,
    }

    exec(compile(module, str(SOURCE), "exec"), namespace)

    endpoint = namespace["generate_cyber2_raw_capture"]

    def run():
        request = SimpleNamespace(
            client="INSYT_Demo",
            project="Project_Scalable",
            generated_by="synthetic-integration-test",
            replace_header_set_rows=True,
        )
        return endpoint(
            workspace="capture",
            header_set_id=state.header,
            request=request,
        )

    return SimpleNamespace(
        run=run,
        state=state,
        blob=container.blob,
    )


def seed_64(env):
    response = env.run()
    assert response["project_raw_record_count"] == 64
    assert len(env.blob.records()) == 64
    return env.blob.records()


def test_initial_create_and_idempotent_regeneration(environment):
    env = environment
    original = seed_64(env)
    original_ids = [r["ucid"] for r in original]

    env.run()
    again = env.blob.records()

    assert len(again) == 64
    assert [r["ucid"] for r in again] == original_ids
    assert again == original


def test_new_header_preserves_all_existing_ucids(environment):
    env = environment
    old = seed_64(env)

    env.state.header = "HDRSET-NEW"
    env.state.doc_id = "INSYT-SYNTHETIC-002"
    env.state.rows = [
        ["First Name", "Row Marker"],
        ["Synthetic", "new-1"],
        ["Synthetic", "new-2"],
    ]

    env.run()
    current = env.blob.records()

    assert len(current) == 66
    assert current[:64] == old
    assert len({r["ucid"] for r in current}) == 66


def test_changed_value_blocks_write(environment):
    env = environment
    seed_64(env)
    before = env.blob.data
    writes = env.blob.write_calls

    env.state.rows[1][0] = "Changed"

    with pytest.raises(HTTPException) as exc:
        env.run()

    assert exc.value.status_code == 409
    assert env.blob.data == before
    assert env.blob.write_calls == writes


def test_missing_row_blocks_write(environment):
    env = environment
    seed_64(env)
    before = env.blob.data
    writes = env.blob.write_calls

    env.state.rows.pop()

    with pytest.raises(HTTPException) as exc:
        env.run()

    assert exc.value.status_code == 409
    assert env.blob.data == before
    assert env.blob.write_calls == writes


@pytest.mark.parametrize("rows", [[], [["First Name", "Row Marker"]]])
def test_empty_or_header_only_csv_blocks_write(environment, rows):
    env = environment
    seed_64(env)
    before = env.blob.data
    writes = env.blob.write_calls

    env.state.rows = rows

    with pytest.raises(HTTPException) as exc:
        env.run()

    assert exc.value.status_code == 409
    assert env.blob.data == before
    assert env.blob.write_calls == writes


def test_etag_write_conflict_preserves_snapshot(environment):
    env = environment
    seed_64(env)
    before = env.blob.data

    env.blob.race_on_write = True

    with pytest.raises(HTTPException) as exc:
        env.run()

    assert exc.value.status_code == 409
    assert env.blob.data == before


def test_etag_read_conflict_preserves_snapshot(environment):
    env = environment
    seed_64(env)
    before = env.blob.data
    writes = env.blob.write_calls

    env.blob.race_on_read = True

    with pytest.raises(HTTPException) as exc:
        env.run()

    assert exc.value.status_code == 409
    assert env.blob.data == before
    assert env.blob.write_calls == writes


def test_invalid_existing_json_fails_without_write(environment):
    env = environment
    seed_64(env)

    env.blob.data = b"invalid-json"
    writes = env.blob.write_calls

    with pytest.raises(HTTPException) as exc:
        env.run()

    assert exc.value.status_code == 409
    assert env.blob.data == b"invalid-json"
    assert env.blob.write_calls == writes


def test_approved_membership_ucids_remain_resolvable(environment):
    env = environment
    old = seed_64(env)

    approved = {
        old[0]["ucid"],
        old[1]["ucid"],
    }

    env.run()

    current_ids = {r["ucid"] for r in env.blob.records()}
    assert approved <= current_ids