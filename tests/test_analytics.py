"""Tests for quantitative analytics and the insight engine."""

from __future__ import annotations

import pytest

from smart_survey.services.analytics import compute_csat, compute_nps
from smart_survey.services.insights import InsightGenerator


class TestNPS:
    def test_all_promoters(self):
        assert compute_nps([9, 10, 10]).score == 100.0

    def test_all_detractors(self):
        assert compute_nps([0, 3, 6]).score == -100.0

    def test_mixed_distribution(self):
        nps = compute_nps([10, 9, 8, 7, 6, 0])
        assert nps.promoters == 2
        assert nps.passives == 2
        assert nps.detractors == 2
        assert nps.score == 0.0

    def test_empty(self):
        nps = compute_nps([])
        assert nps.score == 0.0
        assert nps.total == 0

    def test_boundaries(self):
        assert compute_nps([9]).promoters == 1
        assert compute_nps([8]).passives == 1
        assert compute_nps([6]).detractors == 1


class TestCSAT:
    def test_all_top_box(self):
        assert compute_csat([5, 4], 5) == 100.0

    def test_none_top_box(self):
        assert compute_csat([1, 2, 3], 5) == 0.0

    def test_half(self):
        assert compute_csat([5, 1], 5) == 50.0

    def test_empty(self):
        assert compute_csat([], 5) == 0.0

    def test_ten_point_scale(self):
        assert compute_csat([10, 9, 8], 10) == pytest.approx(66.67, abs=0.01)


class TestAnalyticsPayload:
    def test_payload_contains_all_sections(self, service, demo_survey):
        payload = service.analytics_for(demo_survey.id)
        assert set(payload) == {"survey", "summary", "kpis", "timeline", "questions"}
        assert payload["summary"]["total_responses"] == 40
        assert len(payload["timeline"]) == 30
        assert payload["kpis"]["nps"]["total"] == 40
        assert payload["kpis"]["csat"] is not None
        assert payload["kpis"]["sentiment"]["count"] > 0

    def test_numeric_question_stats(self, service, demo_survey):
        payload = service.analytics_for(demo_survey.id)
        rating = next(q for q in payload["questions"] if q["type"] == "rating")
        assert rating["count"] == 40
        assert rating["min"] >= 1 and rating["max"] <= 5
        assert sum(rating["distribution"].values()) == 40

    def test_choice_distribution_sums_to_total(self, service, demo_survey):
        payload = service.analytics_for(demo_survey.id)
        choice = next(q for q in payload["questions"] if q["type"] == "single_choice")
        assert sum(option["count"] for option in choice["options"]) == 40

    def test_multi_choice_counts_respondents(self, service, demo_survey):
        payload = service.analytics_for(demo_survey.id)
        multi = next(q for q in payload["questions"] if q["type"] == "multi_choice")
        assert multi["count"] == 40

    def test_empty_survey_analytics(self, service):
        from smart_survey.schemas import QuestionCreate, SurveyCreate

        survey = service.create(
            SurveyCreate(title="Empty survey", questions=[QuestionCreate(text="Any feedback?")])
        )
        payload = service.analytics_for(survey.id)
        assert payload["summary"]["total_responses"] == 0
        assert payload["kpis"]["nps"] is None
        assert payload["timeline"] == []


class TestInsights:
    def test_insights_have_required_fields(self, service, demo_survey):
        findings = service.insights_for(demo_survey.id)
        assert findings
        for finding in findings:
            assert {"title", "description", "severity", "category"} <= set(finding)
            assert finding["severity"] in {"critical", "warning", "positive", "info"}

    def test_sorted_by_severity(self, service, demo_survey):
        order = {"critical": 0, "warning": 1, "info": 2, "positive": 3}
        findings = service.insights_for(demo_survey.id)
        severities = [order[f["severity"]] for f in findings]
        assert severities == sorted(severities)

    def test_no_responses_produces_collection_hint(self):
        generator = InsightGenerator()
        findings = generator.generate(
            {"summary": {"total_responses": 0}, "kpis": {}, "questions": []}
        )
        assert any(f.category == "collection" for f in findings)

    def test_low_nps_is_critical(self):
        generator = InsightGenerator()
        findings = generator.generate(
            {
                "summary": {"total_responses": 50, "completion_rate": 95},
                "kpis": {"nps": {"score": -20, "promoters": 5, "detractors": 25}},
                "questions": [],
            }
        )
        assert any(f.severity == "critical" and f.metric == "nps" for f in findings)
