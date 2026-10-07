"""File parsing: Shapefile ZIP, KML, KMZ - including malformed and hostile input."""
import pytest
import shapefile

from app.errors import InvalidFileError
from app.readers import detect_file_type, read_file
from app.models import FileType
from tests.factories import (
    LINE_LONLAT,
    SQUARE_LONLAT,
    kml_line,
    kml_point,
    kml_polygon,
    make_kml,
    make_shapefile_zip,
    placemark,
    prj_for,
    zip_bytes,
)

LIMITS = dict(max_uncompressed_bytes=5 * 1024 * 1024, max_features=1000)


def read(file_type, data, **overrides):
    return read_file(file_type, data, **{**LIMITS, **overrides})


# ---------- type detection ----------

@pytest.mark.parametrize("name,ftype", [
    ("parcels.zip", FileType.SHAPEFILE), ("SURVEY.KML", FileType.KML), ("map.kmz", FileType.KMZ),
])
def test_detect_file_type(name, ftype):
    assert detect_file_type(name) == ftype


@pytest.mark.parametrize("name", ["data.geojson", "file.shp", "noext", "evil.kml.exe"])
def test_detect_rejects_other_types(name):
    with pytest.raises(InvalidFileError):
        detect_file_type(name)


# ---------- shapefile ----------

def test_shapefile_polygons_with_attributes_and_crs():
    data = make_shapefile_zip(
        shapefile.POLYGON,
        [("poly", [SQUARE_LONLAT]), ("poly", [[(80.8, 16.5), (80.8, 16.6), (80.9, 16.6), (80.8, 16.5)]])],
        records=[{"name": "Plot A", "owner": "Ravi"}, {"name": "Plot B", "owner": "Lakshmi"}],
    )
    result = read(FileType.SHAPEFILE, data)
    assert result.crs.to_epsg() == 4326
    assert not result.crs_assumed
    assert [f.geometry_type for f in result.features] == ["Polygon", "Polygon"]
    assert result.features[0].properties == {"name": "Plot A", "owner": "Ravi"}
    assert result.features[1].index == 1


def test_shapefile_projected_crs_from_prj():
    data = make_shapefile_zip(
        shapefile.POLYLINE, [("line", [[(500000, 1800000), (500300, 1800400)]])], prj=prj_for(32644)
    )
    result = read(FileType.SHAPEFILE, data)
    assert result.crs.to_epsg(min_confidence=70) == 32644
    assert result.features[0].geometry_type == "LineString"


def test_shapefile_inside_a_folder_and_with_macos_junk():
    data = make_shapefile_zip(
        shapefile.POINT, [("point", (80.6, 16.5))], folder="export/data/",
        extra={"__MACOSX/export/data/._layer.shp": b"junk", "readme.txt": b"hi"},
    )
    result = read(FileType.SHAPEFILE, data)
    assert result.features[0].geometry_type == "Point"


def test_shapefile_sidecar_names_are_case_insensitive():
    import io
    import zipfile
    original = make_shapefile_zip(shapefile.POINT, [("point", (80.6, 16.5))])
    src = zipfile.ZipFile(io.BytesIO(original))
    renamed = {n.replace("layer.dbf", "LAYER.DBF"): src.read(n) for n in src.namelist()}
    result = read(FileType.SHAPEFILE, zip_bytes(renamed))
    assert len(result.features) == 1


def test_shapefile_without_prj_lonlat_is_assumed_wgs84():
    data = make_shapefile_zip(shapefile.POLYGON, [("poly", [SQUARE_LONLAT])], prj=None)
    result = read(FileType.SHAPEFILE, data)
    assert result.crs.to_epsg() == 4326
    assert result.crs_assumed
    assert any("assuming EPSG:4326" in w for w in result.warnings)


def test_shapefile_without_prj_projected_coords_has_unknown_crs():
    data = make_shapefile_zip(shapefile.POLYGON, [("poly", [[(500000, 1800000), (500000, 1800100), (500100, 1800100), (500000, 1800000)]])], prj=None)
    result = read(FileType.SHAPEFILE, data)
    assert result.crs is None
    assert any("unknown" in w for w in result.warnings)


