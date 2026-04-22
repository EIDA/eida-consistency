"""Report comparison utilities."""

import json
import logging
from pathlib import Path
from typing import Any, Dict


import requests

def _load_report(path: str | Path) -> Dict[str, Any]:
    """Load a JSON report from disk or URL."""
    path_str = str(path)
    if path_str.startswith("http://") or path_str.startswith("https://"):
        try:
            response = requests.get(path_str, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Failed to fetch report from URL {path_str}: {e}")
            raise
    
    try:
        return json.loads(Path(path).read_text())
    except Exception as e:
        logging.error(f"Failed to load report {path}: {e}")
        raise


def compare_reports(report1: str | Path, report2: str | Path, report_dir: Path | None = None) -> None:
    """
    Compare two reports and log differences.
    """
    def _resolve(p_str: str | Path) -> Path:
        p = Path(p_str)
        # If it's a URL or absolute, or already exists, return as is
        if str(p_str).startswith(("http://", "https://")) or p.is_absolute() or p.exists():
            return p
        # Otherwise try relative to report_dir
        if report_dir:
            return Path(report_dir) / p
        return p

    r1 = _resolve(report1)
    r2 = _resolve(report2)

    report_a = _load_report(r1)
    report_b = _load_report(r2)

    # Simple diff example: score and totals
    a_sum = report_a["summary"]
    b_sum = report_b["summary"]

    logging.info("Report comparison:")
    logging.info(f"  Node: {a_sum['node']} vs {b_sum['node']}")
    logging.info(f"  Total checks: {a_sum['total_checked']} vs {b_sum['total_checked']}")
    logging.info(f"  Consistent: {a_sum['total_consistent']} vs {b_sum['total_consistent']}")
    logging.info(f"  Inconsistent: {a_sum['total_inconsistent']} vs {b_sum['total_inconsistent']}")
    logging.info(f"  Score: {a_sum['score']}% vs {b_sum['score']}%")
