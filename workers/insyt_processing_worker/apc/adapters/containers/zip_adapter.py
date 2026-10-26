from __future__ import annotations

import re
import stat
import zipfile

from pathlib import Path, PurePosixPath

from ..base import AdapterContext, AdapterResult, PreparedChild


class ZipAdapter:
    name = "zip"
    extensions = (".zip",)

    MAX_MEMBERS = 10000
    MAX_MEMBER_BYTES = 2 * 1024**3
    MAX_TOTAL_BYTES = 10 * 1024**3
    MAX_RATIO = 1000

    def process(self, context: AdapterContext) -> AdapterResult:
        children = []
        errors = []
        total_bytes = 0
        seen = set()

        remaining_bytes = context.metadata.get(
            "zip_remaining_bytes"
        )
        remaining_files = context.metadata.get(
            "zip_remaining_files"
        )

        byte_limit = min(
            self.MAX_TOTAL_BYTES,
            max(0, int(remaining_bytes))
            if remaining_bytes is not None
            else self.MAX_TOTAL_BYTES,
        )
        file_limit = min(
            self.MAX_MEMBERS,
            max(0, int(remaining_files))
            if remaining_files is not None
            else self.MAX_MEMBERS,
        )

        root = Path(
            context.work_dir
            or context.source_path.parent / "_zip_extracted"
        ) / context.file_id

        def reject_path(name: str) -> PurePosixPath:
            if not name or "\x00" in name:
                raise ValueError("Invalid member name")

            name = name.replace("\\", "/")
            path = PurePosixPath(name)

            if (
                path.is_absolute()
                or not path.parts
                or any(p in (".", "..") for p in name.split("/"))
                or re.match(r"^[A-Za-z]:", name)
                or any(":" in p for p in path.parts)
            ):
                raise ValueError("Unsafe ZIP member path")

            return path

        try:
            with zipfile.ZipFile(context.source_path) as archive:
                members = archive.infolist()

                if len(members) > self.MAX_MEMBERS:
                    raise ValueError("ZIP member count exceeds limit")

                root.mkdir(parents=True, exist_ok=True)
                root = root.resolve(strict=True)

                for member in members:
                    if member.is_dir():
                        continue

                    destination = None
                    created_by_adapter = False

                    try:
                        logical = reject_path(member.filename)

                        key = logical.as_posix().casefold()
                        if key in seen:
                            raise ValueError("Duplicate ZIP member path")
                        seen.add(key)

                        mode = member.external_attr >> 16
                        file_type = stat.S_IFMT(mode)

                        if file_type not in (0, stat.S_IFREG):
                            raise ValueError(
                                "Symbolic links and special files rejected"
                            )

                        if member.flag_bits & 1:
                            raise ValueError("Encrypted member")

                        if len(children) >= file_limit:
                            raise ValueError(
                                "ZIP_JOB_FILE_BUDGET_EXCEEDED"
                            )

                        if member.file_size > self.MAX_MEMBER_BYTES:
                            raise ValueError("Member exceeds size limit")

                        if (
                            member.file_size /
                            max(member.compress_size, 1)
                            > self.MAX_RATIO
                        ):
                            raise ValueError(
                                "Compression ratio exceeds limit"
                            )

                        if (
                            total_bytes + member.file_size
                            > byte_limit
                        ):
                            raise ValueError(
                                "ZIP_JOB_BYTE_BUDGET_EXCEEDED"
                            )

                        destination = root.joinpath(*logical.parts)
                        destination.parent.mkdir(
                            parents=True, exist_ok=True
                        )

                        parent = destination.parent.resolve(strict=True)

                        if not parent.is_relative_to(root):
                            raise ValueError(
                                "ZIP destination escapes extraction root"
                            )

                        if destination.is_symlink():
                            raise ValueError(
                                "Existing symbolic link rejected"
                            )

                        copied = 0

                        with archive.open(member) as source:
                            with destination.open("xb") as output:
                                created_by_adapter = True
                                while True:
                                    chunk = source.read(1024 * 1024)

                                    if not chunk:
                                        break

                                    copied += len(chunk)

                                    if (
                                        copied > self.MAX_MEMBER_BYTES
                                        or total_bytes + copied
                                        > byte_limit
                                    ):
                                        raise ValueError(
                                            "ZIP_JOB_BYTE_BUDGET_EXCEEDED"
                                        )

                                    output.write(chunk)

                        total_bytes += copied

                        children.append(
                            PreparedChild(
                                source_path=destination,
                                normalized_path=(
                                    f"{context.normalized_path}"
                                    f"!/{logical.as_posix()}"
                                ),
                                relationship="container_member",
                                original_name=logical.name,
                                extension=destination.suffix.lower(),
                                metadata={
                                    "zip_member_path": logical.as_posix(),
                                    "zip_member_bytes": copied,
                                    "zip_crc32": f"{member.CRC:08x}",
                                },
                            )
                        )

                    except Exception as exc:
                        if created_by_adapter and destination is not None:
                            try:
                                destination.unlink(missing_ok=True)
                            except OSError:
                                pass

                        errors.append({
                            "member": member.filename,
                            "error": str(exc),
                        })

        except Exception as exc:
            return AdapterResult(
                adapter_name=self.name,
                handled=True,
                status="failed",
                source_file_id=context.file_id,
                error=str(exc),
                metadata={"member_errors": errors},
            )

        if not children and not errors:
            errors.append({
                "member": "",
                "error": "ZIP_EMPTY_ARCHIVE",
            })

        return AdapterResult(
            adapter_name=self.name,
            handled=True,
            status=(
                "completed_with_warnings" if errors
                else "completed"
            ),
            source_file_id=context.file_id,
            children=children,
            metadata={
                "extracted_file_count": len(children),
                "extracted_bytes": total_bytes,
                "member_errors": errors,
            },
        )


ZIP_ADAPTER = ZipAdapter()
