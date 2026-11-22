"""Settings, environment info and demo data tools."""

from __future__ import annotations

import streamlit as st

from smart_survey import __version__
from smart_survey.config import get_settings
from smart_survey.ui import components as ui
from smart_survey.ui import data


def render(survey_id: int | None = None) -> None:
    ui.hero(
        "Settings",
        "Runtime configuration, demo data and diagnostics.",
        pill=f"v{__version__}",
    )
    settings = get_settings()

    with st.container(border=True):
        st.markdown("#### Runtime")
        rows = {
            "Environment": settings.environment,
            "Database": settings.database_url.split("://", 1)[0],
            "NLP backend": settings.nlp_backend,
            "Max topics": settings.nlp_max_topics,
            "API docs": f"{settings.public_base_url.rstrip('/')}/docs",
            "Admin API key": "•" * 12 + settings.admin_api_key[-4:],
        }
        st.table({"Setting": list(rows), "Value": list(rows.values())})

    with st.container(border=True):
        st.markdown("#### Demo data")
        st.caption("Generates a realistic six-question survey with synthetic responses.")
        count = st.slider("Responses to generate", min_value=20, max_value=300, value=60, step=10)
        if st.button("Generate demo survey", type="primary"):
            data.seed_demo(responses=count, force=True)
            st.success(f"Demo survey created with {count} responses.")
            st.rerun()

    with st.container(border=True):
        st.markdown("#### Diagnostics")
        st.caption("Cached analytics are refreshed automatically every 15 seconds.")
        if st.button("Clear cache and refresh"):
            data.invalidate()
            st.rerun()

    st.caption(
        "Tip: run the REST API with `uvicorn smart_survey.api.main:app --reload` "
        "to explore the interactive OpenAPI documentation."
    )
