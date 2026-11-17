"""Regression guards for the shared Cyber2 JSON/CSV Header Mapping route.

These tests verify authorization placement and the pure native JSON
adapter. Full authenticated API/Azure integration tests remain required
before release.
"""

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
CYBER2 = ROOT / "backend" / "app" / "api" / "cyber2"


def read_tree(filename):
    return ast.parse(
        (CYBER2 / filename).read_text(encoding="utf-8-sig")
    )


def find_function(tree, name):
    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    ]
    assert len(matches) == 1
    return matches[0]


def calls_named(function, name):
    return [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


def test_header_set_creation_authorized_before_storage():
    tree = read_tree("header_sets.py")
    route = find_function(tree, "create_cyber2_header_set")

    assert "admin" in [arg.arg for arg in route.args.args]

    checks = calls_named(route, "require_scoped_project_access")
    storage = calls_named(route, "_processing_container_client")

    assert len(checks) == 1
    assert len(storage) == 1
    assert checks[0].lineno < storage[0].lineno


def test_identification_authorized_before_manifest_read():
    tree = read_tree("header_identification.py")
    route = find_function(tree, "identify_cyber2_header_set")

    assert "admin" in [arg.arg for arg in route.args.args]

    checks = calls_named(route, "require_scoped_project_access")
    loads = calls_named(route, "_load_header_set")

    assert len(checks) >= 1
    assert len(loads) == 1
    assert min(check.lineno for check in checks) < loads[0].lineno


def test_csv_and_json_identification_paths_remain_present():
    tree = read_tree("header_identification.py")
    route = find_function(tree, "identify_cyber2_header_set")

    assert len(calls_named(route, "_read_csv_rows")) == 1
    assert len(calls_named(route, "analyze_csv_rows")) == 1
    assert len(calls_named(
        route, "preview_cyber2_json_native"
    )) == 1
    assert len(calls_named(
        route, "_json_review_as_identification_document"
    )) == 1


def get_json_adapter():
    tree = read_tree("header_identification.py")
    function = find_function(
        tree, "_json_review_as_identification_document"
    )

    isolated = ast.Module(
        body=[function],
        type_ignores=[],
    )
    namespace = {}
    exec(
        compile(isolated, "<json-adapter-regression>", "exec"),
        namespace,
    )
    return namespace["_json_review_as_identification_document"]


def example_inputs():
    sha = "a" * 64
    document = {
        "doc_id": "TEST0001",
        "source_kind": "native_json",
        "source_sha256": sha,
        "source_native_path": "synthetic/source/native/TEST0001.json",
    }
    review = {
        "source_sha256": sha,
        "mapping_approved": False,
        "csv_generated": False,
        "record_count": 2,
        "columns": [
            {
                "json_pointer": "/employee",
                "json_kind": "object",
                "source_header": "employee",
            },
            {
                "json_pointer": "/employee/first_name",
                "json_kind": "scalar",
                "source_header": "employee.first_name",
                "recommended_protocol_header": "First Name",
                "sample_values": ["SYNTHETIC"],
                "ai_confidence": 0.91,
                "ai_invoked": True,
            },
            {
                "json_pointer": "/employee/ssn",
                "json_kind": "scalar",
                "source_header": "employee.ssn",
                "recommended_protocol_header": None,
                "sample_values": ["<REDACTED>"],
            },
        ],
    }
    return document, review


def test_json_adapter_preserves_pointers_and_excludes_parent():
    adapter = get_json_adapter()
    doc, review = example_inputs()
    result = adapter(doc, review)

    assert result["column_count"] == 2
    assert len(result["structural_fields"]) == 1
    assert [
        c["json_pointer"] for c in result["columns"]
    ] == ["/employee/first_name", "/employee/ssn"]
    assert result["columns"][0]["ai_confidence"] == 0.91
    assert all(not c["approved"] for c in result["columns"])


def test_json_adapter_rejects_source_hash_mismatch():
    adapter = get_json_adapter()
    doc, review = example_inputs()
    doc["source_sha256"] = "b" * 64

    with pytest.raises(ValueError):
        adapter(doc, review)


def test_json_adapter_rejects_premature_csv_status():
    adapter = get_json_adapter()
    doc, review = example_inputs()
    review["csv_generated"] = True

    with pytest.raises(ValueError):
        adapter(doc, review)


def test_json_schema_groups_are_stable_and_distinct():
    adapter = get_json_adapter()
    doc, review = example_inputs()

    first = adapter(doc, review)
    second = adapter({**doc, "doc_id": "TEST0002"}, review)

    assert first["schema_signature"] == second["schema_signature"]

    changed = {
        **review,
        "columns": review["columns"][:-1],
    }
    third = adapter(doc, changed)

    assert first["schema_signature"] != third["schema_signature"]

# STEP 540: RUNTIME CREATION TESTS

import copy
import re
import uuid
from types import SimpleNamespace
from fastapi import HTTPException


def _runtime_creation_function():
    tree = read_tree("header_sets.py")
    function = copy.deepcopy(
        find_function(tree, "create_cyber2_header_set")
    )
    function.decorator_list = []

    isolated = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            function,
        ],
        type_ignores=[],
    )
    return compile(
        ast.fix_missing_locations(isolated),
        "<header-set-runtime>",
        "exec",
    )


