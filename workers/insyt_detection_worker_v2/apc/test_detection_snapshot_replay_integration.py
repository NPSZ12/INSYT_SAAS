import ast
from pathlib import Path

from apc import detection_job_runner as runner
from apc.detection_publication_guard import (
    publish_detection_once,
)


def test_guard_supports_claim_aware_publisher():
    class Claim:
        def __init__(self):
            self.released = False
            self.lease = None

        def assert_active(self):
            pass

        def renew(self):
            pass

        def publish_completion(self, payload):
            self.saved = payload

        def release(self):
            self.released = True

    class Blob:
        def download_blob(self):
            return self

        def readall(self):
            return b""

    class Store:
        lease_seconds = 60

        def try_acquire(self, checkpoint):
            claim = Claim()
            claim.blob = Blob()
            self.claim = claim
            return claim

    store = Store()
    observed = []

    def publisher(claim):
        observed.append(claim)
        return {
            "status": "completed",
            "detection_job_id": "DET-SYNTHETIC",
        }

    result = publish_detection_once(
        detection_job_id="DET-SYNTHETIC",
        claim_store=store,
        publish_results=lambda: (_ for _ in ()).throw(
            AssertionError("Wrong publisher")
        ),
        publish_results_with_claim=publisher,
    )

    assert result["status"] == "completed"
    assert observed == [store.claim]
    assert store.claim.released


def test_runner_replays_snapshot_under_claim():
    tree = ast.parse(
        Path(runner.__file__).read_text(
            encoding="utf-8-sig"
        )
    )

    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "run_data_element_detection_job"
    )

    helpers = [
        node for node in function.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_publish_snapshot_and_replay"
    ]

    assert len(helpers) == 1

    helper = helpers[0]

    names = {
        node.func.id
        for node in ast.walk(helper)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
    }

    assert "load_or_create_publication_snapshot" in names
    assert "_write_processing_json" in names
    assert "_publish_final_results" in names

    guards = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "publish_detection_once"
    ]

    assert len(guards) == 1

    keywords = {
        kw.arg: kw.value
        for kw in guards[0].keywords
    }

    callback = keywords["publish_results_with_claim"]

    assert isinstance(callback, ast.Name)
    assert callback.id == "_publish_snapshot_and_replay"