"""Celery tasks for mailbox pipelines."""

from __future__ import annotations

import logging
from typing import Any, Dict

from ..ui import db as db_store
from .celery_app import app
from .mailbox_run import run_scheduled_mailbox_pipeline
from .run_lock import release_run_lock, try_acquire_run_lock

logger = logging.getLogger(__name__)


@app.task(name="graph_enterprise.run_mailbox_pipeline")
def run_mailbox_pipeline(inbox_id: int) -> Dict[str, Any]:
    with db_store.get_connection() as conn:
        if db_store.get_global_polling_paused(conn):
            logger.info("Skipping inbox %s: global polling paused", inbox_id)
            return {"skipped": "global_pause"}
        row = db_store.get_inbox_by_id(conn, inbox_id)
    if not row:
        logger.warning("Skipping inbox %s: not found", inbox_id)
        return {"skipped": "missing_inbox"}
    if not row.get("is_active"):
        logger.info("Skipping inbox %s: inactive", inbox_id)
        return {"skipped": "inactive"}

    if not try_acquire_run_lock(inbox_id):
        logger.info("Skipping inbox %s: lock held or lock unavailable", inbox_id)
        return {"skipped": "locked"}

    try:
        run_scheduled_mailbox_pipeline(inbox_id)
        return {"ok": True, "inbox_id": inbox_id}
    finally:
        release_run_lock(inbox_id)