def _exercise_creation(
    kind="native_json",
    denied=False,
    tampered=False,
    assigned=False,
):
    doc_id = "TEST0001"
    base = "capture/ClientA/ProjectA"

    source = {
        "doc_id": doc_id,
        "source_kind": kind,
        "intake_index_path": (
            f"{base}/cyber2/intake/documents/{doc_id}.json"
        ),
        "original_filename": "synthetic.json",
    }

    if kind == "native_json":
        source.update({
            "source_native_path": (
                f"{base}/source/native/{doc_id}.json"
            ),
            "source_sha256": "a" * 64,
            "source_bytes": 100,
            "source_format": "json",
            "source_csv_path": "",
        })
    else:
        source.update({
            "source_csv_path": (
                f"{base}/cyber2/intake/csv/{doc_id}.csv"
            ),
        })

    if assigned:
        source["header_set_id"] = "HDRSET-EXISTING"

    if tampered:
        source["source_native_path"] = (
            "capture/OtherClient/OtherProject/"
            f"source/native/{doc_id}.json"
        )

    effects = {
        "authorized": False,
        "reads": 0,
        "writes": [],
    }

    def authorize(admin, workspace, client, project):
        if denied:
            raise HTTPException(
                status_code=403,
                detail="Synthetic access denied",
            )
        assert (workspace, client, project) == (
            "capture", "ClientA", "ProjectA"
        )
        effects["authorized"] = True

    def base_path(**kwargs):
        assert effects["authorized"]
        return base

    class FakeContainer:
        def list_blobs(self, name_starts_with):
            assert effects["authorized"]
            assert name_starts_with == (
                f"{base}/cyber2/intake/documents/"
            )
            effects["reads"] += 1
            return [
                SimpleNamespace(
                    name=source["intake_index_path"]
                )
            ]

    def read_blob(path):
        assert effects["authorized"]
        assert path == source["intake_index_path"]
        effects["reads"] += 1
        return dict(source)

    def write_blob(**kwargs):
        assert effects["authorized"]
        effects["writes"].append(kwargs)
        return {"ok": True}

    namespace = {
        "Query": lambda *a, **k: None,
        "Depends": lambda *a, **k: None,
        "require_admin": lambda: None,
        "HTTPException": HTTPException,
        "require_scoped_project_access": authorize,
        "_project_base_path": base_path,
        "_processing_container_client": FakeContainer,
        "_read_processing_json_blob": read_blob,
        "_write_processing_json_blob": write_blob,
        "_utc_now": lambda: "2026-11-17T00:00:00Z",
        "uuid4": uuid.uuid4,
        "re": re,
    }

    exec(_runtime_creation_function(), namespace)

    request = SimpleNamespace(
        client="ClientA",
        project="ProjectA",
        doc_ids=[doc_id],
        requested_by="synthetic-test",
    )

    try:
        result = namespace["create_cyber2_header_set"](
            workspace="capture",
            request=request,
            admin=object(),
        )
        return result, effects, None
    except HTTPException as exc:
        return None, effects, exc


def test_runtime_denied_access_before_storage():
    result, effects, error = _exercise_creation(denied=True)

    assert result is None
    assert error.status_code == 403
    assert effects["reads"] == 0
    assert effects["writes"] == []


def test_runtime_json_rejects_cross_project_path():
    result, effects, error = _exercise_creation(tampered=True)

    assert result is None
    assert error.status_code == 409
    assert effects["writes"] == []


def test_runtime_json_keeps_native_without_csv():
    result, effects, error = _exercise_creation()

    assert error is None
    assert result["status"] == "created"
    assert result["document_count"] == 1

    doc = result["documents"][0]
    assert doc["source_kind"] == "native_json"
    assert doc["source_sha256"] == "a" * 64
    assert doc["source_bytes"] == 100
    assert doc["source_csv_path"] == ""
    assert doc["source_native_path"].endswith(
        "/TEST0001.json"
    )
    assert len(effects["writes"]) == 2
    assert all(
        not item["blob_path"].endswith(".csv")
        for item in effects["writes"]
    )


