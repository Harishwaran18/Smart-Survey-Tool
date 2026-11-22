"""Tests for survey orchestration: creation, validation and lifecycle."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from smart_survey.db.models import SurveyStatus
from smart_survey.errors import ConflictError, NotFoundError, ValidationError
from smart_survey.schemas import (
    AnswerIn,
    QuestionCreate,
    ResponseCreate,
    SurveyCreate,
    SurveyUpdate,
)


def _published_survey(service) -> int:
    survey = service.create(
        SurveyCreate(
            title="Customer Pulse",
            status="published",
            questions=[
                QuestionCreate(text="How likely to recommend?", qtype="nps"),
                QuestionCreate(
                    text="Overall satisfaction", qtype="rating", scale_min=1, scale_max=5
                ),
                QuestionCreate(
                    text="Favourite feature",
                    qtype="single_choice",
                    options=["Dashboard", "Exports", "API"],
                ),
                QuestionCreate(
                    text="Features used",
                    qtype="multi_choice",
                    options=["Dashboard", "Exports", "API"],
                    required=False,
                ),
                QuestionCreate(text="Would you renew?", qtype="boolean"),
                QuestionCreate(text="Anything else?", qtype="long_text", required=False),
            ],
        )
    )
    return survey.id


class TestCreation:
    def test_slug_is_generated_and_unique(self, service):
        first = service.create(SurveyCreate(title="My Survey"))
        second = service.create(SurveyCreate(title="My Survey"))
        assert first.slug == "my-survey"
        assert second.slug == "my-survey-2"

    def test_questions_are_ordered(self, service):
        survey = service.create(
            SurveyCreate(
                title="Ordered",
                questions=[QuestionCreate(text=f"Question number {i}") for i in range(1, 4)],
            )
        )
        assert [q.position for q in survey.questions] == [0, 1, 2]

    def test_nps_scale_is_forced(self, service):
        survey = service.create(
            SurveyCreate(title="NPS", questions=[QuestionCreate(text="Recommend us?", qtype="nps")])
        )
        question = survey.questions[0]
        assert (question.scale_min, question.scale_max) == (0, 10)

    def test_choice_requires_two_options(self):
        with pytest.raises(PydanticValidationError):
            QuestionCreate(text="Pick one", qtype="single_choice", options=["only"])

    def test_get_missing_survey_raises(self, service):
        with pytest.raises(NotFoundError):
            service.get(9999)

    def test_update_replaces_questions(self, service):
        survey = service.create(SurveyCreate(title="Editable"))
        updated = service.update(
            survey.id,
            SurveyUpdate(questions=[QuestionCreate(text="Replaced question text")]),
        )
        assert [q.text for q in updated.questions] == ["Replaced question text"]


class TestLifecycle:
    def test_publish_requires_questions(self, service):
        survey = service.create(SurveyCreate(title="No questions"))
        with pytest.raises(ConflictError):
            service.set_status(survey.id, SurveyStatus.PUBLISHED)

    def test_publish_then_close(self, service):
        survey_id = _published_survey(service)
        assert service.get(survey_id).status == "published"
        service.set_status(survey_id, SurveyStatus.CLOSED)
        assert service.get(survey_id).status == "closed"

    def test_delete_cascades(self, service, session):
        survey_id = _published_survey(service)
        service.delete(survey_id)
        session.flush()
        with pytest.raises(NotFoundError):
            service.get(survey_id)


class TestSubmission:
    def test_valid_submission_is_stored(self, service):
        survey_id = _published_survey(service)
        survey = service.get(survey_id)
        q = {question.qtype: question for question in survey.questions}
        response = service.submit_response(
            survey.slug,
            ResponseCreate(
                answers=[
                    AnswerIn(question_id=q["nps"].id, value=9),
                    AnswerIn(question_id=q["rating"].id, value=4),
                    AnswerIn(question_id=q["single_choice"].id, value="Exports"),
                    AnswerIn(question_id=q["boolean"].id, value=True),
                ]
            ),
        )
        assert response.id is not None
        assert service.response_count(survey_id) == 1

    def test_missing_required_question_rejected(self, service):
        survey_id = _published_survey(service)
        survey = service.get(survey_id)
        with pytest.raises(ValidationError):
            service.submit_response(survey.slug, ResponseCreate(answers=[]))

    def test_out_of_scale_value_rejected(self, service):
        survey_id = _published_survey(service)
        survey = service.get(survey_id)
        rating = next(q for q in survey.questions if q.qtype == "rating")
        nps = next(q for q in survey.questions if q.qtype == "nps")
        single = next(q for q in survey.questions if q.qtype == "single_choice")
        boolean = next(q for q in survey.questions if q.qtype == "boolean")
        with pytest.raises(ValidationError):
            service.submit_response(
                survey.slug,
                ResponseCreate(
                    answers=[
                        AnswerIn(question_id=nps.id, value=9),
                        AnswerIn(question_id=rating.id, value=99),
                        AnswerIn(question_id=single.id, value="Exports"),
                        AnswerIn(question_id=boolean.id, value=True),
                    ]
                ),
            )

    def test_invalid_choice_rejected(self, service):
        survey_id = _published_survey(service)
        survey = service.get(survey_id)
        q = {question.qtype: question for question in survey.questions}
        with pytest.raises(ValidationError):
            service.submit_response(
                survey.slug,
                ResponseCreate(
                    answers=[
                        AnswerIn(question_id=q["nps"].id, value=9),
                        AnswerIn(question_id=q["rating"].id, value=4),
                        AnswerIn(question_id=q["single_choice"].id, value="Not an option"),
                        AnswerIn(question_id=q["boolean"].id, value=True),
                    ]
                ),
            )

    def test_unknown_question_rejected(self, service):
        survey_id = _published_survey(service)
        survey = service.get(survey_id)
        with pytest.raises(ValidationError):
            service.submit_response(
                survey.slug, ResponseCreate(answers=[AnswerIn(question_id=99999, value="x")])
            )

    def test_closed_survey_rejects_submission(self, service):
        survey_id = _published_survey(service)
        service.set_status(survey_id, SurveyStatus.CLOSED)
        survey = service.get(survey_id)
        q = {question.qtype: question for question in survey.questions}
        with pytest.raises(ConflictError):
            service.submit_response(
                survey.slug,
                ResponseCreate(
                    answers=[
                        AnswerIn(question_id=q["nps"].id, value=9),
                        AnswerIn(question_id=q["rating"].id, value=4),
                        AnswerIn(question_id=q["single_choice"].id, value="API"),
                        AnswerIn(question_id=q["boolean"].id, value=False),
                    ]
                ),
            )

    def test_optional_question_may_be_skipped(self, service):
        survey_id = _published_survey(service)
        survey = service.get(survey_id)
        q = {question.qtype: question for question in survey.questions}
        response = service.submit_response(
            survey.slug,
            ResponseCreate(
                answers=[
                    AnswerIn(question_id=q["nps"].id, value=10),
                    AnswerIn(question_id=q["rating"].id, value=5),
                    AnswerIn(question_id=q["single_choice"].id, value="Dashboard"),
                    AnswerIn(question_id=q["boolean"].id, value=True),
                ]
            ),
        )
        assert len(response.answers) == 4

    def test_seed_is_idempotent(self, service):
        first = service.seed_demo(responses=20)
        second = service.seed_demo(responses=20)
        assert first.id == second.id
        assert service.response_count(first.id) == 20

    def test_seed_force_regenerates(self, service):
        service.seed_demo(responses=10)
        second = service.seed_demo(responses=15, force=True)
        assert second.slug == "product-experience-2026"
        assert service.response_count(second.id) == 15
