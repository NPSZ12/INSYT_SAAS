from __future__ import annotations

import os
import shutil
import subprocess
import tempfile


from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Iterable

from .pst_backend import (
    PstBackend,
    PstMessage,
)


class ReadPstBackend:
    """
    PST backend using the Linux readpst utility.

    readpst performs only PST/mailbox extraction.

    Each exported RFC822 EML is then returned to the normal
    INSYT PST -> EML -> APC adapter chain.
    """

    name = "readpst"

    def __init__(
        self,
        executable: str = "readpst",
    ):
        self.executable = executable

    def iter_messages(
        self,
        pst_path: Path,
    ) -> Iterable[PstMessage]:
        executable, runtime_env = (
            self._prepare_runtime()
        )

        if (
            not pst_path.exists()
            or not pst_path.is_file()
        ):
            raise RuntimeError(
                f"PST file does not exist: {pst_path}"
            )

        with tempfile.TemporaryDirectory(
            prefix="insyt_readpst_"
        ) as temp_root:
            output_dir = (
                Path(temp_root)
                / "export"
            )

            output_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            command = [
                executable,

                #
                # Separate messages with file extensions.
                #
                "-e",

                #
                # Prefer UTF-8 bodies.
                #
                "-8",

                #
                # Email items only for this adapter.
                #
                "-t",
                "e",

                #
                # Keep initial processing deterministic.
                # We can increase this later.
                #
                "-j",
                "1",

                #
                # Quiet except errors.
                #
                "-q",

                "-o",
                str(output_dir),

                str(pst_path),
            ]

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                env=runtime_env,
            )

            if completed.returncode != 0:
                raise RuntimeError(
                    "readpst failed with exit code "
                    f"{completed.returncode}: "
                    f"{completed.stderr.strip()}"
                )

            yield from (
                self._iter_exported_messages(
                    output_dir
                )
            )

    def _iter_exported_messages(
        self,
        output_dir: Path,
    ) -> Iterable[PstMessage]:
        """
        Convert readpst's exported EML tree into the
        backend-neutral PstMessage contract.
        """

        eml_paths = sorted(
            path
            for path in output_dir.rglob(
                "*.eml"
            )
            if path.is_file()
        )

        for eml_path in eml_paths:
            raw_eml = eml_path.read_bytes()

            try:
                message = BytesParser(
                    policy=policy.default
                ).parsebytes(
                    raw_eml
                )

            except Exception as exc:
                raise RuntimeError(
                    "Unable to parse readpst EML output: "
                    f"{eml_path}: {exc}"
                ) from exc

            relative_parent = (
                eml_path.parent.relative_to(
                    output_dir
                )
            )

            folder_path = (
                relative_parent.as_posix()
            )

            if folder_path in {
                "",
                ".",
            }:
                folder_path = "Mailbox"

            yield PstMessage(
                folder_path=folder_path,

                source_name=(
                    eml_path.name
                ),

                raw_eml_bytes=raw_eml,

                message_id=self._header(
                    message,
                    "Message-ID",
                ),

                subject=self._header(
                    message,
                    "Subject",
                ),

                sender=self._header(
                    message,
                    "From",
                ),

                to=self._header(
                    message,
                    "To",
                ),

                cc=self._header(
                    message,
                    "Cc",
                ),

                bcc=self._header(
                    message,
                    "Bcc",
                ),

                sent_at=self._header(
                    message,
                    "Date",
                ),

                metadata={
                    "readpst_relative_path": (
                        eml_path
                        .relative_to(output_dir)
                        .as_posix()
                    ),
                    "readpst_folder_path": (
                        folder_path
                    ),
                },
            )

    def _prepare_runtime(
        self,
    ) -> tuple[str, dict[str, str]]:
        """
        Resolve readpst.

        Priority:
          1. explicit READPST_EXECUTABLE
          2. bundled INSYT Debian runtime
          3. system PATH

        Bundled native files are copied to /tmp before
        execution so ZIP/package deployment permissions
        cannot prevent execution.
        """

        environment = os.environ.copy()

        explicit = str(
            os.getenv(
                "READPST_EXECUTABLE",
                "",
            )
            or ""
        ).strip()

        if explicit:
            explicit_path = Path(
                explicit
            )

            if (
                explicit_path.exists()
                and explicit_path.is_file()
            ):
                return (
                    str(explicit_path),
                    environment,
                )

            raise RuntimeError(
                "READPST_EXECUTABLE does not "
                f"exist: {explicit_path}"
            )

        worker_root = (
            Path(__file__)
            .resolve()
            .parents[3]
        )

        bundled_root = (
            worker_root
            / "native"
            / "readpst"
        )

        bundled_executable = (
            bundled_root
            / "bin"
            / "readpst"
        )

        if bundled_executable.is_file():
            runtime_root = (
                Path(
                    tempfile.gettempdir()
                )
                / "insyt-readpst-runtime"
            )

            runtime_bin = (
                runtime_root
                / "bin"
            )

            runtime_lib = (
                runtime_root
                / "lib"
            )

            runtime_executable = (
                runtime_bin
                / "readpst"
            )

            runtime_bin.mkdir(
                parents=True,
                exist_ok=True,
            )

            runtime_lib.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                bundled_executable,
                runtime_executable,
            )

            runtime_executable.chmod(
                0o755
            )

            bundled_lib = (
                bundled_root
                / "lib"
            )

            if bundled_lib.is_dir():
                for source_library in (
                    bundled_lib.iterdir()
                ):
                    if not source_library.is_file():
                        continue

                    shutil.copy2(
                        source_library,
                        runtime_lib
                        / source_library.name,
                    )

            existing_library_path = (
                environment.get(
                    "LD_LIBRARY_PATH",
                    "",
                )
            )

            environment[
                "LD_LIBRARY_PATH"
            ] = (
                str(runtime_lib)
                if not existing_library_path
                else (
                    f"{runtime_lib}:"
                    f"{existing_library_path}"
                )
            )

            return (
                str(runtime_executable),
                environment,
            )

        system_executable = (
            shutil.which(
                self.executable
            )
        )

        if system_executable:
            return (
                system_executable,
                environment,
            )

        raise RuntimeError(
            "readpst runtime was not found. "
            "No READPST_EXECUTABLE was configured, "
            "no bundled runtime was deployed, and "
            "readpst is not available on PATH."
        )

    @staticmethod
    def _header(
        message,
        name: str,
    ) -> str:
        value = message.get(
            name
        )

        if value is None:
            return ""

        return str(
            value
        ).strip()