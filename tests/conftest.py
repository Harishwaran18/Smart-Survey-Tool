"""Shared pytest fixtures.

The environment is configured at import time (before any project module is
imported) so that ``get_settings`` and the SQLAlchemy engine bind to an isolated
temporary database.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="smart-survey-tests-"))
os.environ["SST_ENVIRONMENT"] = "test"
os.environ["SST_DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}"
os.environ["SST_ADMIN_API_KEY"] = "test-api-key"
os.environ["SST_LOG_LEVEL"] = "WARNING"
os.environ["SST_NLP_BACKEND"] = "classic"

import pytest  # noqa: E402

from smart_survey.db.models import Base  # noqa: E402
from smart_survey.db.session import get_engine, get_session  # noqa: E402
from smart_survey.services.survey_service import SurveyService  # noqa: E402

ADMIN_HEADERS = {"X-API-Key": "test-api-key"}


@pytest.fixture()
def clean_db():
    """Recreate the schema so every test starts from a known state."""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture()
def session(clean_db):
    with get_session() as db_session:
        yield db_session


@pytest.fixture()
def service(session):
    return SurveyService(session)


@pytest.fixture()
def demo_survey(service):
    survey = service.seed_demo(responses=40, force=True)
    # Commit so other connections (the API client, the Streamlit app) can read it.
    service.session.commit()
    return survey


@pytest.fixture()
def client(clean_db):
    from fastapi.testclient import TestClient

    from smart_survey.api.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
