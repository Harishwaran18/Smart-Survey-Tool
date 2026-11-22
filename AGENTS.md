# Agent notes

## Commands

```bash
pip install -r requirements-dev.txt && pip install -e .   # setup
make test            # pytest (106 tests, ~11s)
make lint            # ruff check
make format          # ruff format
make typecheck       # mypy
python -m smart_survey seed --responses 60 --force        # demo data
python -m smart_survey ui --port 8501                     # Streamlit
python -m smart_survey serve --port 8000 --reload          # FastAPI
```

## Layout rules

- `smart_survey/db` → SQLAlchemy models + repositories. Only this layer runs SQL.
- `smart_survey/services` → business logic. Must not import `fastapi` or `streamlit`.
- `smart_survey/api` → HTTP only; raise `SmartSurveyError` subclasses from services.
- `smart_survey/ui` → Streamlit pages; read through `ui/data.py` cached wrappers.
- `tests/conftest.py` sets `SST_*` env vars **before** importing project modules and
  points the engine at a temp SQLite file. Fixtures: `clean_db`, `session`,
  `service`, `demo_survey`, `client`.

## Gotchas

- `get_settings()` is `lru_cache`d; tests must set env vars at import time.
- The `session` fixture commits only on teardown — call `session.commit()` before
  reading the data from another connection (API client, AppTest).
- `TfidfVectorizer.get_feature_names_out()` lives on the vectorizer, not on the
  returned matrix.
- SQLite reuses rowids after deletes; do not assert on ids after a forced reseed.
- Streamlit `st.cache_data` persists across AppTest runs — clear it in fixtures.
