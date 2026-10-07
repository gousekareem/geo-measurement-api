"""Picks a reader based on the file extension."""
from ..errors import InvalidFileError
from ..models import FileType
from .base import RawFeature, ReadResult
from .kml_reader import read_kml, read_kmz
from .shapefile_reader import read_shapefile_zip

EXTENSIONS = {".zip": FileType.SHAPEFILE, ".kml": FileType.KML, ".kmz": FileType.KMZ}


def detect_file_type(filename: str) -> FileType:
    lower = filename.lower()
    for ext, file_type in EXTENSIONS.items():
        if lower.endswith(ext):
            return file_type
    raise InvalidFileError(
        f"Unsupported file type '{filename}'. Upload a .zip (Shapefile), .kml or .kmz file"
    )


def read_file(file_type: FileType, data: bytes, *, max_uncompressed_bytes: int, max_features: int) -> ReadResult:
    if file_type == FileType.SHAPEFILE:
        return read_shapefile_zip(data, max_uncompressed_bytes, max_features)
    if file_type == FileType.KMZ:
        return read_kmz(data, max_uncompressed_bytes, max_features)
    return read_kml(data, max_features)


__all__ = ["RawFeature", "ReadResult", "detect_file_type", "read_file", "EXTENSIONS"]
