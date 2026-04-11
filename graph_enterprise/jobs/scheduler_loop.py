"""
Master scheduler: every 60s, enqueue Celery tasks for due inboxes.

After each successful enqueue, ``next_run_at`` is pushed forward by at least the inbox's
polling interval (and a minimum floor) so slow queues or long runs do not re-enqueue the
same inbox while a worker still holds the Redis run lock. The worker sets the real
schedule when the run completes.

Skips enqueue when ``is_run_lock_held`` reports an active lock (requires Redis — same URL
rules as ``graph_enterprise.jobs.run_lock``).

Run: ``python -m graph_enterprise.jobs.scheduler_loop``

Requires workers: ``celery -A graph_enterprise.jobs.celery_app worker -l info``
"""

from __future__ import annotations

import logging
import time

from dotenv import load_dotenv

from ..ui import db as db_store
from .run_lock import is_run_lock_held
from .tasks import run_mailbox_pipeline

logger = logging.getLogger(__name__)
INTERVAL_SEC = 60
# Minimum deferral after enqueue; actual bump uses max(this, inbox polling interval) so
# long runs cannot become due again solely because the fixed grace was shorter than the poll cadence.
ENQUEUE_GRACE_MINUTES = 5


def tick() -> None:
    with db_store.get_connection() as conn:
        if db_store.get_global_polling_paused(conn):
            logger.info("Global polling paused; no tasks enqueued.")
            return
        due = db_store.list_due_inboxes(conn)
    for row in due:
        iid = int(row["id"])
        if is_run_lock_held(iid):
            logger.info(
                "Skipping enqueue for inbox %s (%s): run lock held (worker still active)",
                iid,
                row.get("mailbox_id"),
            )
            continue
        try:
            run_mailbox_pipeline.delay(iid)
        except Exception:
            logger.exception(
                "Failed to enqueue run_mailbox_pipeline(%s) for %s",
                iid,
                row.get("mailbox_id"),
            )
            continue
        poll_mins = int(row.get("polling_interval_minutes") or 5)
        grace = max(ENQUEUE_GRACE_MINUTES, poll_mins)
        with db_store.get_connection() as conn:
            db_store.bump_inbox_next_run_after_enqueue(conn, iid, grace_minutes=grace)
        logger.info("Enqueued run_mailbox_pipeline(%s) for %s", iid, row.get("mailbox_id"))


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    db_store.init_db()
    logger.info("Scheduler loop started (interval=%ss).", INTERVAL_SEC)
    while True:
        try:
            tick()
        except Exception:
            logger.exception("Scheduler tick failed")
        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
