"""Public survey form (the respondent experience)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from smart_survey.config import get_settings
from smart_survey.schemas import AnswerIn, ResponseCreate
from smart_survey.ui import components as ui
from smart_survey.ui import data


def render(survey_id: int) -> None:
    survey = data.survey_detail(survey_id)
    if survey is None:
        ui.empty_state("Survey not found.", "🔍")
        return

    is_open = survey["status"] == "published"
    ui.hero(
        survey["title"],
        survey.get("description") or "Your feedback shapes what we build next.",
        pill="Open for responses" if is_open else f"Closed · {survey['status']}",
    )

    settings = get_settings()
    link = f"{settings.public_base_url.rstrip('/')}/api/v1/public/surveys/{survey['slug']}"
    with st.expander("Share this survey"):
        st.code(link, language="text")
        st.caption("Anyone with this link can submit a response through the public API.")
        st.code(
            f"""curl -X POST "{link}/responses" \\
  -H "Content-Type: application/json" \\
  -d '{{"answers": [{{"question_id": {survey['questions'][0]['id'] if survey['questions'] else 1}, "value": "Great product"}}]}}'""",
            language="bash",
        )

    test_mode = False
    if not is_open:
        st.warning("This survey is not published. Enable test mode to submit anyway.")
        test_mode = st.toggle("Test mode", value=False)
        if not test_mode:
            return

    with st.form("respond-form"):
        values: dict[int, Any] = {}
        for question in survey["questions"]:
            values[question["id"]] = _render_input(question)
        submitted = st.form_submit_button(
            "Submit response", type="primary", use_container_width=True
        )

    if submitted:
        answers = [
            AnswerIn(question_id=qid, value=value)
            for qid, value in values.items()
            if value not in (None, "", [])
        ]
        try:
            data.submit_response(
                survey["slug"], ResponseCreate(answers=answers), require_open=not test_mode
            )
        except Exception as exc:
            st.error(f"Could not submit: {exc}")
        else:
            st.success("Thank you — your response has been recorded.")
            st.balloons()


def _render_input(question: dict[str, Any]) -> Any:
    label = question["text"] + (" *" if question["required"] else "")
    qtype = question["type"]
    key = f"q-{question['id']}"

    if qtype == "long_text":
        return st.text_area(label, key=key, height=120)
    if qtype == "text":
        return st.text_input(label, key=key)
    if qtype == "rating":
        low = question.get("scale_min") or 1
        high = question.get("scale_max") or 5
        return st.slider(label, min_value=low, max_value=high, value=low, key=key)
    if qtype == "nps":
        return st.select_slider(
            label + "  (0 = not likely, 10 = extremely likely)",
            options=list(range(0, 11)),
            value=8,
            key=key,
        )
    if qtype == "single_choice":
        return st.radio(label, question.get("options", []), key=key, index=None)
    if qtype == "multi_choice":
        return st.multiselect(label, question.get("options", []), key=key)
    if qtype == "boolean":
        choice = st.radio(label, ["Yes", "No"], key=key, index=None)
        return None if choice is None else choice == "Yes"
    return st.text_input(label, key=key)
