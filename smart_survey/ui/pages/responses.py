"""Responses browser with filtering and downloads."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from smart_survey.ui import components as ui
from smart_survey.ui import data


def render(survey_id: int) -> None:
    survey = data.survey_detail(survey_id)
    if survey is None:
        ui.empty_state("Survey not found.", "🔍")
        return

    ui.hero(
        "Responses",
        "Inspect individual submissions, filter by keyword and export in any format.",
        pill=f"{survey['slug']}",
    )

    frame = data.responses_frame(survey_id)
    if frame.empty:
        ui.empty_state("No responses collected yet.", "📭")
        return

    columns = st.columns([2, 2, 1])
    with columns[0]:
        search = st.text_input("Search all answers", placeholder="keyword, email, segment…")
    with columns[1]:
        text_columns = [
            c
            for c in frame.columns
            if frame[c].dtype == object and c not in ("submitted_at", "source")
        ]
        column = st.selectbox("Column", ["All columns"] + text_columns)
    with columns[2]:
        st.metric("Rows", f"{len(frame):,}")

    filtered = frame
    if search:
        mask = frame.astype(str).apply(
            lambda row: row.str.contains(search, case=False, na=False).any(), axis=1
        )
        filtered = frame[mask]
    if column != "All columns" and search:
        filtered = frame[frame[column].astype(str).str.contains(search, case=False, na=False)]

    st.caption(f"Showing {len(filtered):,} of {len(frame):,} responses")
    st.dataframe(filtered, use_container_width=True, height=440, hide_index=True)

    st.markdown("#### Download")
    download_columns = st.columns(3)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    downloads = [
        ("CSV (wide)", "csv", "text/csv", "csv"),
        (
            "Excel workbook",
            "excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        ),
        ("JSON (with analytics)", "json", "application/json", "json"),
    ]
    for column, (label, fmt, mime, extension) in zip(download_columns, downloads, strict=False):
        with column:
            payload = data.export_bytes(survey_id, fmt)
            st.download_button(
                label,
                data=payload,
                file_name=f"{survey['slug']}-{timestamp}.{extension}",
                mime=mime,
                use_container_width=True,
            )

    st.write("")
    with st.expander("Preview tidy (long) export"):
        long_frame = data.export_bytes(survey_id, "csv", long_format=True).decode("utf-8")
        st.code("\n".join(long_frame.splitlines()[:12]) + "\n…", language="csv")