def test_runtime_csv_creation_unchanged():
    result, effects, error = _exercise_creation(kind="csv")

    assert error is None
    assert result["status"] == "created"
    assert result["document_count"] == 1

    doc = result["documents"][0]
    assert doc["source_kind"] == "csv"
    assert doc["source_csv_path"].endswith(".csv")
    assert len(effects["writes"]) == 2

# STEP 541: IDENTIFICATION AUTHORIZATION RUNTIME TESTS

def _exercise_identification_authorization(denied):
    """Run the actual identification entry until authorization/storage."""
    tree = read_tree("header_identification.py")
    function = copy.deepcopy(
        find_function(tree, "identify_cyber2_header_set")
    )
    function.decorator_list = []

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            function,
        ],
        type_ignores=[],
    )

    module = ast.fix_missing_locations(module)

    events = []

    class StorageReached(Exception):
        pass

    def authorize(admin, workspace, client, project):
        events.append("authorize")
        assert workspace == "capture"
        assert client == "ClientA"
        assert project == "ProjectA"

        if denied:
            raise HTTPException(
                status_code=403,
                detail="Synthetic project access denied.",
            )

    def load_header_set(**kwargs):
        events.append("read_header_set")
        raise StorageReached()

    namespace = {
        "Query": lambda *args, **kwargs: None,
        "Depends": lambda *args, **kwargs: None,
        "require_admin": lambda: None,
        "HTTPException": HTTPException,
        "require_scoped_project_access": authorize,
        "_load_header_set": load_header_set,
    }

    exec(
        compile(module, "<identification-runtime>", "exec"),
        namespace,
    )

    function_under_test = namespace[
        "identify_cyber2_header_set"
    ]

    try:
        function_under_test(
            workspace="capture",
            header_set_id="HDRSET-SYNTHETIC",
            client="ClientA",
            project="ProjectA",
            ai_suggestions=False,
            admin=object(),
        )
    except HTTPException as exc:
        return events, exc.status_code
    except StorageReached:
        return events, "storage_reached"

    raise AssertionError(
        "Identification unexpectedly completed."
    )


def test_runtime_identification_denies_before_manifest_read():
    events, outcome = _exercise_identification_authorization(
        denied=True
    )

    assert outcome == 403
    assert events == ["authorize"]


def test_runtime_identification_authorizes_before_manifest_read():
    events, outcome = _exercise_identification_authorization(
        denied=False
    )

    assert outcome == "storage_reached"
    assert events == ["authorize", "read_header_set"]

# STEP 542: IDENTIFICATION SOURCE ROUTING TESTS

def _exercise_identification_source(
    kind="native_json",
    ai=False,
    tampered=False,
):
    """Run actual identification route to the source reader boundary."""
    tree = read_tree("header_identification.py")
    function = copy.deepcopy(
        find_function(tree, "identify_cyber2_header_set")
    )
    function.decorator_list = []

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            function,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)

    class ReaderReached(Exception):
        pass

    doc_id = "TEST0001"
    base = "capture/ClientA/ProjectA"
    sha = "a" * 64
    native = f"{base}/source/native/{doc_id}.json"

    document = {
        "doc_id": doc_id,
        "source_kind": kind,
        "source_native_path": native if kind == "native_json" else "",
        "source_sha256": sha if kind == "native_json" else "",
        "source_bytes": 100 if kind == "native_json" else None,
        "source_csv_path": (
            "" if kind == "native_json"
            else f"{base}/cyber2/intake/csv/{doc_id}.csv"
        ),
    }

    intake = dict(document)

    if tampered:
        intake["source_sha256"] = "b" * 64

    events = []

    def authorize(admin, workspace, client, project):
        assert (workspace, client, project) == (
            "capture", "ClientA", "ProjectA"
        )
        events.append("authorize")

    def load_header_set(**kwargs):
        events.append("load_header_set")
        return {"documents": [dict(document)]}

    def load_protocol(**kwargs):
        events.append("load_protocol")
        return {"library": {"First Name": {}}}

    def project_path(**kwargs):
        return base

    def read_intake(path):
        assert path == (
            f"{base}/cyber2/intake/documents/{doc_id}.json"
        )
        events.append("read_json_registration")
        return dict(intake)

    def preview(**kwargs):
        assert kwargs["doc_id"] == doc_id
        assert kwargs["workspace"] == "capture"
        assert "ai_suggestions" not in kwargs
        assert kwargs["admin"] is admin
        events.append("verified_json_preview")
        raise ReaderReached()

    def read_csv(**kwargs):
        assert kwargs["blob_path"] == document["source_csv_path"]
        events.append("read_csv")
        raise ReaderReached()

    namespace = {
        "Query": lambda *a, **k: None,
        "Depends": lambda *a, **k: None,
        "require_admin": lambda: None,
        "HTTPException": HTTPException,
        "require_scoped_project_access": authorize,
        "_load_header_set": load_header_set,
        "_load_protocol_library": load_protocol,
        "_review_container": lambda workspace: "synthetic-review",
        "_project_base_path": project_path,
        "_read_processing_json_blob": read_intake,
        "preview_cyber2_json_native": preview,
        "_read_review_blob_bytes": read_csv,
    }

    exec(
        compile(module, "<identification-routing>", "exec"),
        namespace,
    )

    admin = object()

    try:
        namespace["identify_cyber2_header_set"](
            workspace="capture",
            header_set_id="HDRSET-SYNTHETIC",
            client="ClientA",
            project="ProjectA",
            ai_suggestions=ai,
            admin=admin,
        )
    except ReaderReached:
        return events, "reader_reached"
    except HTTPException as exc:
        return events, exc.status_code

    raise AssertionError(
        "Identification unexpectedly completed without reaching reader."
    )


