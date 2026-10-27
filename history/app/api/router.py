from fastapi import APIRouter
from fastapi.responses import JSONResponse

from history.app.api.routes.health import router as health_router
from history.app.api.routes.session import router as session_router
from history.app.api.routes.snapshots import router as snapshots_router

router = APIRouter()
router.include_router(health_router)
router.include_router(snapshots_router)
router.include_router(session_router)


@router.get("/api", include_in_schema=False)
async def api_info() -> JSONResponse:
    return JSONResponse(
        {
            "service": "Flight Tracker History API",
            "endpoints": [
                "/api/history?limit=25",
                "/api/latest (includes aircraft positions)",
                "/api/timeline?minutes=60&limit=120",
                "/api/heatmap?hours=1",
                "/api/session",
                "/health/live",
                "/health/ready",
            ],
        }
    )
