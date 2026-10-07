"""Turns (geometry, CRS) into a measurement. Never raises for bad geometry -
every problem becomes a status + message on that feature."""
from dataclasses import dataclass

from pyproj import CRS
from shapely import force_2d, make_valid, transform
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

from ..models import MeasurementStatus
from .crs import (
    WGS84,
    get_transformer,
    horizontal_crs,
    is_measurable,
    metres_per_unit,
    needs_reprojection,
    utm_epsg_for,
    crs_label,
)

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString", "LinearRing"}
POINT_TYPES = {"Point", "MultiPoint"}


@dataclass
class Measurement:
    status: MeasurementStatus
    area_m2: float | None = None
    perimeter_m: float | None = None
    length_m: float | None = None
    measurement_crs: str | None = None
    message: str | None = None


def measure(geometry: BaseGeometry | None, source_crs: CRS | None, geometry_type: str | None = None) -> Measurement:
    if geometry is None:
        if geometry_type:
            return Measurement(MeasurementStatus.UNSUPPORTED, message=f"Geometry type '{geometry_type}' is not supported")
        return Measurement(MeasurementStatus.ERROR, message="Feature has no geometry")

    gtype = geometry.geom_type
    if geometry.is_empty:
        return Measurement(MeasurementStatus.ERROR, message="Geometry is empty")
    if gtype in POINT_TYPES:
        return Measurement(MeasurementStatus.NOT_APPLICABLE, message="Points have no area or length")
    if gtype not in AREA_TYPES | LENGTH_TYPES:
        return Measurement(MeasurementStatus.UNSUPPORTED, message=f"Measurement is not supported for {gtype}")
    if source_crs is None:
        return Measurement(MeasurementStatus.ERROR, message="CRS is unknown, so the geometry cannot be measured reliably")
    if not is_measurable(source_crs):
        return Measurement(MeasurementStatus.ERROR, message=f"CRS '{source_crs.name}' is not geographic or projected")

    geometry = force_2d(geometry)
    notes: list[str] = []

    if gtype in AREA_TYPES and not geometry.is_valid:
        reason = explain_validity(geometry)
        geometry = _polygonal_part(make_valid(geometry))
        notes.append(f"Invalid polygon ({reason}) was repaired before measuring")
        if geometry.is_empty:
            return Measurement(MeasurementStatus.ERROR, message=f"Invalid polygon could not be repaired ({reason})")

    projected, target_label, factor = _to_measurement_crs(geometry, source_crs)

    result = Measurement(MeasurementStatus.MEASURED, measurement_crs=target_label, message="; ".join(notes) or None)
    if gtype in AREA_TYPES:
        result.area_m2 = projected.area * factor * factor
        result.perimeter_m = projected.length * factor
    else:
        result.length_m = projected.length * factor
    return result


def _to_measurement_crs(geometry: BaseGeometry, source_crs: CRS) -> tuple[BaseGeometry, str, float]:
    """Returns (geometry in a metric projected CRS, that CRS's label, metres per unit)."""
    source_crs = horizontal_crs(source_crs)

    if not needs_reprojection(source_crs):
        return geometry, crs_label(source_crs), metres_per_unit(source_crs)

    # Get lon/lat so we can pick the UTM zone from the feature's centroid.
    if source_crs.is_geographic and source_crs.equals(WGS84, ignore_axis_order=True):
        lonlat = geometry
    else:
        lonlat = transform(geometry, get_transformer(source_crs.to_wkt(), 4326).transform, interleaved=False)

    centroid = lonlat.centroid
    utm_epsg = utm_epsg_for(centroid.x, centroid.y)
    projected = transform(lonlat, get_transformer(WGS84.to_wkt(), utm_epsg).transform, interleaved=False)
    return projected, f"EPSG:{utm_epsg}", 1.0


def _polygonal_part(geometry: BaseGeometry) -> BaseGeometry:
    """make_valid may return a GeometryCollection (e.g. polygon + stray line); keep only polygons."""
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return geometry
    polys = []
    for g in getattr(geometry, "geoms", []):
        if isinstance(g, Polygon):
            polys.append(g)
        elif isinstance(g, MultiPolygon):
            polys.extend(g.geoms)
    return MultiPolygon(polys) if polys else Polygon()