def test_runtime_json_uses_verified_reader_with_explicit_ai():
    events, outcome = _exercise_identification_source(
        kind="native_json",
        ai=True,
    )
    assert outcome == "reader_reached"
    assert events.count("verified_json_preview") == 1
    assert "read_csv" not in events
    assert events.index("authorize") < events.index("load_header_set")


def test_runtime_json_ai_not_automatic():
    events, outcome = _exercise_identification_source(
        kind="native_json",
        ai=False,
    )
    assert outcome == "reader_reached"
    assert events.count("verified_json_preview") == 1
    assert "read_csv" not in events


def test_runtime_json_registration_hash_mismatch_blocks_reader():
    events, outcome = _exercise_identification_source(
        kind="native_json",
        ai=True,
        tampered=True,
    )
    assert outcome == 409
    assert "verified_json_preview" not in events
    assert "read_csv" not in events


def test_runtime_csv_uses_existing_csv_reader():
    events, outcome = _exercise_identification_source(
        kind="csv",
        ai=False,
    )
    assert outcome == "reader_reached"
    assert events.count("read_csv") == 1
    assert "verified_json_preview" not in events
    assert "read_json_registration" not in events

# STEP 547: HEADER SET DETAIL ACCESS TESTS

def _exercise_header_set_detail_access(denied):
    import copy

    tree = read_tree("header_identification.py")
    function = copy.deepcopy(
        find_function(tree, "get_cyber2_header_set")
    )
    function.decorator_list = []

    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            ),
            function,
        ],
        type_ignores=[],
    )

    ast.fix_missing_locations(module)

    events = []

    class StorageReached(Exception):
        pass

    def authorize(admin, workspace, client, project):
        events.append("authorize")

        assert (workspace, client, project) == (
            "capture", "ClientA", "ProjectA"
        )

        if denied:
            raise HTTPException(
                status_code=403,
                detail="Synthetic access denied.",
            )

    def load_header_set(**kwargs):
        events.append("read_header_set")
        raise StorageReached()

    namespace = {
        "Query": lambda *a, **k: None,
        "Depends": lambda *a, **k: None,
        "require_admin": lambda: None,
        "HTTPException": HTTPException,
        "require_scoped_project_access": authorize,
        "_load_header_set": load_header_set,
    }

    exec(
        compile(module, "<header-detail-runtime>", "exec"),
        namespace,
    )

    try:
        namespace["get_cyber2_header_set"](
            workspace="capture",
            header_set_id="HDRSET-SYNTHETIC",
            client="ClientA",
            project="ProjectA",
            admin=object(),
        )

    except HTTPException as exc:
        return events, exc.status_code

    except StorageReached:
        return events, "storage_reached"

    raise AssertionError(
        "Header Set GET unexpectedly completed."
    )


def test_header_set_detail_denied_before_storage():
    events, outcome = _exercise_header_set_detail_access(
        denied=True
    )

    assert outcome == 403
    assert events == ["authorize"]


def test_header_set_detail_authorized_before_storage():
    events, outcome = _exercise_header_set_detail_access(
        denied=False
    )

    assert outcome == "storage_reached"
    assert events == ["authorize", "read_header_set"]


def test_header_set_detail_route_has_admin_dependency():
    tree = read_tree("header_identification.py")
    route = find_function(tree, "get_cyber2_header_set")

    assert "admin" in [a.arg for a in route.args.args]

    checks = calls_named(
        route, "require_scoped_project_access"
    )
    reads = calls_named(route, "_load_header_set")

    assert len(checks) == 1
    assert len(reads) == 1
    assert checks[0].lineno < reads[0].lineno

# STEP 549: HEADER SET LIST ACCESS

