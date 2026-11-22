"""HTTP contract tests for the REST API."""

from __future__ import annotations

import pytest

from tests.conftest import ADMIN_HEADERS

SURVEY_PAYLOAD = {
    "title": "API Survey",
    "description": "Created through the REST API",
    "status": "draft",
    "questions": [
        {"text": "How likely to recommend?", "qtype": "nps"},
        {"text": "Satisfaction", "qtype": "rating", "scale_min": 1, "scale_max": 5},
        {"text": "Preferred plan", "qtype": "single_choice", "options": ["Free", "Pro"]},
        {"text": "Comments", "qtype": "long_text", "required": False},
    ],
}


@pytest.fixture()
def survey(client):
    response = client.post("/api/v1/surveys", json=SURVEY_PAYLOAD, headers=ADMIN_HEADERS)
    assert response.status_code == 201
    return response.json()


class TestSystem:
    def test_health(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["database"] == "sqlite"

    def test_openapi_is_served(self, client):
        spec = client.get("/openapi.json").json()
        assert spec["info"]["title"]
        assert "/api/v1/surveys" in spec["paths"]

    def test_docs_page(self, client):
        assert client.get("/docs").status_code == 200


class TestAuth:
    def test_admin_routes_require_key(self, client):
        assert client.get("/api/v1/surveys").status_code == 401

    def test_wrong_key_rejected(self, client):
        assert client.get("/api/v1/surveys", headers={"X-API-Key": "nope"}).status_code == 401

    def test_public_routes_are_open(self, client, survey):
        response = client.get(f"/api/v1/public/surveys/{survey['slug']}")
        assert response.status_code == 200


class TestSurveyCrud:
    def test_create(self, survey):
        assert survey["slug"] == "api-survey"
        assert len(survey["questions"]) == 4

    def test_list_pagination(self, client, survey):
        body = client.get("/api/v1/surveys?limit=1&offset=0", headers=ADMIN_HEADERS).json()
        assert body["total"] >= 1
        assert len(body["items"]) == 1
        assert body["items"][0]["question_count"] == 4

    def test_get(self, client, survey):
        body = client.get(f"/api/v1/surveys/{survey['id']}", headers=ADMIN_HEADERS).json()
        assert body["title"] == "API Survey"

    def test_get_missing_returns_404(self, client):
        response = client.get("/api/v1/surveys/424242", headers=ADMIN_HEADERS)
        assert response.status_code == 404
        assert response.json()["error"] == "NotFoundError"

    def test_patch(self, client, survey):
        response = client.patch(
            f"/api/v1/surveys/{survey['id']}",
            json={"title": "Renamed Survey"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Renamed Survey"

    def test_publish_and_close(self, client, survey):
        published = client.post(f"/api/v1/surveys/{survey['id']}/publish", headers=ADMIN_HEADERS)
        assert published.json()["status"] == "published"
        closed = client.post(f"/api/v1/surveys/{survey['id']}/close", headers=ADMIN_HEADERS)
        assert closed.json()["status"] == "closed"

    def test_delete(self, client, survey):
        response = client.delete(f"/api/v1/surveys/{survey['id']}", headers=ADMIN_HEADERS)
        assert response.status_code == 204
        assert (
            client.get(f"/api/v1/surveys/{survey['id']}", headers=ADMIN_HEADERS).status_code == 404
        )

    def test_validation_error_shape(self, client):
        response = client.post("/api/v1/surveys", json={"title": "x"}, headers=ADMIN_HEADERS)
        assert response.status_code == 422
        assert response.json()["error"] == "ValidationError"

    def test_share_link(self, client, survey):
        body = client.get(
            f"/api/v1/surveys/{survey['id']}/share-link", headers=ADMIN_HEADERS
        ).json()
        assert body["slug"] == survey["slug"]
        assert body["url"].endswith(survey["slug"])


class TestResponses:
    def _publish(self, client, survey):
        client.post(f"/api/v1/surveys/{survey['id']}/publish", headers=ADMIN_HEADERS)

    def test_submit_and_read(self, client, survey):
        self._publish(client, survey)
        questions = {q["qtype"]: q for q in survey["questions"]}
        payload = {
            "answers": [
                {"question_id": questions["nps"]["id"], "value": 9},
                {"question_id": questions["rating"]["id"], "value": 4},
                {"question_id": questions["single_choice"]["id"], "value": "Pro"},
                {"question_id": questions["long_text"]["id"], "value": "Great tool, very fast"},
            ],
            "duration_seconds": 120,
        }
        created = client.post(f"/api/v1/public/surveys/{survey['slug']}/responses", json=payload)
        assert created.status_code == 201
        assert len(created.json()["answers"]) == 4

        listing = client.get(
            f"/api/v1/surveys/{survey['id']}/responses", headers=ADMIN_HEADERS
        ).json()
        assert listing["total"] == 1

    def test_draft_survey_rejects_response(self, client, survey):
        response = client.post(
            f"/api/v1/public/surveys/{survey['slug']}/responses", json={"answers": []}
        )
        assert response.status_code == 409

    def test_missing_required_answer_returns_422(self, client, survey):
        self._publish(client, survey)
        response = client.post(
            f"/api/v1/public/surveys/{survey['slug']}/responses", json={"answers": []}
        )
        assert response.status_code == 422
        assert response.json()["error"] == "ValidationError"


class TestAnalyticsEndpoints:
    def test_analytics(self, client, survey):
        client.post(f"/api/v1/surveys/{survey['id']}/publish", headers=ADMIN_HEADERS)
        questions = {q["qtype"]: q for q in survey["questions"]}
        client.post(
            f"/api/v1/public/surveys/{survey['slug']}/responses",
            json={
                "answers": [
                    {"question_id": questions["nps"]["id"], "value": 10},
                    {"question_id": questions["rating"]["id"], "value": 5},
                    {"question_id": questions["single_choice"]["id"], "value": "Free"},
                ]
            },
        )
        body = client.get(f"/api/v1/surveys/{survey['id']}/analytics", headers=ADMIN_HEADERS).json()
        assert body["summary"]["total_responses"] == 1
        assert body["kpis"]["nps"]["score"] == 100.0

    def test_insights(self, client, survey):
        body = client.get(f"/api/v1/surveys/{survey['id']}/insights", headers=ADMIN_HEADERS).json()
        assert isinstance(body, list)
        assert body and "severity" in body[0]

    @pytest.mark.parametrize(
        ("fmt", "content_type"),
        [
            ("csv", "text/csv"),
            ("excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("json", "application/json"),
        ],
    )
    def test_export_formats(self, client, survey, fmt, content_type):
        response = client.get(
            f"/api/v1/surveys/{survey['id']}/export?format={fmt}", headers=ADMIN_HEADERS
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(content_type)
        assert len(response.content) > 0

    def test_export_long_format(self, client, survey):
        response = client.get(
            f"/api/v1/surveys/{survey['id']}/export?format=csv&long_format=true",
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200
        header = response.content.decode().splitlines()[0]
        assert "question" in header
