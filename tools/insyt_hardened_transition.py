"""INSYT append-only hardened history validation.

Validates history integrity; does not authenticate the origin
of approvals and does not authorize production deployment.
"""

import re

SHA = re.compile(r"^[0-9a-f]{40}$")


class TransitionDenied(Exception):
    pass


def deny(message):
    raise TransitionDenied("STOP: " + message)


def validate_history(baseline, previous, proposed):
    """Require preservation of all baseline and previous versions.

    History schema:
    {
      "schema_version": 1,
      "features": {
        "feature-id": {
          "versions": [
            {"version": 1, "source": {"file/path": "git-blob-sha"}},
            {"version": 2, "source": {"file/path": "git-blob-sha"}}
          ]
        }
      }
    }

    This structure tracks immutable source identities.
    Functional contracts and test requirements are separate
    mandatory controls in the final policy architecture.
    """

    for label, obj in (
        ("previous", previous),
        ("proposed", proposed),
    ):
        if not isinstance(obj, dict):
            deny(label + " history must be an object")

        if obj.get("schema_version") != 1:
            deny(label + " history schema mismatch")

        features = obj.get("features")

        if not isinstance(features, dict):
            deny(label + " features missing")

    prior = previous["features"]
    future = proposed["features"]

    if not set(prior).issubset(future):
        deny("Previously hardened feature removed")

    for feature, record in future.items():
        if not isinstance(feature, str) or not feature:
            deny("Invalid feature identifier")

        if not isinstance(record, dict):
            deny("Invalid feature record")

        versions = record.get("versions")

        if not isinstance(versions, list) or not versions:
            deny("Missing version history: " + feature)

        for index, version in enumerate(versions, 1):
            if not isinstance(version, dict):
                deny("Invalid version record: " + feature)

            if version.get("version") != index:
                deny("Nonsequential version: " + feature)

            source = version.get("source")

            if not isinstance(source, dict) or not source:
                deny("Missing source inventory: " + feature)

            for path, blob in source.items():
                if (
                    not isinstance(path, str)
                    or not path
                    or path.startswith("/")
                    or "\\" in path
                    or ".." in path.split("/")
                ):
                    deny("Unsafe source path")

                if not isinstance(blob, str) or not SHA.fullmatch(blob):
                    deny("Invalid source blob: " + path)

    for feature, record in prior.items():
        old_versions = record.get("versions")
        new_versions = future[feature].get("versions")

        if not isinstance(old_versions, list):
            deny("Invalid previous history")

        if len(new_versions) < len(old_versions):
            deny("Hardened version deleted: " + feature)

        if new_versions[:len(old_versions)] != old_versions:
            deny("Historical version rewritten: " + feature)

    if not isinstance(baseline, dict) or not baseline:
        deny("Original hardened baseline missing")

    for path, blob in baseline.items():
        if not isinstance(blob, str) or not SHA.fullmatch(blob):
            deny("Invalid historical baseline blob")

        located = False

        for record in future.values():
            for version in record["versions"]:
                if version["version"] == 1:
                    if version["source"].get(path) == blob:
                        located = True
                        break
            if located:
                break

        if not located:
            deny("Original hardened source history missing: " + path)

    return True
