"""Public response submission and admin response listing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from smart_survey.api.deps import Pagination, db_session, pagination, require_admin
from smart_survey.db.models import Response
from smart_survey.schemas import (
    AnswerRead,
    Paginated,
    QuestionRead,
    ResponseCreate,
    ResponseRead,
    SurveyRead,
)
from smart_survey.services.survey_service import SurveyService

public_router = APIRouter()
admin_router = APIRouter(dependencies=[Depends(require_admin)])


def _serialise(response: Response) -> ResponseRead:
    return ResponseRead(
        id=response.id,
        survey_id=response.survey_id,
        submitted_at=response.submitted_at,
        duration_seconds=response.duration_seconds,
        source=response.source,
        answers=[
            AnswerRead(question_id=a.question_id, value=a.as_python) for a in response.answers
        ],
    )


@public_router.get(
    "/surveys/{slug}",
    response_model=SurveyRead,
    summary="Fetch a published survey to render the form",
)
def get_public_survey(slug: str, session: Session = Depends(db_session)) -> SurveyRead:
    return SurveyRead.model_validate(SurveyService(session).get_by_slug(slug))


@public_router.post(
    "/surveys/{slug}/responses",
    response_model=ResponseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a survey response",
)
def submit_response(
    slug: str,
    payload: ResponseCreate,
    request: Request,
    session: Session = Depends(db_session),
) -> ResponseRead:
    service = SurveyService(session)
    response = service.submit_response(
        slug,
        payload,
        source=request.headers.get("x-source", "api"),
    )
    return _serialise(response)


@admin_router.get(
    "/surveys/{survey_id}/responses",
    response_model=Paginated,
    summary="List responses for a survey",
)
def list_responses(
    survey_id: int,
    page: Pagination = Depends(pagination),
    session: Session = Depends(db_session),
) -> Any:
    service = SurveyService(session)
    responses = service.responses_for(survey_id, limit=page.limit, offset=page.offset)
    return Paginated(
        total=service.response_count(survey_id),
        limit=page.limit,
        offset=page.offset,
        items=[_serialise(r).model_dump() for r in responses],
    )


@admin_router.get(
    "/surveys/{survey_id}/questions",
    response_model=list[QuestionRead],
    summary="List questions for a survey",
)
def list_questions(survey_id: int, session: Session = Depends(db_session)) -> list[QuestionRead]:
    survey = SurveyService(session).get(survey_id)
    return [QuestionRead.model_validate(q) for q in survey.questions]