def _exercise_header_list_access(denied):
    tree = read_tree("header_sets.py")
    import copy

    function = copy.deepcopy(
        find_function(tree, "list_cyber2_header_sets")
    )
    function.decorator_list = []

    module = ast.fix_missing_locations(
        ast.Module(
            body=[
                ast.ImportFrom(
                    module="__future__",
                    names=[ast.alias(name="annotations")],
                    level=0,
                ),
                function,
            ],
            type_ignores=[],
        )
    )

    events = []

    class StorageReached(Exception):
        pass

    def authorize(admin, workspace, client, project):
        events.append("authorize")
        assert (workspace, client, project) == (
            "capture", "ClientA", "ProjectA"
        )
        if denied:
            raise HTTPException(
                status_code=403,
                detail="Synthetic access denied.",
            )

    def project_path(**kwargs):
        events.append("project_path")
        return "capture/ClientA/ProjectA"

    def storage():
        events.append("storage")
        raise StorageReached()

    namespace = {
        "Query": lambda *a, **k: None,
        "Depends": lambda *a, **k: None,
        "require_admin": lambda: None,
        "require_scoped_project_access": authorize,
        "_project_base_path": project_path,
        "_processing_container_client": storage,
        "HTTPException": HTTPException,
    }

    exec(
        compile(module, "<header-list-runtime>", "exec"),
        namespace,
    )

    try:
        namespace["list_cyber2_header_sets"](
            workspace="capture",
            client="ClientA",
            project="ProjectA",
            admin=object(),
        )
    except HTTPException as exc:
        return events, exc.status_code
    except StorageReached:
        return events, "storage_reached"

    raise AssertionError("Listing unexpectedly completed.")


def test_header_listing_denied_before_any_storage():
    events, status = _exercise_header_list_access(True)
    assert status == 403
    assert events == ["authorize"]


def test_header_listing_authorized_before_storage():
    events, status = _exercise_header_list_access(False)
    assert status == "storage_reached"
    assert events == ["authorize", "project_path", "storage"]

# STEP 550: MAPPING ACCESS TESTS

@pytest.mark.parametrize(
    "name",
    [
        "get_cyber2_header_mapping",
        "approve_cyber2_header_mapping",
        "get_cyber2_mapped_csvs",
        "generate_cyber2_mapped_csvs",
    ],
)
def test_mapping_routes_reject_unauthorized_access(name):
    import copy
    from types import SimpleNamespace
    from fastapi import HTTPException

    tree = read_tree("schema_mapping.py")
    function = copy.deepcopy(find_function(tree, name))
    function.decorator_list = []

    module = ast.fix_missing_locations(
        ast.Module(
            body=[
                ast.ImportFrom(
                    module="__future__",
                    names=[ast.alias(name="annotations")],
                    level=0,
                ),
                function,
            ],
            type_ignores=[],
        )
    )

    calls = []

    def deny(admin, workspace, client, project):
        calls.append((workspace, client, project))
        raise HTTPException(
            status_code=403,
            detail="Synthetic project access denied.",
        )

    namespace = {
        "Query": lambda *a, **k: None,
        "Depends": lambda *a, **k: None,
        "require_admin": lambda: None,
        "require_scoped_project_access": deny,
        "HTTPException": HTTPException,
    }

    exec(
        compile(module, "<mapping-access-test>", "exec"),
        namespace,
    )

    args = {
        "workspace": "capture",
        "header_set_id": "HDRSET-SYNTHETIC",
        "admin": object(),
    }

    if "request" in [
        arg.arg for arg in function.args.args
    ]:
        args["request"] = SimpleNamespace(
            client="ClientA",
            project="ProjectA",
            documents=[],
        )
    else:
        args["client"] = "ClientA"
        args["project"] = "ProjectA"

    with pytest.raises(HTTPException) as error:
        namespace[name](**args)

    assert error.value.status_code == 403
    assert calls == [
        ("capture", "ClientA", "ProjectA")
    ]

# STEP 551: LEGACY CSV SOURCE ELIGIBILITY TESTS

def _legacy_csv_gate():
    tree = read_tree("schema_mapping.py")
    function = find_function(
        tree,
        "_require_csv_sources_for_legacy_generation",
    )

    module = ast.fix_missing_locations(
        ast.Module(body=[function], type_ignores=[])
    )

    from fastapi import HTTPException

    namespace = {"HTTPException": HTTPException}
    exec(
        compile(module, "<legacy-csv-guard>", "exec"),
        namespace,
    )

    return namespace[
        "_require_csv_sources_for_legacy_generation"
    ]


@pytest.mark.parametrize(
    "kind",
    ["native_json", "json", "jsonl", "unsupported"],
)
def test_legacy_csv_generator_rejects_non_csv_sources(kind):
    from fastapi import HTTPException

    guard = _legacy_csv_gate()

    identification = {
        "documents": [{
            "doc_id": "TEST0001",
            "source_kind": kind,
            "source_csv_path": "synthetic.csv",
        }]
    }

    with pytest.raises(HTTPException) as error:
        guard(identification)

    assert error.value.status_code == 409


