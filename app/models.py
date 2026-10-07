import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FileStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FileType(str, enum.Enum):
    SHAPEFILE = "shapefile"
    KML = "kml"
    KMZ = "kmz"


class MeasurementStatus(str, enum.Enum):
    MEASURED = "measured"              # area or length computed
    NOT_APPLICABLE = "not_applicable"  # points: nothing to measure
    UNSUPPORTED = "unsupported"        # e.g. GeometryCollection, gx:Track
    ERROR = "error"                    # empty/malformed geometry, unknown CRS


def _enum(e):
    return SAEnum(e, native_enum=False, length=32, values_callable=lambda x: [m.value for m in x])


class GeoFile(Base):
    __tablename__ = "geo_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[FileType] = mapped_column(_enum(FileType))
    size_bytes: Mapped[int] = mapped_column(Integer)

    status: Mapped[FileStatus] = mapped_column(_enum(FileStatus), default=FileStatus.PROCESSING, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    crs: Mapped[str | None] = mapped_column(String(100), nullable=True)   # e.g. "EPSG:4326"
    crs_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crs_wkt: Mapped[str | None] = mapped_column(Text, nullable=True)      # full definition, used for measuring
    crs_assumed: Mapped[bool] = mapped_column(Boolean, default=False)     # True if no .prj and WGS84 was inferred
    feature_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    features: Mapped[list["Feature"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", order_by="Feature.feature_index"
    )


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("file_id", "feature_index", name="uq_feature_file_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("geo_files.id", ondelete="CASCADE"), index=True)
    feature_index: Mapped[int] = mapped_column(Integer)           # 0-based position in the file
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # KML id attr / shapefile record no.

    geometry_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    geometry: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # GeoJSON, in the file's CRS
    properties: Mapped[dict] = mapped_column(JSON, default=dict)

    measurement_status: Mapped[MeasurementStatus] = mapped_column(_enum(MeasurementStatus), index=True)
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    perimeter_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(String(100), nullable=True)
    measurement_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped[GeoFile] = relationship(back_populates="features")
