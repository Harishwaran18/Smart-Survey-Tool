"""Repository layer: all database access lives here so services stay pure."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from smart_survey.db.models import Answer, Question, Response, Survey, SurveyStatus


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "survey"


class SurveyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _base_query(self) -> Select[tuple[Survey]]:
        return select(Survey).options(selectinload(Survey.questions))

    def get(self, survey_id: int) -> Survey | None:
        return self.session.get(Survey, survey_id)

    def get_by_slug(self, slug: str) -> Survey | None:
        stmt = self._base_query().where(Survey.slug == slug)
        return self.session.execute(stmt).scalar_one_or_none()

    def list(self, *, status: str | None = None, limit: int = 100, offset: int = 0) -> list[Survey]:
        stmt = self._base_query().order_by(Survey.created_at.desc())
        if status:
            stmt = stmt.where(Survey.status == status)
        stmt = stmt.limit(limit).offset(offset)
        return list(self.session.execute(stmt).scalars().all())

    def count(self, *, status: str | None = None) -> int:
        stmt = select(func.count(Survey.id))
        if status:
            stmt = stmt.where(Survey.status == status)
        return int(self.session.execute(stmt).scalar_one())

    def create(
        self,
        *,
        title: str,
        description: str | None = None,
        slug: str | None = None,
        status: str = SurveyStatus.DRAFT.value,
        questions: Sequence[dict[str, Any]] = (),
    ) -> Survey:
        survey = Survey(
            title=title.strip(),
            description=description,
            slug=self._unique_slug(slug or title),
            status=status,
        )
        for position, payload in enumerate(questions):
            survey.questions.append(self._build_question(position, payload))
        self.session.add(survey)
        self.session.flush()
        return survey

    def replace_questions(self, survey: Survey, questions: Sequence[dict[str, Any]]) -> Survey:
        survey.questions.clear()
        self.session.flush()
        for position, payload in enumerate(questions):
            survey.questions.append(self._build_question(position, payload))
        self.session.flush()
        return survey

    def update(self, survey: Survey, **fields: Any) -> Survey:
        for key, value in fields.items():
            if value is not None and hasattr(survey, key):
                setattr(survey, key, value)
        self.session.flush()
        return survey

    def delete(self, survey: Survey) -> None:
        self.session.delete(survey)

    def _build_question(self, position: int, payload: dict[str, Any]) -> Question:
        return Question(
            position=position,
            text=payload["text"],
            qtype=payload.get("qtype", "text"),
            required=payload.get("required", True),
            options=payload.get("options"),
            scale_min=payload.get("scale_min"),
            scale_max=payload.get("scale_max"),
        )

    def _unique_slug(self, source: str) -> str:
        base = slugify(source)
        candidate = base
        suffix = 2
        while self.get_by_slug(candidate) is not None:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate


class ResponseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, response_id: int) -> Response | None:
        return self.session.get(Response, response_id)

    def list_for_survey(
        self,
        survey_id: int,
        *,
        limit: int = 500,
        offset: int = 0,
        since: datetime | None = None,
    ) -> list[Response]:
        stmt = (
            select(Response)
            .where(Response.survey_id == survey_id)
            .options(selectinload(Response.answers))
            .order_by(Response.submitted_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if since:
            stmt = stmt.where(Response.submitted_at >= since)
        return list(self.session.execute(stmt).scalars().all())

    def count_for_survey(self, survey_id: int) -> int:
        stmt = select(func.count(Response.id)).where(Response.survey_id == survey_id)
        return int(self.session.execute(stmt).scalar_one())

    def add(
        self,
        survey: Survey,
        answers: Sequence[dict[str, Any]],
        *,
        duration_seconds: int | None = None,
        respondent_meta: dict[str, Any] | None = None,
        source: str = "api",
    ) -> Response:
        response = Response(
            survey_id=survey.id,
            duration_seconds=duration_seconds,
            respondent_meta=respondent_meta,
            source=source,
        )
        questions = {q.id: q for q in survey.questions}
        for payload in answers:
            question = questions.get(payload["question_id"])
            if question is None:
                continue
            response.answers.append(self._build_answer(question, payload))
        self.session.add(response)
        self.session.flush()
        return response

    def _build_answer(self, question: Question, payload: dict[str, Any]) -> Answer:
        value = payload.get("value")
        answer = Answer(question_id=question.id)
        if isinstance(value, bool):
            answer.value_boolean = value
        elif isinstance(value, (list, tuple)):
            answer.value_choices = [str(v) for v in value]
        elif isinstance(value, (int, float)):
            answer.value_number = float(value)
        elif value is not None:
            text = str(value).strip()
            if question.type.is_choice:
                answer.value_choice = text
            else:
                answer.value_text = text
        return answer

    def delete(self, response: Response) -> None:
        self.session.delete(response)

    def purge_for_survey(self, survey_id: int) -> int:
        responses = self.list_for_survey(survey_id, limit=100_000)
        for response in responses:
            self.session.delete(response)
        return len(responses)
