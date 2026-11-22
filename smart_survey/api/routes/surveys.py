"""Survey management endpoints (admin authenticated)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from smart_survey.api.deps import Pagination, db_session, pagination, require_admin
from smart_survey.config import get_settings
from smart_survey.db.models import SurveyStatus
from smart_survey.schemas import (
    Paginated,
    SurveyCreate,
    SurveyRead,
    SurveySummary,
    SurveyUpdate,
)
from smart_survey.services.survey_service import SurveyService

router = APIRouter(prefix="/surveys", dependencies=[Depends(require_admin)])


def _service(session: Session) -> SurveyService:
    return SurveyService(session)


@router.get("", response_model=Paginated, summary="List surveys")
def list_surveys(
    status_filter: str | None = None,
    page: Pagination = Depends(pagination),
    session: Session = Depends(db_session),
) -> Any:
    service = _service(session)
    surveys = service.list(status=status_filter, limit=page.limit, offset=page.offset)
    items = [
        SurveySummary(
            id=s.id,
            slug=s.slug,
            title=s.title,
            status=s.status,
            created_at=s.created_at,
            question_count=len(s.questions),
            response_count=service.response_count(s.id),
        ).model_dump()
        for s in surveys
    ]
    return Paginated(
        total=service.count(status=status_filter), limit=page.limit, offset=page.offset, items=items
    )


@router.post(
    "", response_model=SurveyRead, status_code=status.HTTP_201_CREATED, summary="Create survey"
)
def create_survey(payload: SurveyCreate, session: Session = Depends(db_session)) -> SurveyRead:
    survey = _service(session).create(payload)
    return SurveyRead.model_validate(survey)


@router.get("/{survey_id}", response_model=SurveyRead, summary="Get survey definition")
def get_survey(survey_id: int, session: Session = Depends(db_session)) -> SurveyRead:
    return SurveyRead.model_validate(_service(session).get(survey_id))


@router.patch("/{survey_id}", response_model=SurveyRead, summary="Update survey")
def update_survey(
    survey_id: int, payload: SurveyUpdate, session: Session = Depends(db_session)
) -> SurveyRead:
    return SurveyRead.model_validate(_service(session).update(survey_id, payload))


@router.post("/{survey_id}/publish", response_model=SurveyRead, summary="Publish survey")
def publish_survey(survey_id: int, session: Session = Depends(db_session)) -> SurveyRead:
    return SurveyRead.model_validate(
        _service(session).set_status(survey_id, SurveyStatus.PUBLISHED)
    )


@router.post("/{survey_id}/close", response_model=SurveyRead, summary="Close survey")
def close_survey(survey_id: int, session: Session = Depends(db_session)) -> SurveyRead:
    return SurveyRead.model_validate(_service(session).set_status(survey_id, SurveyStatus.CLOSED))


@router.delete("/{survey_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete survey")
def delete_survey(survey_id: int, session: Session = Depends(db_session)) -> Response:
    _service(session).delete(survey_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{survey_id}/share-link", summary="Public share link for a survey")
def share_link(survey_id: int, session: Session = Depends(db_session)) -> dict[str, str]:
    survey = _service(session).get(survey_id)
    base = get_settings().public_base_url.rstrip("/")
    return {"slug": survey.slug, "url": f"{base}/api/v1/public/surveys/{survey.slug}"}
