from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import FileAdapter


_ADAPTERS: dict[str, FileAdapter] = {}


def normalize_extension(
    extension: str | None,
) -> str:
    value = str(extension or "").strip().lower()

    if not value:
        return ""

    if not value.startswith("."):
        value = f".{value}"

    return value


def register_adapter(
    adapter: FileAdapter,
) -> None:
    """
    Register one adapter for each extension it handles.
    """

    for extension in adapter.extensions:
        normalized = normalize_extension(extension)

        if not normalized:
            continue

        existing = _ADAPTERS.get(normalized)

        #
        # Registering the exact same adapter more than once
        # is harmless. This lets adapter bootstrap remain
        # safely idempotent.
        #
        if existing is adapter:
            continue

        if existing is not None:
            raise ValueError(
                f"Adapter already registered for "
                f"{normalized}: {existing.name}"
            )

        _ADAPTERS[normalized] = adapter


def get_adapter(
    *,
    extension: str | None = None,
    path: str | Path | None = None,
) -> FileAdapter | None:
    """
    Resolve an adapter by normalized extension.

    Signature/MIME inspection can be added later without
    changing callers.
    """

    resolved_extension = normalize_extension(
        extension
    )

    if not resolved_extension and path:
        resolved_extension = normalize_extension(
            Path(path).suffix
        )

    if not resolved_extension:
        return None

    return _ADAPTERS.get(
        resolved_extension
    )


def registered_extensions() -> tuple[str, ...]:
    return tuple(
        sorted(_ADAPTERS.keys())
    )


def registered_adapters() -> dict[str, str]:
    return {
        extension: adapter.name
        for extension, adapter in sorted(
            _ADAPTERS.items()
        )
    }


def clear_registry_for_tests() -> None:
    """
    Test helper only.
    """

    _ADAPTERS.clear()