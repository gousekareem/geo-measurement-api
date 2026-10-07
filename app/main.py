"""App factory. Run with:  uvicorn app.main:create_app --factory --reload"""
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import sessionmaker
import os

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

    # Mount static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", tags=["meta"])
    def root():
        """Serve the landing page"""
        landing_page = os.path.join(os.path.dirname(__file__), "static", "index.html")
        if os.path.exists(landing_page):
            return FileResponse(landing_page, media_type="text/html")
        return {
            "message": "Geo Measurement API is running",
            "status": "ok",
            "health": "/health",
            "docs": "/docs",
            "api": "/api/files/",
        }

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    app.include_router(router, tags=["files"])
    return app
