"""Reads KML (and KMZ = zipped KML).

The OGC KML 2.2 spec fixes the coordinate system to WGS84 longitude/latitude
(EPSG:4326), so no CRS detection is needed.

Parsing uses defusedxml: uploaded XML is untrusted, and the standard library parser
is open to entity-expansion ("billion laughs") and external-entity (XXE) attacks.
"""
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring
from pyproj import CRS
from shapely.geometry import (
    GeometryCollection,
    LinearRing,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry

from ..errors import InvalidFileError
from .base import RawFeature, ReadResult
from .zip_utils import open_zip, read_member

WGS84 = CRS.from_epsg(4326)

SUPPORTED_GEOMETRY_TAGS = {"Point", "LineString", "LinearRing", "Polygon", "MultiGeometry"}
# Valid KML geometry elements we recognise but don't convert (reported as unsupported).
OTHER_GEOMETRY_TAGS = {"Model", "Track", "MultiTrack"}


class _CoordinateError(ValueError):
    pass


def _local(tag: str) -> str:
    """'{http://www.opengis.net/kml/2.2}Placemark' -> 'Placemark' (namespace-agnostic)."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(el: Element, name: str) -> Element | None:
    return next((c for c in el if _local(c.tag) == name), None)


def _children(el: Element, name: str) -> list[Element]:
    return [c for c in el if _local(c.tag) == name]


def read_kmz(data: bytes, max_uncompressed_bytes: int, max_features: int) -> ReadResult:
    zf, members = open_zip(data, max_uncompressed_bytes)
    with zf:
        kmls = [m for m in members if m.filename.lower().endswith(".kml")]
        if not kmls:
            raise InvalidFileError("KMZ does not contain a .kml file")
        # By convention the main document is doc.kml at the root; otherwise the first .kml.
        main = next((m for m in kmls if m.filename.lower() == "doc.kml"), kmls[0])
        return read_kml(read_member(zf, main, max_uncompressed_bytes), max_features)


def read_kml(data: bytes, max_features: int) -> ReadResult:
    try:
        root = fromstring(data, forbid_dtd=True)
    except (ParseError, DefusedXmlException) as exc:
        raise InvalidFileError(f"Invalid KML (XML could not be parsed): {exc}")

    if _local(root.tag) != "kml":
        raise InvalidFileError(f"Not a KML document (root element is <{_local(root.tag)}>)")

    placemarks = [el for el in root.iter() if _local(el.tag) == "Placemark"]
    if len(placemarks) > max_features:
        raise InvalidFileError(f"KML has {len(placemarks)} features (max {max_features})")

    features = [_to_feature(i, pm) for i, pm in enumerate(placemarks)]
    warnings = [] if features else ["KML contains no Placemarks"]
    return ReadResult(features=features, crs=WGS84, warnings=warnings)


def _to_feature(index: int, pm: Element) -> RawFeature:
    props = _properties(pm)
    source_id = pm.get("id") or None

    geom_el = next(
        (c for c in pm if _local(c.tag) in SUPPORTED_GEOMETRY_TAGS | OTHER_GEOMETRY_TAGS), None
    )
    if geom_el is None:
        return RawFeature(index, None, props, source_id, error="Placemark has no geometry")

    tag = _local(geom_el.tag)
    if tag in OTHER_GEOMETRY_TAGS:
        return RawFeature(index, None, props, source_id, geometry_type_hint=tag)

    try:
        geometry = _parse_geometry(geom_el)
    except _CoordinateError as exc:
        return RawFeature(index, None, props, source_id, geometry_type_hint=tag, error=str(exc))
    return RawFeature(index, geometry, props, source_id)


def _properties(pm: Element) -> dict:
    props: dict = {}
    for field in ("name", "description"):
        el = _child(pm, field)
        if el is not None and el.text is not None:
            props[field] = el.text.strip()

    ext = _child(pm, "ExtendedData")
    if ext is not None:
        # <Data name="x"><value>..</value></Data>
        for data in _children(ext, "Data"):
            value = _child(data, "value")
            if data.get("name"):
                props[data.get("name")] = value.text.strip() if value is not None and value.text else None
        # <SchemaData><SimpleData name="x">..</SimpleData></SchemaData>
        for schema_data in _children(ext, "SchemaData"):
            for simple in _children(schema_data, "SimpleData"):
                if simple.get("name"):
                    props[simple.get("name")] = simple.text.strip() if simple.text else None
    return props


def _parse_coordinates(el: Element | None) -> list[tuple[float, float]]:
    coords_el = _child(el, "coordinates") if el is not None else None
    if coords_el is None or not (coords_el.text or "").strip():
        raise _CoordinateError(f"<{_local(el.tag) if el is not None else '?'}> has no coordinates")

    coords = []
    for token in coords_el.text.split():
        parts = token.split(",")
        try:
            lon, lat = float(parts[0]), float(parts[1])  # altitude (3rd value) is dropped
        except (ValueError, IndexError):
            raise _CoordinateError(f"Malformed coordinate '{token}'")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise _CoordinateError(f"Coordinate out of range: lon={lon}, lat={lat}")
        coords.append((lon, lat))
    return coords


def _ring(boundary: Element | None) -> list[tuple[float, float]]:
    ring_el = _child(boundary, "LinearRing") if boundary is not None else None
    if ring_el is None:
        raise _CoordinateError("Polygon boundary has no <LinearRing>")
    coords = _parse_coordinates(ring_el)
    if len(coords) < 3:
        raise _CoordinateError("Polygon ring needs at least 3 coordinates")
    return coords


def _parse_geometry(el: Element) -> BaseGeometry:
    tag = _local(el.tag)
    if tag == "Point":
        return Point(_parse_coordinates(el)[0])
    if tag == "LineString":
        coords = _parse_coordinates(el)
        if len(coords) < 2:
            raise _CoordinateError("LineString needs at least 2 coordinates")
        return LineString(coords)
    if tag == "LinearRing":
        coords = _parse_coordinates(el)
        if len(coords) < 3:
            raise _CoordinateError("LinearRing needs at least 3 coordinates")
        return LinearRing(coords)
    if tag == "Polygon":
        outer = _ring(_child(el, "outerBoundaryIs"))
        inner = [_ring(b) for b in _children(el, "innerBoundaryIs")]
        return Polygon(outer, inner)
    if tag == "MultiGeometry":
        return _parse_multi(el)
    raise _CoordinateError(f"Unsupported geometry <{tag}>")


def _parse_multi(el: Element) -> BaseGeometry:
    parts: list[BaseGeometry] = []
    for child in el:
        tag = _local(child.tag)
        if tag in SUPPORTED_GEOMETRY_TAGS:
            g = _parse_geometry(child)
            # flatten nested MultiGeometry
            parts.extend(g.geoms if tag == "MultiGeometry" and hasattr(g, "geoms") else [g])
    if not parts:
        return GeometryCollection()

    types = {p.geom_type for p in parts}
    if types == {"Point"}:
        return MultiPoint(parts)
    if types <= {"LineString", "LinearRing"}:
        return MultiLineString([LineString(p.coords) for p in parts])
    if types == {"Polygon"}:
        return MultiPolygon(parts)
    return GeometryCollection(parts)  # mixed types
