"""Reusable Streamlit render helpers: KPI cards, charts, insight cards."""

from __future__ import annotations

import html
from collections.abc import Sequence
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from smart_survey.ui.theme import PALETTE, SENTIMENT_COLORS, SEVERITY_COLORS

PLOT_LAYOUT = dict(
    font=dict(family="Inter, sans-serif", color=PALETTE["text"], size=12),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=30, b=10),
    hoverlabel=dict(bgcolor="white", font_size=12),
)


def hero(title: str, subtitle: str, pill: str = "") -> None:
    badge = f'<span class="pill">{html.escape(pill)}</span>' if pill else ""
    st.markdown(
        f'<div class="hero"><h1>{html.escape(title)}</h1>'
        f"<p>{html.escape(subtitle)}</p>{badge}</div>",
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str, delta: str | None = None, hint: str | None = None) -> None:
    delta_html = ""
    if delta:
        direction = "up" if not delta.strip().startswith("-") else "down"
        delta_html = f'<div class="delta {direction}">{html.escape(delta)}</div>'
    hint_html = f'<div class="hint">{html.escape(hint)}</div>' if hint else ""
    st.markdown(
        f'<div class="kpi"><div class="label">{html.escape(label)}</div>'
        f'<div class="value">{html.escape(value)}</div>{delta_html}{hint_html}</div>',
        unsafe_allow_html=True,
    )


def kpi_row(cards: Sequence[dict[str, Any]]) -> None:
    columns = st.columns(len(cards))
    for column, card in zip(columns, cards, strict=False):
        with column:
            kpi_card(**card)


def section(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"### {title}")
    if subtitle:
        st.caption(subtitle)


def summary_box(label: str, text: str) -> None:
    if not text:
        return
    st.markdown(
        f'<div class="summary-box"><div class="label">{html.escape(label)}</div>'
        f"<p>{html.escape(text)}</p></div>",
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    return f'<span class="badge {html.escape(status)}">{html.escape(status.upper())}</span>'


def insight_card(insight: dict[str, Any]) -> None:
    color = SEVERITY_COLORS.get(insight.get("severity", "info"), PALETTE["neutral"])
    recommendation = insight.get("recommendation")
    rec_html = (
        f'<div class="rec"><b>Recommendation:</b> {html.escape(recommendation)}</div>'
        if recommendation
        else ""
    )
    evidence = insight.get("evidence") or []
    evidence_html = "".join(
        f'<div class="desc" style="margin-top:6px;padding-left:10px;border-left:2px solid #E2E8F0;">'
        f"“{html.escape(item)}”</div>"
        for item in evidence[:3]
    )
    st.markdown(
        f'<div class="insight" style="border-left-color:{color}">'
        f'<span class="tag" style="color:{color}">{html.escape(insight.get("severity", "info"))}'
        f' · {html.escape(insight.get("category", ""))}</span>'
        f'<div class="title">{html.escape(insight.get("title", ""))}</div>'
        f'<div class="desc">{html.escape(insight.get("description", ""))}</div>'
        f"{evidence_html}{rec_html}</div>",
        unsafe_allow_html=True,
    )


def sentiment_donut(counts: dict[str, int], height: int = 260) -> go.Figure:
    labels = ["Positive", "Neutral", "Negative"]
    values = [counts.get("POSITIVE", 0), counts.get("NEUTRAL", 0), counts.get("NEGATIVE", 0)]
    colors = [
        SENTIMENT_COLORS["POSITIVE"],
        SENTIMENT_COLORS["NEUTRAL"],
        SENTIMENT_COLORS["NEGATIVE"],
    ]
    total = sum(values) or 1
    # Blank labels for empty slices so the 0% markers do not overlap at the top.
    texts = [f"{value} ({value / total:.0%})" if value else "" for value in values]
    figure = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.62,
            marker=dict(colors=colors, line=dict(color="white", width=2)),
            text=texts,
            textinfo="text",
            textposition="inside",
            hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        )
    )
    figure.update_layout(
        **PLOT_LAYOUT, height=height, showlegend=True, legend=dict(orientation="h", y=-0.08)
    )
    return figure


