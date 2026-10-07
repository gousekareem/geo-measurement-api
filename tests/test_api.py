"""End-to-end API tests: upload -> file info -> features -> measurements."""
import pytest
import shapefile
from pyproj import Geod
from shapely.geometry import LineString, Polygon

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

GEOD = Geod(ellps="WGS84")
SQUARE_TRUE_AREA = abs(GEOD.geometry_area_perimeter(Polygon(SQUARE_LONLAT))[0])
LINE_TRUE_LENGTH = GEOD.geometry_length(LineString(LINE_LONLAT))


def mixed_kml():
    return make_kml(
        placemark(kml_polygon(SQUARE_LONLAT), name="Field", pid="field-1"),
        placemark(kml_line(LINE_LONLAT), name="Road"),
        placemark(kml_point(80.6, 16.5), name="Well"),
        placemark("<gx:Track><gx:coord>80.6 16.5 0</gx:coord></gx:Track>", name="GPS"),
    )


# ---------- upload ----------

def test_upload_kml(upload):
    r = upload("survey.kml", mixed_kml(), "application/vnd.google-earth.kml+xml")
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == "survey.kml"
    assert body["file_type"] == "kml"
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 4
    assert body["crs"] == "EPSG:4326"
    assert body["crs_assumed"] is False
    assert r.headers["location"].endswith(f"/api/files/{body['id']}/")


def test_upload_shapefile_zip(upload):
    data = make_shapefile_zip(shapefile.POLYGON, [("poly", [SQUARE_LONLAT])], records=[{"name": "Plot A"}])
    r = upload("parcels.zip", data, "application/zip")
    assert r.status_code == 201
    assert r.json()["crs"] == "EPSG:4326"
    assert r.json()["file_type"] == "shapefile"


def test_upload_kmz(upload):
    r = upload("map.kmz", zip_bytes({"doc.kml": mixed_kml()}))
    assert r.status_code == 201
    assert r.json()["feature_count"] == 4


def test_upload_unsupported_extension(upload):
    r = upload("data.geojson", b"{}")
    assert r.status_code == 400
    assert "Unsupported file type" in r.json()["detail"]


def test_upload_empty_file(upload):
    assert upload("a.kml", b"").status_code == 400


def test_upload_too_large(upload, settings):
    assert upload("big.kml", b"x" * (settings.max_upload_bytes + 1)).status_code == 413


def test_upload_without_file_field(client):
    assert client.post("/api/files/").status_code == 422


def test_upload_corrupt_file_returns_422_with_record(client, upload):
    r = upload("broken.zip", b"not a zip at all")
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == "FAILED"
    assert "not a valid ZIP" in body["error"]
    # the failure is stored and can be looked up later
    again = client.get(f"/api/files/{body['id']}/").json()
    assert again["status"] == "FAILED"
    # but features/measurements aren't available
    assert client.get(f"/api/files/{body['id']}/measurements/").status_code == 409


# ---------- file info ----------

def test_get_file_info(client, upload):
    file_id = upload("survey.kml", mixed_kml()).json()["id"]
    r = client.get(f"/api/files/{file_id}/")
    assert r.status_code == 200
    body = r.json()
    for key in ("id", "filename", "feature_count", "crs", "status"):
        assert key in body
    assert body["links"]["measurements"].endswith(f"/api/files/{file_id}/measurements/")


def test_get_file_404(client):
    assert client.get("/api/files/nope/").status_code == 404
    assert client.get("/api/files/nope/measurements/").status_code == 404


def test_list_and_delete_files(client, upload):
    ids = [upload(f"f{i}.kml", mixed_kml()).json()["id"] for i in range(3)]
    listing = client.get("/api/files/?limit=2").json()
    assert listing["total"] == 3 and len(listing["items"]) == 2

    assert client.delete(f"/api/files/{ids[0]}/").status_code == 204
    assert client.get(f"/api/files/{ids[0]}/").status_code == 404
    assert client.get("/api/files/").json()["total"] == 2


# ---------- features ----------

def test_features_include_id_type_geometry_crs_properties(client, upload):
    file_id = upload("survey.kml", mixed_kml()).json()["id"]
    body = client.get(f"/api/files/{file_id}/features/").json()
    assert body["total"] == 4
    first = body["items"][0]
    assert first["feature_id"] == 0
    assert first["source_id"] == "field-1"
    assert first["geometry_type"] == "Polygon"
    assert first["crs"] == "EPSG:4326"
    assert first["geometry"]["type"] == "Polygon"
    assert first["geometry"]["coordinates"][0][0] == [80.6, 16.5]
    assert first["properties"] == {"name": "Field"}

    track = body["items"][3]
    assert track["geometry_type"] == "Track" and track["geometry"] is None


def test_features_filter_and_paginate(client, upload):
    file_id = upload("survey.kml", mixed_kml()).json()["id"]
    lines = client.get(f"/api/files/{file_id}/features/?geometry_type=LineString").json()
    assert lines["total"] == 1 and lines["items"][0]["properties"]["name"] == "Road"
    page = client.get(f"/api/files/{file_id}/features/?limit=2&offset=2").json()
    assert [f["feature_id"] for f in page["items"]] == [2, 3]


# ---------- measurements ----------

