"""Rule-based insight engine.

Turns the analytics payload into prioritised, human readable findings with an
explicit recommendation. This is deliberately transparent (every insight points
at the metric that produced it) rather than an opaque model output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["critical", "warning", "positive", "info"]

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "positive": 3}


@dataclass(slots=True)
class Insight:
    title: str
    description: str
    severity: Severity
    category: str
    metric: str | None = None
    value: float | None = None
    recommendation: str | None = None
    evidence: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "category": self.category,
            "metric": self.metric,
            "value": self.value,
            "recommendation": self.recommendation,
            "evidence": self.evidence,
        }


class InsightGenerator:
    """Derives insights from :func:`compute_survey_analytics` output."""

    def __init__(self, min_responses: int = 5) -> None:
        self.min_responses = min_responses

    def generate(self, analytics: dict[str, Any]) -> list[Insight]:
        insights: list[Insight] = []
        summary = analytics.get("summary", {})
        kpis = analytics.get("kpis", {})
        total = summary.get("total_responses", 0)

        insights.extend(self._volume_insights(summary, total))
        insights.extend(self._nps_insights(kpis.get("nps")))
        insights.extend(self._csat_insights(kpis.get("csat")))
        insights.extend(self._sentiment_insights(kpis.get("sentiment")))
        insights.extend(self._question_insights(analytics.get("questions", [])))

        return sorted(
            insights,
            key=lambda i: (_SEVERITY_ORDER.get(i.severity, 9), -(i.value or 0)),
        )

    def _volume_insights(self, summary: dict[str, Any], total: int) -> list[Insight]:
        out: list[Insight] = []
        if total == 0:
            out.append(
                Insight(
                    title="No responses yet",
                    description="The survey has not collected any responses. Share the public link to start gathering data.",
                    severity="info",
                    category="collection",
                    recommendation="Publish the survey and distribute the public response link.",
                )
            )
            return out
        if total < self.min_responses:
            out.append(
                Insight(
                    title="Sample size too small for reliable conclusions",
                    description=(
                        f"Only {total} responses collected. Statistical confidence is low "
                        f"below {self.min_responses} responses."
                    ),
                    severity="warning",
                    category="collection",
                    metric="total_responses",
                    value=float(total),
                    recommendation="Increase distribution before acting on the findings.",
                )
            )
        trend = summary.get("response_trend_pct")
        if trend is not None and trend <= -25:
            out.append(
                Insight(
                    title="Response volume is dropping",
                    description=f"Responses fell {abs(trend):.0f}% week over week.",
                    severity="warning",
                    category="collection",
                    metric="response_trend_pct",
                    value=trend,
                    recommendation="Re-engage respondents with a reminder or a shorter survey.",
                )
            )
        elif trend is not None and trend >= 25:
            out.append(
                Insight(
                    title="Response volume is growing",
                    description=f"Responses grew {trend:.0f}% week over week.",
                    severity="positive",
                    category="collection",
                    metric="response_trend_pct",
                    value=trend,
                )
            )
        completion = summary.get("completion_rate")
        if completion is not None and completion < 70 and total >= self.min_responses:
            out.append(
                Insight(
                    title="High drop-off rate",
                    description=f"Only {completion:.0f}% of responses completed every required question.",
                    severity="critical",
                    category="survey_design",
                    metric="completion_rate",
                    value=completion,
                    recommendation="Shorten the survey or move optional questions to the end.",
                )
            )
        return out

    def _nps_insights(self, nps: dict[str, Any] | None) -> list[Insight]:
        if not nps:
            return []
        score = nps.get("score", 0)
        if score >= 50:
            return [
                Insight(
                    title="Excellent Net Promoter Score",
                    description=f"NPS is {score:.0f}, indicating strong advocacy.",
                    severity="positive",
                    category="loyalty",
                    metric="nps",
                    value=score,
                )
            ]
        if score >= 0:
            return [
                Insight(
                    title="Neutral Net Promoter Score",
                    description=f"NPS is {score:.0f}. Promoters barely outnumber detractors.",
                    severity="warning",
                    category="loyalty",
                    metric="nps",
                    value=score,
                    recommendation="Investigate detractor verbatims to identify friction points.",
                )
            ]
        return [
            Insight(
                title="Negative Net Promoter Score",
                description=(
                    f"NPS is {score:.0f}: {nps.get('detractors', 0)} detractors vs "
                    f"{nps.get('promoters', 0)} promoters."
                ),
                severity="critical",
                category="loyalty",
                metric="nps",
                value=score,
                recommendation="Prioritise detractor follow-up within 48 hours.",
            )
        ]

    def _csat_insights(self, csat: float | None) -> list[Insight]:
        if csat is None:
            return []
        if csat >= 80:
            return [
                Insight(
                    title="High satisfaction",
                    description=f"{csat:.0f}% of ratings are in the top box of the scale.",
                    severity="positive",
                    category="satisfaction",
                    metric="csat",
                    value=csat,
                )
            ]
        if csat < 60:
            return [
                Insight(
                    title="Satisfaction below target",
                    description=f"Only {csat:.0f}% of ratings are in the top box of the scale.",
                    severity="critical",
                    category="satisfaction",
                    metric="csat",
                    value=csat,
                    recommendation="Review the lowest rated questions and recent negative verbatims.",
                )
            ]
        return []

    def _sentiment_insights(self, sentiment: dict[str, Any] | None) -> list[Insight]:
        if not sentiment or not sentiment.get("count"):
            return []
        counts = sentiment.get("sentiment", {})
        total = sentiment.get("count", 0) or 1
        negative_share = counts.get("NEGATIVE", 0) / total * 100
        positive_share = counts.get("POSITIVE", 0) / total * 100
        out: list[Insight] = []
        if negative_share >= 30:
            out.append(
                Insight(
                    title="Significant negative sentiment in verbatims",
                    description=f"{negative_share:.0f}% of free-text responses are negative.",
                    severity="critical" if negative_share >= 50 else "warning",
                    category="sentiment",
                    metric="negative_share",
                    value=round(negative_share, 2),
                    recommendation="Read the negative highlights and fix the most frequent complaint.",
                    evidence=sentiment.get("highlights", {}).get("negative", [])[:3],
                )
            )
        elif positive_share >= 70:
            out.append(
                Insight(
                    title="Strong positive sentiment",
                    description=f"{positive_share:.0f}% of free-text responses are positive.",
                    severity="positive",
                    category="sentiment",
                    metric="positive_share",
                    value=round(positive_share, 2),
                    evidence=sentiment.get("highlights", {}).get("positive", [])[:3],
                )
            )
        summary = sentiment.get("summary")
        if summary:
            out.append(
                Insight(
                    title="What respondents are saying",
                    description=summary,
                    severity="info",
                    category="sentiment",
                    metric="summary",
                )
            )
        return out

    def _question_insights(self, questions: list[dict[str, Any]]) -> list[Insight]:
        out: list[Insight] = []
        for question in questions:
            qtype = question.get("type")
            if qtype in ("rating", "nps") and question.get("count", 0) >= 3:
                std = question.get("std_dev", 0.0)
                scale = (question.get("scale_max") or 5) - (question.get("scale_min") or 1)
                if scale > 0 and std / scale >= 0.35:
                    out.append(
                        Insight(
                            title="Polarised opinions",
                            description=(
                                f"Responses to '{question['text']}' are widely spread "
                                f"(σ={std:.2f} on a {scale}-point range)."
                            ),
                            severity="warning",
                            category="survey_design",
                            metric="std_dev",
                            value=float(std),
                            recommendation="Segment the audience to find who is unhappy.",
                        )
                    )
            if qtype in ("single_choice", "multi_choice") and question.get("options"):
                top = question["options"][0]
                if top["percentage"] >= 60:
                    out.append(
                        Insight(
                            title="Dominant option",
                            description=(
                                f"{top['percentage']:.0f}% of respondents chose '{top['label']}' "
                                f"for '{question['text']}'."
                            ),
                            severity="info",
                            category="distribution",
                            metric="top_option_share",
                            value=float(top["percentage"]),
                        )
                    )
            if qtype in ("text", "long_text") and question.get("skipped", 0) > question.get(
                "answered", 0
            ):
                out.append(
                    Insight(
                        title="High skip rate on a free-text question",
                        description=(
                            f"'{question['text']}' was skipped by {question['skipped']} respondents."
                        ),
                        severity="warning",
                        category="survey_design",
                        metric="skipped",
                        value=float(question["skipped"]),
                        recommendation="Consider making the question optional or offering choice options.",
                    )
                )
        return out
