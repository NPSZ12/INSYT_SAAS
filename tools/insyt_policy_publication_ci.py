"""INSYT policy publication CI.

Validate policy transitions without granting deployment authority.
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

POLICY_BRANCH = "policy/insyt-hardened"
RELEASE_REF = "refs/remotes/origin/release/json-promotion-20261119"
VALIDATOR = "tools/insyt_policy_renewal.py"

SHA = re.compile(r"^[0-9a-f]{40}$")


def require(condition, message):
    if not condition:
        raise SystemExit("STOP: " + message)


def git(*args, env=None):
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
    )

    require(result.returncode == 0, "Git verification failed")

    return result.stdout


def revision(ref):
    value = git("rev-parse", "--verify", ref).decode().strip()
    require(SHA.fullmatch(value), "Invalid Git revision")
    return value


def load_trusted_context():
    require(
        os.environ.get("GITHUB_ACTIONS") == "true",
        "GitHub Actions context required",
    )

    require(
        os.environ.get("GITHUB_EVENT_NAME") == "pull_request",
        "Pull request context required",
    )

    require(
        os.environ.get("GITHUB_REPOSITORY") == "NPSZ12/INSYT_SAAS",
        "Unexpected repository",
    )

    event = json.loads(
        Path(os.environ["GITHUB_EVENT_PATH"]).read_text(
            encoding="utf-8"
        )
    )

    pr = event["pull_request"]

    require(
        pr["base"]["ref"] == POLICY_BRANCH,
        "Unexpected policy target",
    )

    require(
        pr["base"]["repo"]["full_name"] == "NPSZ12/INSYT_SAAS",
        "Unexpected policy repository",
    )

    base = pr["base"]["sha"]
    proposed = pr["head"]["sha"]

    require(
        SHA.fullmatch(base) and SHA.fullmatch(proposed),
        "Invalid pull request identities",
    )

    require(
        revision("refs/remotes/origin/" + POLICY_BRANCH) == base,
        "Policy base changed",
    )

    git("merge-base", "--is-ancestor", base, proposed)

    target = revision("HEAD")

    require(
        target == os.environ.get("GITHUB_SHA"),
        "Checkout differs from CI revision",
    )

    git("merge-base", "--is-ancestor", base, target)
    git("merge-base", "--is-ancestor", proposed, target)

    require(
        revision(target + "^{tree}") ==
        revision(proposed + "^{tree}"),
        "Unexpected merged policy content",
    )

    return base, target, revision(RELEASE_REF)


def validate_installed_renewal(base, target, release):
    trusted_source = git("show", base + ":" + VALIDATOR)

    require(
        git("show", target + ":" + VALIDATOR) == trusted_source,
        "Renewal validator modification prohibited",
    )

    namespace = {
        "__name__": "trusted_policy_renewal",
        "__file__": str(ROOT / VALIDATOR),
    }

    exec(
        compile(
            trusted_source.decode("utf-8-sig"),
            VALIDATOR,
            "exec",
        ),
        namespace,
    )

    namespace["validate_renewal"](base, target, release)

    print("PASS: Validator executed from protected policy base")


def validate_bootstrap(base, target, release):
    """Validate the explicitly reviewed first installation."""

    require(
        base == "d65ad75fb0ccaabea9ddc9cdc056b06446cc1a10",
        "Unexpected bootstrap policy base",
    )

    require(
        release == "f60598571badd4b1d52cc9c607e75a26bbd45fb4",
        "Unexpected bootstrap release",
    )

    reviewed = {
        "tools/insyt_policy_renewal.py":
            "5982e67dc6a0517a7b4a75f0076290711971d3da",
        "tools/test_insyt_policy_renewal.py":
            "cf135bffdf476b22bf4d26c82e1010fe1ae9ecac",
    }

    for path, expected in reviewed.items():
        require(
            revision(target + ":" + path) == expected,
            "Reviewed installation file differs: " + path,
        )

    signed_proposal = "2a661c5c349b061bd6ad4e13d5dcfd1c43a8518d"

    git("merge-base", "--is-ancestor", signed_proposal, target)

    changes = git(
        "diff", "--name-only", signed_proposal, target, "--"
    ).decode().splitlines()

    require(
        set(changes) == {
            ".github/workflows/insyt-release-validation.yml",
            "tools/insyt_policy_publication_ci.py",
        },
        "Unexpected bootstrap integration changes",
    )

    # Use the reviewed validator to verify the signed renewal
    # independently of the security installation files.

    namespace = {
        "__name__": "reviewed_bootstrap_validator",
        "__file__": str(ROOT / VALIDATOR),
    }

    exec(
        compile(
            git("show", target + ":" + VALIDATOR)
                .decode("utf-8-sig"),
            VALIDATOR,
            "exec",
        ),
        namespace,
    )

    archive = (
        ".github/insyt-release/approval-history/"
        "INSYT-JSON-039D5A740525.json"
    )

    original_proposal = "d9ccfb7c5bcb737cca252b14f5713b09a1fd52dc"

    with tempfile.TemporaryDirectory() as folder:

        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(
            Path(folder) / "bootstrap.index"
        )

        git("read-tree", original_proposal, env=env)

        blob = revision(target + ":" + archive)

        git(
            "update-index", "--add", "--cacheinfo",
            "100644," + blob + "," + archive,
            env=env,
        )

        tree = git("write-tree", env=env).decode().strip()

        env["GIT_AUTHOR_NAME"] = "INSYT Policy Validation"
        env["GIT_AUTHOR_EMAIL"] = "validation@example.invalid"
        env["GIT_COMMITTER_NAME"] = "INSYT Policy Validation"
        env["GIT_COMMITTER_EMAIL"] = "validation@example.invalid"

        isolated = git(
            "commit-tree", tree,
            "-p", original_proposal,
            "-m", "Isolated signed policy validation",
            env=env,
        ).decode().strip()

        namespace["validate_renewal"](base, isolated, release)

    print("PASS: Reviewed bootstrap source identities")
    print("PASS: Existing signed policy renewal")
    print("PASS: Original signed ancestry preserved")
    print("BOOTSTRAP VALIDATION ONLY - INDEPENDENT REVIEW REQUIRED")


def main():
    base, target, release = load_trusted_context()

    result = subprocess.run(
        ["git", "cat-file", "-e", base + ":" + VALIDATOR],
        cwd=ROOT,
        capture_output=True,
    )

    if result.returncode != 0:
        validate_bootstrap(base, target, release)
        return

    validate_installed_renewal(base, target, release)

    print("PASS: Protected-base policy publication verified")
    print("POLICY VALIDATION ONLY - NOT DEPLOYMENT AUTHORIZATION")


if __name__ == "__main__":
    main()