def test_legacy_csv_generator_accepts_csv_source():
    guard = _legacy_csv_gate()

    guard({
        "documents": [{
            "doc_id": "TEST0001",
            "source_kind": "csv",
            "source_csv_path": "synthetic.csv",
        }]
    })


def test_legacy_csv_generator_accepts_older_csv_metadata():
    guard = _legacy_csv_gate()

    guard({
        "documents": [{
            "doc_id": "TEST0001",
            "source_csv_path": "synthetic.csv",
        }]
    })


def test_legacy_csv_generator_rejects_missing_source():
    from fastapi import HTTPException

    guard = _legacy_csv_gate()

    with pytest.raises(HTTPException) as error:
        guard({
            "documents": [{
                "doc_id": "TEST0001",
                "source_kind": "csv",
                "source_csv_path": "",
            }]
        })

    assert error.value.status_code == 409


def test_legacy_csv_generator_rejects_mixed_source_set():
    from fastapi import HTTPException

    guard = _legacy_csv_gate()

    with pytest.raises(HTTPException):
        guard({
            "documents": [
                {
                    "doc_id": "CSV001",
                    "source_kind": "csv",
                    "source_csv_path": "synthetic.csv",
                },
                {
                    "doc_id": "JSON001",
                    "source_kind": "native_json",
                    "source_csv_path": "",
                },
            ]
        })


def test_legacy_csv_generator_requires_identification():
    from fastapi import HTTPException

    guard = _legacy_csv_gate()

    with pytest.raises(HTTPException):
        guard({"documents": []})


def test_legacy_csv_guard_precedes_approved_mapping_and_reader():
    tree = read_tree("schema_mapping.py")
    route = find_function(
        tree,
        "generate_cyber2_mapped_csvs",
    )

    def call_lines(name):
        return [
            node.lineno
            for node in ast.walk(route)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]

    guard = call_lines(
        "_require_csv_sources_for_legacy_generation"
    )
    approved = call_lines("_approved_mapping_path")
    reader = call_lines("_read_review_blob_bytes")

    assert len(guard) == 1
    assert len(approved) == 1
    assert len(reader) == 1
    assert guard[0] < approved[0] < reader[0]

# STEP 552: COMPLETE JSON IDENTIFICATION TESTS

