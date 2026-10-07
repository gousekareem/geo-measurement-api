"""Measurement + CRS handling, checked against pyproj's geodesic (ellipsoidal) calculation,
which is the ground truth for areas/lengths on the WGS84 ellipsoid."""
import pytest
from pyproj import CRS, Geod, Transformer
from shapely import transform
from shapely.geometry import (
    GeometryCollection,
    LinearRing,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

from app.measurement import measure
from app.measurement.crs import crs_label, needs_reprojection, utm_epsg_for
from app.models import MeasurementStatus

GEOD = Geod(ellps="WGS84")
WGS84 = CRS.from_epsg(4326)


def geodesic_area(geom):
    return abs(GEOD.geometry_area_perimeter(geom)[0])


def reproject(geom, src, dst):
    t = Transformer.from_crs(src, dst, always_xy=True)
    return transform(geom, t.transform, interleaved=False)


# ---------- choosing the projection ----------

@pytest.mark.parametrize("lon,lat,epsg", [
    (80.65, 16.5, 32644),   # Vijayawada -> UTM 44N
    (-0.12, 51.5, 32630),   # London -> UTM 30N
    (151.2, -33.9, 32756),  # Sydney -> UTM 56S
    (-180, 0, 32601),
    (180, 0, 32660),        # clamp to zone 60
    (0, 85, 32661),         # UPS North
    (0, -85, 32761),        # UPS South
])
def test_utm_zone_selection(lon, lat, epsg):
    assert utm_epsg_for(lon, lat) == epsg


@pytest.mark.parametrize("epsg,expected", [
    (4326, True),    # geographic
    (4269, True),    # NAD83 geographic
    (3857, True),    # Web Mercator: projected but area-distorting
    (3395, True),    # World Mercator
    (32644, False),  # UTM: measure natively
    (27700, False),  # British National Grid
    (2263, False),   # NY State Plane (US feet)
])
def test_needs_reprojection(epsg, expected):
    assert needs_reprojection(CRS.from_epsg(epsg)) is expected


def test_crs_label():
    assert crs_label(CRS.from_epsg(4326)) == "EPSG:4326"
    assert crs_label(CRS.from_wkt(CRS.from_epsg(32644).to_wkt("WKT1_ESRI"))) == "EPSG:32644"
    assert crs_label(None) is None


# ---------- accuracy ----------

@pytest.mark.parametrize("bounds", [
    (80.6, 16.5, 80.7, 16.6),      # India, near equator-ish
    (-0.2, 51.4, -0.1, 51.5),      # London
    (151.1, -33.95, 151.2, -33.85),  # Sydney (southern hemisphere)
    (24.9, 60.1, 25.1, 60.3),      # Helsinki (high latitude)
])
def test_polygon_area_in_wgs84_matches_geodesic(bounds):
    poly = box(*bounds)
    m = measure(poly, WGS84)
    assert m.status == MeasurementStatus.MEASURED
    assert m.measurement_crs.startswith("EPSG:32")
    assert m.area_m2 == pytest.approx(geodesic_area(poly), rel=2e-3)
    assert m.area_m2 > 1e6  # sanity: definitely not "square degrees"
    assert m.length_m is None


def test_line_length_in_wgs84_matches_geodesic():
    line = LineString([(80.6, 16.5), (80.65, 16.55), (80.7, 16.6)])
    m = measure(line, WGS84)
    assert m.status == MeasurementStatus.MEASURED
    assert m.length_m == pytest.approx(GEOD.geometry_length(line), rel=2e-3)
    assert m.area_m2 is None


def test_projected_utm_is_measured_natively_exactly():
    square = box(500000, 1800000, 500100, 1800100)  # 100 m x 100 m in UTM 44N
    m = measure(square, CRS.from_epsg(32644))
    assert m.area_m2 == pytest.approx(10_000)
    assert m.perimeter_m == pytest.approx(400)
    assert m.measurement_crs == "EPSG:32644"


def test_projected_crs_in_feet_is_converted_to_metres():
    square = box(980000, 190000, 981000, 191000)  # 1000 ft x 1000 ft, NY State Plane (EPSG:2263, US ft)
    m = measure(square, CRS.from_epsg(2263))
    assert m.area_m2 == pytest.approx(1000 * 0.3048006 * 1000 * 0.3048006, rel=1e-5)


def test_web_mercator_is_reprojected_not_measured_naively():
    lonlat = box(10.0, 60.0, 10.1, 60.1)
    merc = reproject(lonlat, 4326, 3857)
    naive = merc.area
    m = measure(merc, CRS.from_epsg(3857))
    true_area = geodesic_area(lonlat)
    assert naive / true_area > 3.9  # Web Mercator inflates area ~4x at 60 deg N
    assert m.area_m2 == pytest.approx(true_area, rel=2e-3)
    assert m.measurement_crs == "EPSG:32632"


def test_other_geographic_datum_is_handled():
    poly = box(-100.1, 40.0, -100.0, 40.1)
    m = measure(poly, CRS.from_epsg(4269))  # NAD83
    assert m.area_m2 == pytest.approx(geodesic_area(poly), rel=2e-3)


def test_polygon_with_hole():
    outer = [(80.6, 16.5), (80.6, 16.6), (80.7, 16.6), (80.7, 16.5)]
    hole = [(80.62, 16.52), (80.62, 16.58), (80.68, 16.58), (80.68, 16.52)]
    with_hole = measure(Polygon(outer, [hole]), WGS84).area_m2
    without = measure(Polygon(outer), WGS84).area_m2
    hole_area = measure(Polygon(hole), WGS84).area_m2
    assert with_hole == pytest.approx(without - hole_area, rel=1e-6)


def test_multipolygon_and_multilinestring():
    mp = MultiPolygon([box(80.6, 16.5, 80.61, 16.51), box(80.7, 16.6, 80.71, 16.61)])
    assert measure(mp, WGS84).area_m2 == pytest.approx(geodesic_area(mp), rel=2e-3)
    ml = MultiLineString([[(80.6, 16.5), (80.61, 16.5)], [(80.7, 16.6), (80.7, 16.61)]])
    assert measure(ml, WGS84).length_m == pytest.approx(GEOD.geometry_length(ml), rel=2e-3)


def test_linear_ring_gets_length():
    ring = LinearRing([(80.6, 16.5), (80.6, 16.6), (80.7, 16.6)])
    m = measure(ring, WGS84)
    assert m.status == MeasurementStatus.MEASURED and m.length_m > 0


def test_3d_coordinates_are_ignored_for_measurement():
    flat = measure(box(80.6, 16.5, 80.7, 16.6), WGS84).area_m2
    poly3d = Polygon([(80.6, 16.5, 100), (80.6, 16.6, 500), (80.7, 16.6, 900), (80.7, 16.5, 50)])
    assert measure(poly3d, WGS84).area_m2 == pytest.approx(flat)


# ---------- graceful handling ----------

@pytest.mark.parametrize("geom", [Point(80.6, 16.5), MultiPoint([(80.6, 16.5), (80.7, 16.6)])])
def test_points_not_applicable(geom):
    m = measure(geom, WGS84)
    assert m.status == MeasurementStatus.NOT_APPLICABLE
    assert m.area_m2 is None and m.length_m is None


def test_geometry_collection_is_unsupported():
    m = measure(GeometryCollection([Point(0, 0), box(0, 0, 1, 1)]), WGS84)
    assert m.status == MeasurementStatus.UNSUPPORTED
    assert "GeometryCollection" in m.message


def test_unparsed_geometry_type_is_unsupported():
    m = measure(None, WGS84, geometry_type="Track")
    assert m.status == MeasurementStatus.UNSUPPORTED
    assert "Track" in m.message


def test_missing_and_empty_geometry_are_errors():
    assert measure(None, WGS84).status == MeasurementStatus.ERROR
    assert measure(Polygon(), WGS84).status == MeasurementStatus.ERROR


def test_unknown_crs_is_error_not_a_guess():
    m = measure(box(0, 0, 100, 100), None)
    assert m.status == MeasurementStatus.ERROR
    assert "CRS is unknown" in m.message


def test_self_intersecting_polygon_is_repaired():
    bowtie = Polygon([(80.6, 16.5), (80.7, 16.6), (80.7, 16.5), (80.6, 16.6), (80.6, 16.5)])
    assert not bowtie.is_valid
    m = measure(bowtie, WGS84)
    assert m.status == MeasurementStatus.MEASURED
    assert "repaired" in m.message
    # the two triangles together cover half the bounding box
    half_box = geodesic_area(box(80.6, 16.5, 80.7, 16.6)) / 2
    assert m.area_m2 == pytest.approx(half_box, rel=5e-3)
