"""Safe, in-memory ZIP access.

Archives are never extracted to disk, so path-traversal ("zip slip") is impossible,
and the declared uncompressed size is checked up front to stop zip bombs.
"""
import io
import zipfile
from pathlib import PurePosixPath

from ..errors import InvalidFileError


def open_zip(data: bytes, max_uncompressed_bytes: int) -> tuple[zipfile.ZipFile, list[zipfile.ZipInfo]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise InvalidFileError("File is not a valid ZIP archive")

    members = [m for m in zf.infolist() if not m.is_dir() and not _is_junk(m.filename)]
    total = sum(m.file_size for m in members)
    if total > max_uncompressed_bytes:
        zf.close()
        raise InvalidFileError(
            f"Archive expands to {total // (1024 * 1024)} MB, over the "
            f"{max_uncompressed_bytes // (1024 * 1024)} MB limit"
        )
    return zf, members


def read_member(zf: zipfile.ZipFile, member: zipfile.ZipInfo, max_bytes: int) -> bytes:
    # Read with a hard cap, in case the header lied about file_size.
    with zf.open(member) as fh:
        data = fh.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise InvalidFileError(f"{member.filename} is larger than allowed")
    return data


def _is_junk(name: str) -> bool:
    # macOS adds "__MACOSX/" folders and "._file" resource forks when zipping.
    parts = PurePosixPath(name).parts
    return "__MACOSX" in parts or PurePosixPath(name).name.startswith("._")
