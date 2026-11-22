"""Command line interface: ``python -m smart_survey <command>``.

Commands
--------
serve        Run the REST API with uvicorn.
ui           Run the Streamlit dashboard.
seed         Create the demo survey with synthetic responses.
import-csv   Migrate a legacy flat CSV of responses.
analyse      Print analytics for a survey slug or id.
export       Write responses to CSV/Excel/JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from smart_survey import __version__
from smart_survey.config import get_settings
from smart_survey.db.session import get_session, init_db
from smart_survey.logging_config import configure_logging, get_logger

logger = get_logger(__name__)


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "smart_survey.api.main:app",
        host=args.host or settings.api_host,
        port=args.port or settings.api_port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )
    return 0


def _cmd_ui(args: argparse.Namespace) -> int:
    import subprocess

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(Path(__file__).resolve().parent.parent / "app.py"),
        "--server.port",
        str(args.port),
    ]
    return subprocess.call(command)


def _cmd_seed(args: argparse.Namespace) -> int:
    from smart_survey.services.survey_service import SurveyService

    init_db()
    with get_session() as session:
        survey = SurveyService(session).seed_demo(responses=args.responses, force=args.force)
        print(json.dumps({"survey_id": survey.id, "slug": survey.slug}, indent=2))
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    from smart_survey.services.importer import import_csv

    init_db()
    with get_session() as session:
        report = import_csv(session, args.path, title=args.title, slug=args.slug)
    print(json.dumps(report.as_dict(), indent=2))
    return 0


def _cmd_analyse(args: argparse.Namespace) -> int:
    from smart_survey.services.survey_service import SurveyService

    init_db()
    with get_session() as session:
        service = SurveyService(session)
        survey = (
            service.get(args.survey) if args.survey.isdigit() else service.get_by_slug(args.survey)
        )
        payload = service.analytics_for(survey.id)
        findings = service.insights_for(survey.id)

    print(f"\n{payload['survey']['title']}  ({payload['survey']['slug']})")
    print("=" * 60)
    for key, value in payload["summary"].items():
        print(f"  {key.replace('_', ' ').title():<32} {value}")
    nps = payload["kpis"].get("nps")
    if nps:
        print(
            f"  {'NPS':<32} {nps['score']}  (P{nps['promoters']}/Pa{nps['passives']}/D{nps['detractors']})"
        )
    sentiment = payload["kpis"].get("sentiment")
    if sentiment:
        print(f"  {'Net sentiment':<32} {sentiment['net_sentiment']:+.1f}")
    print("\nInsights")
    print("-" * 60)
    for finding in findings:
        print(f"  [{finding['severity'].upper():<8}] {finding['title']}")
        print(f"             {finding['description']}")
    print()
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from smart_survey.services.export import ExportService
    from smart_survey.services.survey_service import SurveyService

    init_db()
    with get_session() as session:
        service = SurveyService(session)
        survey = (
            service.get(args.survey) if args.survey.isdigit() else service.get_by_slug(args.survey)
        )
        responses = service.responses_for(survey.id, limit=100_000)
        if args.format == "csv":
            content = ExportService.to_csv(survey, responses, long_format=args.long)
        elif args.format == "excel":
            content = ExportService.to_excel(survey, responses, service.analytics_for(survey.id))
        else:
            content = ExportService.to_json(survey, responses, service.analytics_for(survey.id))

    destination = Path(args.out) if args.out else Path(f"{survey.slug}.{args.format}")
    destination.write_bytes(content)
    print(f"Wrote {len(content):,} bytes to {destination}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smart-survey",
        description="Smart Survey Tool - AI survey collection and analytics",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the REST API")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=_cmd_serve)

    ui = sub.add_parser("ui", help="Run the Streamlit dashboard")
    ui.add_argument("--port", type=int, default=8501)
    ui.set_defaults(func=_cmd_ui)

    seed = sub.add_parser("seed", help="Create demo survey data")
    seed.add_argument("--responses", type=int, default=60)
    seed.add_argument("--force", action="store_true")
    seed.set_defaults(func=_cmd_seed)

    importer = sub.add_parser("import-csv", help="Import legacy responses from CSV")
    importer.add_argument("path")
    importer.add_argument("--title")
    importer.add_argument("--slug")
    importer.set_defaults(func=_cmd_import)

    analyse = sub.add_parser("analyse", help="Print analytics and insights")
    analyse.add_argument("survey", help="Survey id or slug")
    analyse.set_defaults(func=_cmd_analyse)

    export = sub.add_parser("export", help="Export responses")
    export.add_argument("survey", help="Survey id or slug")
    export.add_argument("--format", choices=["csv", "excel", "json"], default="csv")
    export.add_argument("--long", action="store_true", help="Tidy/long CSV format")
    export.add_argument("--out")
    export.set_defaults(func=_cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    try:
        return int(args.func(args))
    except Exception as exc:  # surface a clean error instead of a traceback
        logger.error("%s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