def test_shapefile_bad_prj_falls_back_with_warning():
    data = make_shapefile_zip(shapefile.POINT, [("point", (80.6, 16.5))], prj="this is not wkt")
    result = read(FileType.SHAPEFILE, data)
    assert result.crs_assumed
    assert any("Could not parse .prj" in w for w in result.warnings)


def test_shapefile_null_geometry_is_kept_as_feature_with_error():
    data = make_shapefile_zip(shapefile.POLYGON, [("poly", [SQUARE_LONLAT]), ("null", None)])
    result = read(FileType.SHAPEFILE, data)
    assert len(result.features) == 2
    assert result.features[1].geometry is None
    assert "NULL" in result.features[1].error


def test_shapefile_cpg_encoding():
    data = make_shapefile_zip(shapefile.POINT, [("point", (80.6, 16.5))], records=[{"name": "Café"}], cpg="UTF-8")
    assert read(FileType.SHAPEFILE, data).features[0].properties["name"] == "Café"


@pytest.mark.parametrize("omit,msg", [((".shx",), ".shx"), ((".dbf",), ".dbf"), ((".shp",), "does not contain a .shp")])
def test_shapefile_missing_components(omit, msg):
    data = make_shapefile_zip(shapefile.POINT, [("point", (1, 1))], omit=omit)
    with pytest.raises(InvalidFileError, match=msg):
        read(FileType.SHAPEFILE, data)


def test_zip_with_two_shapefiles_rejected():
    a = make_shapefile_zip(shapefile.POINT, [("point", (1, 1))], name="a")
    import io
    import zipfile
    files = {n: zipfile.ZipFile(io.BytesIO(a)).read(n) for n in zipfile.ZipFile(io.BytesIO(a)).namelist()}
    files.update({n.replace("a.", "b."): c for n, c in files.items()})
    with pytest.raises(InvalidFileError, match="2 shapefiles"):
        read(FileType.SHAPEFILE, zip_bytes(files))


def test_not_a_zip():
    with pytest.raises(InvalidFileError, match="not a valid ZIP"):
        read(FileType.SHAPEFILE, b"definitely not a zip")


def test_corrupt_shp_contents():
    data = zip_bytes({"x.shp": b"garbage" * 20, "x.shx": b"garbage", "x.dbf": b"garbage"})
    with pytest.raises(InvalidFileError, match="Could not read shapefile"):
        read(FileType.SHAPEFILE, data)


def test_zip_bomb_guard():
    data = zip_bytes({"big.shp": b"\0" * 2_000_000})
    with pytest.raises(InvalidFileError, match="over the"):
        read(FileType.SHAPEFILE, data, max_uncompressed_bytes=1_000_000)


def test_shapefile_feature_limit():
    data = make_shapefile_zip(shapefile.POINT, [("point", (i % 100, 1)) for i in range(20)])
    with pytest.raises(InvalidFileError, match="max 10"):
        read(FileType.SHAPEFILE, data, max_features=10)


# ---------- KML ----------

def test_kml_geometries_properties_and_ids():
    kml = make_kml(
        placemark(kml_polygon(SQUARE_LONLAT), name="Field", pid="f1",
                  extended='<ExtendedData><Data name="crop"><value>Rice</value></Data>'
                           '<SchemaData schemaUrl="#s"><SimpleData name="owner">Ravi</SimpleData></SchemaData></ExtendedData>'),
        placemark(kml_line(LINE_LONLAT), name="Road"),
        placemark(kml_point(80.6, 16.5), name="Well"),
    )
    result = read(FileType.KML, kml)
    assert result.crs.to_epsg() == 4326
    assert [f.geometry_type for f in result.features] == ["Polygon", "LineString", "Point"]
    assert result.features[0].source_id == "f1"
    assert result.features[0].properties == {"name": "Field", "crop": "Rice", "owner": "Ravi"}


def test_kml_polygon_with_hole_and_altitude():
    hole = [(80.62, 16.52), (80.62, 16.58), (80.68, 16.58), (80.62, 16.52)]
    result = read(FileType.KML, make_kml(placemark(kml_polygon(SQUARE_LONLAT, [hole]))))
    poly = result.features[0].geometry
    assert len(poly.interiors) == 1


