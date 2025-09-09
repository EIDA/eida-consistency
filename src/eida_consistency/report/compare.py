"""Report comparison utilities."""

import json
import logging
from pathlib import Path
from typing import Any, Dict


def _load_report(path: Path) -> Dict[str, Any]:
    """Load a JSON report from disk."""
    try:
        return json.loads(Path(path).read_text())
    except Exception as e:
        logging.error(f"Failed to load report {path}: {e}")
        raise


def compare_reports(report1: str | Path, report2: str | Path, report_dir: Path | None = None) -> None:
    """
    Compare two reports and log differences.

    Parameters
    ----------
    report1, report2 : str | Path
        Paths or filenames of reports. If filenames are given and report_dir is set,
        the files will be resolved relative to that directory.
    report_dir : Path, optional
        Directory to resolve reports from if only a filename is provided.
    """
    r1 = Path(report1)
    r2 = Path(report2)

    if report_dir:
        if not r1.is_absolute():
            r1 = Path(report_dir) / r1
        if not r2.is_absolute():
            r2 = Path(report_dir) / r2

    report_a = _load_report(r1)
    report_b = _load_report(r2)

    # Simple diff example: score and totals
    a_sum = report_a["summary"]
    b_sum = report_b["summary"]

    logging.info("📊 Report comparison:")
    logging.info(f"  Node: {a_sum['node']} vs {b_sum['node']}")
    logging.info(f"  Total checks: {a_sum['total_checked']} vs {b_sum['total_checked']}")
    logging.info(f"  Consistent: {a_sum['total_consistent']} vs {b_sum['total_consistent']}")
    logging.info(f"  Inconsistent: {a_sum['total_inconsistent']} vs {b_sum['total_inconsistent']}")
    logging.info(f"  Score: {a_sum['score']}% vs {b_sum['score']}%")
