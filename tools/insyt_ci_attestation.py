#!/usr/bin/env python3
"""Read-only GitHub Actions validation attestation.

This is ONE release prerequisite. It does not grant
deployment approval or substitute for trusted branch rules.
"""

import argparse
import json
import re
import subprocess
import sys

REPO = "NPSZ12/INSYT_SAAS"
WORKFLOW_PATH = ".github/workflows/insyt-release-validation.yml"

REQUIRED_JOBS = {
    "Protected Source Integrity",
    "API Startup and JSON Regressions",
    "Frontend Build Validation",
}


def stop(message):
    print("STOP:", message, file=sys.stderr)
    raise SystemExit(2)


def gh_api(path):
    result = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        stop("GitHub API request failed.")

    try:
        return json.loads(result.stdout)
    except ValueError:
        stop("GitHub returned invalid JSON.")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--sha",
        required=True,
        help="Full 40-character release commit SHA",
    )

    args = parser.parse_args()
    sha = args.sha.lower()

    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        stop("Full 40-character commit SHA required.")

    workflow = gh_api(
        f"repos/{REPO}/actions/workflows/"
        "insyt-release-validation.yml"
    )

    if workflow.get("path") != WORKFLOW_PATH:
        stop("Unexpected validation workflow identity.")

    workflow_id = workflow.get("id")

    if not isinstance(workflow_id, int):
        stop("Workflow ID missing.")

    runs = gh_api(
        f"repos/{REPO}/actions/workflows/{workflow_id}/runs"
        f"?head_sha={sha}&per_page=100"
    ).get("workflow_runs", [])

    matches = [
        run
        for run in runs
        if run.get("head_sha", "").lower() == sha
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("event") in ("pull_request", "push")
    ]

    if not matches:
        stop("No successful validation run for exact SHA.")

    for run in matches:
        run_id = run.get("id")

        jobs = gh_api(
            f"repos/{REPO}/actions/runs/"
            f"{run_id}/jobs?per_page=100"
        )

        if jobs.get("total_count", 0) > 100:
            stop("Job result pagination not implemented.")

        observed = {}

        for job in jobs.get("jobs", []):
            name = job.get("name")

            if name in REQUIRED_JOBS:
                if name in observed:
                    stop("Duplicate required CI job.")

                observed[name] = job

        if set(observed) != REQUIRED_JOBS:
            continue

        if all(
            job.get("status") == "completed"
            and job.get("conclusion") == "success"
            for job in observed.values()
        ):
            print("PASS: Exact Git commit:", sha)
            print("PASS: Trusted workflow path:", WORKFLOW_PATH)
            print("PASS: All three validation jobs succeeded.")
            print("PASS: GitHub Actions run:", run_id)
            print("NOTE: Independent release approval still required.")
            return

    stop("Required validation jobs did not all pass.")


if __name__ == "__main__":
    main()
