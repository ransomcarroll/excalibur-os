"""CLI entrypoint: `excalibur ship`."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click
import structlog
from dotenv import load_dotenv

from excalibur.config import load
from excalibur.scheduler import run_shipment


def _load_dotenv_into_process_env() -> None:
    """Export .env values to os.environ so the Claude Agent SDK (which reads
    ANTHROPIC_API_KEY from the environment, not from our Settings instance)
    can find its credentials. pydantic-settings reads .env too but only
    populates the Settings object — it does not export to os.environ.
    """
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        load_dotenv(cwd_env, override=False)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )


@click.group()
def cli() -> None:
    """Excalibur — nightly shipper for Linear issues."""


@cli.command()
@click.option("--dry-run", is_flag=True, help="Harvest + group, do not execute.")
@click.option("--only", default=None, help="Comma-separated issue IDs to restrict shipment to.")
@click.option("--verbose", is_flag=True)
def ship(dry_run: bool, only: str | None, verbose: bool) -> None:
    """Run one full shipment cycle now."""
    _setup_logging(verbose)
    _load_dotenv_into_process_env()
    settings = load()
    only_list = [x.strip() for x in only.split(",")] if only else None
    asyncio.run(run_shipment(settings, dry_run=dry_run, only=only_list))


if __name__ == "__main__":
    cli()
