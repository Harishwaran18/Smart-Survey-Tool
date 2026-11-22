"""Normalised relational schema for surveys, questions, responses and answers."""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class QuestionType(str, enum.Enum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    RATING = "rating"
    NPS = "nps"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    BOOLEAN = "boolean"

    @property
    def is_numeric(self) -> bool:
        return self in (QuestionType.RATING, QuestionType.NPS)

    @property
    def is_free_text(self) -> bool:
        return self in (QuestionType.TEXT, QuestionType.LONG_TEXT)

    @property
    def is_choice(self) -> bool:
        return self in (QuestionType.SINGLE_CHOICE, QuestionType.MULTI_CHOICE)


class SurveyStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=SurveyStatus.DRAFT.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    questions: Mapped[list[Question]] = relationship(
        back_populates="survey",
        cascade="all, delete-orphan",
        order_by="Question.position",
        lazy="selectin",
    )
    responses: Mapped[list[Response]] = relationship(
        back_populates="survey", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def is_open(self) -> bool:
        return self.status == SurveyStatus.PUBLISHED.value


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("survey_id", "position", name="uq_question_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    survey_id: Mapped[int] = mapped_column(ForeignKey("surveys.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(String(500))
    qtype: Mapped[str] = mapped_column(String(30), default=QuestionType.TEXT.value)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    options: Mapped[list[str] | None] = mapped_column(JSON)
    scale_min: Mapped[int | None] = mapped_column(Integer)
    scale_max: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    survey: Mapped[Survey] = relationship(back_populates="questions")
    answers: Mapped[list[Answer]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )

    @property
    def type(self) -> QuestionType:
        return QuestionType(self.qtype)


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    survey_id: Mapped[int] = mapped_column(ForeignKey("surveys.id", ondelete="CASCADE"), index=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    respondent_meta: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(40), default="api")

    survey: Mapped[Survey] = relationship(back_populates="responses")
    answers: Mapped[list[Answer]] = relationship(
        back_populates="response", cascade="all, delete-orphan", lazy="selectin"
    )

    def answer_for(self, question_id: int) -> Answer | None:
        return next((a for a in self.answers if a.question_id == question_id), None)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("response_id", "question_id", name="uq_answer_question"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    response_id: Mapped[int] = mapped_column(
        ForeignKey("responses.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[float | None] = mapped_column(Float)
    value_choice: Mapped[str | None] = mapped_column(String(200))
    value_choices: Mapped[list[str] | None] = mapped_column(JSON)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean)

    response: Mapped[Response] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship(back_populates="answers")

    @property
    def as_python(self) -> Any:
        if self.value_choices is not None:
            return list(self.value_choices)
        if self.value_boolean is not None:
            return self.value_boolean
        if self.value_number is not None:
            return self.value_number
        if self.value_choice is not None:
            return self.value_choice
        return self.value_text
