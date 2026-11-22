"""Export responses and analytics to CSV, Excel and JSON."""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from typing import Any

import pandas as pd

from smart_survey.db.models import QuestionType, Response, Survey


def responses_to_frame(survey: Survey, responses: Sequence[Response]) -> pd.DataFrame:
    """One row per response, one column per question (wide format)."""
    questions = list(survey.questions)
    rows: list[dict[str, Any]] = []
    for response in responses:
        row: dict[str, Any] = {
            "response_id": response.id,
            "submitted_at": response.submitted_at.isoformat() if response.submitted_at else None,
            "duration_seconds": response.duration_seconds,
            "source": response.source,
        }
        for question in questions:
            answer = response.answer_for(question.id)
            row[question.text] = _render(answer) if answer is not None else None
        rows.append(row)
    columns = ["response_id", "submitted_at", "duration_seconds", "source"] + [
        question.text for question in questions
    ]
    return pd.DataFrame(rows, columns=columns)


def responses_to_long_frame(survey: Survey, responses: Sequence[Response]) -> pd.DataFrame:
    """One row per answer (tidy/long format) - ideal for BI tools."""
    records: list[dict[str, Any]] = []
    for response in responses:
        for question in survey.questions:
            answer = response.answer_for(question.id)
            records.append(
                {
                    "response_id": response.id,
                    "submitted_at": response.submitted_at.isoformat()
                    if response.submitted_at
                    else None,
                    "question_id": question.id,
                    "question": question.text,
                    "question_type": question.qtype,
                    "value": _render(answer) if answer is not None else None,
                }
            )
    return pd.DataFrame(
        records,
        columns=[
            "response_id",
            "submitted_at",
            "question_id",
            "question",
            "question_type",
            "value",
        ],
    )


def _render(answer: Any) -> Any:
    if answer is None:
        return None
    value = answer.as_python
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return value


class ExportService:
    """Serialises survey data into downloadable artefacts."""

    @staticmethod
    def to_csv(
        survey: Survey, responses: Sequence[Response], *, long_format: bool = False
    ) -> bytes:
        frame = (
            responses_to_long_frame(survey, responses)
            if long_format
            else responses_to_frame(survey, responses)
        )
        return frame.to_csv(index=False).encode("utf-8")

    @staticmethod
    def to_excel(
        survey: Survey, responses: Sequence[Response], analytics: dict[str, Any] | None = None
    ) -> bytes:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            responses_to_frame(survey, responses).to_excel(
                writer, sheet_name="Responses", index=False
            )
            if analytics:
                ExportService._analytics_frame(analytics).to_excel(
                    writer, sheet_name="Analytics", index=False
                )
                timeline = pd.DataFrame(analytics.get("timeline", []))
                if not timeline.empty:
                    timeline.to_excel(writer, sheet_name="Timeline", index=False)
        return buffer.getvalue()

    @staticmethod
    def to_json(
        survey: Survey, responses: Sequence[Response], analytics: dict[str, Any] | None = None
    ) -> bytes:
        payload = {
            "survey": {
                "id": survey.id,
                "slug": survey.slug,
                "title": survey.title,
                "description": survey.description,
                "status": survey.status,
                "questions": [
                    {
                        "id": q.id,
                        "position": q.position,
                        "text": q.text,
                        "type": q.qtype,
                        "required": q.required,
                        "options": q.options,
                    }
                    for q in survey.questions
                ],
            },
            "responses": responses_to_frame(survey, responses).to_dict(orient="records"),
            "analytics": analytics,
        }
        return json.dumps(payload, indent=2, default=str).encode("utf-8")

    @staticmethod
    def _analytics_frame(analytics: dict[str, Any]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for question in analytics.get("questions", []):
            row: dict[str, Any] = {
                "question": question["text"],
                "type": question["type"],
                "answered": question.get("answered"),
                "skipped": question.get("skipped"),
            }
            if question["type"] in (QuestionType.RATING.value, QuestionType.NPS.value):
                row.update(
                    {
                        "mean": question.get("mean"),
                        "median": question.get("median"),
                        "std_dev": question.get("std_dev"),
                        "csat": question.get("csat"),
                    }
                )
                if "nps" in question:
                    row["nps"] = question["nps"]["score"]
            elif question["type"] in (
                QuestionType.SINGLE_CHOICE.value,
                QuestionType.MULTI_CHOICE.value,
            ):
                row["top_option"] = question.get("top")
            elif question["type"] == QuestionType.BOOLEAN.value:
                row["yes_percentage"] = question.get("yes_percentage")
            else:
                nlp = question.get("nlp") or {}
                row["average_words"] = question.get("average_words")
                row["net_sentiment"] = nlp.get("net_sentiment")
                row["summary"] = nlp.get("summary")
            rows.append(row)
        return pd.DataFrame(rows)
