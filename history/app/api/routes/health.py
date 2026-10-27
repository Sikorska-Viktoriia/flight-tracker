import logging

import asyncpg
from fastapi import APIRouter, HTTPException, Request
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Check whether the API process is alive")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", summary="Check whether the API can access its database")
@router.get("/health", include_in_schema=False)
async def readiness(request: Request) -> dict[str, str]:
    try:
        async with request.app.state.pool.acquire() as connection:
            await connection.fetchval("SELECT 1")
    except (asyncpg.PostgresError, AttributeError) as error:
        logger.warning("service readiness check failed: %s", error)
        raise HTTPException(status_code=503, detail="a required service is unavailable") from error
    try:
        await request.app.state.session_store.ping()
    except (asyncpg.PostgresError, RedisError, AttributeError) as error:
        logger.warning("session store readiness check failed: %s", error)
        raise HTTPException(status_code=503, detail="session store is unavailable") from error
    return {"status": "ok"}
