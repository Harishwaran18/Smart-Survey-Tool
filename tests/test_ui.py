"""End-to-end smoke tests for the Streamlit UI using Streamlit's AppTest harness."""

from __future__ import annotations

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from smart_survey.db.session import get_session
from smart_survey.services.survey_service import SurveyService

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture()
def app(demo_survey):
    st.cache_data.clear()
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def _navigate(at: AppTest, page: str) -> AppTest:
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception, at.exception
    return at


def test_app_boots(app):
    assert at_least_one_markdown(app)
    assert app.sidebar.selectbox[0].value is not None


def at_least_one_markdown(app: AppTest) -> bool:
    return len(app.markdown) > 0


@pytest.mark.parametrize(
    "page",
    ["Dashboard", "Collect responses", "AI insights", "Responses", "Survey builder", "Settings"],
)
def test_every_page_renders_without_exception(app, page):
    _navigate(app, page)
    assert not app.exception


def test_dashboard_shows_kpis(app):
    _navigate(app, "Dashboard")
    html = " ".join(markdown.value for markdown in app.markdown)
    assert "Total responses" in html
    assert "Net Promoter Score" in html


def test_collect_form_renders_inputs(app):
    _navigate(app, "Collect responses")
    assert app.button  # at least the submit button exists


def test_insights_page_lists_findings(app):
    _navigate(app, "AI insights")
    html = " ".join(markdown.value for markdown in app.markdown)
    assert "insight" in html.lower()


def test_builder_page_is_reachable(app):
    _navigate(app, "Survey builder")
    assert app.session_state["page"] == "Survey builder"


def test_ui_survives_missing_survey(app):
    app.session_state["selected_survey"] = 999999
    app.run()
    assert not app.exception


def test_seed_then_counts_are_consistent(app, demo_survey):
    with get_session() as session:
        service = SurveyService(session)
        assert service.response_count(demo_survey.id) == 40
        analytics = service.analytics_for(demo_survey.id)
        assert analytics["summary"]["total_responses"] == 40
