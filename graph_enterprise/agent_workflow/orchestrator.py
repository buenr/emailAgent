"""Orchestrate customizable agentic workflows using Gemini function calling and configured external APIs."""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from ..classification.gemini_category_batch import (
    _GEMINI_MAX_RETRIES,
    _api_rejects_thinking_config,
    _make_genai_client,
    _model_is_flash_lite,
    _sanitize_for_prompt,
    body_text_for_classification,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowResult:
    email_id: str
    agent_name: Optional[str] = None
    extracted: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.response_data is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "email_id": self.email_id,
            "agent_name": self.agent_name,
            "extracted": self.extracted,
            "response_data": self.response_data,
            "error": self.error,
            "success": self.success,
        }


# ---------------------------------------------------------------------------
# Gemini function-calling extraction
# ---------------------------------------------------------------------------


def _build_genai_function_declarations(
    func_decls: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert user-defined function declarations into the dict format expected by google.genai."""
    out: List[Dict[str, Any]] = []
    for fd in func_decls:
        props: Dict[str, Any] = {}
        required_list: List[str] = []
        for p in fd.get("parameters", []):
            props[p["name"]] = {
                "type": p.get("type", "string"),
                "description": p.get("description", ""),
            }
            if p.get("required"):
                required_list.append(p["name"])
        schema: Dict[str, Any] = {
            "type": "object",
            "properties": props,
        }
        if required_list:
            schema["required"] = required_list
        out.append({
            "name": fd["name"],
            "description": fd.get("description", ""),
            "parameters": schema,
        })
    return out


def _retryable_genai_error(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return getattr(exc, "code", None) == 429
    return False


def _default_thinking_budget() -> int:
    import os
    return int(os.environ.get("GEMINI_THINKING_BUDGET", "8192"))


def _thinking_config_for_model(model_name: str) -> types.ThinkingConfig:
    if _model_is_flash_lite(model_name):
        return types.ThinkingConfig(thinking_budget=_default_thinking_budget())
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)


def extract_with_function_calling(
    email: Dict[str, Any],
    extraction_prompt_body: str,
    function_declarations: List[Dict[str, Any]],
    mailbox_config: Any = None,
) -> Dict[str, Any]:
    """
    Use Gemini function calling with user-defined function schemas to extract
    structured data from an email.

    Returns a dict of extracted field values (from the function call args), or
    an empty dict if no function was called.
    """
    client, model_name = _make_genai_client(mailbox_config)

    subject = _sanitize_for_prompt(str(email.get("subject", "")))
    body = body_text_for_classification(email)
    user_message = f"Subject: {subject}\n\nBody:\n{body}"

    contents = [types.Content(role="user", parts=[types.Part(text=user_message)])]

    genai_funcs = _build_genai_function_declarations(function_declarations)
    tool = types.Tool(function_declarations=genai_funcs)
    allowed_names = [fd["name"] for fd in genai_funcs]

    config_kwargs: Dict[str, Any] = {
        "system_instruction": extraction_prompt_body,
        "temperature": 0.0,
        "max_output_tokens": 4096,
        "tools": [tool],
        "tool_config": types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY,
                allowed_function_names=allowed_names,
            )
        ),
    }

    use_thinking = True
    thinking_fallback_tried = False
    api_retry_count = 0
    response = None

    while response is None:
        if use_thinking:
            config_kwargs["thinking_config"] = _thinking_config_for_model(model_name)
        else:
            config_kwargs.pop("thinking_config", None)
        config = types.GenerateContentConfig(**config_kwargs)
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
        except genai_errors.APIError as e:
            if (
                use_thinking
                and not thinking_fallback_tried
                and _api_rejects_thinking_config(e)
            ):
                use_thinking = False
                thinking_fallback_tried = True
                continue
            if _retryable_genai_error(e):
                api_retry_count += 1
                if api_retry_count > _GEMINI_MAX_RETRIES:
                    logger.error(
                        "Agentic extraction failed after %s retries: %s",
                        _GEMINI_MAX_RETRIES,
                        e,
                    )
                    return {}
                delay = min(2.0 ** api_retry_count + random.random(), 60.0)
                logger.warning(
                    "Agentic extraction API error (retry %s/%s): %s; sleeping %.1fs",
                    api_retry_count,
                    _GEMINI_MAX_RETRIES,
                    e,
                    delay,
                )
                time.sleep(delay)
                continue
            logger.error("Agentic extraction non-retryable error: %s", e)
            return {}

    if not response.candidates:
        return {}

    parts = response.candidates[0].content.parts
    for part in parts:
        fc = getattr(part, "function_call", None) or getattr(part, "functionCall", None)
        if fc is None:
            continue
        args = dict(getattr(fc, "args", {}) or {})
        return args

    return {}


# ---------------------------------------------------------------------------
# Agent API calls
# ---------------------------------------------------------------------------


def _build_agent_payload(
    email_id: str,
    inbox_mailbox_id: str,
    category: str,
    msg: Dict[str, Any],
    extracted: Dict[str, Any],
) -> Dict[str, Any]:
    sender = msg.get("sender") or {}
    sender_addr = sender.get("emailAddress", {}).get("address", "Unknown") if isinstance(sender, dict) else str(sender)
    return {
        "email_id": email_id,
        "mailbox_id": inbox_mailbox_id,
        "category": category,
        "extracted_data": extracted,
        "subject": str(msg.get("subject", "")),
        "sender": sender_addr,
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
            extracted=payload.get("extracted_data"),
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


def _post_webhook(
    webhook_url: str,
    results: List[Dict[str, Any]],
    timeout_s: float = 30.0,
) -> None:
    """POST a summary of all extraction + API results to the configured webhook."""
    try:
        resp = httpx.post(
            webhook_url,
            json={"agentic_results": results},
            headers={"Content-Type": "application/json"},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        logger.info("Webhook POST to %s succeeded (HTTP %s)", webhook_url, resp.status_code)
    except Exception as exc:
        logger.warning("Webhook POST to %s failed: %s", webhook_url, exc)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run_agent_workflow(
    agentic_config: Dict[str, Any],
    extraction_prompt_body: str,
    messages: List[Dict[str, Any]],
    predictions: List[Dict[str, Any]],
    agent_api_configs: List[Dict[str, str]],
    mailbox_config: Any = None,
) -> List[AgentWorkflowResult]:
    """
    Execute a fully customizable agentic workflow:

    1. Filter predictions to only those in ``trigger_categories``.
    2. For each triggered message, call Gemini function calling with user-defined schemas.
    3. Sequentially call each configured Agent API with the extracted data.
    4. Optionally POST all results to a webhook.

    Args:
        agentic_config: Dict from ``get_agentic_workflow_for_inbox`` (or API payload).
        extraction_prompt_body: The prompt template body used as system instruction.
        messages: Full list of fetched messages.
        predictions: Classification predictions (with ``email_id`` and ``category``).
        agent_api_configs: List of dicts with ``name``, ``api_url``, ``api_key``.
        mailbox_config: Optional MailboxPipelineConfig for Gemini client creation.
    """
    trigger_cats = set(agentic_config.get("trigger_categories", []))
    func_decls = agentic_config.get("function_declarations", [])
    api_names_to_call = set(agentic_config.get("agent_api_names", []))
    webhook_url = (agentic_config.get("webhook_url") or "").strip()
    inbox_mailbox_id = agentic_config.get("inbox_mailbox_id", "")

    # Filter to only matching APIs
    selected_apis = [c for c in agent_api_configs if c.get("name") in api_names_to_call]

    # Filter predictions to trigger categories
    triggered = [p for p in predictions if p.get("category") in trigger_cats]
    if not triggered:
        logger.info("Agentic workflow: no predictions matched trigger categories %s", trigger_cats)
        return []

    msg_by_id = {m.get("id"): m for m in messages if m.get("id")}
    results: List[AgentWorkflowResult] = []

    for pred in triggered:
        email_id = pred.get("email_id", "")
        category = pred.get("category", "")
        msg = msg_by_id.get(email_id)
        if not msg:
            results.append(AgentWorkflowResult(
                email_id=email_id,
                error="Original message not found in fetched messages.",
            ))
            continue

        # Step 1: Extract structured data via Gemini function calling
        if func_decls:
            try:
                extracted = extract_with_function_calling(
                    msg, extraction_prompt_body, func_decls, mailbox_config
                )
            except Exception as exc:
                logger.exception("Agentic extraction failed for %s: %s", email_id, exc)
                results.append(AgentWorkflowResult(email_id=email_id, error=str(exc)))
                continue
        else:
            extracted = {}

        # Step 2: Sequentially call each Agent API
        payload = _build_agent_payload(email_id, inbox_mailbox_id, category, msg, extracted)

        if not selected_apis:
            # No APIs to call, just log extraction
            results.append(AgentWorkflowResult(
                email_id=email_id,
                extracted=extracted,
                response_data={"note": "No agent APIs configured; extraction only."},
            ))
            continue

        for api_config in selected_apis:
            result = _call_agent_api(api_config, payload)
            result.extracted = extracted
            results.append(result)

    # Step 3: Webhook callback
    if webhook_url and results:
        _post_webhook(webhook_url, [r.to_dict() for r in results])

    return results
