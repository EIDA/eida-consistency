"""Command-line interface for eida-consistency.

Examples
--------
$ eida-consistency --log-level DEBUG consistency --node NOA --epochs 5
$ eida-consistency compare report1.json report2.json

"""
import logging
from pathlib import Path

import click
from eida_consistency.runner import run_consistency_check
from eida_consistency.report.compare import compare_reports


def normalize_log_level(level: str) -> int:
	"""Normalize a log level string to its numeric value or raise on invalid.

	Parameters
	----------
	level: str
		Log level name such as "DEBUG", "INFO", "WARNING", "ERROR".

	Returns
	-------
	int
		The numeric logging level (e.g., logging.INFO).
	"""
	numeric = getattr(logging, str(level).upper(), None)
	if not isinstance(numeric, int):
		raise click.BadParameter(f"Invalid log level: {level}")
	return numeric


def _setup_logging(level: str) -> None:
	"""Configure root logger once."""
	numeric = normalize_log_level(level)
	logging.basicConfig(
		level=numeric,
		format="%(asctime)s [%(levelname)s] %(message)s",
		datefmt="%H:%M:%S",
	)


@click.group(invoke_without_command=True)
@click.option(
	"--log-level",
	default="INFO",
	type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
	show_default=True,
	help="Set logging verbosity.",
)
@click.pass_context
def cli(ctx, log_level):
	"""EIDA consistency checker."""
	_setup_logging(log_level)
	ctx.obj = {"log_level": log_level}
	# If no subcommand provided, show usage and return non-zero
	if ctx.invoked_subcommand is None and not ctx.resilient_parsing:
		click.echo(ctx.get_help())
		ctx.exit(1)


@cli.command()
@click.option("--node", required=True, help="EIDA node code (e.g., RESIF, NOA)")
@click.option("--epochs", type=int, default=10, show_default=True, help="Number of epochs")
@click.option("--duration", type=int, default=600, show_default=True, help="Duration (s)")
@click.option("--seed", type=int, help="Random seed")
@click.option(
	"--delete-old",
	is_flag=True,
	help="(NOT IMPLEMENTED) Remove old reports beyond retention policy.",
)
def consistency(node, epochs, duration, seed, delete_old):
	"""Run availability + dataselect consistency check."""
	if delete_old:
		logging.warning("'--delete-old' flag is present but not yet implemented.")
	run_consistency_check(
		node=node,
		epochs=epochs,
		duration=duration,
		seed=seed,
	)


@cli.command()
@click.argument("report1", type=click.Path(exists=True, path_type=Path))
@click.argument("report2", type=click.Path(exists=True, path_type=Path))
def compare(report1, report2):
	"""Compare two JSON report files."""
	compare_reports(str(report1), str(report2))


if __name__ == "__main__":
	cli()