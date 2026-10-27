import logging
import re
import secrets
from typing import Literal

import asyncpg
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/session", tags=["session"])
SESSION_COOKIE = "flight_tracker_session"
SESSION_KEY_PREFIX = "flight-tracker:session:"
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,64}$")


class SessionPreferences(BaseModel):
    theme: Literal["dark", "light"] = "dark"


def _session_id(request: Request) -> tuple[str, bool]:
    session_id = request.cookies.get(SESSION_COOKIE, "")
    if SESSION_ID_PATTERN.fullmatch(session_id):
        return session_id, False
    return secrets.token_urlsafe(32), True


async def _save_preferences(
    request: Request, session_id: str, preferences: SessionPreferences
) -> None:
    try:
        await request.app.state.session_store.set(
            f"{SESSION_KEY_PREFIX}{session_id}",
            preferences.model_dump_json(),
            ex=request.app.state.settings.session_ttl_sec,
        )
    except (asyncpg.PostgresError, RedisError) as error:
        logger.exception("could not save user interface preferences")
        raise HTTPException(status_code=503, detail="session store is unavailable") from error


def _set_session_cookie(response: Response, request: Request, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=request.app.state.settings.session_ttl_sec,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


@router.get("", response_model=SessionPreferences)
async def get_session_preferences(request: Request, response: Response) -> SessionPreferences:
    session_id, is_new = _session_id(request)
    try:
        stored_preferences = await request.app.state.session_store.get(
            f"{SESSION_KEY_PREFIX}{session_id}"
        )
    except (asyncpg.PostgresError, RedisError) as error:
        logger.exception("could not load user interface preferences")
        raise HTTPException(status_code=503, detail="session store is unavailable") from error

    if stored_preferences is None:
        preferences = SessionPreferences()
        await _save_preferences(request, session_id, preferences)
    else:
        try:
            preferences = SessionPreferences.model_validate_json(stored_preferences)
        except ValueError as error:
            logger.exception("stored user interface preferences are invalid")
            raise HTTPException(status_code=500, detail="stored session is invalid") from error

    if is_new:
        _set_session_cookie(response, request, session_id)
    return preferences


@router.put("", response_model=SessionPreferences)
async def update_session_preferences(
    preferences: SessionPreferences, request: Request, response: Response
) -> SessionPreferences:
    session_id, _ = _session_id(request)
    await _save_preferences(request, session_id, preferences)
    _set_session_cookie(response, request, session_id)
    return preferences
