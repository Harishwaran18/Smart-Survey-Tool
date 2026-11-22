"""Pydantic contracts shared by the REST API, the UI and the services layer."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from smart_survey.db.models import QuestionType

QTypeLiteral = Literal[
    "text", "long_text", "rating", "nps", "single_choice", "multi_choice", "boolean"
]


class QuestionCreate(BaseModel):
    text: Annotated[str, Field(min_length=3, max_length=500)]
    qtype: QTypeLiteral = "text"
    required: bool = True
    options: list[str] | None = None
    scale_min: int | None = Field(default=None, ge=0, le=100)
    scale_max: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def _check_type_rules(self) -> QuestionCreate:
        qtype = QuestionType(self.qtype)
        if qtype.is_choice:
            if not self.options or len(self.options) < 2:
                raise ValueError("choice questions need at least two options")
            if len(set(self.options)) != len(self.options):
                raise ValueError("options must be unique")
        if qtype is QuestionType.NPS:
            self.scale_min = 0
            self.scale_max = 10
        elif qtype is QuestionType.RATING:
            self.scale_min = 1 if self.scale_min is None else self.scale_min
            self.scale_max = 5 if self.scale_max is None else self.scale_max
            if self.scale_max <= self.scale_min:
                raise ValueError("scale_max must be greater than scale_min")
        return self


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    text: str
    qtype: str
    required: bool
    options: list[str] | None = None
    scale_min: int | None = None
    scale_max: int | None = None


class SurveyCreate(BaseModel):
    title: Annotated[str, Field(min_length=3, max_length=200)]
    description: str | None = Field(default=None, max_length=2000)
    slug: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9\-]*$")
    status: Literal["draft", "published", "closed"] = "draft"
    questions: list[QuestionCreate] = Field(default_factory=list, max_length=50)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        return value.strip()


class SurveyUpdate(BaseModel):
    title: Annotated[str, Field(min_length=3, max_length=200)] | None = None
    description: str | None = None
    status: Literal["draft", "published", "closed"] | None = None
    questions: list[QuestionCreate] | None = None


class SurveyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    description: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    questions: list[QuestionRead] = Field(default_factory=list)


class SurveySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    status: str
    created_at: datetime
    question_count: int = 0
    response_count: int = 0


class AnswerIn(BaseModel):
    question_id: int
    value: Any = None


class ResponseCreate(BaseModel):
    answers: list[AnswerIn] = Field(default_factory=list)
    duration_seconds: int | None = Field(default=None, ge=0, le=86_400)
    respondent_meta: dict[str, Any] | None = None


class AnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: int
    value: Any = None


class ResponseRead(BaseModel):
    id: int
    survey_id: int
    submitted_at: datetime
    duration_seconds: int | None = None
    source: str
    answers: list[AnswerRead] = Field(default_factory=list)


class InsightRead(BaseModel):
    title: str
    description: str
    severity: str
    category: str
    metric: str | None = None
    value: float | None = None
    recommendation: str | None = None
    evidence: list[str] = Field(default_factory=list)


class Paginated(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[Any]


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    nlp_backend: str
