"""Entry point for GitHub Actions and local runs (``python main.py``)."""
from __future__ import annotations

import argparse
import sys

from application.observer import Observer
from domain import errors as E
from domain.errors import FlashTrendError
from domain.models import ONE_OFF_MIN_MINUTES, RUN_MODES, RunRequest
from infrastructure import settings as cfg
from presentation.log import LogObserver
from presentation.output import write_output

EXIT_OK, EXIT_RUN_ERROR, EXIT_CONFIG = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flashtrend", description="FlashTrend daily digest")
    sub = p.add_subparsers(dest="command")
    run = sub.add_parser("run", help="collect → score → dedup → Gemini → Supabase (default)")
    run.add_argument("--dry-run", action="store_true",
                     help="read real data, write nothing, skip Gemini and image upload")
    run.add_argument("--output-dir", default=None,
                     help="also write <run_id>_digest.json and the chart PNG here (debug only)")
    run.add_argument("--mode", default="digest", help=f"what to look for: {' | '.join(RUN_MODES)} "
                     "(empty = digest)")
    run.add_argument("--query", default=None, help="search mode: what to search for, any language")
    run.add_argument("--request", default=None, help="the caller's tag, stored on the run to find it")
    run.add_argument("--min-minutes", default=None,
                     help=f"trending/search: keep videos at least this long, 0 = every length "
                          f"(empty = {ONE_OFF_MIN_MINUTES})")
    sub.add_parser("check-media", help="HEAD every media URL; mark 404s alive=false")
    sub.add_parser("check-bilibili", help="one anonymous Bilibili search + channel card (no secrets needed)")
    p.set_defaults(command="run", dry_run=False, output_dir=None, mode="digest", query=None, request=None,
                   min_minutes=None)
    return p


def main(argv: list[str] | None = None, observer: Observer | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg.load_dotenv()
    if args.command == "check-bilibili":  # reads Bilibili anonymously: needs none of the four secrets
        from composition_root import build_bilibili_check

        return EXIT_OK if build_bilibili_check(observer or LogObserver(())).run() else EXIT_RUN_ERROR
    try:
        settings = cfg.from_env()
    except (cfg.MissingSettings, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    obs = observer or LogObserver(settings.secret_values())
    try:
        minutes = str(args.min_minutes or "").strip()
        request = RunRequest(args.mode or "digest", args.query, args.request,
                             int(minutes) if minutes else ONE_OFF_MIN_MINUTES)
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    from composition_root import build_digest, build_media_check

    if args.command == "check-media":
        build_media_check(settings, obs).run()
        return EXIT_OK

    try:
        result = build_digest(settings, obs, dry_run=args.dry_run).run(request)
    except FlashTrendError as exc:  # e.g. SCHEMA_MISMATCH before a run row exists
        obs.warn(f"{exc.code}: {exc.message}")
        return EXIT_RUN_ERROR

    if args.output_dir:
        chart_png = None
        try:
            from infrastructure.chart import MatplotlibChart

            image = MatplotlibChart().render(result.run_id, result.ideas)
            chart_png = image.png if image else None
        except Exception as exc:  # noqa: BLE001 - debug export only
            obs.warn(f"chart not written: {type(exc).__name__}: {exc}")
        for path in write_output(args.output_dir, result, chart_png):
            obs.info(f"wrote {path}")

    if args.dry_run:  # Gemini was skipped on purpose, so LLM_DISABLED is the expected outcome
        obs.info("dry run: nothing was written")
        return EXIT_OK if result.error is None or result.error["code"] == E.LLM_DISABLED else EXIT_RUN_ERROR
    return EXIT_OK if result.status == "ok" else EXIT_RUN_ERROR
