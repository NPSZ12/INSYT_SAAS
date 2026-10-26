from __future__ import annotations

import json
import os
import sys


def main() -> int:
    # The subprocess is isolated from the APC job database
    # and performs read-only PDF structural inspection.
    if len(sys.argv) != 2:
        return 2

    try:
        if os.name == "posix":
            import resource

            cpu = max(
                2,
                int(os.getenv(
                    "INSYT_PDF_PROBE_CPU_SECONDS", "15"
                )),
            )
            memory_mb = max(
                256,
                int(os.getenv(
                    "INSYT_PDF_PROBE_MEMORY_MB", "1024"
                )),
            )

            resource.setrlimit(
                resource.RLIMIT_CPU,
                (cpu, cpu + 2),
            )
            resource.setrlimit(
                resource.RLIMIT_AS,
                (
                    memory_mb * 1024 * 1024,
                    memory_mb * 1024 * 1024,
                ),
            )

        from pypdf import PdfReader

        reader = PdfReader(sys.argv[1], strict=False)
        encrypted = bool(reader.is_encrypted)

        pages = None if encrypted else len(reader.pages)

        if not encrypted and pages <= 0:
            raise ValueError("PDF has no readable pages")

        result = {
            "status": "encrypted" if encrypted else "validated",
            "encrypted": encrypted,
            "pages": pages,
        }

    except ImportError:
        result = {"status": "parser_unavailable"}

    except Exception as exc:
        result = {
            "status": "failed",
            "error_type": type(exc).__name__,
        }

    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
