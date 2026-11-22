"""Shared FastAPI dependencies: database session, pagination and admin auth."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Header, Query
from sqlalchemy.orm import Session

from smart_survey.config import get_settings
from smart_survey.db.session import get_session
from smart_survey.errors import AuthError


def db_session() -> Iterator[Session]:
    with get_session() as session:
        yield session


@dataclass(slots=True)
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: int = Query(default=50, ge=1, le=500, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


def require_admin(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Validate the admin API key using a constant-time comparison."""
    settings = get_settings()
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.admin_api_key):
        raise AuthError("invalid or missing X-API-Key header")


AdminAuth = Depends(require_admin)
DbSession = Depends(db_session)
PageParams = Depends(pagination)