@pytest.mark.parametrize(
    "document_count,different_schema,ai_enabled,expected_groups",
    [
        (1, False, True, 1),
        (1, False, False, 1),
        (2, False, True, 1),
        (2, True, True, 2),
    ],
)
def test_runtime_json_identification_persists_and_groups(
    document_count,
    different_schema,
    ai_enabled,
    expected_groups,
):
    import copy

    tree = read_tree("header_identification.py")

    names = (
        "_json_review_as_identification_document",
        "identify_cyber2_header_set",
    )

    functions = [
        copy.deepcopy(find_function(tree, name))
        for name in names
    ]

    for function in functions:
        function.decorator_list = []

    module = ast.fix_missing_locations(
        ast.Module(
            body=[
                ast.ImportFrom(
                    module="__future__",
                    names=[ast.alias(name="annotations")],
                    level=0,
                ),
                *functions,
            ],
            type_ignores=[],
        )
    )

    base = "capture/ClientA/ProjectA"
    doc_ids = [
        f"TEST{i:04d}"
        for i in range(1, document_count + 1)
    ]

    documents = []
    registrations = {}

    for doc_id in doc_ids:
        document = {
            "doc_id": doc_id,
            "source_kind": "native_json",
            "source_native_path": (
                f"{base}/source/native/{doc_id}.json"
            ),
            "source_sha256": "a" * 64,
            "source_bytes": 100,
            "source_csv_path": "",
        }

        documents.append(document)
        registrations[doc_id] = dict(document)

    manifest = {
        "header_set_id": "HDRSET-SYNTHETIC",
        "status": "pending_header_identification",
        "documents": documents,
    }

    writes = []
    preview_calls = []
    events = []

    def authorize(admin, workspace, client, project):
        assert (workspace, client, project) == (
            "capture", "ClientA", "ProjectA"
        )
        events.append("authorize")

    def load_header_set(**kwargs):
        assert events and events[0] == "authorize"
        events.append("load_header_set")
        return manifest

    def load_protocol(**kwargs):
        return {
            "library": {
                "First Name": {},
                "Social Security Number": {},
            },
            "source_blob": "synthetic-approved-protocol",
        }

    def read_intake(path):
        doc_id = path.rsplit("/", 1)[-1].removesuffix(".json")
        assert path == (
            f"{base}/cyber2/intake/documents/{doc_id}.json"
        )
        return registrations[doc_id]

    def preview(**kwargs):
        doc_id = kwargs["doc_id"]

        assert doc_id in doc_ids
        assert "ai_suggestions" not in kwargs
        assert kwargs["workspace"] == "capture"

        preview_calls.append(doc_id)

        columns = [
            {
                "json_pointer": "/employee",
                "json_kind": "object",
                "source_header": "employee",
            },
            {
                "json_pointer": "/employee/first_name",
                "json_kind": "scalar",
                "source_header": "employee.first_name",
                "sample_values": ["SYNTHETIC"],
                "recommended_protocol_header": "First Name",
                "ai_invoked": False,
                "ai_confidence": None,
                "ai_review_required": True,
            },
        ]

        if different_schema and doc_id == doc_ids[-1]:
            columns.append({
                "json_pointer": "/employee/ssn",
                "json_kind": "scalar",
                "source_header": "employee.ssn",
                "sample_values": ["<REDACTED>"],
                "recommended_protocol_header": (
                    "Social Security Number"
                ),
                "ai_invoked": False,
                "ai_review_required": True,
            })

        return {
            "doc_id": doc_id,
            "source_sha256_verified": True,
            "header_review": {
                "protocol_headers": [
                    "First Name", "Social Security Number"
                ],
                "source_sha256": "a" * 64,
                "record_count": 2,
                "mapping_approved": False,
                "csv_generated": False,
                "columns": columns,
            },
        }

    def write_blob(**kwargs):
        writes.append(kwargs)
        return {"ok": True}

    namespace = {
        "Query": lambda *a, **k: None,
        "Depends": lambda *a, **k: None,
        "require_admin": lambda: None,
        "HTTPException": HTTPException,
        "require_scoped_project_access": authorize,
        "_load_header_set": load_header_set,
        "_load_protocol_library": load_protocol,
        "_review_container": lambda w: "synthetic-review",
        "_project_base_path": lambda **k: base,
        "_read_processing_json_blob": read_intake,
        "preview_cyber2_json_native": preview,
        "_header_identification_path": (
            lambda **k: f"{base}/cyber2/header_mapping/"
            "HDRSET-SYNTHETIC/identification.json"
        ),
        "_header_set_manifest_path": (
            lambda **k: f"{base}/cyber2/header_sets/"
            "HDRSET-SYNTHETIC.json"
        ),
        "_utc_now": lambda: "2026-11-17T00:00:00Z",
        "_write_processing_json_blob": write_blob,
    }

    def fake_should_invoke_ai(**kwargs):
        assert kwargs["matched"] is True
        return ai_enabled

    def fake_resolve_header_with_ai(**kwargs):
        assert ai_enabled
        assert kwargs["deterministic_recommendation"] in {
            "First Name", "Social Security Number"
        }
        assert set(kwargs["protocol_headers"]) == {
            "First Name", "Social Security Number"
        }
        return {
            "ai_invoked": True,
            "ai_status": "completed",
            "ai_recommendation": kwargs[
                "deterministic_recommendation"
            ],
            "ai_confidence": 0.91,
        }

    namespace["should_invoke_ai"] = fake_should_invoke_ai
    namespace["resolve_header_with_ai"] = (
        fake_resolve_header_with_ai
    )

    exec(
        compile(module, "<json-identification-complete>", "exec"),
        namespace,
    )

    result = namespace["identify_cyber2_header_set"](
        workspace="capture",
        header_set_id="HDRSET-SYNTHETIC",
        client="ClientA",
        project="ProjectA",
        ai_suggestions=ai_enabled,
        admin=object(),
    )

    assert result["status"] == "completed"
    assert result["completed_document_count"] == document_count
    assert result["error_document_count"] == 0
    assert preview_calls == doc_ids

    # Both existing durable metadata writes must occur.
    assert len(writes) == 2
    assert all(
        item.get("overwrite") is True
        for item in writes
    )

    identification_writes = [
        item for item in writes
        if item["blob_path"].endswith("/identification.json")
    ]

    assert len(identification_writes) == 1

    saved = identification_writes[0]["payload"]

    assert saved["status"] == "completed"
    assert saved["document_count"] == document_count
    assert saved["schema_group_count"] == expected_groups
    assert len(saved["schema_groups"]) == expected_groups
    assert len(saved["documents"]) == document_count

    for document in saved["documents"]:
        assert document["source_kind"] == "native_json"
        assert document["source_sha256"] == "a" * 64
        assert document["source_csv_path"] == ""
        assert document["ai_invoked_column_count"] == (
            len(document["columns"]) if ai_enabled else 0
        )
        assert all(
            bool(c.get("ai_invoked")) is ai_enabled
            for c in document["columns"]
        )
        assert document["identification_status"] == "COMPLETED"
        assert document["columns"]
        assert document["structural_fields"]
        assert all(
            column["json_kind"] == "scalar"
            for column in document["columns"]
        )
        assert all(
            column["approved"] is False
            for column in document["columns"]
        )

    manifest_writes = [
        item for item in writes
        if item["blob_path"].endswith(
            "/header_sets/HDRSET-SYNTHETIC.json"
        )
    ]

    assert len(manifest_writes) == 1

    saved_manifest = manifest_writes[0]["payload"]

    assert saved_manifest["status"] == (
        "header_identification_complete"
    )
    assert saved_manifest["header_identification_path"] == (
        identification_writes[0]["blob_path"]
    )

    assert not any(
        item["blob_path"].endswith(".csv")
        for item in writes
    )

