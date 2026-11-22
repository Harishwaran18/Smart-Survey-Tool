"""Survey builder and management page."""

from __future__ import annotations

from typing import Any

import streamlit as st

from smart_survey.db.models import SurveyStatus
from smart_survey.schemas import QuestionCreate, SurveyCreate
from smart_survey.ui import components as ui
from smart_survey.ui import data

QUESTION_LABELS = {
    "text": "Short text",
    "long_text": "Long text",
    "rating": "Rating scale",
    "nps": "Net Promoter Score (0-10)",
    "single_choice": "Single choice",
    "multi_choice": "Multiple choice",
    "boolean": "Yes / No",
}


def _state() -> list[dict[str, Any]]:
    return st.session_state.setdefault("builder_questions", [])


def render(survey_id: int | None = None) -> None:
    ui.hero(
        "Survey builder",
        "Design multi-question surveys with validation, branching-ready types and instant publishing.",
        pill="Authoring",
    )
    create_tab, manage_tab = st.tabs(["Create a survey", "Manage surveys"])
    with create_tab:
        _render_create()
    with manage_tab:
        _render_manage()


def _render_create() -> None:
    questions = _state()

    with st.container(border=True):
        title = st.text_input("Survey title", placeholder="e.g. Q1 Customer Satisfaction Pulse")
        description = st.text_area(
            "Description", placeholder="Why are you running this survey?", height=80
        )

    st.markdown("#### Questions")
    if not questions:
        st.caption("No questions yet — add your first one below.")
    for index, question in enumerate(list(questions)):
        columns = st.columns([6, 1])
        with columns[0]:
            detail = QUESTION_LABELS.get(question["qtype"], question["qtype"])
            if question.get("options"):
                detail += f" · {len(question['options'])} options"
            required = "required" if question["required"] else "optional"
            st.markdown(f"**{index + 1}. {question['text']}**")
            st.caption(f"{detail} · {required}")
        with columns[1]:
            if st.button("Remove", key=f"remove-{index}", use_container_width=True):
                questions.pop(index)
                st.rerun()

    with st.form("add-question", clear_on_submit=True):
        st.markdown("##### Add a question")
        left, right = st.columns([3, 2])
        with left:
            text = st.text_input("Question text", placeholder="How satisfied are you with…?")
        with right:
            qtype_label = st.selectbox("Type", list(QUESTION_LABELS.values()))
        qtype = next(key for key, label in QUESTION_LABELS.items() if label == qtype_label)
        options_raw = ""
        scale_min, scale_max, required = None, None, True
        if qtype in ("single_choice", "multi_choice"):
            options_raw = st.text_input(
                "Options (comma separated)", placeholder="Option A, Option B, Option C"
            )
        if qtype == "rating":
            cols = st.columns(3)
            scale_min = cols[0].number_input("Scale min", min_value=1, max_value=10, value=1)
            scale_max = cols[1].number_input("Scale max", min_value=2, max_value=10, value=5)
            required = cols[2].checkbox("Required", value=True)
        elif qtype != "nps":
            required = st.checkbox("Required", value=True)

        if st.form_submit_button("Add question", type="primary"):
            _add_question(text, qtype, options_raw, scale_min, scale_max, required)

    st.write("")
    cols = st.columns([1, 1, 2])
    publish_now = cols[0].button("Save & publish", type="primary", use_container_width=True)
    save_draft = cols[1].button("Save as draft", use_container_width=True)
    if publish_now or save_draft:
        _save(title, description, publish_now)


def _add_question(
    text: str,
    qtype: str,
    options_raw: str,
    scale_min: int | None,
    scale_max: int | None,
    required: bool,
) -> None:
    options = [option.strip() for option in options_raw.split(",") if option.strip()]
    payload = {
        "text": text.strip(),
        "qtype": qtype,
        "required": required,
        "options": options or None,
        "scale_min": scale_min,
        "scale_max": scale_max,
    }
    try:
        validated = QuestionCreate(**payload)
    except Exception as exc:  # pydantic ValidationError
        st.error(f"Could not add question: {exc}")
        return
    _state().append(validated.model_dump())
    st.rerun()


def _save(title: str, description: str, publish: bool) -> None:
    questions = _state()
    if not title.strip():
        st.error("Give the survey a title before saving.")
        return
    if not questions:
        st.error("Add at least one question.")
        return
    payload = SurveyCreate(
        title=title,
        description=description or None,
        status=SurveyStatus.PUBLISHED.value if publish else SurveyStatus.DRAFT.value,
        questions=[QuestionCreate(**question) for question in questions],
    )
    survey_id = data.create_survey(payload)
    st.session_state["builder_questions"] = []
    st.session_state["selected_survey"] = survey_id
    st.success(
        f"Survey saved as {'published' if publish else 'draft'}. Switch to the Dashboard to see it."
    )


def _render_manage() -> None:
    surveys = data.list_surveys()
    if not surveys:
        ui.empty_state("No surveys yet. Create your first one in the previous tab.", "🗂️")
        return

    for survey in surveys:
        with st.container(border=True):
            header, actions = st.columns([3, 2])
            with header:
                st.markdown(
                    f"**{survey['title']}** {ui.status_badge(survey['status'])}",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"{survey['question_count']} questions · {survey['response_count']} responses · "
                    f"slug `{survey['slug']}`"
                )
            with actions:
                buttons = st.columns(3)
                if survey["status"] != SurveyStatus.PUBLISHED.value:
                    if buttons[0].button("Publish", key=f"pub-{survey['id']}"):
                        data.set_status(survey["id"], SurveyStatus.PUBLISHED)
                        st.rerun()
                elif buttons[0].button("Close", key=f"close-{survey['id']}"):
                    data.set_status(survey["id"], SurveyStatus.CLOSED)
                    st.rerun()
                if buttons[1].button("Open", key=f"open-{survey['id']}"):
                    st.session_state["selected_survey"] = survey["id"]
                    st.session_state["page"] = "Dashboard"
                    st.rerun()
                if buttons[2].button("Delete", key=f"del-{survey['id']}"):
                    st.session_state[f"confirm-delete-{survey['id']}"] = True
            if st.session_state.get(f"confirm-delete-{survey['id']}"):
                st.warning("This permanently deletes the survey and all responses.")
                if st.button(
                    "Yes, delete permanently", key=f"confirm-{survey['id']}", type="primary"
                ):
                    data.delete_survey(survey["id"])
                    st.session_state.pop(f"confirm-delete-{survey['id']}", None)
                    if st.session_state.get("selected_survey") == survey["id"]:
                        st.session_state.pop("selected_survey", None)
                    st.rerun()