def test_measurements_for_mixed_kml(client, upload):
    file_id = upload("survey.kml", mixed_kml()).json()["id"]
    body = client.get(f"/api/files/{file_id}/measurements/").json()
    assert body["source_crs"] == "EPSG:4326"
    assert body["units"]["area"] == "m²"

    poly, line, point, track = body["items"]

    assert poly["status"] == "measured"
    assert poly["measurement_crs"] == "EPSG:32644"
    assert poly["area_m2"] == pytest.approx(SQUARE_TRUE_AREA, rel=2e-3)
    assert poly["area_hectares"] == pytest.approx(poly["area_m2"] / 10_000, rel=1e-4)
    assert poly["perimeter_m"] > 0
    assert poly["length_m"] is None

    assert line["status"] == "measured"
    assert line["length_m"] == pytest.approx(LINE_TRUE_LENGTH, rel=2e-3)
    assert line["area_m2"] is None

    assert point["status"] == "not_applicable"
    assert point["area_m2"] is None and point["length_m"] is None

    assert track["status"] == "unsupported"
    assert "Track" in track["message"]

    s = body["summary"]
    assert s == {
        "total_features": 4, "measured": 2, "not_applicable": 1, "unsupported": 1, "errors": 0,
        "total_area_m2": pytest.approx(poly["area_m2"], abs=0.01),
        "total_length_m": pytest.approx(line["length_m"], abs=0.01),
        "by_geometry_type": {"Polygon": 1, "LineString": 1, "Point": 1, "Track": 1},
    }


def test_measurements_status_filter(client, upload):
    file_id = upload("survey.kml", mixed_kml()).json()["id"]
    body = client.get(f"/api/files/{file_id}/measurements/?status=measured").json()
    assert body["total"] == 2
    assert body["summary"]["total_features"] == 4  # summary always covers the whole file
    assert client.get(f"/api/files/{file_id}/measurements/?status=bad").status_code == 422


def test_projected_shapefile_measured_natively(client, upload):
    square = [(500000, 1800000), (500000, 1800100), (500100, 1800100), (500100, 1800000), (500000, 1800000)]
    data = make_shapefile_zip(shapefile.POLYGON, [("poly", [square])], prj=prj_for(32644))
    file_id = upload("utm.zip", data).json()["id"]
    assert client.get(f"/api/files/{file_id}/").json()["crs"] == "EPSG:32644"
    m = client.get(f"/api/files/{file_id}/measurements/").json()["items"][0]
    assert m["area_m2"] == 10000.0
    assert m["perimeter_m"] == 400.0
    assert m["measurement_crs"] == "EPSG:32644"


def test_web_mercator_shapefile_not_measured_in_mercator_units(client, upload):
    from pyproj import Transformer
    t = Transformer.from_crs(4326, 3857, always_xy=True)
    lonlat = [(10.0, 60.0), (10.0, 60.1), (10.1, 60.1), (10.1, 60.0), (10.0, 60.0)]
    merc = [t.transform(x, y) for x, y in lonlat]
    data = make_shapefile_zip(shapefile.POLYGON, [("poly", [merc])], prj=prj_for(3857))
    file_id = upload("merc.zip", data).json()["id"]
    m = client.get(f"/api/files/{file_id}/measurements/").json()["items"][0]
    true_area = abs(GEOD.geometry_area_perimeter(Polygon(lonlat))[0])
    assert m["area_m2"] == pytest.approx(true_area, rel=2e-3)
    assert m["measurement_crs"] == "EPSG:32632"


def test_shapefile_without_prj_reports_assumption(client, upload):
    data = make_shapefile_zip(shapefile.POLYLINE, [("line", [LINE_LONLAT])], prj=None)
    body = upload("noprj.zip", data).json()
    assert body["crs"] == "EPSG:4326"
    assert body["crs_assumed"] is True
    assert body["warnings"]
    m = client.get(f"/api/files/{body['id']}/measurements/").json()["items"][0]
    assert m["length_m"] == pytest.approx(LINE_TRUE_LENGTH, rel=2e-3)


def test_unknown_crs_completes_but_measurements_are_errors(client, upload):
    square = [(500000, 1800000), (500000, 1800100), (500100, 1800100), (500000, 1800000)]
    data = make_shapefile_zip(shapefile.POLYGON, [("poly", [square])], prj=None)
    body = upload("mystery.zip", data).json()
    assert body["status"] == "COMPLETED"
    assert body["crs"] is None
    m = client.get(f"/api/files/{body['id']}/measurements/").json()
    assert m["items"][0]["status"] == "error"
    assert m["summary"]["errors"] == 1


def test_bad_features_do_not_fail_the_upload(client, upload):
    kml = make_kml(
        placemark("<Point><coordinates>oops</coordinates></Point>", name="Bad"),
        placemark(kml_polygon(SQUARE_LONLAT), name="Good"),
    )
    body = upload("partial.kml", kml).json()
    assert body["status"] == "COMPLETED"
    items = client.get(f"/api/files/{body['id']}/measurements/").json()["items"]
    assert items[0]["status"] == "error" and "Malformed" in items[0]["message"]
    assert items[1]["status"] == "measured"


def test_null_shape_in_shapefile(client, upload):
    data = make_shapefile_zip(shapefile.POLYGON, [("poly", [SQUARE_LONLAT]), ("null", None)])
    body = upload("withnull.zip", data).json()
    items = client.get(f"/api/files/{body['id']}/measurements/").json()["items"]
    assert [i["status"] for i in items] == ["measured", "error"]