# STEP 554: NATIVE JSON ASSIGNMENT GUARD

def test_runtime_assigned_json_cannot_create_duplicate_header_set():
    result, effects, error = _exercise_creation(
        kind="native_json",
        assigned=True,
    )

    assert result is None
    assert error is not None
    assert error.status_code == 409
    assert effects["writes"] == []
    assert error.detail["existing_assignments"] == [{
        "doc_id": "TEST0001",
        "header_set_id": "HDRSET-EXISTING",
    }]


def test_runtime_existing_csv_assignment_behavior_unchanged():
    result, effects, error = _exercise_creation(
        kind="csv",
        assigned=True,
    )

    assert error is None
    assert result["status"] == "created"
    assert result["documents"][0]["source_kind"] == "csv"

# STEP 556: APPROVED JSON PROVENANCE

def _approval_provenance_values(
    dictionary_name,
    source,
):
    import ast
    import copy

    tree = read_tree("schema_mapping.py")
    route = find_function(
        tree,
        "approve_cyber2_header_mapping",
    )

    matches = [
        call.args[0]
        for call in ast.walk(route)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == dictionary_name
        and call.func.attr == "append"
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Dict)
    ]

    assert len(matches) == 1

    dictionary = matches[0]
    values = {}

    for key, expression in zip(
        dictionary.keys,
        dictionary.values,
    ):
        assert isinstance(key, ast.Constant)

        if key.value not in {
            "json_pointer",
            "json_kind",
            "json_field_path",
            "source_kind",
            "source_native_path",
            "source_sha256",
            "source_bytes",
            "source_format",
            "source_profile",
        }:
            continue

        isolated = ast.fix_missing_locations(
            ast.Expression(
                body=copy.deepcopy(expression)
            )
        )

        values[key.value] = eval(
            compile(
                isolated,
                "<approved-source-provenance>",
                "eval",
            ),
            {},
            {
                "identified_column": source,
                "identified_document": source,
            },
        )

    return values


def test_approved_native_json_document_preserves_source_identity():
    original = {
        "source_kind": "native_json",
        "source_native_path": (
            "capture/ClientA/ProjectA/source/native/"
            "TEST0001.json"
        ),
        "source_sha256": "a" * 64,
        "source_bytes": 1024,
        "source_format": "json",
        "source_profile": "plain",
    }

    result = _approval_provenance_values(
        "approved_documents",
        original,
    )

    assert result == original


def test_approved_json_column_preserves_exact_pointer():
    original = {
        "json_pointer": "/employee/first~1last",
        "json_kind": "scalar",
        "json_field_path": "employee.first/last",
    }

    result = _approval_provenance_values(
        "approved_columns",
        original,
    )

    assert result == original


def test_legacy_csv_approval_source_defaults_remain():
    result = _approval_provenance_values(
        "approved_documents",
        {
            "doc_id": "TESTCSV1",
            "source_csv_path": "synthetic.csv",
        },
    )

    assert result["source_kind"] == "csv"
    assert result["source_native_path"] == ""
    assert result["source_sha256"] == ""
    assert result["source_bytes"] is None


def test_approval_provenance_is_from_identification_not_request():
    tree = read_tree("schema_mapping.py")
    route = find_function(
        tree,
        "approve_cyber2_header_mapping",
    )

    relevant_keys = {
        "json_pointer",
        "source_native_path",
        "source_sha256",
    }

    found = {}

    for node in ast.walk(route):
        if not isinstance(node, ast.Dict):
            continue

        for key, expression in zip(
            node.keys,
            node.values,
        ):
            if (
                isinstance(key, ast.Constant)
                and key.value in relevant_keys
            ):
                found[key.value] = ast.unparse(expression)

    assert set(found) == relevant_keys
    assert "identified_column" in found["json_pointer"]
    assert "identified_document" in found["source_native_path"]
    assert "identified_document" in found["source_sha256"]
    assert all(
        "request." not in value
        for value in found.values()
    )
