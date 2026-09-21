from __future__ import annotations

from .base import (
    AdapterContext,
    AdapterResult,
)
from .registry import get_adapter


def dispatch_to_adapter(
    context: AdapterContext,
) -> AdapterResult | None:
    """
    Route a file to its registered type-specific adapter.

    Returns:
        AdapterResult
            when a registered adapter handles the file.

        None
            when no special adapter exists and the file
            should continue through normal APC processing.

    This function does not register adapters and does
    not modify the APC pipeline. It only performs routing.
    """

    adapter = get_adapter(
        extension=context.extension,
        path=context.source_path,
    )

    if adapter is None:
        return None

    return adapter.process(
        context
    )