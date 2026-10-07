"""Builds test Shapefile ZIPs and KML documents in memory."""
import io
import zipfile

import shapefile
from pyproj import CRS

WGS84_PRJ = CRS.from_epsg(4326).to_wkt("WKT1_ESRI")

# Small square near Vijayawada (about 10.6 km x 11.1 km)
SQUARE_LONLAT = [(80.6, 16.5), (80.6, 16.6), (80.7, 16.6), (80.7, 16.5), (80.6, 16.5)]
LINE_LONLAT = [(80.6, 16.5), (80.7, 16.6)]


def prj_for(epsg: int) -> str:
    return CRS.from_epsg(epsg).to_wkt("WKT1_ESRI")


def make_shapefile_zip(
    shape_type: int,
    shapes: list,
    records: list[dict] | None = None,
    prj: str | None = WGS84_PRJ,
    name: str = "layer",
    folder: str = "",
    omit: tuple[str, ...] = (),
    extra: dict[str, bytes] | None = None,
    cpg: str | None = None,
) -> bytes:
    """shapes: list of ("poly", rings) | ("line", parts) | ("point", (x, y)) | ("null", None)."""
    shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shape_type)
    records = records or [{"name": f"feature {i}"} for i in range(len(shapes))]
    fields = list(records[0].keys())
    for f in fields:
        sample = records[0][f]
        if isinstance(sample, (int, float)):
            w.field(f, "N", decimal=2)
        else:
            w.field(f, "C")
    for (kind, value), rec in zip(shapes, records):
        if kind == "poly":
            w.poly(value)
        elif kind == "line":
            w.line(value)
        elif kind == "point":
            w.point(*value)
        else:
            w.null()
        w.record(*[rec[f] for f in fields])
    w.close()

    files = {".shp": shp.getvalue(), ".shx": shx.getvalue(), ".dbf": dbf.getvalue()}
    if prj is not None:
        files[".prj"] = prj.encode()
    if cpg is not None:
        files[".cpg"] = cpg.encode()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for ext, content in files.items():
            if ext not in omit:
                zf.writestr(f"{folder}{name}{ext}", content)
        for path, content in (extra or {}).items():
            zf.writestr(path, content)
    return buf.getvalue()


def coords(points) -> str:
    return " ".join(f"{x},{y},0" for x, y in points)


def make_kml(*placemarks: str, namespace: str = "http://www.opengis.net/kml/2.2") -> bytes:
    body = "\n".join(placemarks)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="{namespace}" xmlns:gx="http://www.google.com/kml/ext/2.2">
  <Document>
    <name>Test</name>
    <Folder>
      {body}
    </Folder>
  </Document>
</kml>""".encode()


def placemark(geometry_xml: str, name: str = "pm", pid: str | None = None, extended: str = "") -> str:
    id_attr = f' id="{pid}"' if pid else ""
    return f"<Placemark{id_attr}><name>{name}</name>{extended}{geometry_xml}</Placemark>"


def kml_polygon(outer, holes=()) -> str:
    inner = "".join(
        f"<innerBoundaryIs><LinearRing><coordinates>{coords(h)}</coordinates></LinearRing></innerBoundaryIs>"
        for h in holes
    )
    return (
        f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords(outer)}</coordinates>"
        f"</LinearRing></outerBoundaryIs>{inner}</Polygon>"
    )


def kml_line(points) -> str:
    return f"<LineString><coordinates>{coords(points)}</coordinates></LineString>"


def kml_point(x, y) -> str:
    return f"<Point><coordinates>{x},{y},0</coordinates></Point>"


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()
