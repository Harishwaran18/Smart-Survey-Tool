"""Streamlit entry point: shell, navigation and survey selection."""

from __future__ import annotations

import streamlit as st

from smart_survey import __version__
from smart_survey.config import get_settings
from smart_survey.logging_config import configure_logging
from smart_survey.ui import components as ui
from smart_survey.ui import data
from smart_survey.ui.pages import builder, collect, dashboard, insights, responses, settings
from smart_survey.ui.theme import inject_theme

PAGES = {
    "Dashboard": dashboard.render,
    "Collect responses": collect.render,
    "AI insights": insights.render,
    "Responses": responses.render,
    "Survey builder": builder.render,
    "Settings": settings.render,
}

_SURVEY_AGNOSTIC = {"Survey builder", "Settings"}


def _sidebar(surveys: list[dict]) -> tuple[str, int | None]:
    with st.sidebar:
        st.markdown(
            '<div class="brand"><div class="mark">SS</div>'
            '<div><div class="name">Smart Survey</div>'
            '<div class="tag">AI survey intelligence</div></div></div>',
            unsafe_allow_html=True,
        )
        if st.session_state.get("page") not in PAGES:
            st.session_state["page"] = "Dashboard"
        page = st.radio(
            "Navigate",
            list(PAGES),
            index=list(PAGES).index(st.session_state["page"]),
            label_visibility="collapsed",
        )
        st.session_state["page"] = page

        st.markdown("---")
        selected: int | None = None
        if surveys:
            labels = {survey["id"]: f"{survey['title']}" for survey in surveys}
            current = st.session_state.get("selected_survey")
            if current not in labels:
                current = surveys[0]["id"]
            selected = st.selectbox(
                "Active survey",
                options=list(labels),
                index=list(labels).index(current),
                format_func=lambda key: labels[key],
            )
            st.session_state["selected_survey"] = selected
            status = next(s["status"] for s in surveys if s["id"] == selected)
            st.caption(f"Status: {status.upper()}")
        else:
            st.caption("No surveys yet")

        st.markdown("---")
        st.caption(f"v{__version__} · {get_settings().environment}")
    return page, selected


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    st.set_page_config(
        page_title="Smart Survey Tool",
        page_icon="📝",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    data.ensure_db()

    surveys = data.list_surveys()
    page, survey_id = _sidebar(surveys)
    render = PAGES[page]

    if page in _SURVEY_AGNOSTIC or survey_id is None:
        if survey_id is None and page not in _SURVEY_AGNOSTIC:
            ui.hero(
                "Welcome to Smart Survey Tool",
                "Create your first survey or generate realistic demo data to explore the analytics.",
                pill="Getting started",
            )
            columns = st.columns(2)
            if columns[0].button("Create a survey", type="primary", use_container_width=True):
                st.session_state["page"] = "Survey builder"
                st.rerun()
            if columns[1].button("Generate demo data", use_container_width=True):
                data.seed_demo(responses=60, force=True)
                st.rerun()
            return
        render(survey_id)
        return

    render(survey_id)
