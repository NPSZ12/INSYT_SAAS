"""Preserve separate JSON source fields in protocol-approved CSV columns.

Duplicate destination headers are suffixed _2, _3, etc.
No CSV generation, storage mutation, or automatic concatenation.
"""

class DuplicateHeaderError(ValueError):
    pass


def assign_json_output_headers(decisions, protocol_headers):
    if not isinstance(decisions, list):
        raise DuplicateHeaderError("Invalid mapping decisions.")

    if not isinstance(protocol_headers, list) or not protocol_headers:
        raise DuplicateHeaderError("Approved protocol required.")

    approved = {}
    reserved = set()

    for header in protocol_headers:
        if not isinstance(header, str) or not header.strip():
            raise DuplicateHeaderError("Invalid protocol header.")

        name = header.strip()
        key = name.casefold()

        if key in reserved:
            raise DuplicateHeaderError("Duplicate protocol header.")

        approved[key] = name
        reserved.add(key)

    assigned = set()
    seen_sources = set()
    output = []

    for decision in decisions:
        if not isinstance(decision, dict):
            raise DuplicateHeaderError("Invalid decision.")

        if decision.get("reviewed") is not True:
            raise DuplicateHeaderError(
                "All supplied decisions must be reviewed."
            )

        pointer = decision.get("json_pointer")

        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise DuplicateHeaderError("Invalid JSON source pointer.")

        if pointer in seen_sources:
            raise DuplicateHeaderError(
                "One JSON source path cannot be mapped twice."
            )

        seen_sources.add(pointer)

        action = decision.get("action")
        treatment = decision.get("treatment")

        if action == "discard" or treatment == "discard":
            continue

        if action not in {"approve", "keep", "map"}:
            raise DuplicateHeaderError("Invalid mapping action.")

        if treatment not in {
            "text",
            "concatenate",
            "mask",
            "yes_if_present",
            "maximum",
            "latest",
        }:
            raise DuplicateHeaderError("Invalid data treatment.")

        requested = decision.get("header")

        if not isinstance(requested, str):
            raise DuplicateHeaderError(
                "Missing approved protocol header."
            )

        base = approved.get(requested.strip().casefold())

        if base is None:
            raise DuplicateHeaderError(
                "Output header is not in the approved protocol."
            )

        candidate = base
        counter = 2

        # Protect both already-assigned output names and
        # independently approved protocol headers.
        while (
            candidate.casefold() in assigned
            or (
                candidate != base
                and candidate.casefold() in reserved
            )
        ):
            candidate = f"{base}_{counter}"
            counter += 1

        assigned.add(candidate.casefold())

        output.append({
            "json_pointer": pointer,
            "protocol_header": base,
            "output_header": candidate,
            "data_treatment": treatment,
            "source_order": len(output),
        })

    return {
        "columns": output,
        "output_headers": [
            item["output_header"] for item in output
        ],
        "column_count": len(output),
        "csv_generated": False,
    }