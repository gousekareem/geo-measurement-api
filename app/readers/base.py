"""Format-independent output of every reader.

Readers only *parse*: they turn bytes into Shapely geometries + attributes + a CRS.
They never measure, so measurement logic is written once for all formats.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pyproj import CRS
from shapely.geometry.base import BaseGeometry


@dataclass
class RawFeature:
    index: int
    geometry: BaseGeometry | None
    properties: dict[str, Any]
    source_id: str | None = None
    # Set when the feature's geometry type is known but can't be parsed into
    # Shapely (e.g. KML gx:Track) - lets the API report it instead of crashing.
    geometry_type_hint: str | None = None
    # Feature-level parse problem (e.g. malformed coordinates). The file still loads.
    error: str | None = None

    @property
    def geometry_type(self) -> str | None:
        if self.geometry is not None:
            return self.geometry.geom_type
        return self.geometry_type_hint


@dataclass
class ReadResult:
    features: list[RawFeature]
    crs: CRS | None
    crs_assumed: bool = False
    warnings: list[str] = field(default_factory=list)


def json_safe(value: Any) -> Any:
    """Make attribute values JSON-serialisable (DBF dates, decimals, bytes...)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    return str(value)
