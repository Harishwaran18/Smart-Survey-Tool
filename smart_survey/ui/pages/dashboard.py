"""Executive dashboard page."""

from __future__ import annotations

from typing import Any

import streamlit as st

from smart_survey.ui import components as ui
from smart_survey.ui import data


def _delta(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:+.1f}% vs previous 7 days"


def _nps_card(nps: dict[str, Any] | None) -> dict[str, Any]:
    if not nps:
        return {"label": "Net Promoter Score", "value": "—", "hint": "No NPS question"}
    return {
        "label": "Net Promoter Score",
        "value": f"{nps['score']:.0f}",
        "hint": f"{nps['promoters']} promoters · {nps['detractors']} detractors",
    }


def _csat_card(csat: float | None) -> dict[str, Any]:
    if csat is None:
        return {"label": "CSAT (top-2-box)", "value": "—", "hint": "No rating question"}
    return {
        "label": "CSAT (top-2-box)",
        "value": f"{csat:.0f}%",
        "hint": "Ratings in the top two points",
    }


def _sentiment_card(sentiment: dict[str, Any] | None) -> dict[str, Any]:
    if not sentiment or not sentiment.get("count"):
        return {"label": "Net sentiment", "value": "—", "hint": "No free-text answers"}
    net = sentiment["net_sentiment"]
    return {
        "label": "Net sentiment",
        "value": f"{net:+.0f}",
        "delta": f"{sentiment['sentiment']['POSITIVE']} positive · {sentiment['sentiment']['NEGATIVE']} negative",
        "hint": f"{sentiment['count']} free-text answers analysed",
    }


def render(survey_id: int) -> None:
    survey = data.survey_detail(survey_id)
    payload = data.analytics(survey_id)
    if survey is None or payload is None:
        ui.empty_state("Survey not found.", "🔍")
        return

    summary = payload["summary"]
    kpis = payload["kpis"]
    ui.hero(
        survey["title"],
        survey.get("description") or "Real-time survey performance and AI-generated insights.",
        pill=f"{survey['status']} · {len(survey['questions'])} questions",
    )

    ui.kpi_row(
        [
            {
                "label": "Total responses",
                "value": f"{summary['total_responses']:,}",
                "delta": _delta(summary.get("response_trend_pct")),
                "hint": f"{summary['responses_last_7_days']} in the last 7 days",
            },
            {
                "label": "Completion rate",
                "value": f"{summary['completion_rate']:.0f}%",
                "hint": f"{summary['completed_responses']} of {summary['total_responses']} complete",
            },
            {
                "label": "Median time",
                "value": (
                    f"{summary['average_duration_seconds'] / 60:.1f} min"
                    if summary.get("average_duration_seconds")
                    else "—"
                ),
                "hint": "Average time to complete",
            },
            _nps_card(kpis.get("nps")),
            _csat_card(kpis.get("csat")),
            _sentiment_card(kpis.get("sentiment")),
        ]
    )

    st.write("")
    if summary["total_responses"] == 0:
        ui.empty_state(
            "No responses collected yet. Share the public link from the Collect page.", "📭"
        )
        return

    left, right = st.columns([1.6, 1])
    with left:
        st.markdown("#### Response volume")
        st.plotly_chart(
            ui.trend_line(payload["timeline"]),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    with right:
        st.markdown("#### Sentiment split")
        sentiment = kpis.get("sentiment")
        if sentiment and sentiment.get("count"):
            st.plotly_chart(
                ui.sentiment_donut(sentiment["sentiment"]),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        else:
            ui.empty_state("No free-text answers to analyse.", "💬")

    st.write("")
    st.markdown("#### Question breakdown")
    tabs = st.tabs([f"Q{q['position'] + 1}" for q in payload["questions"]])
    for tab, question in zip(tabs, payload["questions"], strict=False):
        with tab:
            _render_question(question)


def _render_question(question: dict[str, Any]) -> None:
    st.markdown(f"**{question['text']}**")
    type_labels = {
        "nps": "NPS",
        "text": "Text",
        "long_text": "Long text",
        "rating": "Rating",
        "single_choice": "Single choice",
        "multi_choice": "Multi choice",
        "boolean": "Yes / No",
    }
    st.caption(
        f"{type_labels.get(question['type'], question['type'])} · {question['answered']} answered · "
        f"{question['skipped']} skipped"
    )
    qtype = question["type"]

    if qtype in ("rating", "nps"):
        left, right = st.columns([1, 1.4])
        with left:
            if qtype == "nps" and question.get("nps"):
                st.plotly_chart(
                    ui.gauge(question["nps"]["score"], "NPS", height=220),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
                nps = question["nps"]
                st.caption(
                    f"Promoters {nps['promoters']} · Passives {nps['passives']} · "
                    f"Detractors {nps['detractors']}"
                )
            else:
                cols = st.columns(3)
                cols[0].metric("Mean", f"{question['mean']:.2f}")
                cols[1].metric("Median", f"{question['median']:.1f}")
                cols[2].metric("CSAT", f"{question['csat']:.0f}%")
        with right:
            st.plotly_chart(
                ui.distribution_chart(question["distribution"]),
                use_container_width=True,
                config={"displayModeBar": False},
            )
    elif qtype in ("single_choice", "multi_choice"):
        options = question.get("options", [])
        labels = [option["label"] for option in options]
        values = [option["count"] for option in options]
        st.plotly_chart(
            ui.bar_chart(labels, values), use_container_width=True, config={"displayModeBar": False}
        )
    elif qtype == "boolean":
        left, right = st.columns([1, 2])
        left.metric("Yes", f"{question['yes_percentage']:.0f}%")
        right.plotly_chart(
            ui.bar_chart(["Yes", "No"], [question["yes"], question["no"]], height=180),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    else:
        nlp = question.get("nlp") or {}
        left, right = st.columns([1, 1.6])
        with left:
            if nlp.get("count"):
                st.plotly_chart(
                    ui.sentiment_donut(nlp["sentiment"], height=220),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
            st.caption(f"Average {question.get('average_words', 0)} words per answer")
        with right:
            if nlp.get("summary"):
                ui.summary_box("AI summary", nlp["summary"])
            if nlp.get("keywords"):
                st.caption("Top keywords")
                st.markdown(
                    " ".join(
                        f'<span class="badge draft">{kw["term"]}</span>'
                        for kw in nlp["keywords"][:10]
                    ),
                    unsafe_allow_html=True,
                )
