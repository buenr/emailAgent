"""Thin HTTP client for Graph v1.0 with bearer token injection."""

from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Optional

try:
    import httpx
except ImportError as exc:  # pragma: no cover
    httpx = None  # type: ignore
    _HTTPX_IMPORT_ERROR = exc
else:
    _HTTPX_IMPORT_ERROR = None

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"

_GRAPH_MAX_RETRIES = 8

# Transient Graph / gateway failures; retry with backoff like 429.
_GRAPH_RETRY_STATUS = frozenset((429, 502, 503, 504))


def _retry_after_seconds(response: httpx.Response) -> Optional[float]:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo:
                now = datetime.now(dt.tzinfo)
            else:
                dt = dt.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
            return max(0.0, (dt - now).total_seconds())
    except (TypeError, ValueError, OverflowError):
        pass
    return None


class GraphHttpClient:
    def __init__(
        self,
        token_provider: Callable[[], str],
        timeout_s: float = 60.0,
    ) -> None:
        if httpx is None:
            raise ImportError(
                "httpx is required for GraphHttpClient. "
                "Install dependencies from requirements.txt (httpx)"
            ) from _HTTPX_IMPORT_ERROR
        self._token_provider = token_provider
        self._timeout = timeout_s
        # Single client: httpx.Client is thread-safe for concurrent requests (pooled connections).
        self._client = httpx.Client(timeout=self._timeout)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token_provider()}",
            "Accept": "application/json",
        }

    def _request_with_retry(self, fn: Callable[[], httpx.Response]) -> httpx.Response:
        attempt = 0
        while True:
            resp = fn()
            if resp.status_code not in _GRAPH_RETRY_STATUS:
                return resp
            attempt += 1
            if attempt > _GRAPH_MAX_RETRIES:
                return resp
            delay = _retry_after_seconds(resp)
            if delay is None:
                delay = min(2.0**attempt + random.random(), 120.0)
            time.sleep(delay)

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        def do() -> httpx.Response:
            return self._client.get(url, headers=self._headers(), params=params)

        return self._request_with_retry(do)

    def post(self, url: str, json_body: Dict[str, Any]) -> httpx.Response:
        def do() -> httpx.Response:
            return self._client.post(
                url,
                headers={**self._headers(), "Content-Type": "application/json"},
                json=json_body,
            )

        return self._request_with_retry(do)

    def patch(self, url: str, json_body: Dict[str, Any]) -> httpx.Response:
        def do() -> httpx.Response:
            return self._client.patch(
                url,
                headers={**self._headers(), "Content-Type": "application/json"},
                json=json_body,
            )

        return self._request_with_retry(do)
