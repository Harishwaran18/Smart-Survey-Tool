# Development guide

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
pre-commit install   # optional
```

## Daily commands

```bash
make test        # run the suite
make cov         # coverage (HTML in htmlcov/)
make lint        # ruff
make format      # ruff format
make typecheck   # mypy
make seed        # demo data
make ui          # Streamlit
make api         # uvicorn --reload
```

## Conventions

- **Layers** — never import `fastapi` or `streamlit` from `smart_survey/services`
  or `smart_survey/db`.
- **Types** — public functions carry annotations; `mypy` runs over the package
  (the UI layer is excluded because Streamlit's types are loose).
- **Errors** — raise a `SmartSurveyError` subclass, never `HTTPException`, from the
  service layer.
- **Logging** — `get_logger(__name__)`, log state changes at INFO, failures at ERROR.
- **Tests** — one behaviour per test, name it after the rule it protects
  (`test_out_of_scale_value_rejected`), and assert on the domain outcome rather
  than on implementation details.

## Adding a question type

1. Add the member to `QuestionType` in `db/models.py`.
2. Extend `QTypeLiteral` and `QuestionCreate._check_type_rules` in `schemas.py`.
3. Handle the value shape in `SurveyService._validate_value` and
   `ResponseRepository._build_answer`.
4. Add an analytics branch in `analytics._question_analysis`.
5. Render it in `ui/pages/collect.py` and `ui/pages/dashboard.py`.
6. Cover it with a service test and an API test.

## Adding an endpoint

1. Create the service method first and test it.
2. Add the route with a Pydantic response model.
3. Add a contract test in `tests/test_api.py` (happy path + at least one failure).
4. Document it in the README API table.

## Database changes

There is no migration tool yet. For local development delete `data/smart_survey.db`
and restart; `init_db()` recreates the schema. Before a production release, adopt
Alembic and generate an initial revision from the current metadata.
