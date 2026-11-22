"""Quantitative analytics: NPS, CSAT, distributions, trends and response quality.

Pure functions over the ORM objects - no I/O, so they are trivially unit testable
and reusable from the API, the Streamlit UI and the export pipeline.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from statistics import mean, median, pstdev
from typing import Any

from smart_survey.db.models import Question, QuestionType, Response, Survey
from smart_survey.services.nlp import NLPService, get_nlp_service


@dataclass(slots=True)
class NPSBreakdown:
    score: float
    promoters: int
    passives: int
    detractors: int
    total: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "score": round(self.score, 2),
            "promoters": self.promoters,
            "passives": self.passives,
            "detractors": self.detractors,
            "total": self.total,
        }


def compute_nps(scores: Sequence[float]) -> NPSBreakdown:
    """Net Promoter Score on a 0-10 scale: %promoters - %detractors."""
    if not scores:
        return NPSBreakdown(0.0, 0, 0, 0, 0)
    promoters = sum(1 for s in scores if s >= 9)
    detractors = sum(1 for s in scores if s <= 6)
    passives = len(scores) - promoters - detractors
    score = (promoters - detractors) / len(scores) * 100
    return NPSBreakdown(score, promoters, passives, detractors, len(scores))


def compute_csat(scores: Sequence[float], scale_max: float) -> float:
    """Top-2-box satisfaction: share of ratings in the top two points of the scale."""
    if not scores:
        return 0.0
    threshold = max(1.0, scale_max - 1)
    satisfied = sum(1 for s in scores if s >= threshold)
    return round(satisfied / len(scores) * 100, 2)


def _numeric_stats(
    values: Sequence[float], scale_min: int | None, scale_max: int | None
) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    lo = scale_min if scale_min is not None else int(min(values))
    hi = scale_max if scale_max is not None else int(max(values))
    distribution = Counter(int(round(v)) for v in values)
    return {
        "count": len(values),
        "mean": round(mean(values), 3),
        "median": round(median(values), 3),
        "std_dev": round(pstdev(values), 3) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
        "scale_min": lo,
        "scale_max": hi,
        "distribution": {str(k): distribution.get(k, 0) for k in range(lo, hi + 1)},
        "csat": compute_csat(values, hi),
    }


def _choice_stats(values: Sequence[str], options: Sequence[str] | None) -> dict[str, Any]:
    counts = Counter(values)
    total = sum(counts.values())
    ordered = list(options) if options else [k for k, _ in counts.most_common()]
    ordered += [k for k in counts if k not in ordered]
    return {
        "count": total,
        "options": [
            {
                "label": option,
                "count": counts.get(option, 0),
                "percentage": round(counts.get(option, 0) / total * 100, 2) if total else 0.0,
            }
            for option in ordered
        ],
        "top": counts.most_common(1)[0][0] if counts else None,
    }


def _multi_choice_stats(
    values: Sequence[Sequence[str]], options: Sequence[str] | None
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for group in values:
        counts.update(group)
    total_respondents = len(values)
    ordered = list(options) if options else [k for k, _ in counts.most_common()]
    ordered += [k for k in counts if k not in ordered]
    return {
        "count": total_respondents,
        "options": [
            {
                "label": option,
                "count": counts.get(option, 0),
                "percentage": round(counts.get(option, 0) / total_respondents * 100, 2)
                if total_respondents
                else 0.0,
            }
            for option in ordered
        ],
        "top": counts.most_common(1)[0][0] if counts else None,
    }


def _timeline(responses: Sequence[Response], days: int = 30) -> list[dict[str, Any]]:
    if not responses:
        return []
    now = datetime.now(UTC)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    buckets: dict[str, int] = {}
    for offset in range(days):
        day = (start + timedelta(days=offset)).date().isoformat()
        buckets[day] = 0
    for response in responses:
        submitted = response.submitted_at
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=UTC)
        key = submitted.date().isoformat()
        if key in buckets:
            buckets[key] += 1
    return [{"date": day, "count": count} for day, count in buckets.items()]


def _question_analysis(
    question: Question, responses: Sequence[Response], nlp: NLPService
) -> dict[str, Any]:
    answers = [r.answer_for(question.id) for r in responses]
    answers = [a for a in answers if a is not None]
    qtype = question.type

    payload: dict[str, Any] = {
        "question_id": question.id,
        "position": question.position,
        "text": question.text,
        "type": qtype.value,
        "required": question.required,
        "answered": len(answers),
        "skipped": len(responses) - len(answers),
    }

    if qtype.is_numeric:
        values = [a.value_number for a in answers if a.value_number is not None]
        payload.update(_numeric_stats(values, question.scale_min, question.scale_max))
        if qtype is QuestionType.NPS:
            payload["nps"] = compute_nps(values).as_dict()
    elif qtype is QuestionType.SINGLE_CHOICE:
        values = [a.value_choice for a in answers if a.value_choice]
        payload.update(_choice_stats(values, question.options))
    elif qtype is QuestionType.MULTI_CHOICE:
        groups = [a.value_choices for a in answers if a.value_choices]
        payload.update(_multi_choice_stats(groups, question.options))
    elif qtype is QuestionType.BOOLEAN:
        values = [bool(a.value_boolean) for a in answers if a.value_boolean is not None]
        yes = sum(1 for v in values if v)
        payload.update(
            {
                "count": len(values),
                "yes": yes,
                "no": len(values) - yes,
                "yes_percentage": round(yes / len(values) * 100, 2) if values else 0.0,
            }
        )
    else:
        texts = [a.value_text for a in answers if a.value_text]
        analysis = nlp.analyze_texts(texts)
        payload.update(
            {
                "count": len(texts),
                "average_words": round(sum(len(t.split()) for t in texts) / len(texts), 2)
                if texts
                else 0.0,
                "nlp": analysis,
            }
        )
    return payload


def compute_survey_analytics(
    survey: Survey,
    responses: Sequence[Response],
    *,
    nlp: NLPService | None = None,
    timeline_days: int = 30,
) -> dict[str, Any]:
    """Full analytics payload for one survey."""
    nlp = nlp or get_nlp_service()
    total = len(responses)
    completed = sum(
        1
        for r in responses
        if all(r.answer_for(q.id) is not None for q in survey.questions if q.required)
    )
    durations = [r.duration_seconds for r in responses if r.duration_seconds]

    free_text = [
        a.value_text
        for r in responses
        for a in r.answers
        if a.value_text and a.question and a.question.type.is_free_text
    ]

    nps_values: list[float] = []
    for question in survey.questions:
        if question.type is QuestionType.NPS:
            nps_values.extend(
                a.value_number
                for r in responses
                if (a := r.answer_for(question.id)) is not None and a.value_number is not None
            )

    rating_values: list[float] = []
    rating_scale_max = 5.0
    for question in survey.questions:
        if question.type is QuestionType.RATING:
            rating_values.extend(
                a.value_number
                for r in responses
                if (a := r.answer_for(question.id)) is not None and a.value_number is not None
            )
            rating_scale_max = float(question.scale_max or 5)

    per_question = [_question_analysis(q, responses, nlp) for q in survey.questions]
    daily = _timeline(responses, days=timeline_days)
    last_7 = sum(point["count"] for point in daily[-7:])
    prev_7 = sum(point["count"] for point in daily[-14:-7])

    return {
        "survey": {
            "id": survey.id,
            "slug": survey.slug,
            "title": survey.title,
            "status": survey.status,
            "questions": len(survey.questions),
        },
        "summary": {
            "total_responses": total,
            "completed_responses": completed,
            "completion_rate": round(completed / total * 100, 2) if total else 0.0,
            "average_duration_seconds": round(mean(durations), 1) if durations else None,
            "responses_last_7_days": last_7,
            "response_trend_pct": round((last_7 - prev_7) / prev_7 * 100, 2) if prev_7 else None,
        },
        "kpis": {
            "nps": compute_nps(nps_values).as_dict() if nps_values else None,
            "csat": compute_csat(rating_values, rating_scale_max) if rating_values else None,
            "sentiment": nlp.analyze_texts(free_text) if free_text else None,
        },
        "timeline": daily,
        "questions": per_question,
    }


class AnalyticsService:
    """Thin stateful wrapper so callers can inject an NLP backend."""

    def __init__(self, nlp: NLPService | None = None, timeline_days: int = 30) -> None:
        self.nlp = nlp or get_nlp_service()
        self.timeline_days = timeline_days

    def analyse(
        self, survey: Survey, responses: Sequence[Response], *, timeline_days: int | None = None
    ) -> dict[str, Any]:
        return compute_survey_analytics(
            survey,
            responses,
            nlp=self.nlp,
            timeline_days=timeline_days or self.timeline_days,
        )

    @staticmethod
    def group_by_day(responses: Sequence[Response]) -> dict[str, int]:
        grouped: defaultdict[str, int] = defaultdict(int)
        for response in responses:
            submitted = response.submitted_at
            if submitted.tzinfo is None:
                submitted = submitted.replace(tzinfo=UTC)
            grouped[submitted.date().isoformat()] += 1
        return dict(sorted(grouped.items()))
