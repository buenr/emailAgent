"""Pluggable API client for ETA/freight lookups by reference number.

This module provides the interface and a placeholder implementation.
Replace the body of ``ETALookupClient.lookup`` with the real API call
once the endpoint details are known.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from ..classification.eta_extractor import ExtractedReferenceNumbers

logger = logging.getLogger(__name__)


@dataclass
class ETALookupResult:
    """Structured result from an ETA lookup API call."""

    success: bool = False
    raw_response: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def format_for_email(self) -> str:
        """Return a human-readable summary suitable for a draft email body."""
        if self.error:
            return f"Lookup failed: {self.error}"
        if self.raw_response:
            return self.raw_response
        if self.data:
            lines = []
            for key, value in self.data.items():
                lines.append(f"  {key}: {value}")
            return "\n".join(lines)
        return "No data returned from lookup."


class ETALookupClient:
    """HTTP client for the external ETA lookup API.

    Configuration is read from ``MailboxPipelineConfig`` fields:
    - ``eta_lookup_api_url``: Base URL of the API.
    - ``eta_lookup_api_key``: Auth header value.

    **Replace the ``lookup`` method body** with the real API integration
    once the endpoint spec is available. The placeholder below documents
    the expected interface.
    """

    def __init__(self, api_url: str, api_key: Optional[str] = None, timeout_s: float = 30.0) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_s

    def lookup(self, ref_numbers: ExtractedReferenceNumbers) -> ETALookupResult:
        """Look up freight status by reference numbers.

        Replace this method body with the real API integration.
        The placeholder demonstrates the expected request/response shape.

        Expected implementation pattern::

            headers = {"Authorization": f"Bearer {self._api_key}"}
            params = ref_numbers.to_dict()  # only non-None fields
            resp = httpx.get(f"{self._api_url}/lookup", params=params, headers=headers, timeout=self._timeout)
            resp.raise_for_status()
            return ETALookupResult(success=True, data=resp.json())

        Args:
            ref_numbers: Extracted reference numbers from the email.

        Returns:
            ETALookupResult with the API response data.
        """
        params = ref_numbers.to_dict()
        if not params:
            return ETALookupResult(success=False, error="No reference numbers to look up.")

        headers: Dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            resp = httpx.get(
                f"{self._api_url}/lookup",
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            try:
                data = resp.json()
                return ETALookupResult(
                    success=True,
                    data=data if isinstance(data, dict) else {"result": data},
                    raw_response=resp.text,
                )
            except Exception:
                return ETALookupResult(
                    success=True,
                    raw_response=resp.text,
                )
        except httpx.HTTPStatusError as e:
            logger.warning("ETA lookup API returned %s: %s", e.response.status_code, e)
            return ETALookupResult(
                success=False,
                error=f"API returned HTTP {e.response.status_code}",
            )
        except httpx.RequestError as e:
            logger.warning("ETA lookup API request failed: %s", e)
            return ETALookupResult(
                success=False,
                error=f"Request failed: {e}",
            )
