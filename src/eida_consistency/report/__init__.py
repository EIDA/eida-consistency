"""Report generation package for consistency checks."""

from .report import (
	create_report_object,
	save_report_json,
	save_report_markdown,
)

# Expose datetime utilities at package level for easier monkeypatching in tests
from datetime import datetime as _builtin_datetime, timezone as _builtin_timezone

# Defaults that tests can override via monkeypatch
datetime = _builtin_datetime
timezone = _builtin_timezone


def _make_unique_filename(node: str, seed: int, extension: str) -> str:
	short_time = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
	return f"{node.lower()}_{seed}_{short_time}.{extension}"


__all__ = [
	"create_report_object",
	"_make_unique_filename",
	"save_report_json",
	"save_report_markdown",
	"datetime",
	"timezone",
]