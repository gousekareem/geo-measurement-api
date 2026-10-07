"""Upload pipeline: detect type -> read -> measure each feature -> persist."""
import logging

from shapely.geometry import LineString, mapping
from sqlalchemy.orm import Session

from .config import Settings
from .errors import InvalidFileError
from .measurement import Measurement, measure
from .measurement.crs import crs_label
from .models import Feature, FileStatus, FileType, GeoFile, MeasurementStatus, utcnow
from .readers import read_file

logger = logging.getLogger(__name__)


def process_upload(db: Session, settings: Settings, filename: str, file_type: FileType, data: bytes) -> GeoFile:
    geo_file = GeoFile(filename=filename, file_type=file_type, size_bytes=len(data), status=FileStatus.PROCESSING)
    db.add(geo_file)
    db.commit()  # record exists even if processing fails, so the client can see why

    try:
        result = read_file(
            file_type,
            data,
            max_uncompressed_bytes=settings.max_uncompressed_bytes,
            max_features=settings.max_features,
        )
        features = []
        for raw in result.features:
            if raw.error:
                # The geometry couldn't be read at all - report the parse problem.
                m = Measurement(MeasurementStatus.ERROR, message=raw.error)
            else:
                m = measure(raw.geometry, result.crs, raw.geometry_type)
            features.append(Feature(
                feature_index=raw.index,
                source_id=raw.source_id,
                geometry_type=raw.geometry_type,
                geometry=_to_geojson(raw.geometry),
                properties=raw.properties,
                measurement_status=m.status,
                area_m2=m.area_m2,
                perimeter_m=m.perimeter_m,
                length_m=m.length_m,
                measurement_crs=m.measurement_crs,
                measurement_message=m.message,
            ))

        geo_file.features = features
        geo_file.feature_count = len(features)
        geo_file.crs = crs_label(result.crs)
        geo_file.crs_name = result.crs.name if result.crs else None
        geo_file.crs_wkt = result.crs.to_wkt() if result.crs else None
        geo_file.crs_assumed = result.crs_assumed
        geo_file.warnings = result.warnings
        geo_file.status = FileStatus.COMPLETED
    except InvalidFileError as exc:
        db.rollback()
        geo_file.status = FileStatus.FAILED
        geo_file.error = str(exc)
    except Exception:
        logger.exception("Unexpected error processing %s", filename)
        db.rollback()
        geo_file.status = FileStatus.FAILED
        geo_file.error = "Internal error while processing the file"

    geo_file.processed_at = utcnow()
    db.commit()
    return geo_file


def _to_geojson(geometry) -> dict | None:
    if geometry is None:
        return None
    if geometry.geom_type == "LinearRing":  # not a GeoJSON type
        geometry = LineString(geometry.coords)
    return mapping(geometry)
