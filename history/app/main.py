from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from history.app.api.router import router
from history.app.config.settings import Settings, get_settings
from history.app.core.logging_config import configure_logging
from history.app.db.pool import create_pool
from history.app.factories.cache_factory import create_cache


def create_app(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.pool = await create_pool(application_settings)
        try:
            app.state.session_store = create_cache(application_settings, app.state.pool)
            try:
                yield
            finally:
                await app.state.session_store.aclose()
        finally:
            await app.state.pool.close()

    application = FastAPI(
        title="Flight Tracker API",
        version="1.0.0",
        description="Read-only API for flight snapshots and aircraft positions.",
        lifespan=lifespan,
    )
    application.state.settings = application_settings
    application.include_router(router)

    if application_settings.serve_frontend:
        if not application_settings.frontend_directory.is_dir():
            raise FileNotFoundError(
                f"Frontend directory does not exist: {application_settings.frontend_directory}"
            )
        application.mount(
            "/",
            StaticFiles(directory=application_settings.frontend_directory, html=True),
            name="frontend",
        )

    return application


configure_logging()
app = create_app()