def test_kml_multigeometry():
    multi = f"<MultiGeometry>{kml_polygon(SQUARE_LONLAT)}{kml_polygon([(81, 17), (81, 17.1), (81.1, 17.1), (81, 17)])}</MultiGeometry>"
    mixed = f"<MultiGeometry>{kml_point(80.6, 16.5)}{kml_line(LINE_LONLAT)}</MultiGeometry>"
    nested = f"<MultiGeometry><MultiGeometry>{kml_line(LINE_LONLAT)}</MultiGeometry>{kml_line(LINE_LONLAT)}</MultiGeometry>"
    result = read(FileType.KML, make_kml(placemark(multi), placemark(mixed), placemark(nested)))
    assert [f.geometry_type for f in result.features] == ["MultiPolygon", "GeometryCollection", "MultiLineString"]


def test_kml_without_namespace_and_kml_21_namespace():
    for ns_kml in (
        make_kml(placemark(kml_point(1, 2)), namespace="http://earth.google.com/kml/2.1"),
        f"<kml><Placemark>{kml_point(1, 2)}</Placemark></kml>".encode(),
    ):
        assert read(FileType.KML, ns_kml).features[0].geometry_type == "Point"


def test_kml_unsupported_geometry_is_reported_not_crashed():
    track = "<gx:Track><when>2020-01-01T00:00:00Z</when><gx:coord>80.6 16.5 0</gx:coord></gx:Track>"
    result = read(FileType.KML, make_kml(placemark(track), placemark(kml_point(1, 1))))
    assert result.features[0].geometry is None
    assert result.features[0].geometry_type == "Track"
    assert result.features[1].geometry_type == "Point"


@pytest.mark.parametrize("geom_xml,msg", [
    ("<Point><coordinates>abc,def</coordinates></Point>", "Malformed coordinate"),
    ("<Point><coordinates>200,16</coordinates></Point>", "out of range"),
    ("<LineString><coordinates>1,1</coordinates></LineString>", "at least 2"),
    ("<Polygon><outerBoundaryIs><LinearRing><coordinates>1,1 2,2</coordinates></LinearRing></outerBoundaryIs></Polygon>", "at least 3"),
    ("<Polygon></Polygon>", "no <LinearRing>"),
])
def test_kml_bad_feature_does_not_fail_whole_file(geom_xml, msg):
    result = read(FileType.KML, make_kml(placemark(geom_xml), placemark(kml_point(1, 1))))
    assert msg in result.features[0].error
    assert result.features[1].geometry is not None


def test_kml_placemark_without_geometry():
    result = read(FileType.KML, make_kml("<Placemark><name>Empty</name></Placemark>"))
    assert result.features[0].geometry is None
    assert "no geometry" in result.features[0].error


def test_kml_with_no_placemarks_warns():
    result = read(FileType.KML, make_kml())
    assert result.features == []
    assert result.warnings


@pytest.mark.parametrize("data,msg", [
    (b"<kml><Placemark>", "could not be parsed"),
    (b"<html><body/></html>", "Not a KML"),
    (b"", "could not be parsed"),
])
def test_kml_invalid_documents(data, msg):
    with pytest.raises(InvalidFileError, match=msg):
        read(FileType.KML, data)


def test_kml_xxe_and_entity_expansion_blocked():
    xxe = b"""<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<kml><Placemark><name>&x;</name></Placemark></kml>"""
    bomb = b"""<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><kml>&b;</kml>"""
    for payload in (xxe, bomb):
        with pytest.raises(InvalidFileError):
            read(FileType.KML, payload)


# ---------- KMZ ----------

def test_kmz_reads_doc_kml():
    kml = make_kml(placemark(kml_polygon(SQUARE_LONLAT)))
    data = zip_bytes({"files/icon.png": b"\x89PNG", "doc.kml": kml})
    assert read(FileType.KMZ, data).features[0].geometry_type == "Polygon"


def test_kmz_without_kml():
    with pytest.raises(InvalidFileError, match="does not contain a .kml"):
        read(FileType.KMZ, zip_bytes({"a.txt": b"x"}))
