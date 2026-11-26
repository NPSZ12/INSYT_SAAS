"""Reusable exact application release transition validation.

Source validation only. Does not approve, sign, publish or deploy.
"""

import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

SHA40 = re.compile(r"^[0-9a-f]{40}$")

COMPONENT_ROOTS = {
    "api": "backend/",
    "frontend": "frontend/",
}

PROTECTED_FILES = frozenset({
    "backend/app/api/auth.py",
    "backend/app/services/security.py",
    "backend/app/main.py",
    "backend/app/database/connection.py",
    "backend/app/database/init_db.py",
    "backend/requirements.txt",
    "frontend/package.json",
    "frontend/package-lock.json",
})

PROTECTED_PREFIXES = (
    "backend/app/api/auth/",
    "backend/app/services/auth/",
    "backend/app/database/",
    "frontend/src/app/auth/",
    "frontend/src/app/login/",
    "frontend/src/app/mfa/",
)

PROTECTED_NAMES = re.compile(
    r"(^|[/_.-])(auth|authentication|authorization|"
    r"entra|mfa|security|credentials|secrets)"
    r"([/_.-]|$)",
    re.IGNORECASE,
)


class TransitionDenied(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise TransitionDenied("STOP: " + message)


def git(*args):
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
    )

    require(
        result.returncode == 0,
        "Git transition verification failed",
    )

    return result.stdout


def revision(value):
    require(
        isinstance(value, str)
        and SHA40.fullmatch(value),
        "Invalid commit identity",
    )

    resolved = git(
        "rev-parse", "--verify", value + "^{commit}"
    ).decode().strip()

    require(
        resolved == value,
        "Commit identity mismatch",
    )

    return resolved


def changed_paths(baseline, candidate):

    raw = git(
        "diff",
        "--name-status",
        "-z",
        "--no-renames",
        baseline,
        candidate,
        "--",
    )

    tokens = raw.decode("utf-8").split("\0")

    if tokens[-1] == "":
        tokens.pop()

    require(
        len(tokens) % 2 == 0,
        "Invalid Git change inventory",
    )

    changes = {}

    for index in range(0, len(tokens), 2):

        status, path = tokens[index:index + 2]

        require(
            path not in changes,
            "Duplicate changed path",
        )

        changes[path] = status

    return changes


def validate_path(path, status):

    require(
        isinstance(path, str)
        and bool(path)
        and not path.startswith("/")
        and "\\" not in path
        and all(
            part not in {"", ".", ".."}
            for part in path.split("/")
        )
        and not any(ord(ch) < 32 for ch in path),
        "Unsafe application source path",
    )

    require(
        status in {"A", "M"},
        "Ordinary upgrades cannot delete or replace file types",
    )

    require(
        path not in PROTECTED_FILES
        and not path.startswith(PROTECTED_PREFIXES)
        and not PROTECTED_NAMES.search(path),
        "Protected source requires separate authorization: " + path,
    )

    name = PurePosixPath(path).name.casefold()

    require(
        not name.startswith((
            "requirements",
            "dockerfile",
            ".env",
        ))
        and name not in {
            "pyproject.toml",
            "poetry.lock",
            "uv.lock",
            "pnpm-lock.yaml",
            "yarn.lock",
            "next.config.ts",
            "next.config.js",
            "next.config.mjs",
            "middleware.ts",
            "middleware.js",
            "proxy.ts",
            "proxy.js",
            ".npmrc",
            ".gitmodules",
        },
        "Dependency or runtime configuration requires separate review",
    )

    matches = [
        component
        for component, root in COMPONENT_ROOTS.items()
        if path.startswith(root)
    ]

    require(
        len(matches) == 1,
        "Non-application source requires separate authorization: " + path,
    )

    return matches[0]


def source_blob(commit, path):

    entry = git(
        "ls-tree", "-z", commit, "--", path
    )

    records = [
        record for record in entry.split(b"\0")
        if record
    ]

    require(
        len(records) == 1,
        "Source tree entry missing: " + path,
    )

    metadata, filename = records[0].split(b"\t", 1)
    mode, kind, blob = metadata.decode().split()

    require(
        filename.decode("utf-8") == path
        and mode == "100644"
        and kind == "blob"
        and SHA40.fullmatch(blob),
        "Unexpected source file type: " + path,
    )

    return blob


def inspect_transition(baseline, candidate):

    revision(baseline)
    revision(candidate)

    require(
        baseline != candidate,
        "Release candidate equals baseline",
    )

    git("merge-base", "--is-ancestor", baseline, candidate)

    changes = changed_paths(baseline, candidate)

    require(
        bool(changes),
        "Empty application upgrade",
    )

    components = {
        component: {
            "baseline": baseline,
            "root": root,
            "changes": {},
        }
        for component, root in COMPONENT_ROOTS.items()
    }

    blobs = {}

    for path, status in sorted(changes.items()):

        component = validate_path(path, status)

        blobs[path] = source_blob(candidate, path)

        if status == "M":
            source_blob(baseline, path)

        components[component]["changes"][path] = status

    return {
        "baseline": baseline,
        "candidate_commit": candidate,
        "components": components,
        "source_blobs": blobs,
    }


def verify_transition(baseline, candidate, proposed):

    observed = inspect_transition(
        baseline,
        candidate,
    )

    require(
        observed == proposed,
        "Proposed application transition differs from Git evidence",
    )

    return observed
