"""FastAPI application factory and public REST surface."""

from __future__ import annotations

from smart_survey.api.routes import analytics, responses, surveys
from smart_survey.config import get_settings
from smart_survey.db.session import init_db
from smart_survey.logging_config import configure_logging, get_logger
from smart_survey.schemas import HealthResponse

logger = get_logger(__name__)

DESCRIPTION = """
Production-grade survey platform API.

* **Surveys** - create, publish and version multi-question surveys.
* **Responses** - validated public submission endpoint with per-type rules.
* **Analytics** - NPS, CSAT, distributions, trends and sentiment.
* **Insights** - prioritised findings with recommendations.
* **Exports** - CSV, Excel and JSON.

Admin endpoints require the `X-API-Key` header.
"""


def create_app():
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    from smart_survey.errors import SmartSurveyError

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    init_db()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "Smart Survey Tool"},
        license_info={"name": "MIT"},
        openapi_tags=[
            {"name": "system", "description": "Health and metadata"},
            {"name": "surveys", "description": "Survey management (admin)"},
            {"name": "responses", "description": "Public submission and admin listing"},
            {"name": "analytics", "description": "Analytics, insights and exports"},
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(SmartSurveyError)
    async def _domain_error(_request, exc: SmartSurveyError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.__class__.__name__,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "ValidationError",
                "message": "request validation failed",
                "details": exc.errors(),
            },
        )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version="1.0.0",
            environment=settings.environment,
            database=settings.database_url.split("://", 1)[0],
            nlp_backend=settings.nlp_backend,
        )

    app.include_router(surveys.router, prefix="/api/v1", tags=["surveys"])
    app.include_router(responses.public_router, prefix="/api/v1/public", tags=["responses"])
    app.include_router(responses.admin_router, prefix="/api/v1", tags=["responses"])
    app.include_router(analytics.router, prefix="/api/v1", tags=["analytics"])

    logger.info("api ready environment=%s", settings.environment)
    return app


app = create_app()
