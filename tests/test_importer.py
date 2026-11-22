"""Tests for the legacy CSV importer."""

from __future__ import annotations

import pytest

from smart_survey.errors import ValidationError
from smart_survey.services.importer import import_csv


def test_imports_rows_and_columns(tmp_path, session):
    csv_file = tmp_path / "responses.csv"
    csv_file.write_text(
        "Name,Email,Feedback\n"
        'Ada,ada@example.com,"Great product, very fast"\n'
        'Linus,linus@example.com,"Support was slow"\n',
        encoding="utf-8",
    )
    report = import_csv(session, csv_file)

    assert report.imported == 2
    assert report.skipped == 0
    assert report.columns == ["Name", "Email", "Feedback"]
    assert report.questions == 3
    assert report.slug == "imported-survey-responses"


def test_skips_blank_rows(tmp_path, session):
    csv_file = tmp_path / "blank.csv"
    csv_file.write_text("Feedback\n\n,\n", encoding="utf-8")
    report = import_csv(session, csv_file)
    assert report.imported == 0
    assert report.skipped == 0


def test_missing_file_raises(session):
    with pytest.raises(ValidationError):
        import_csv(session, "/nonexistent/file.csv")


def test_legacy_repository_file_is_importable(session):
    from pathlib import Path

    legacy = Path(__file__).resolve().parent.parent / "survey_responses.csv"
    if not legacy.exists():
        pytest.skip("legacy sample file not present")
    report = import_csv(session, legacy, title="Legacy Feedback")
    assert report.imported >= 1
    assert "Feedback" in report.columns
