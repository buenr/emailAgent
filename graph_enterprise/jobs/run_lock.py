"""Per-inbox run coordination: Redis SET NX when available; optional dev bypass."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_lock_key = "ge:mailbox_run:{}"
_no_redis_url_logged = False
_allow_bypass_logged = False


def redis_url_for_run_lock() -> Optional[str]:
    """URL for Redis locking: explicit ``REDIS_URL``, else redis broker or result backend."""
    for name in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        raw = (os.environ.get(name) or "").strip()
        if raw.lower().startswith("redis"):
            return raw
    return None


def _lock_ttl_seconds() -> int:
    raw = (os.environ.get("GRAPH_ENTERPRISE_RUN_LOCK_TTL_SEC") or "").strip()
    if raw.isdigit():
        return max(60, int(raw))
    return 3600


def _allow_lock_bypass() -> bool:
    v = (os.environ.get("GRAPH_ENTERPRISE_ALLOW_NO_RUN_LOCK") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def try_acquire_run_lock(inbox_id: int) -> bool:
    """
    Acquire an exclusive lock for this inbox (cross-process when Redis is configured).

    When no Redis URL is available, returns False unless ``GRAPH_ENTERPRISE_ALLOW_NO_RUN_LOCK``
    is set (dev / single-worker), so overlapping workers are not assumed safe.

    On Redis errors, returns False (fail closed) to avoid unbounded duplicate Graph work.
    """
    global _no_redis_url_logged, _allow_bypass_logged
    from ..ui import db as db_store

    if db_store.is_demo_mode():
        return True

    url = redis_url_for_run_lock()
    if not url:
        if _allow_lock_bypass():
            if not _allow_bypass_logged:
                logger.warning(
                    "Per-inbox run lock disabled (no redis URL and "
                    "GRAPH_ENTERPRISE_ALLOW_NO_RUN_LOCK is set); overlapping runs are possible."
                )
                _allow_bypass_logged = True
            return True
        if not _no_redis_url_logged:
            logger.error(
                "Run lock unavailable: set REDIS_URL (recommended even when Celery uses RabbitMQ) "
                "or GRAPH_ENTERPRISE_ALLOW_NO_RUN_LOCK=1 for single-worker dev only. "
                "Skipping mailbox runs until configured."
            )
            _no_redis_url_logged = True
        return False
    try:
        import redis

        r = redis.from_url(url)
        return bool(
            r.set(_lock_key.format(inbox_id), "1", nx=True, ex=_lock_ttl_seconds())
        )
    except Exception as exc:
        logger.warning("Run lock acquire failed (Redis error), skipping run: %s", exc)
        return False


def release_run_lock(inbox_id: int) -> None:
    url = redis_url_for_run_lock()
    if not url:
        return
    try:
        import redis

        redis.from_url(url).delete(_lock_key.format(inbox_id))
    except Exception:
        pass


def is_run_lock_held(inbox_id: int) -> bool:
    """True if the lock key exists (another worker likely still running this inbox)."""
    url = redis_url_for_run_lock()
    if not url:
        return False
    try:
        import redis

        return bool(redis.from_url(url).exists(_lock_key.format(inbox_id)))
    except Exception:
        return False
