"""Structured per-mailbox run records (JSON to stdout)."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TextIO


def _safe_write(stream: TextIO, text: str) -> None:
    try:
        stream.write(text)
    except UnicodeEncodeError:
        buf = getattr(stream, "buffer", None)
        if buf is not None:
            buf.write(text.encode("utf-8", errors="replace"))
        else:
            stream.write(text.encode("ascii", errors="backslashreplace").decode("ascii"))


@dataclass
class RunMetrics:
    mailbox_id: str
    run_id: str
    started_at_utc: str
    finished_at_utc: str
    fetched_count: int
    classified_count: int
    tagged_count: int
    failures: int
    latency_ms: float
    model_id: str
    prompt_version: str
    category_histogram: Dict[str, int] = field(default_factory=dict)
    classifications: List[Dict[str, Any]] = field(default_factory=list)
    truncated_by_policy: bool = False
    notes: Optional[str] = None
    status: str = "Success"
    total_tokens_used: Optional[int] = None
    error_message: Optional[str] = None

    def to_json_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def emit_run_record(metrics: RunMetrics, stream: TextIO = sys.stdout) -> None:
    """
    Write one run as JSON. Default is indented (readable). Set ``RUN_LOG_JSON_COMPACT=1``
    for a single-line record (log shippers / jq --slurp).
    """
    payload = metrics.to_json_dict()
    compact = os.environ.get("RUN_LOG_JSON_COMPACT", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if compact:
        _safe_write(stream, json.dumps(payload, ensure_ascii=False) + "\n")
        return
    _safe_write(stream, "\n")
    _safe_write(stream, "=" * 72 + "\n")
    _safe_write(stream, " MAILBOX RUN RECORD\n")
    _safe_write(stream, "=" * 72 + "\n")
    _safe_write(stream, json.dumps(payload, ensure_ascii=False, indent=2))
    _safe_write(stream, "\n")
    _safe_write(stream, "=" * 72 + "\n\n")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunTimer:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000.0
