"""Celery application (broker: Redis via ``CELERY_BROKER_URL``)."""

from __future__ import annotations

import os

from celery import Celery

_broker = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0").strip()

app = Celery(
    "graph_enterprise",
    broker=_broker,
    include=["graph_enterprise.jobs.tasks"],
)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
