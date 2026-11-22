"""Survey orchestration: creation, response validation, analytics and seeding."""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from smart_survey.db.models import Question, QuestionType, Response, Survey, SurveyStatus
from smart_survey.db.repository import ResponseRepository, SurveyRepository
from smart_survey.errors import ConflictError, NotFoundError, ValidationError
from smart_survey.logging_config import get_logger
from smart_survey.schemas import QuestionCreate, ResponseCreate, SurveyCreate, SurveyUpdate
from smart_survey.services.analytics import AnalyticsService
from smart_survey.services.insights import InsightGenerator

logger = get_logger(__name__)

MAX_TEXT_LENGTH = 10_000


class SurveyService:
    def __init__(
        self,
        session: Session,
        *,
        analytics: AnalyticsService | None = None,
        insights: InsightGenerator | None = None,
    ) -> None:
        self.session = session
        self.surveys = SurveyRepository(session)
        self.responses = ResponseRepository(session)
        self.analytics = analytics or AnalyticsService()
        self.insights = insights or InsightGenerator()

    # ------------------------------------------------------------------ reads
    def get(self, survey_id: int) -> Survey:
        survey = self.surveys.get(survey_id)
        if survey is None:
            raise NotFoundError(f"survey {survey_id} not found")
        return survey

    def get_by_slug(self, slug: str) -> Survey:
        survey = self.surveys.get_by_slug(slug)
        if survey is None:
            raise NotFoundError(f"survey '{slug}' not found")
        return survey

    def list(self, *, status: str | None = None, limit: int = 100, offset: int = 0) -> list[Survey]:
        return self.surveys.list(status=status, limit=limit, offset=offset)

    def count(self, *, status: str | None = None) -> int:
        return self.surveys.count(status=status)

    # ----------------------------------------------------------------- writes
    def create(self, payload: SurveyCreate) -> Survey:
        survey = self.surveys.create(
            title=payload.title,
            description=payload.description,
            slug=payload.slug,
            status=payload.status,
            questions=[q.model_dump() for q in payload.questions],
        )
        logger.info("created survey id=%s slug=%s", survey.id, survey.slug)
        return survey

    def update(self, survey_id: int, payload: SurveyUpdate) -> Survey:
        survey = self.get(survey_id)
        data = payload.model_dump(exclude_unset=True)
        questions = data.pop("questions", None)
        survey = self.surveys.update(survey, **data)
        if questions is not None:
            survey = self.surveys.replace_questions(
                survey, [QuestionCreate(**q).model_dump() for q in questions]
            )
        return survey

    def set_status(self, survey_id: int, status: SurveyStatus) -> Survey:
        survey = self.get(survey_id)
        if status is SurveyStatus.PUBLISHED and not survey.questions:
            raise ConflictError("cannot publish a survey without questions")
        survey.status = status.value
        self.session.flush()
        return survey

    def delete(self, survey_id: int) -> None:
        self.surveys.delete(self.get(survey_id))

    # -------------------------------------------------------------- responses
    def submit_response(
        self,
        slug: str,
        payload: ResponseCreate,
        *,
        source: str = "api",
        require_open: bool = True,
    ) -> Response:
        survey = self.get_by_slug(slug)
        if require_open and not survey.is_open:
            raise ConflictError(f"survey '{slug}' is not accepting responses ({survey.status})")

        answers = self._validate_answers(survey, payload.answers)
        response = self.responses.add(
            survey,
            answers,
            duration_seconds=payload.duration_seconds,
            respondent_meta=payload.respondent_meta,
            source=source,
        )
        logger.info("response id=%s survey=%s answers=%s", response.id, slug, len(answers))
        return response

    def _validate_answers(self, survey: Survey, answers: Sequence[Any]) -> list[dict[str, Any]]:
        by_question = {a.question_id: a for a in answers}
        unknown = set(by_question) - {q.id for q in survey.questions}
        if unknown:
            raise ValidationError(f"unknown question ids: {sorted(unknown)}")

        cleaned: list[dict[str, Any]] = []
        for question in survey.questions:
            submitted = by_question.get(question.id)
            value = submitted.value if submitted else None
            if value is None or (isinstance(value, str) and not value.strip()):
                if question.required:
                    raise ValidationError(
                        f"question {question.id} ('{question.text}') is required",
                        details={"question_id": question.id},
                    )
                continue
            cleaned.append(
                {"question_id": question.id, "value": self._validate_value(question, value)}
            )
        return cleaned

    def _validate_value(self, question: Question, value: Any) -> Any:
        qtype = question.type
        if qtype.is_numeric:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError(f"question {question.id} expects a number")
            low = question.scale_min if question.scale_min is not None else 0
            high = question.scale_max if question.scale_max is not None else 10
            if not low <= float(value) <= high:
                raise ValidationError(
                    f"question {question.id} value must be between {low} and {high}",
                    details={"question_id": question.id, "min": low, "max": high},
                )
            return float(value)
        if qtype is QuestionType.SINGLE_CHOICE:
            if value not in (question.options or []):
                raise ValidationError(f"question {question.id} value must be one of the options")
            return value
        if qtype is QuestionType.MULTI_CHOICE:
            if not isinstance(value, list) or not value:
                raise ValidationError(f"question {question.id} expects a non-empty list")
            invalid = [v for v in value if v not in (question.options or [])]
            if invalid:
                raise ValidationError(f"question {question.id} has invalid options: {invalid}")
            return [str(v) for v in value]
        if qtype is QuestionType.BOOLEAN:
            if not isinstance(value, bool):
                raise ValidationError(f"question {question.id} expects true or false")
            return value
        if not isinstance(value, str):
            raise ValidationError(f"question {question.id} expects text")
        if len(value) > MAX_TEXT_LENGTH:
            raise ValidationError(f"question {question.id} exceeds {MAX_TEXT_LENGTH} characters")
        return value.strip()

    # -------------------------------------------------------------- analytics
    def analytics_for(self, survey_id: int, *, timeline_days: int = 30) -> dict[str, Any]:
        survey = self.get(survey_id)
        responses = self.responses.list_for_survey(survey_id, limit=100_000)
        return self.analytics.analyse(survey, responses, timeline_days=timeline_days)

    def insights_for(self, survey_id: int) -> list[dict[str, Any]]:
        payload = self.analytics_for(survey_id)
        return [insight.as_dict() for insight in self.insights.generate(payload)]

    def responses_for(self, survey_id: int, *, limit: int = 500, offset: int = 0) -> list[Response]:
        self.get(survey_id)
        return self.responses.list_for_survey(survey_id, limit=limit, offset=offset)

    def response_count(self, survey_id: int) -> int:
        return self.responses.count_for_survey(survey_id)

    # ------------------------------------------------------------------- seed
    def seed_demo(self, *, responses: int = 60, force: bool = False) -> Survey:
        """Create a realistic demo survey with synthetic responses (idempotent)."""
        existing = self.surveys.get_by_slug("product-experience-2026")
        if existing is not None and not force:
            return existing
        if existing is not None:
            self.surveys.delete(existing)
            self.session.flush()

        survey = self.surveys.create(
            title="Product Experience Survey 2026",
            description="Quarterly pulse check on product satisfaction, support and roadmap priorities.",
            slug="product-experience-2026",
            status=SurveyStatus.PUBLISHED.value,
            questions=[
                {
                    "text": "How likely are you to recommend us to a colleague?",
                    "qtype": "nps",
                    "scale_min": 0,
                    "scale_max": 10,
                },
                {
                    "text": "How satisfied are you with the product overall?",
                    "qtype": "rating",
                    "scale_min": 1,
                    "scale_max": 5,
                },
                {
                    "text": "Which area should we improve first?",
                    "qtype": "single_choice",
                    "options": ["Performance", "Usability", "Pricing", "Support", "Reporting"],
                },
                {
                    "text": "Which features do you use weekly?",
                    "qtype": "multi_choice",
                    "options": ["Dashboard", "Survey builder", "Exports", "API", "AI insights"],
                    "required": False,
                },
                {
                    "text": "Would you renew your subscription?",
                    "qtype": "boolean",
                },
                {
                    "text": "What is the single biggest thing we could improve?",
                    "qtype": "long_text",
                    "required": False,
                },
            ],
        )
        self._seed_responses(survey, responses)
        logger.info("seeded demo survey id=%s with %s responses", survey.id, responses)
        return survey

    def _seed_responses(self, survey: Survey, count: int) -> None:
        rng = random.Random(42)
        positive = [
            "The dashboard is really fast and easy to use, love the exports.",
            "Great support team, very helpful and friendly every single time.",
            "Excellent reporting, it saved our team hours every week.",
            "Very reliable application, smooth experience overall.",
            "The AI insights are awesome and genuinely useful.",
        ]
        neutral = [
            "It is okay, nothing special but it works fine.",
            "Decent tool, pricing is a bit high for small teams.",
            "Works as expected, documentation could be clearer.",
            "Average experience, the UI feels dated in places.",
        ]
        negative = [
            "The app is slow and crashes when exporting large reports.",
            "Support was rude and it took days to get a reply.",
            "Confusing menu and the pricing is expensive for what you get.",
            "Terrible performance during peak hours, very frustrating.",
            "Too many bugs after the last update, reporting is broken.",
        ]
        improvement_notes = [
            "Better reporting filters and saved views.",
            "Faster exports for large datasets.",
            "Clearer pricing and a cheaper starter plan.",
            "More responsive support with faster first reply.",
            "Improve mobile usability and navigation.",
            "Add API rate limit visibility.",
        ]
        sentiment_pool = positive * 5 + neutral * 3 + negative * 2
        now = datetime.now(UTC)
        questions = list(survey.questions)

        for _ in range(count):
            mood = rng.choices(["positive", "neutral", "negative"], weights=[55, 25, 20])[0]
            nps = (
                rng.choice([9, 10])
                if mood == "positive"
                else rng.choice([7, 8])
                if mood == "neutral"
                else rng.choice([0, 2, 3, 5])
            )
            rating = (
                rng.choice([4, 5])
                if mood == "positive"
                else rng.choice([3, 4])
                if mood == "neutral"
                else rng.choice([1, 2])
            )
            focus = rng.choice(["Performance", "Usability", "Pricing", "Support", "Reporting"])
            features = rng.sample(
                ["Dashboard", "Survey builder", "Exports", "API", "AI insights"],
                k=rng.randint(1, 3),
            )
            renew = mood == "positive" if rng.random() < 0.8 else rng.random() < 0.5
            note = (
                rng.choice(improvement_notes) if rng.random() < 0.7 else rng.choice(sentiment_pool)
            )

            values = {
                questions[0].id: nps,
                questions[1].id: rating,
                questions[2].id: focus,
                questions[3].id: features,
                questions[4].id: renew,
                questions[5].id: note,
            }
            response = Response(
                survey_id=survey.id,
                submitted_at=now - timedelta(days=rng.randint(0, 27), hours=rng.randint(0, 23)),
                duration_seconds=rng.randint(45, 480),
                source="seed",
                respondent_meta={"segment": rng.choice(["enterprise", "smb", "startup"])},
            )
            for question in questions:
                self.session.add(
                    self._build_seed_answer(response, question, values.get(question.id))
                )
            self.session.add(response)
        self.session.flush()

    @staticmethod
    def _build_seed_answer(response: Response, question: Question, value: Any):
        from smart_survey.db.models import Answer

        answer = Answer(question_id=question.id, response=response)
        if isinstance(value, bool):
            answer.value_boolean = value
        elif isinstance(value, list):
            answer.value_choices = value
        elif isinstance(value, (int, float)):
            answer.value_number = float(value)
        elif isinstance(value, str) and question.type.is_choice:
            answer.value_choice = value
        else:
            answer.value_text = value
        return answer
