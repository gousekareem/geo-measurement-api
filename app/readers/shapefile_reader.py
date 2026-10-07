"""Reads a zipped ESRI Shapefile (.shp + .shx + .dbf, optional .prj/.cpg) with pyshp.

pyshp is pure Python, so the project installs with plain `pip` - no GDAL needed.
"""
import codecs
import io
from pathlib import PurePosixPath

import shapefile
from pyproj import CRS
from pyproj.exceptions import CRSError
from shapely.geometry import shape

from ..errors import InvalidFileError
from .base import RawFeature, ReadResult, json_safe
from .zip_utils import open_zip, read_member

WGS84 = CRS.from_epsg(4326)


def read_shapefile_zip(data: bytes, max_uncompressed_bytes: int, max_features: int) -> ReadResult:
    zf, members = open_zip(data, max_uncompressed_bytes)
    with zf:
        shp_members = [m for m in members if m.filename.lower().endswith(".shp")]
        if not shp_members:
            raise InvalidFileError("ZIP does not contain a .shp file")
        if len(shp_members) > 1:
            names = ", ".join(m.filename for m in shp_members)
            raise InvalidFileError(f"ZIP contains {len(shp_members)} shapefiles ({names}); upload one shapefile per ZIP")

        shp = shp_members[0]
        stem = shp.filename[:-4].lower()
        by_name = {m.filename.lower(): m for m in members}

        def sidecar(ext: str, required: bool) -> bytes | None:
            member = by_name.get(stem + ext)
            if member is None:
                if required:
                    raise InvalidFileError(
                        f"Shapefile is missing its {ext} file (expected {PurePosixPath(shp.filename).stem}{ext})"
                    )
                return None
            return read_member(zf, member, max_uncompressed_bytes)

        shp_bytes = read_member(zf, shp, max_uncompressed_bytes)
        shx_bytes = sidecar(".shx", required=True)
        dbf_bytes = sidecar(".dbf", required=True)
        prj_bytes = sidecar(".prj", required=False)
        cpg_bytes = sidecar(".cpg", required=False)

    warnings: list[str] = []
    encoding = _encoding_from_cpg(cpg_bytes, warnings)

    try:
        reader = shapefile.Reader(
            shp=io.BytesIO(shp_bytes),
            shx=io.BytesIO(shx_bytes),
            dbf=io.BytesIO(dbf_bytes),
            encoding=encoding,
            encodingErrors="replace",
        )
        if len(reader) > max_features:
            raise InvalidFileError(f"Shapefile has {len(reader)} features (max {max_features})")
        features = [_to_feature(i, sr) for i, sr in enumerate(reader.iterShapeRecords())]
    except InvalidFileError:
        raise
    except Exception as exc:  # pyshp raises a variety of errors on corrupt input
        raise InvalidFileError(f"Could not read shapefile: {exc}")

    crs, assumed = _resolve_crs(prj_bytes, features, warnings)
    return ReadResult(features=features, crs=crs, crs_assumed=assumed, warnings=warnings)


def _to_feature(index: int, shape_record) -> RawFeature:
    props = {k: json_safe(v) for k, v in shape_record.record.as_dict().items()}
    shp = shape_record.shape
    if shp.shapeType == shapefile.NULL:
        return RawFeature(index, None, props, source_id=str(index), error="Feature has a NULL geometry")
    try:
        geom = shape(shp.__geo_interface__)
    except Exception as exc:
        return RawFeature(index, None, props, source_id=str(index), error=f"Invalid geometry: {exc}")
    return RawFeature(index, geom, props, source_id=str(index))


def _encoding_from_cpg(cpg: bytes | None, warnings: list[str]) -> str:
    if not cpg:
        return "utf-8"
    name = cpg.decode("ascii", errors="ignore").strip()
    # .cpg often holds bare code-page numbers like "1252"
    candidate = f"cp{name}" if name.isdigit() else name
    try:
        return codecs.lookup(candidate).name
    except LookupError:
        warnings.append(f"Unknown .cpg encoding '{name}', using UTF-8")
        return "utf-8"


def _resolve_crs(prj: bytes | None, features: list[RawFeature], warnings: list[str]) -> tuple[CRS | None, bool]:
    if prj:
        wkt = prj.decode("utf-8", errors="replace").strip()
        try:
            return CRS.from_wkt(wkt), False
        except CRSError as exc:
            warnings.append(f"Could not parse .prj file ({exc})")
    else:
        warnings.append("Shapefile has no .prj file")

    # No usable CRS: if every coordinate fits lon/lat ranges, assume WGS84 (by far the
    # most common case) and flag it. Otherwise refuse to guess - measurements would be wrong.
    if _looks_geographic(features):
        warnings.append("Coordinates fall within longitude/latitude range; assuming EPSG:4326")
        return WGS84, True
    warnings.append("CRS is unknown; measurements cannot be calculated")
    return None, False


def _looks_geographic(features: list[RawFeature]) -> bool:
    geoms = [f.geometry for f in features if f.geometry is not None and not f.geometry.is_empty]
    if not geoms:
        return False
    for g in geoms:
        minx, miny, maxx, maxy = g.bounds
        if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
            return False
    return True
