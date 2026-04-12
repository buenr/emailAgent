"""Orchestrate generic agent workflows using configured external APIs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from ..classification.eta_extractor import ExtractedReferenceNumbers, extract_reference_numbers
from ..config.models import MailboxPipelineConfig
from ..ui import db as ui_db

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowResult:
    email_id: str
    agent_name: Optional[str] = None
    extracted: Optional[ExtractedReferenceNumbers] = None
    response_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.response_data is not None

    def format_for_email(self) -> str:
        if self.error:
            return f"Agent workflow failed: {self.error}"
        if self.response_data:
            lines = [f"{k}: {v}" for k, v in self.response_data.items()]
            return "\n".join(lines)
        return "No agent response data available."


def _build_agent_payload(
    email_id: str,
    mailbox: MailboxPipelineConfig,
    category: str,
    msg: Dict[str, Any],
    extracted: ExtractedReferenceNumbers,
) -> Dict[str, Any]:
    return {
        "email_id": email_id,
        "mailbox_id": mailbox.mailbox_id,
        "category": category,
        "reference_numbers": extracted.to_dict(),
        "subject": str(msg.get("subject", "")),
        "body": str(msg.get("body", "")),
        "from": msg.get("from"),
        "received_date_time": msg.get("receivedDateTime"),
    }


def _call_agent_api(
    agent_config: Dict[str, str],
    payload: Dict[str, Any],
    timeout_s: float = 30.0,
) -> AgentWorkflowResult:
    name = agent_config.get("name") or "unnamed"
    api_url = str(agent_config.get("api_url", "")).strip()
    api_key = str(agent_config.get("api_key", "")).strip()
    if not api_url:
        return AgentWorkflowResult(
            email_id=str(payload.get("email_id", "")),
            agent_name=name,
            error="Configured agent API is missing api_url.",
        )

    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = httpx.post(api_url, json=payload, headers=headers, timeout=timeout_s)
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            data = {"raw_response": resp.text}
        return AgentWorkflowResult(
            email_id=str(payload.get("email_id", "")),
            agent_name=name,
            response_data=data if isinstance(data, dict) else {"result": data},
        )
    except httpx.HTTPStatusError as exc:
        logger.warning("Agent API %s returned %s: %s", name, exc.response.status_code, exc)
        return AgentWorkflowResult(
            email_id=str(payload.get("email_id", "")),
            agent_name=name,
            error=f"Agent API returned HTTP {exc.response.status_code}",
        )
    except httpx.RequestError as exc:
        logger.warning("Agent API request failed for %s: %s", name, exc)
        return AgentWorkflowResult(
            email_id=str(payload.get("email_id", "")),
            agent_name=name,
            error=f"Agent API request failed: {exc}",
        )


def run_agent_workflow(
    mailbox: MailboxPipelineConfig,
    graph_client: Any,
    eta_predictions: List[Dict[str, Any]],
    messages: List[Dict[str, Any]],
) -> List[AgentWorkflowResult]:
    try:
        with ui_db.get_connection() as conn:
            agent_configs = ui_db.get_agent_api_configs(conn)
    except Exception as exc:
        logger.exception("Failed to load agent API configs: %s", exc)
        agent_configs = []

    if not agent_configs:
        logger.info("Agent workflow skipped: no configured agent APIs.")
        return []

    msg_by_id = {m.get("id"): m for m in messages if m.get("id")}
    results: List[AgentWorkflowResult] = []

    for pred in eta_predictions:
        email_id = pred.get("email_id", "")
        msg = msg_by_id.get(email_id)
        if not msg:
            results.append(AgentWorkflowResult(
                email_id=email_id,
                error="Original message not found in fetched messages.",
            ))
            continue

        try:
            extracted = extract_reference_numbers(msg, mailbox)
        except Exception as exc:
            logger.exception("Agent workflow extraction failed for %s: %s", email_id, exc)
            results.append(AgentWorkflowResult(email_id=email_id, error=str(exc)))
            continue

        if not extracted.has_any():
            logger.info("Agent workflow: no reference numbers found in message %s", email_id)
            results.append(AgentWorkflowResult(email_id=email_id, extracted=extracted))
            continue

        payload = _build_agent_payload(
            email_id,
            mailbox,
            str(pred.get("category", "ETAOrTracking")),
            msg,
            extracted,
        )
        for agent_config in agent_configs:
            result = _call_agent_api(agent_config, payload)
            result.extracted = extracted
            results.append(result)

    return results
