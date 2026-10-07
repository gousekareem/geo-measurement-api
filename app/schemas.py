from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel

from .models import FileStatus, FileType, MeasurementStatus

# SQLite drops tzinfo; all stored timestamps are UTC.
UTCDatetime = Annotated[datetime, AfterValidator(lambda v: v if v.tzinfo else v.replace(tzinfo=timezone.utc))]


class FileOut(BaseModel):
    id: str
    filename: str
    file_type: FileType
    size_bytes: int
    status: FileStatus
    feature_count: int
    crs: str | None
    crs_name: str | None
    crs_assumed: bool
    warnings: list[str]
    error: str | None
    created_at: UTCDatetime
    processed_at: UTCDatetime | None
    links: dict[str, str]


class FileList(BaseModel):
    items: list[FileOut]
    total: int
    limit: int
    offset: int


class FeatureOut(BaseModel):
    feature_id: int            # 0-based index within the file
    source_id: str | None      # KML id attribute / shapefile record number
    geometry_type: str | None
    crs: str | None
    geometry: dict[str, Any] | None  # GeoJSON geometry, coordinates in `crs`
    properties: dict[str, Any]


class FeatureList(BaseModel):
    file_id: str
    items: list[FeatureOut]
    total: int
    limit: int
    offset: int


class MeasurementOut(BaseModel):
    feature_id: int
    geometry_type: str | None
    status: MeasurementStatus
    area_m2: float | None = None
    area_hectares: float | None = None
    area_km2: float | None = None
    perimeter_m: float | None = None
    length_m: float | None = None
    length_km: float | None = None
    measurement_crs: str | None = None
    message: str | None = None


class MeasurementSummary(BaseModel):
    total_features: int
    measured: int
    not_applicable: int
    unsupported: int
    errors: int
    total_area_m2: float
    total_length_m: float
    by_geometry_type: dict[str, int]


class MeasurementList(BaseModel):
    file_id: str
    source_crs: str | None
    units: dict[str, str]
    summary: MeasurementSummary
    items: list[MeasurementOut]
    total: int
    limit: int
    offset: int
