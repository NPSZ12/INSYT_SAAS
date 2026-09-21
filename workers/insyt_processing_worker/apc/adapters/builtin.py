from __future__ import annotations

from .email.eml_adapter import EML_ADAPTER
from .email.pst_adapter import PstAdapter
from .email.readpst_backend import ReadPstBackend
from .registry import register_adapter


PST_ADAPTER = PstAdapter(
    backend=ReadPstBackend()
)


#
# Every INSYT file-type adapter will eventually be
# listed here.
#
# Adding a new file type should require adding its
# adapter to this tuple, rather than modifying the
# shared APC ingestion logic.
#
BUILTIN_ADAPTERS = (
    EML_ADAPTER,
    PST_ADAPTER,
)


def register_builtin_adapters() -> None:
    """
    Register all INSYT built-in file adapters.

    This function has no production effect unless it
    is explicitly called by the dispatcher/bootstrap.
    """

    for adapter in BUILTIN_ADAPTERS:
        register_adapter(
            adapter
        )