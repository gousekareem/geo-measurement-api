"""CRS helpers: describing a CRS, and choosing the projected CRS to measure in.

Strategy
--------
* Geographic CRS (lon/lat degrees, e.g. EPSG:4326): degrees are not a unit of
  distance, so each feature is reprojected to the **UTM zone containing its
  centroid** (UPS for the poles). UTM is conformal with scale error <= ~0.1%
  within its 6 degree zone - accurate for the field/parcel/route-sized
  features this API targets.
* Projected CRS that preserves local scale (UTM, state plane, national grids...):
  measured **natively** - the data's author already chose a suitable projection.
  Values are converted to metres using the CRS's axis unit (handles US feet etc.).
* Mercator-family projections (incl. Web Mercator EPSG:3857) are projected but
  inflate areas massively away from the equator (4x at 60 deg). They are treated
  like geographic data: converted to WGS84, then to local UTM.
"""
from functools import lru_cache

from pyproj import CRS, Transformer

WGS84 = CRS.from_epsg(4326)


def horizontal_crs(crs: CRS) -> CRS:
    """Compound CRS (e.g. horizontal + vertical datum) -> its horizontal part."""
    if crs.is_compound and crs.sub_crs_list:
        return crs.sub_crs_list[0]
    return crs


def crs_label(crs: CRS | None) -> str | None:
    """'EPSG:4326' when an EPSG code can be identified, else the CRS name."""
    if crs is None:
        return None
    epsg = crs.to_epsg(min_confidence=70)
    return f"EPSG:{epsg}" if epsg else crs.name


def is_area_distorting_projection(crs: CRS) -> bool:
    op = crs.coordinate_operation
    method = (op.method_name if op else "").lower()
    return "mercator" in method and "transverse" not in method


def needs_reprojection(crs: CRS) -> bool:
    crs = horizontal_crs(crs)
    if crs.is_geographic:
        return True
    if crs.is_projected:
        return is_area_distorting_projection(crs)
    return True


def is_measurable(crs: CRS) -> bool:
    crs = horizontal_crs(crs)
    return crs.is_geographic or crs.is_projected


def utm_epsg_for(lon: float, lat: float) -> int:
    """EPSG code of the UTM zone (WGS84) containing lon/lat; UPS beyond UTM's latitude limits."""
    if lat >= 84:
        return 32661  # UPS North
    if lat < -80:
        return 32761  # UPS South
    zone = int((lon + 180) // 6) + 1
    zone = min(max(zone, 1), 60)
    return (32600 if lat >= 0 else 32700) + zone


def metres_per_unit(crs: CRS) -> float:
    """Linear unit of a projected CRS in metres (1.0 for metres, 0.3048006 for US survey ft...)."""
    axis = horizontal_crs(crs).axis_info
    return axis[0].unit_conversion_factor if axis else 1.0


@lru_cache(maxsize=256)
def get_transformer(source_wkt: str, target_epsg: int) -> Transformer:
    # always_xy=True: keep (x=lon/easting, y=lat/northing) order regardless of the
    # CRS's official axis order (EPSG:4326 is officially lat, lon).
    return Transformer.from_crs(CRS.from_wkt(source_wkt), CRS.from_epsg(target_epsg), always_xy=True)
