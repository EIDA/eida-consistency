# src/eida_consistency/report/storage.py
import os
import logging
from pathlib import Path

import obstore as obs
from obstore.store import S3Store

logger = logging.getLogger(__name__)

# Defaults for local MinIO; overridable via .env
S3_ENDPOINT = os.getenv("EIDA_S3_ENDPOINT", "http://localhost:9000")
S3_BUCKET   = os.getenv("EIDA_S3_BUCKET", "eida")
S3_KEY      = os.getenv("EIDA_S3_KEY", "devuser")
S3_SECRET   = os.getenv("EIDA_S3_SECRET", "devpassword")


def _make_store() -> S3Store:
    return S3Store(
        S3_BUCKET,
        endpoint=S3_ENDPOINT,
        access_key_id=S3_KEY,
        secret_access_key=S3_SECRET,
        virtual_hosted_style_request=False,
        client_options={"allow_http": True},  # allow plain HTTP for local dev
    )


def upload_report(report_path: str) -> str | None:
    """Upload a report file into the bucket and return its key or None."""
    try:
        path = Path(report_path)
        obj_key = f"reports/{path.name}"

        store = _make_store()
        obs.put(store, obj_key, path.read_bytes())

        logger.info("Report uploaded successfully: %s", obj_key)
        # Return the object key (not a public URL, since bucket is private)
        return obj_key

    except Exception as e:
        logger.error("Upload failed: %s", e, exc_info=True)
        return None


def list_reports() -> list[str]:
    """List all objects under 'reports/' in the bucket."""
    store = _make_store()
    files = obs.list(store, prefix="reports/").collect()
    return files


def download_report(obj_key: str, dest: str) -> None:
    """Download a report from S3 into a local file."""
    store = _make_store()
    resp = obs.get(store, obj_key)
    Path(dest).write_bytes(resp.bytes())
    logger.info("Report %s downloaded to %s", obj_key, dest)


def delete_report(obj_key: str) -> None:
    """Delete a report from the bucket."""
    store = _make_store()
    obs.delete(store, obj_key)
    logger.info("Report %s deleted", obj_key)
