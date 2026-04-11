"""ETA pipeline: extract reference numbers → API lookup → create draft reply.

This orchestrator runs after the main classification + write-back step for
messages classified as **ETAOrTracking**. Each step is wrapped in try/except
so that failures never fail the main classification run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..classification.eta_extractor import ExtractedReferenceNumbers, extract_reference_numbers
from ..config.models import MailboxPipelineConfig
from ..eta_lookup.api_client import ETALookupClient, ETALookupResult
from ..microsoft_graph.draft import build_draft_body_html, create_reply_draft
from ..microsoft_graph.http_client import GraphHttpClient

logger = logging.getLogger(__name__)

ETA_CATEGORY = "ETAOrTracking"


@dataclass
class ETAPipelineResult:
    """Outcome of the ETA pipeline for a single message."""

    email_id: str
    extracted: Optional[ExtractedReferenceNumbers] = None
    lookup_result: Optional[ETALookupResult] = None
    draft_message_id: Optional[str] = None
    extraction_error: Optional[str] = None
    lookup_error: Optional[str] = None
    draft_error: Optional[str] = None

    @property
    def success(self) -> bool:
        return (
            self.extraction_error is None
            and self.lookup_error is None
            and self.draft_error is None
            and self.draft_message_id is not None
        )


def _build_lookup_client(mailbox: MailboxPipelineConfig) -> Optional[ETALookupClient]:
    """Create an ETALookupClient from mailbox config, or None if unconfigured."""
    url = mailbox.eta_lookup_api_url
    if not url or not url.strip():
        return None
    return ETALookupClient(
        api_url=url.strip(),
        api_key=mailbox.eta_lookup_api_key,
    )


def run_eta_pipeline(
    mailbox: MailboxPipelineConfig,
    graph_client: GraphHttpClient,
    eta_predictions: List[Dict[str, Any]],
    messages: List[Dict[str, Any]],
) -> List[ETAPipelineResult]:
    """Run the ETA extraction → lookup → draft pipeline for ETAOrTracking messages.

    Args:
        mailbox: Per-inbox configuration (includes eta_lookup_* fields).
        graph_client: Authenticated Graph HTTP client for draft creation.
        eta_predictions: Prediction dicts with ``email_id`` and ``category`` == "ETAOrTracking".
        messages: Full message dicts (same list passed to classification).

    Returns:
        List of ETAPipelineResult for auditing/logging.
    """
    lookup_client = _build_lookup_client(mailbox)
    if lookup_client is None and mailbox.eta_lookup_api_url:
        logger.warning(
            "ETA lookup enabled for %s but API client could not be built (missing URL?).",
            mailbox.mailbox_id,
        )

    msg_by_id = {m.get("id"): m for m in messages if m.get("id")}
    results: List[ETAPipelineResult] = []

    for pred in eta_predictions:
        email_id = pred.get("email_id", "")
        msg = msg_by_id.get(email_id)
        if not msg:
            results.append(ETAPipelineResult(
                email_id=email_id,
                extraction_error="Original message not found in fetched messages.",
            ))
            continue

        result = ETAPipelineResult(email_id=email_id)

        # Step 1: Extract reference numbers via Gemini function calling.
        try:
            extracted = extract_reference_numbers(msg, mailbox)
            result.extracted = extracted
            if not extracted.has_any():
                logger.info(
                    "ETA pipeline: no reference numbers found in message %s", email_id
                )
                results.append(result)
                continue
            logger.info(
                "ETA pipeline: extracted from %s: %s",
                email_id,
                extracted.to_dict(),
            )
        except Exception as exc:
            logger.exception("ETA extraction failed for %s: %s", email_id, exc)
            result.extraction_error = str(exc)
            results.append(result)
            continue

        # Step 2: Call external API with extracted numbers.
        if lookup_client is None:
            logger.info(
                "ETA pipeline: no lookup client configured; skipping API call for %s",
                email_id,
            )
            result.lookup_error = "No API client configured."
            results.append(result)
            continue

        try:
            lookup_result = lookup_client.lookup(extracted)
            result.lookup_result = lookup_result
            if not lookup_result.success:
                logger.warning(
                    "ETA lookup failed for %s: %s", email_id, lookup_result.error
                )
                result.lookup_error = lookup_result.error
                results.append(result)
                continue
            logger.info("ETA lookup succeeded for %s", email_id)
        except Exception as exc:
            logger.exception("ETA lookup call failed for %s: %s", email_id, exc)
            result.lookup_error = str(exc)
            results.append(result)
            continue

        # Step 3: Create draft reply with API response.
        if not mailbox.eta_draft_enabled:
            logger.info("ETA draft disabled; skipping draft creation for %s", email_id)
            results.append(result)
            continue

        try:
            draft_body = build_draft_body_html(extracted, lookup_result)
            draft_id = create_reply_draft(
                graph_client,
                mailbox.mailbox_id,
                email_id,
                draft_body,
            )
            if draft_id:
                result.draft_message_id = draft_id
                logger.info(
                    "ETA pipeline: created draft %s for message %s",
                    draft_id,
                    email_id,
                )
            else:
                result.draft_error = "create_reply_draft returned None."
        except Exception as exc:
            logger.exception("ETA draft creation failed for %s: %s", email_id, exc)
            result.draft_error = str(exc)

        results.append(result)

    return results
