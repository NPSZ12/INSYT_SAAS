#!/usr/bin/env python3
"""INSYT production deployment authorization.

Permanent entry point for all production deployments.

Fail closed until independently protected source approval
and exact-commit GitHub CI attestation are both implemented.

Never authorize a release from an environment variable,
a command-line bypass, or a file supplied by the
candidate deployment branch alone.
"""

import argparse
import os
import re
import sys


def stop(message):
    print("STOP:", message, file=sys.stderr)
    raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--component",
        choices=("api", "frontend"),
        required=True,
    )
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()

    if os.getenv("GITHUB_ACTIONS") != "true":
        stop("Deployment gate must run in GitHub Actions.")

    if os.getenv("GITHUB_REPOSITORY") != "NPSZ12/INSYT_SAAS":
        stop("Unexpected GitHub repository.")

    if os.getenv("GITHUB_REF") != (
        "refs/heads/release/json-promotion-20261119"
    ):
        stop("Unauthorized deployment branch.")

    sha = args.sha.lower()

    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        stop("Full Git commit SHA required.")

    if os.getenv("GITHUB_SHA", "").lower() != sha:
        stop("Deployment commit does not match GitHub checkout.")

    # DENY BY DEFAULT.
    #
    # This checkpoint must be replaced with a verified,
    # independently trusted exact-source approval AND
    # successful exact-commit CI attestation.
    #
    # No environment-variable approval overrides.
    # No temporary developer bypass.
    stop(
        "Independent release approval is not installed. "
        "Production deployment denied."
    )


if __name__ == "__main__":
    main()
