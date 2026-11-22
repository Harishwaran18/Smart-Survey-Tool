"""AI insights page: prioritised findings, topics, keywords and narrative summary."""

from __future__ import annotations

import streamlit as st

from smart_survey.ui import components as ui
from smart_survey.ui import data
from smart_survey.ui.theme import PALETTE, SEVERITY_COLORS

SEVERITY_LABELS = {
    "all": "All findings",
    "critical": "Critical",
    "warning": "Warnings",
    "positive": "Wins",
    "info": "Context",
}


def render(survey_id: int) -> None:
    survey = data.survey_detail(survey_id)
    payload = data.analytics(survey_id)
    if survey is None or payload is None:
        ui.empty_state("Survey not found.", "🔍")
        return

    ui.hero(
        "AI insights",
        "Findings are generated from your metrics, ranked by business impact, with a recommended action.",
        pill="Automated analysis",
    )

    if payload["summary"]["total_responses"] == 0:
        ui.empty_state("Insights appear once responses are collected.", "🧠")
        return

    findings = data.insights(survey_id)
    # The narrative summary is rendered in its own section below, so keep it out of the list.
    findings = [finding for finding in findings if finding.get("metric") != "summary"]
    counts = {severity: 0 for severity in SEVERITY_COLORS}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1

    ui.kpi_row(
        [
            {"label": "Critical", "value": str(counts.get("critical", 0)), "hint": "Act now"},
            {"label": "Warnings", "value": str(counts.get("warning", 0)), "hint": "Watch closely"},
            {"label": "Wins", "value": str(counts.get("positive", 0)), "hint": "Reinforce"},
            {"label": "Signals", "value": str(counts.get("info", 0)), "hint": "Context"},
        ]
    )

    st.write("")
    severity = st.radio(
        "Filter",
        options=list(SEVERITY_LABELS),
        format_func=lambda key: SEVERITY_LABELS[key],
        horizontal=True,
        label_visibility="collapsed",
    )
    visible = [f for f in findings if severity == "all" or f["severity"] == severity]
    if not visible:
        ui.empty_state("No findings in this category.", "✅")
    for finding in visible:
        ui.insight_card(finding)

    st.write("")
    sentiment = (payload.get("kpis") or {}).get("sentiment")
    if sentiment and sentiment.get("count"):
        st.markdown("#### Narrative summary")
        ui.summary_box("What respondents are saying", sentiment.get("summary", ""))

        left, right = st.columns([1, 1])
        with left:
            st.markdown("##### Top keywords")
            keywords = sentiment.get("keywords", [])
            st.markdown(
                " ".join(f'<span class="badge draft">{kw["term"]}</span>' for kw in keywords[:14]),
                unsafe_allow_html=True,
            )
        with right:
            st.markdown("##### Topics discovered")
            for topic in sentiment.get("topics", [])[:5]:
                st.markdown(
                    f'<div class="card" style="padding:12px 14px;margin-bottom:8px;">'
                    f'<b>Theme {topic["cluster"] + 1}</b> · {topic["size"]} mentions<br>'
                    f'<span style="color:{PALETTE["neutral"]};font-size:.85rem;">'
                    f'{", ".join(topic["keywords"][:6])}</span></div>',
                    unsafe_allow_html=True,
                )

        highlights = sentiment.get("highlights", {})
        if highlights.get("positive") or highlights.get("negative"):
            st.markdown("#### Verbatim highlights")
            columns = st.columns(2)
            with columns[0]:
                st.markdown("**Praise**")
                for item in highlights.get("positive", []):
                    st.markdown(f"> {item}")
            with columns[1]:
                st.markdown("**Concerns**")
                for item in highlights.get("negative", []):
                    st.markdown(f"> {item}")
