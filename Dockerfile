# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY pyproject.toml README.md ./
COPY smart_survey ./smart_survey
COPY app.py ./
COPY .streamlit ./.streamlit

RUN pip install --no-deps -e . \
 && mkdir -p /app/data \
 && useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser

ENV SST_ENVIRONMENT=production \
    SST_API_HOST=0.0.0.0 \
    SST_API_PORT=8000 \
    SST_DATABASE_URL=sqlite:////app/data/smart_survey.db

EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "smart_survey.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
