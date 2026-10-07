from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .errors import InvalidFileError
from .models import Feature, FileStatus, GeoFile, MeasurementStatus
from .processing import process_upload
from .readers import detect_file_type
from .schemas import (
    FeatureList,
    FeatureOut,
    FileList,
    FileOut,
    MeasurementList,
    MeasurementOut,
    MeasurementSummary,
)

router = APIRouter(prefix="/api")


def get_db(request: Request):
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def _get_file_or_404(db: Session, file_id: str) -> GeoFile:
    geo_file = db.get(GeoFile, file_id)
    if geo_file is None:
        raise HTTPException(404, detail=f"File {file_id} not found")
    return geo_file


def _file_out(f: GeoFile, request: Request) -> FileOut:
    return FileOut(
        id=f.id,
        filename=f.filename,
        file_type=f.file_type,
        size_bytes=f.size_bytes,
        status=f.status,
        feature_count=f.feature_count,
        crs=f.crs,
        crs_name=f.crs_name,
        crs_assumed=f.crs_assumed,
        warnings=f.warnings or [],
        error=f.error,
        created_at=f.created_at,
        processed_at=f.processed_at,
        links={
            "self": str(request.url_for("get_file", file_id=f.id)),
            "features": str(request.url_for("list_features", file_id=f.id)),
            "measurements": str(request.url_for("get_measurements", file_id=f.id)),
        },
    )


def _round(v: float | None, digits: int) -> float | None:
    return None if v is None else round(v, digits)


def _measurement_out(feat: Feature) -> MeasurementOut:
    return MeasurementOut(
        feature_id=feat.feature_index,
        geometry_type=feat.geometry_type,
        status=feat.measurement_status,
        area_m2=_round(feat.area_m2, 2),
        area_hectares=_round(feat.area_m2 / 10_000 if feat.area_m2 is not None else None, 4),
        area_km2=_round(feat.area_m2 / 1_000_000 if feat.area_m2 is not None else None, 6),
        perimeter_m=_round(feat.perimeter_m, 2),
        length_m=_round(feat.length_m, 2),
        length_km=_round(feat.length_m / 1000 if feat.length_m is not None else None, 4),
        measurement_crs=feat.measurement_crs,
        message=feat.measurement_message,
    )


def _ensure_completed(geo_file: GeoFile) -> None:
    if geo_file.status != FileStatus.COMPLETED:
        raise HTTPException(409, detail=f"File status is {geo_file.status.value}: {geo_file.error or 'not processed'}")


# ---------- endpoints ----------

@router.post("/files/", status_code=201, response_model=FileOut,
             responses={400: {}, 413: {}, 422: {"model": FileOut}})
def upload_file(request: Request, response: Response, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a .zip (Shapefile), .kml or .kmz. The file is parsed and measured during the request."""
    settings = request.app.state.settings
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(400, detail="No filename provided")
    try:
        file_type = detect_file_type(filename)
    except InvalidFileError as exc:
        raise HTTPException(400, detail=str(exc))

    # Read at most limit+1 bytes so an oversized upload never fully lands in memory.
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, detail=f"File exceeds {settings.max_upload_bytes // (1024 * 1024)} MB limit")
    if not data:
        raise HTTPException(400, detail="Uploaded file is empty")

    geo_file = process_upload(db, settings, filename, file_type, data)
    body = _file_out(geo_file, request)
    location = body.links["self"]

    if geo_file.status == FileStatus.FAILED:
        # Still return the record (with its id and error) so the failure is inspectable later.
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"), headers={"Location": location})
    response.headers["Location"] = location
    return body


@router.get("/files/", response_model=FileList)
def list_files(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count()).select_from(GeoFile))
    files = db.scalars(select(GeoFile).order_by(GeoFile.created_at.desc()).limit(limit).offset(offset)).all()
    return FileList(items=[_file_out(f, request) for f in files], total=total, limit=limit, offset=offset)


@router.get("/files/{file_id}/", response_model=FileOut, name="get_file")
def get_file(file_id: str, request: Request, db: Session = Depends(get_db)):
    return _file_out(_get_file_or_404(db, file_id), request)


@router.delete("/files/{file_id}/", status_code=204)
def delete_file(file_id: str, db: Session = Depends(get_db)):
    db.delete(_get_file_or_404(db, file_id))
    db.commit()
    return Response(status_code=204)


@router.get("/files/{file_id}/features/", response_model=FeatureList, name="list_features")
def list_features(
    file_id: str,
    geometry_type: str | None = Query(None, description="e.g. Polygon, LineString, Point"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Every feature with its geometry (GeoJSON, in the file's CRS) and attributes."""
    geo_file = _get_file_or_404(db, file_id)
    _ensure_completed(geo_file)

    conditions = [Feature.file_id == file_id]
    if geometry_type:
        conditions.append(Feature.geometry_type == geometry_type)
    total = db.scalar(select(func.count()).select_from(Feature).where(*conditions))
    rows = db.scalars(
        select(Feature).where(*conditions).order_by(Feature.feature_index).limit(limit).offset(offset)
    ).all()
    items = [
        FeatureOut(
            feature_id=f.feature_index,
            source_id=f.source_id,
            geometry_type=f.geometry_type,
            crs=geo_file.crs,
            geometry=f.geometry,
            properties=f.properties or {},
        )
        for f in rows
    ]
    return FeatureList(file_id=file_id, items=items, total=total, limit=limit, offset=offset)


@router.get("/files/{file_id}/measurements/", response_model=MeasurementList, name="get_measurements")
def get_measurements(
    file_id: str,
    status: MeasurementStatus | None = Query(None, description="Filter, e.g. ?status=measured"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Area (polygons) / length (lines) per feature, plus file-wide totals."""
    geo_file = _get_file_or_404(db, file_id)
    _ensure_completed(geo_file)

    conditions = [Feature.file_id == file_id]
    if status is not None:
        conditions.append(Feature.measurement_status == status)
    total = db.scalar(select(func.count()).select_from(Feature).where(*conditions))
    rows = db.scalars(
        select(Feature).where(*conditions).order_by(Feature.feature_index).limit(limit).offset(offset)
    ).all()

    return MeasurementList(
        file_id=file_id,
        source_crs=geo_file.crs,
        units={"area": "m²", "length": "m", "perimeter": "m"},
        summary=_summary(db, file_id),
        items=[_measurement_out(f) for f in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _summary(db: Session, file_id: str) -> MeasurementSummary:
    """Aggregates over *all* features (not just the current page) in SQL."""
    def count_status(s: MeasurementStatus):
        return func.sum(case((Feature.measurement_status == s, 1), else_=0))

    row = db.execute(
        select(
            func.count(),
            count_status(MeasurementStatus.MEASURED),
            count_status(MeasurementStatus.NOT_APPLICABLE),
            count_status(MeasurementStatus.UNSUPPORTED),
            count_status(MeasurementStatus.ERROR),
            func.coalesce(func.sum(Feature.area_m2), 0.0),
            func.coalesce(func.sum(Feature.length_m), 0.0),
        ).where(Feature.file_id == file_id)
    ).one()
    by_type = db.execute(
        select(func.coalesce(Feature.geometry_type, "None"), func.count())
        .where(Feature.file_id == file_id)
        .group_by(Feature.geometry_type)
    ).all()
    return MeasurementSummary(
        total_features=row[0],
        measured=row[1] or 0,
        not_applicable=row[2] or 0,
        unsupported=row[3] or 0,
        errors=row[4] or 0,
        total_area_m2=round(row[5], 2),
        total_length_m=round(row[6], 2),
        by_geometry_type={t: n for t, n in by_type},
    )
