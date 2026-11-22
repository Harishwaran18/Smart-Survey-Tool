"""Analytics, insights and export endpoints."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response as FileResponse
from sqlalchemy.orm import Session

from smart_survey.api.deps import db_session, require_admin
from smart_survey.schemas import InsightRead
from smart_survey.services.export import ExportService
from smart_survey.services.survey_service import SurveyService

router = APIRouter(prefix="/surveys/{survey_id}", dependencies=[Depends(require_admin)])


@router.get("/analytics", summary="Quantitative analytics (NPS, CSAT, distributions, trends)")
def get_analytics(
    survey_id: int,
    timeline_days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    return SurveyService(session).analytics_for(survey_id, timeline_days=timeline_days)


@router.get("/insights", response_model=list[InsightRead], summary="Prioritised AI insights")
def get_insights(survey_id: int, session: Session = Depends(db_session)) -> list[InsightRead]:
    return [InsightRead(**item) for item in SurveyService(session).insights_for(survey_id)]


@router.get("/export", summary="Export responses (csv, excel, json)")
def export_survey(
    survey_id: int,
    format: Literal["csv", "excel", "json"] = Query(default="csv"),
    long_format: bool = Query(default=False, description="One row per answer (tidy format)"),
    session: Session = Depends(db_session),
) -> FileResponse:
    service = SurveyService(session)
    survey = service.get(survey_id)
    responses = service.responses_for(survey_id, limit=100_000)
    slug = survey.slug

    if format == "csv":
        content = ExportService.to_csv(survey, responses, long_format=long_format)
        media, filename = "text/csv", f"{slug}.csv"
    elif format == "excel":
        content = ExportService.to_excel(survey, responses, service.analytics_for(survey_id))
        media, filename = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{slug}.xlsx",
        )
    else:
        content = ExportService.to_json(survey, responses, service.analytics_for(survey_id))
        media, filename = "application/json", f"{slug}.json"

    return FileResponse(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