def trend_line(timeline: Sequence[dict[str, Any]], height: int = 260) -> go.Figure:
    dates = [point["date"] for point in timeline]
    counts = [point["count"] for point in timeline]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=dates,
            y=counts,
            mode="lines+markers",
            line=dict(color=PALETTE["primary"], width=3),
            marker=dict(size=6, color=PALETTE["primary"]),
            fill="tozeroy",
            fillcolor="rgba(79,70,229,0.10)",
            hovertemplate="%{x}: %{y} responses<extra></extra>",
        )
    )
    figure.update_layout(
        **PLOT_LAYOUT, height=height, yaxis=dict(gridcolor="#E2E8F0", rangemode="tozero")
    )
    return figure


def bar_chart(
    labels: Sequence[str], values: Sequence[float], height: int = 260, horizontal: bool = True
) -> go.Figure:
    colors = [PALETTE["primary"] if i == 0 else "#A5B4FC" for i in range(len(labels))]
    if horizontal:
        figure = go.Figure(
            go.Bar(
                x=values,
                y=labels,
                orientation="h",
                marker_color=colors,
                text=values,
                textposition="outside",
                hovertemplate="%{y}: %{x}<extra></extra>",
            )
        )
        figure.update_layout(
            **PLOT_LAYOUT, height=height, xaxis=dict(showgrid=True, gridcolor="#E2E8F0")
        )
    else:
        figure = go.Figure(
            go.Bar(
                x=labels,
                y=values,
                marker_color=colors,
                text=values,
                textposition="outside",
                hovertemplate="%{x}: %{y}<extra></extra>",
            )
        )
        figure.update_layout(**PLOT_LAYOUT, height=height, yaxis=dict(gridcolor="#E2E8F0"))
    return figure


def gauge(
    value: float, title: str, low: float = -100, high: float = 100, height: int = 240
) -> go.Figure:
    figure = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            title={"text": title, "font": {"size": 13, "color": PALETTE["neutral"]}},
            number={"font": {"size": 30, "color": PALETTE["text"]}},
            gauge={
                "axis": {"range": [low, high], "tickwidth": 1, "tickcolor": "#CBD5E1"},
                "bar": {"color": PALETTE["primary"], "thickness": 0.28},
                "bgcolor": "white",
                "borderwidth": 0,
                "steps": [
                    {"range": [low, low + (high - low) * 0.35], "color": "#FEE2E2"},
                    {
                        "range": [low + (high - low) * 0.35, low + (high - low) * 0.6],
                        "color": "#FEF3C7",
                    },
                    {"range": [low + (high - low) * 0.6, high], "color": "#DCFCE7"},
                ],
            },
        )
    )
    figure.update_layout(**PLOT_LAYOUT, height=height)
    return figure


def distribution_chart(distribution: dict[str, int], height: int = 240) -> go.Figure:
    keys = sorted(distribution, key=lambda k: int(k))
    values = [distribution[k] for k in keys]
    figure = go.Figure(
        go.Bar(
            x=keys,
            y=values,
            marker_color=PALETTE["accent"],
            text=values,
            textposition="outside",
            hovertemplate="Score %{x}: %{y}<extra></extra>",
        )
    )
    figure.update_layout(
        **PLOT_LAYOUT, height=height, yaxis=dict(gridcolor="#E2E8F0", rangemode="tozero")
    )
    return figure


def empty_state(message: str, icon: str = "📊") -> None:
    st.markdown(
        f'<div class="card" style="text-align:center;padding:40px;">'
        f'<div style="font-size:2rem;">{icon}</div>'
        f'<p style="margin-top:8px;">{html.escape(message)}</p></div>',
        unsafe_allow_html=True,
    )
