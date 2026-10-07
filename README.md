# Geospatial File Measurement API

A FastAPI service that accepts a **Shapefile (.zip)**, **KML** or **KMZ** file, extracts every
feature (ID, geometry type, geometry, CRS, attributes) and calculates **area** for polygons and
**length** for lines. Each feature is reprojected to a suitable metric projection first, so
latitude/longitude degrees are never measured directly.

**Stack:** Python 3.11+ · FastAPI · SQLAlchemy 2 + SQLite · Shapely 2 · pyproj · pyshp · defusedxml · pytest

---

## Contents
1. [Setup](#setup)
2. [API](#api)
3. [Architecture](#architecture)
4. [Design decisions](#design-decisions)
5. [Testing](#testing)
6. [Learnings](#learnings)
7. [Future scope](#future-scope)

---

## Setup

```bash
git clone https://github.com/<your-username>/geo-measurement-api.git
cd geo-measurement-api

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn app.main:create_app --factory --reload
```

- API: http://127.0.0.1:8000
- Swagger UI (upload files from the browser): http://127.0.0.1:8000/docs

No GDAL or system libraries are required; every dependency installs from pip wheels.

Optional environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./geofiles.db` | Any SQLAlchemy URL (e.g. PostgreSQL) |
| `MAX_UPLOAD_MB` | `50` | Max upload size |
| `MAX_UNCOMPRESSED_MB` | `200` | Max total size inside a ZIP/KMZ (zip-bomb guard) |
| `MAX_FEATURES` | `100000` | Max features per file |

Sample files are in `sample_data/` (regenerate with `python scripts/make_samples.py`):

| File | Contents |
|---|---|
| `survey.kml` | Polygon, LineString, Point, MultiGeometry, and a `gx:Track` (unsupported) |
| `parcels_wgs84.zip` | Polygons in EPSG:4326, one with a hole |
| `plots_utm44n.zip` | Polygons already projected (EPSG:32644): exactly 10,000 m² and 10,000 m² |
| `roads_wgs84.zip` | LineStrings in EPSG:4326 |

---

## API

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/files/` | Upload and process a file (multipart field `file`) |
| GET | `/api/files/` | List uploaded files (`limit`, `offset`) |
| GET | `/api/files/{id}/` | File information |
| GET | `/api/files/{id}/features/` | Features: ID, type, geometry (GeoJSON), CRS, properties (`geometry_type`, `limit`, `offset`) |
| GET | `/api/files/{id}/measurements/` | Area/length per feature + totals (`status`, `limit`, `offset`) |
| DELETE | `/api/files/{id}/` | Delete a file and its features |
| GET | `/health` | Liveness check |

### Upload — `POST /api/files/`

```bash
curl -F "file=@sample_data/survey.kml" http://127.0.0.1:8000/api/files/
curl -F "file=@sample_data/parcels_wgs84.zip" http://127.0.0.1:8000/api/files/
```

**201 Created** (`Location` header points to the file):

```json
{
  "id": "717fa8bb-0284-4ba1-bb79-fb9c007f7a4b",
  "filename": "survey.kml",
  "file_type": "kml",
  "size_bytes": 1541,
  "status": "COMPLETED",
  "feature_count": 5,
  "crs": "EPSG:4326",
  "crs_name": "WGS 84",
  "crs_assumed": false,
  "warnings": [],
  "error": null,
  "created_at": "2026-10-07T11:39:44.068881Z",
  "processed_at": "2026-10-07T11:39:44.081596Z",
  "links": {
    "self": "http://127.0.0.1:8000/api/files/717fa8bb-.../",
    "features": "http://127.0.0.1:8000/api/files/717fa8bb-.../features/",
    "measurements": "http://127.0.0.1:8000/api/files/717fa8bb-.../measurements/"
  }
}
```

Error responses:

| Code | When | Body |
|---|---|---|
| 400 | Wrong extension, empty file, no filename | `{"detail": "Unsupported file type 'x.geojson'. Upload a .zip (Shapefile), .kml or .kmz file"}` |
| 413 | Upload over `MAX_UPLOAD_MB` | `{"detail": "File exceeds 50 MB limit"}` |
| 422 | File couldn't be parsed (corrupt ZIP, missing .shx/.dbf, invalid XML, ...) | The file record with `"status": "FAILED"` and `"error"`, kept so it can be looked up later |

### File information — `GET /api/files/{id}/`

Returns the same object as the upload response.

### Features — `GET /api/files/{id}/features/`

```bash
curl "http://127.0.0.1:8000/api/files/<id>/features/?limit=2"
```

```json
{
  "file_id": "717fa8bb-...",
  "items": [
    {
      "feature_id": 0,
      "source_id": "field-1",
      "geometry_type": "Polygon",
      "crs": "EPSG:4326",
      "geometry": {"type": "Polygon", "coordinates": [[[80.62, 16.51], [80.62, 16.515], [80.626, 16.515], [80.626, 16.51], [80.62, 16.51]]]},
      "properties": {"name": "North field", "crop": "Paddy"}
    },
    {
      "feature_id": 1,
      "source_id": "road-1",
      "geometry_type": "LineString",
      "crs": "EPSG:4326",
      "geometry": {"type": "LineString", "coordinates": [[80.62, 16.506], [80.64, 16.506], [80.648, 16.512]]},
      "properties": {"name": "Access road"}
    }
  ],
  "total": 5, "limit": 2, "offset": 0
}
```

- `feature_id`: 0-based position in the file.
- `source_id`: the KML `id` attribute, or the shapefile record number.
- `geometry`: GeoJSON, with coordinates in the file's own CRS.

### Measurements — `GET /api/files/{id}/measurements/`

```bash
curl http://127.0.0.1:8000/api/files/<id>/measurements/
curl "http://127.0.0.1:8000/api/files/<id>/measurements/?status=measured"
```

```json
{
  "file_id": "717fa8bb-...",
  "source_crs": "EPSG:4326",
  "units": {"area": "m²", "length": "m", "perimeter": "m"},
  "summary": {
    "total_features": 5, "measured": 3, "not_applicable": 1, "unsupported": 1, "errors": 0,
    "total_area_m2": 365961.77,
    "total_length_m": 3215.8,
    "by_geometry_type": {"LineString": 1, "MultiPolygon": 1, "Point": 1, "Polygon": 1, "Track": 1}
  },
  "items": [
    {"feature_id": 0, "geometry_type": "Polygon", "status": "measured",
     "area_m2": 354156.49, "area_hectares": 35.4156, "area_km2": 0.354156, "perimeter_m": 2386.82,
     "length_m": null, "length_km": null, "measurement_crs": "EPSG:32644", "message": null},
    {"feature_id": 1, "geometry_type": "LineString", "status": "measured",
     "area_m2": null, "area_hectares": null, "area_km2": null, "perimeter_m": null,
     "length_m": 3215.8, "length_km": 3.2158, "measurement_crs": "EPSG:32644", "message": null},
    {"feature_id": 2, "geometry_type": "Point", "status": "not_applicable",
     "area_m2": null, "length_m": null, "measurement_crs": null, "message": "Points have no area or length"},
    {"feature_id": 3, "geometry_type": "MultiPolygon", "status": "measured",
     "area_m2": 11805.28, "area_hectares": 1.1805, "perimeter_m": 742.09, "measurement_crs": "EPSG:32644"},
    {"feature_id": 4, "geometry_type": "Track", "status": "unsupported",
     "area_m2": null, "length_m": null, "message": "Geometry type 'Track' is not supported"}
  ],
  "total": 5, "limit": 100, "offset": 0
}
```
*(Some null fields are trimmed above for brevity.)*

The `summary` always covers the whole file, regardless of `status`, `limit` or `offset`.

| `status` | Meaning |
|---|---|
| `measured` | Polygon/MultiPolygon → `area_m2` and `perimeter_m`; LineString/MultiLineString/LinearRing → `length_m` |
| `not_applicable` | Point/MultiPoint; nothing to measure |
| `unsupported` | GeometryCollection (mixed types), KML `gx:Track`/`Model` |
| `error` | Null/empty/malformed geometry, or the file's CRS is unknown. `message` says which |

---

## Architecture

### Application structure

```
app/
├── main.py              App factory (create_app): settings, DB, routes
├── config.py            Settings from environment variables
├── database.py          SQLAlchemy engine
├── models.py            GeoFile + Feature tables, status enums
├── schemas.py           Pydantic response models
├── api.py               HTTP layer only: validation, status codes, pagination
├── processing.py        Upload pipeline: read -> measure -> persist
├── errors.py            InvalidFileError (user-facing parse errors)
├── readers/             Parsing only (bytes -> Shapely geometries + attributes + CRS)
│   ├── __init__.py      Picks a reader by extension
│   ├── base.py          RawFeature / ReadResult (format-independent)
│   ├── shapefile_reader.py
│   ├── kml_reader.py    KML + KMZ
│   └── zip_utils.py     Safe in-memory ZIP access
└── measurement/         Measuring only, no knowledge of file formats
    ├── crs.py           CRS description and choice of projection
    └── calculator.py    measure(geometry, crs) -> Measurement
tests/                   98 tests (readers, measurement accuracy, API)
scripts/make_samples.py  Generates sample_data/
```

Each layer depends only on the one below it. Readers know nothing about measuring, and the
calculator knows nothing about file formats. So adding GeoJSON or GeoPackage support means adding
a reader, and changing the projection strategy means editing `crs.py`; nothing else changes.

### File-processing flow

```
POST /api/files/
  │
  ├─ 1. Validate extension (.zip / .kml / .kmz) ─────────────── 400
  ├─ 2. Read at most MAX_UPLOAD_MB + 1 bytes ────────────────── 413
  ├─ 3. Save GeoFile row (status=PROCESSING)
  ├─ 4. Reader → ReadResult(features, crs, warnings)
  │      ZIP:  open in memory, check total uncompressed size, find exactly one .shp
  │            (+ .shx, .dbf required; .prj, .cpg optional), parse with pyshp
  │      KML:  parse with defusedxml, find every <Placemark> (in any Folder/Document),
  │            convert geometry, read name/description/ExtendedData
  │      KMZ:  open ZIP → doc.kml (or first .kml) → KML reader
  ├─ 5. For each feature → measure(geometry, crs)
  ├─ 6. Save Feature rows; GeoFile status=COMPLETED ────────────────── 201
  └─    InvalidFileError → status=FAILED + error message ──────────── 422
```

A bad **feature** (malformed coordinates, NULL shape, unsupported type) never fails the
**file**. It is stored with a status and message, and the other features are processed normally.
Only a file that can't be read at all (corrupt ZIP, invalid XML, missing .dbf) is marked
`FAILED`.

### Measurement calculation flow

```
measure(geometry, crs)
  ├─ None / empty geometry ...................... error
  ├─ Point, MultiPoint .......................... not_applicable
  ├─ not Polygon/Line type ...................... unsupported
  ├─ CRS unknown ................................ error (never guess)
  ├─ drop Z (altitude)
  ├─ invalid polygon (e.g. self-intersecting) ... make_valid() + note in message
  ├─ project to a metric CRS (see CRS handling)
  └─ Polygon → area (m²) + perimeter (m)   |   Line → length (m)
```

Measurements are calculated once, at upload, and stored, so `GET .../measurements/` is a plain
database read. Totals and counts are SQL aggregates over all of the file's features.

### CRS handling

**Detecting the source CRS**
- **KML/KMZ:** the OGC KML 2.2 specification fixes coordinates to WGS84 lon/lat, so the CRS is
  always EPSG:4326.
- **Shapefile:** parsed from the `.prj` WKT with pyproj and reported as `EPSG:xxxx` when it can be
  identified. If the `.prj` is missing or unreadable:
  - if every coordinate is within ±180 / ±90, EPSG:4326 is assumed, with `crs_assumed: true` and a
    warning;
  - otherwise the CRS is reported as unknown and measurements return `error`. A wrong guess would
    produce confidently wrong numbers.

**Choosing the measurement projection**

| Source CRS | Strategy | Why |
|---|---|---|
| Geographic (EPSG:4326, NAD83, …) | Reproject **each feature** to the **UTM zone of its centroid** (UPS above 84°N / below 80°S) | Degrees aren't distances. Within its 6° zone UTM's scale error is ≤ ~0.1% |
| Projected, scale-preserving (UTM, state plane, national grids) | Measure **natively**, converting the axis unit to metres (e.g. US survey feet) | The data's author already chose an appropriate projection; reprojecting would only add error |
| Mercator family (Web Mercator EPSG:3857, EPSG:3395) | Treat like geographic: → WGS84 → local UTM | These are projected, but they inflate areas by about 4× at 60° latitude; measuring in them is a common mistake |

`measurement_crs` on every measurement shows which projection was used.

**Accuracy check.** The tests compare results against pyproj's geodesic calculation on the WGS84
ellipsoid, the exact answer, for features in India, London, Sydney and Helsinki. All are within
0.2%, and typically within 0.08%. Another test confirms that a Web Mercator polygon at 60°N measured
naively would be 4× too large, while the API's answer matches the geodesic value.

Transformers use `always_xy=True`, so coordinates are always (lon, lat) / (x, y). EPSG:4326's
official axis order is (lat, lon), a classic source of swapped coordinates.

---

## Design decisions

**FastAPI over Django/DRF.** The service is a small, API-only app with file upload and JSON
output, and needs no admin, templates or auth. FastAPI gives typed request/response models,
automatic OpenAPI docs (useful for uploading from `/docs`), and less boilerplate. The app-factory
pattern (`create_app(settings)`) gives each test its own database.

**pyshp + Shapely + pyproj instead of GeoPandas/Fiona/GDAL.** GDAL is the most capable option, but it
is a heavy native dependency that often fails to install on Windows and in slim containers. With
only two formats to support, pyshp (pure Python) and a small KML parser handle them fully, and the
project installs with `pip install`. *Trade-off:* adding many more formats (GeoPackage, GML, FGB)
would justify switching readers to Fiona/pyogrio, and only `app/readers/` would change.

**Own KML parser on defusedxml rather than fastkml.** It's about 200 lines, handles namespaces
(KML 2.1, 2.2 or none), nested Folders, MultiGeometry, holes and ExtendedData, and is hardened
against XXE and entity-expansion ("billion laughs") attacks, which matters for user uploads.

**UTM per feature vs. alternatives for measuring.**
- *One projection for the whole file:* fails for files spanning large areas.
- *Geodesic calculation on the ellipsoid (`pyproj.Geod`):* the most accurate, with no projection
  needed. But the brief asks to transform to a projected CRS, and UTM results are explainable and
  reproducible in QGIS. I use geodesic results in the tests as the reference.
- *Equal-area projection (e.g. LAEA centred on the feature):* exact area at any size, but not
  suited to lengths. Two strategies would add complexity for little gain at parcel/route scale.
- **Chosen:** UTM zone of each feature's centroid. It is standard, has an EPSG code, and is
  accurate to ~0.1% within a zone.

**Synchronous processing in the upload request.** Typical survey/parcel files are parsed and
measured in milliseconds to seconds, so the client gets a final result immediately with no queue
infrastructure. The model still has a `status` field (`PROCESSING` → `COMPLETED`/`FAILED`), so
moving to background processing (Celery/RQ, returning 202) would be a small change to `api.py`.

**Measure once at upload and store the results.** Reads are frequent and uploads happen once.
Storing measurements makes GETs cheap and lets SQL compute totals.

**Partial failure is per feature.** A malformed placemark or NULL shape shouldn't cost the user
their other 999 features. Problems are recorded per feature with a status and message, and only an
unreadable file fails as a whole.

**Failed uploads are kept (422 + record).** The client gets an ID and a clear `error` it can look
up later, rather than a bare error.

**Security on uploads.** Size cap read without buffering everything; ZIPs read in memory, never
extracted (no zip-slip); total uncompressed size checked (zip bombs); a per-file feature limit;
defusedxml for XML.

**SQLite + SQLAlchemy.** Zero setup to run locally, and portable to PostgreSQL via `DATABASE_URL`.
Geometry is stored as GeoJSON in a JSON column, which is enough because all spatial work happens
in Python. PostGIS would make sense for spatial queries (see future scope).

**Invalid polygons are repaired, not rejected.** Self-intersecting "bow-tie" polygons are common in
hand-digitised data. `make_valid()` repairs them, and the measurement's `message` says so, so the
user knows.

---

## Testing

```bash
pytest -q
```

98 tests, each using a temporary database. Test data is generated in memory
(`tests/factories.py`).

| File | Covers |
|---|---|
| `tests/test_measurement.py` | UTM zone selection; which CRSs are reprojected; accuracy against geodesic area/length in 4 regions; native projected measurement (metres and US feet); Web Mercator; holes, multi-geometries, 3D; points, collections, empty geometries, unknown CRS, self-intersecting polygons |
| `tests/test_readers.py` | Shapefile attributes/CRS/.cpg encoding, folders inside ZIPs, macOS junk files, missing .prj/.shx/.dbf, NULL shapes, multiple shapefiles, corrupt files, zip bombs, feature limit; KML geometries/holes/MultiGeometry/ExtendedData/namespaces, malformed coordinates, XXE and entity expansion; KMZ |
| `tests/test_api.py` | Upload (KML, ZIP, KMZ), 400/413/422 cases, file info, list/delete, features with filtering and pagination, measurements and summary, status filter, projected/Mercator/no-.prj/unknown-CRS shapefiles, partial failures |

---

## Learnings

- **"Projected" doesn't mean "safe to measure".** Web Mercator is a projected CRS in metres, yet
  its areas are about 4× too large at 60° latitude. Choosing a projection depends on its
  properties (conformal, equal-area, scale error), not just whether its unit is metres.
- **Axis order is a real trap.** EPSG:4326 is officially (lat, lon), but almost all data is stored
  as (lon, lat). `always_xy=True` in pyproj avoids silently swapped coordinates.
- **Shapefiles are really several files.** `.shp` holds the geometry, `.dbf` the attributes, `.shx`
  the index; `.prj` (CRS) and `.cpg` (text encoding) are optional, and losing them is common.
  Handling a missing `.prj` meant deciding when it is reasonable to assume and when to refuse.
- **Verify against a reference, not just "looks plausible".** Comparing UTM results with pyproj's
  geodesic calculations turned "it returns a number" into "it returns the right number within 0.1%".
- **Uploaded files are untrusted input.** XML entity attacks, zip bombs and path traversal are
  real risks in a file-processing API, and each has a simple defence.
- **Real data is messy.** Self-intersecting polygons, NULL shapes, mixed MultiGeometries, altitude
  values and junk macOS files all appear in practice. Reporting problems per feature makes the API
  useful instead of fragile.

## Future scope

- **More formats:** GeoJSON, GeoPackage, GML, FlatGeobuf, via Fiona/pyogrio behind the same reader
  interface.
- **Background processing** for very large files: Celery/RQ worker, `202 Accepted`, and progress on
  the status endpoint.
- **PostGIS** for spatial queries (bounding-box filters, "features within X km") and `ST_Area` on
  the geography type as a cross-check.
- **Very large features:** geodesic or equal-area measurement for features spanning several UTM
  zones; correct handling of features crossing the antimeridian (±180°).
- **Choice of method and units:** `?method=geodesic|projected`, `?units=acres|ft`.
- **Multi-layer uploads:** several shapefiles in one ZIP, or a KML's folders as separate layers.
- **Store original files** (object storage such as S3) to allow reprocessing and downloads, plus
  GeoJSON/CSV export of the results.
- **Authentication**, per-user file ownership, and rate limiting.
- **Deployment:** Dockerfile, Alembic migrations, CI running the tests on every push.
