import os
from dataclasses import dataclass, field


def _int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./geofiles.db"))
    # Size of the uploaded file itself.
    max_upload_bytes: int = field(default_factory=lambda: _int_env("MAX_UPLOAD_MB", 50) * 1024 * 1024)
    # Total uncompressed size allowed inside a ZIP/KMZ (zip-bomb protection).
    max_uncompressed_bytes: int = field(default_factory=lambda: _int_env("MAX_UNCOMPRESSED_MB", 200) * 1024 * 1024)
    # Upper bound on features per file.
    max_features: int = field(default_factory=lambda: _int_env("MAX_FEATURES", 100_000))
