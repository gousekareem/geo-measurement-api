import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        max_upload_bytes=2 * 1024 * 1024,
        max_uncompressed_bytes=5 * 1024 * 1024,
        max_features=1000,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def upload(client):
    def _upload(filename: str, content: bytes, content_type: str = "application/octet-stream"):
        return client.post("/api/files/", files={"file": (filename, content, content_type)})
    return _upload
