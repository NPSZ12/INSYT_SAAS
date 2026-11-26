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

    # Execute the complete validator dependency chain from
    # the protected policy base, never from proposed source.

    modules = (
        "insyt_release_transition.py",
        "insyt_protected_source.py",
        "insyt_new_scope_validation.py",
        "insyt_policy_renewal.py",
    )

    with tempfile.TemporaryDirectory(
        prefix="insyt-trusted-policy-"
    ) as folder:

        trusted = Path(folder)

        for name in modules:

            path = "tools/" + name

            original = git("show", base + ":" + path)
            proposed = git("show", target + ":" + path)

            require(
                original == proposed,
                "Trusted validator modification prohibited: "
                + path,
            )

            (trusted / name).write_bytes(original)

        # Each module derives ROOT from its source location.
        # Bind Git operations to the actual repository while
        # keeping Python imports isolated from candidate files.

        runner = trusted / "trusted_runner.py"

        runner.write_text(
            """
import sys
from pathlib import Path

trusted = Path(__file__).resolve().parent
sys.path.insert(0, str(trusted))

import insyt_release_transition as transition
import insyt_protected_source as protected
import insyt_new_scope_validation as scope
import insyt_policy_renewal as renewal

root = Path(sys.argv[1]).resolve()

transition.ROOT = root
renewal.ROOT = root

for module in (transition, protected, scope, renewal):
    if Path(module.__file__).resolve().parent != trusted:
        raise SystemExit("STOP: Untrusted validator import")

renewal.validate_renewal(
    sys.argv[2],
    sys.argv[3],
    sys.argv[4],
)
""",
            encoding="utf-8",
        )

        import sys

        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)

        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                str(runner),
                str(ROOT),
                base,
                target,
                release,
            ],
            cwd=trusted,
            env=environment,
        )

        require(
            result.returncode == 0,
            "Trusted policy validation failed",
        )

    print(
        "PASS: Complete validator chain executed "
        "from protected policy base"
    )


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
