"""Cached data access for the Streamlit UI.

All functions return plain Python objects so cached values survive after the
SQLAlchemy session closes.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from smart_survey.db.models import SurveyStatus
from smart_survey.db.session import get_session, init_db
from smart_survey.schemas import ResponseCreate, SurveyCreate, SurveyUpdate
from smart_survey.services.export import ExportService, responses_to_frame
from smart_survey.services.survey_service import SurveyService


def ensure_db() -> None:
    init_db()


def invalidate() -> None:
    st.cache_data.clear()


@st.cache_data(ttl=15, show_spinner=False)
def list_surveys() -> list[dict[str, Any]]:
    with get_session() as session:
        service = SurveyService(session)
        surveys = service.list(limit=200)
        return [
            {
                "id": survey.id,
                "slug": survey.slug,
                "title": survey.title,
                "description": survey.description,
                "status": survey.status,
                "question_count": len(survey.questions),
                "response_count": service.response_count(survey.id),
                "created_at": survey.created_at.isoformat(),
            }
            for survey in surveys
        ]


@st.cache_data(ttl=15, show_spinner=False)
def survey_detail(survey_id: int) -> dict[str, Any] | None:
    with get_session() as session:
        try:
            survey = SurveyService(session).get(survey_id)
        except Exception:
            return None
        return {
            "id": survey.id,
            "slug": survey.slug,
            "title": survey.title,
            "description": survey.description,
            "status": survey.status,
            "created_at": survey.created_at.isoformat(),
            "questions": [
                {
                    "id": question.id,
                    "position": question.position,
                    "text": question.text,
                    "type": question.qtype,
                    "required": question.required,
                    "options": question.options or [],
                    "scale_min": question.scale_min,
                    "scale_max": question.scale_max,
                }
                for question in survey.questions
            ],
        }


@st.cache_data(ttl=15, show_spinner="Analysing responses…")
def analytics(survey_id: int) -> dict[str, Any] | None:
    with get_session() as session:
        try:
            return SurveyService(session).analytics_for(survey_id)
        except Exception:
            return None


@st.cache_data(ttl=15, show_spinner=False)
def insights(survey_id: int) -> list[dict[str, Any]]:
    with get_session() as session:
        try:
            return SurveyService(session).insights_for(survey_id)
        except Exception:
            return []


@st.cache_data(ttl=15, show_spinner=False)
def responses_frame(survey_id: int) -> pd.DataFrame:
    with get_session() as session:
        service = SurveyService(session)
        survey = service.get(survey_id)
        responses = service.responses_for(survey_id, limit=100_000)
        return responses_to_frame(survey, responses)


@st.cache_data(ttl=15, show_spinner=False)
def export_bytes(survey_id: int, fmt: str, long_format: bool = False) -> bytes:
    with get_session() as session:
        service = SurveyService(session)
        survey = service.get(survey_id)
        responses = service.responses_for(survey_id, limit=100_000)
        if fmt == "csv":
            return ExportService.to_csv(survey, responses, long_format=long_format)
        if fmt == "excel":
            return ExportService.to_excel(survey, responses, service.analytics_for(survey_id))
        return ExportService.to_json(survey, responses, service.analytics_for(survey_id))


# --------------------------------------------------------------------- writes
def create_survey(payload: SurveyCreate) -> int:
    with get_session() as session:
        survey = SurveyService(session).create(payload)
        survey_id = survey.id
    invalidate()
    return survey_id


def update_survey(survey_id: int, payload: SurveyUpdate) -> None:
    with get_session() as session:
        SurveyService(session).update(survey_id, payload)
    invalidate()


def set_status(survey_id: int, status: SurveyStatus) -> None:
    with get_session() as session:
        SurveyService(session).set_status(survey_id, status)
    invalidate()


def delete_survey(survey_id: int) -> None:
    with get_session() as session:
        SurveyService(session).delete(survey_id)
    invalidate()


def submit_response(slug: str, payload: ResponseCreate, *, require_open: bool = True) -> None:
    with get_session() as session:
        SurveyService(session).submit_response(
            slug, payload, source="streamlit", require_open=require_open
        )
    invalidate()


def seed_demo(responses: int = 60, force: bool = False) -> None:
    with get_session() as session:
        SurveyService(session).seed_demo(responses=responses, force=force)
    invalidate()
