"""App factory. Run with:  uvicorn app.main:create_app --factory --reload"""
import logging

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from .api import router
from .config import Settings
from .database import Base, make_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)

    app = FastAPI(
        title="Geospatial File Measurement API",
        version="1.0.0",
        description="Upload a Shapefile (.zip) or KML/KMZ; get features, CRS, and area/length measurements.",
    )
    app.state.settings = settings
    app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    app.include_router(router, tags=["files"])
    return app
