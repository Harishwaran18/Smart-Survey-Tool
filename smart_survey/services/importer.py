"""Import historical survey data from CSV files.

The legacy Smart Survey Tool stored responses in a flat ``survey_responses.csv``
file. This module migrates such files into the normalised schema so old data is
not lost when upgrading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from smart_survey.db.models import Answer, Question, QuestionType, Response, SurveyStatus
from smart_survey.db.repository import SurveyRepository
from smart_survey.errors import ValidationError

_MAX_COLUMNS = 50
_LONG_TEXT_HINTS = ("feedback", "comment", "response", "message", "note", "reason", "detail")


@dataclass(slots=True)
class ImportReport:
    survey_id: int
    slug: str
    questions: int
    imported: int
    skipped: int
    columns: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "survey_id": self.survey_id,
            "slug": self.slug,
            "questions": self.questions,
            "imported": self.imported,
            "skipped": self.skipped,
            "columns": self.columns,
        }


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "imported-survey"


def _infer_type(column: str) -> QuestionType:
    lowered = column.lower()
    if any(hint in lowered for hint in _LONG_TEXT_HINTS):
        return QuestionType.LONG_TEXT
    return QuestionType.TEXT


def import_csv(
    session: Session,
    path: str | Path,
    *,
    title: str | None = None,
    slug: str | None = None,
) -> ImportReport:
    csv_path = Path(path)
    if not csv_path.exists():
        raise ValidationError(f"CSV file not found: {csv_path}")

    frame = pd.read_csv(csv_path, dtype=str)
    columns = [str(column).strip() for column in frame.columns]
    if not columns:
        raise ValidationError("CSV file has no columns")
    if len(columns) > _MAX_COLUMNS:
        raise ValidationError(f"CSV has {len(columns)} columns; maximum is {_MAX_COLUMNS}")
    frame = frame.dropna(how="all")

    survey_title = title or f"Imported survey - {csv_path.stem.replace('_', ' ').title()}"
    survey_slug = slug or _slugify(survey_title)

    repo = SurveyRepository(session)
    survey = repo.create(
        title=survey_title,
        description=f"Imported from {csv_path.name}",
        slug=survey_slug,
        status=SurveyStatus.PUBLISHED.value,
        questions=[
            {"text": column, "qtype": _infer_type(column).value, "required": False}
            for column in columns
        ],
    )

    imported = skipped = 0
    question_by_column = dict(zip(columns, survey.questions, strict=False))
    for _, row in frame.iterrows():
        values = {
            column: ("" if pd.isna(row[column]) else str(row[column]).strip()) for column in columns
        }
        if not any(values.values()):
            skipped += 1
            continue
        response = Response(survey_id=survey.id, source="import")
        for column, value in values.items():
            if not value:
                continue
            response.answers.append(_build_answer(question_by_column[column], value))
        session.add(response)
        imported += 1

    session.flush()
    return ImportReport(
        survey_id=survey.id,
        slug=survey.slug,
        questions=len(columns),
        imported=imported,
        skipped=skipped,
        columns=columns,
    )


def _build_answer(question: Question, value: str) -> Answer:
    answer = Answer(question_id=question.id)
    if question.type.is_choice and question.options and value in question.options:
        answer.value_choice = value
        return answer
    answer.value_text = value[:10_000]
    return answer
