"""Generates the files in sample_data/ (run: python scripts/make_samples.py)."""
import io
import sys
import zipfile
from pathlib import Path

import shapefile
from pyproj import CRS

OUT = Path(__file__).resolve().parent.parent / "sample_data"


def write_shapefile_zip(path: Path, shape_type: int, epsg: int, fields: list[tuple], rows: list[tuple]):
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shape_type)
    for f in fields:
        w.field(*f)
    for geometry, record in rows:
        kind, value = geometry
        getattr(w, kind)(value) if kind != "point" else w.point(*value)
        w.record(*record)
    w.close()
    stem = path.stem
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{stem}.shp", shp.getvalue())
        zf.writestr(f"{stem}.shx", shx.getvalue())
        zf.writestr(f"{stem}.dbf", dbf.getvalue())
        zf.writestr(f"{stem}.prj", CRS.from_epsg(epsg).to_wkt("WKT1_ESRI"))
        zf.writestr(f"{stem}.cpg", "UTF-8")


def main():
    OUT.mkdir(exist_ok=True)

    # 1. Farm parcels in WGS84 (lon/lat) near Vijayawada
    write_shapefile_zip(
        OUT / "parcels_wgs84.zip", shapefile.POLYGON, 4326,
        [("parcel_id", "C", 10), ("owner", "C", 40), ("crop", "C", 20)],
        [
            (("poly", [[(80.6200, 16.5100), (80.6200, 16.5150), (80.6260, 16.5150), (80.6260, 16.5100), (80.6200, 16.5100)]]), ("P-001", "Ravi Kumar", "Paddy")),
            (("poly", [[(80.6270, 16.5100), (80.6270, 16.5140), (80.6320, 16.5140), (80.6320, 16.5100), (80.6270, 16.5100)],
                       [(80.6285, 16.5110), (80.6305, 16.5110), (80.6305, 16.5125), (80.6285, 16.5125), (80.6285, 16.5110)]]), ("P-002", "Lakshmi Devi", "Cotton")),
        ],
    )

    # 2. Same idea but already in a projected CRS (UTM zone 44N, metres)
    write_shapefile_zip(
        OUT / "plots_utm44n.zip", shapefile.POLYGON, 32644,
        [("plot", "C", 10)],
        [
            (("poly", [[(500000, 1825000), (500000, 1825100), (500100, 1825100), (500100, 1825000), (500000, 1825000)]]), ("100x100m",)),
            (("poly", [[(500200, 1825000), (500200, 1825050), (500400, 1825050), (500400, 1825000), (500200, 1825000)]]), ("200x50m",)),
        ],
    )

    # 3. Roads as lines
    write_shapefile_zip(
        OUT / "roads_wgs84.zip", shapefile.POLYLINE, 4326,
        [("road", "C", 40), ("lanes", "N", 2, 0)],
        [
            (("line", [[(80.6200, 16.5060), (80.6400, 16.5060), (80.6480, 16.5120)]]), ("Canal Road", 2)),
            (("line", [[(80.6300, 16.5000), (80.6300, 16.5200)]]), ("Temple Street", 1)),
        ],
    )

    # 4. KML with every case: polygon, line, point, multigeometry, unsupported track
    (OUT / "survey.kml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Document>
    <name>Site survey</name>
    <Placemark id="field-1">
      <name>North field</name>
      <ExtendedData><Data name="crop"><value>Paddy</value></Data></ExtendedData>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
        80.6200,16.5100,0 80.6200,16.5150,0 80.6260,16.5150,0 80.6260,16.5100,0 80.6200,16.5100,0
      </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>
    <Placemark id="road-1">
      <name>Access road</name>
      <LineString><coordinates>80.6200,16.5060,0 80.6400,16.5060,0 80.6480,16.5120,0</coordinates></LineString>
    </Placemark>
    <Placemark id="well-1">
      <name>Borewell</name>
      <Point><coordinates>80.6230,16.5120,0</coordinates></Point>
    </Placemark>
    <Placemark id="ponds">
      <name>Ponds</name>
      <MultiGeometry>
        <Polygon><outerBoundaryIs><LinearRing><coordinates>80.6300,16.5100 80.6300,16.5110 80.6310,16.5110 80.6300,16.5100</coordinates></LinearRing></outerBoundaryIs></Polygon>
        <Polygon><outerBoundaryIs><LinearRing><coordinates>80.6320,16.5100 80.6320,16.5110 80.6330,16.5110 80.6320,16.5100</coordinates></LinearRing></outerBoundaryIs></Polygon>
      </MultiGeometry>
    </Placemark>
    <Placemark id="gps-1">
      <name>Tractor GPS track</name>
      <gx:Track><when>2026-01-01T10:00:00Z</when><gx:coord>80.62 16.51 0</gx:coord></gx:Track>
    </Placemark>
  </Document>
</kml>
""", encoding="utf-8")

    print("Wrote:", *sorted(p.name for p in OUT.iterdir()), sep="\n  ", file=sys.stdout)


if __name__ == "__main__":
    main()
