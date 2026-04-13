"""Orchestrate customizable agentic workflows using Gemini function calling and configured external APIs."""

from __future__ import annotations

import html
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
from ..microsoft_graph.draft import create_reply_draft, send_draft

logger = logging.getLogger(__name__)


@dataclass
class AgentWorkflowResult:
    email_id: str
    agent_name: Optional[str] = None
    extracted: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None
    response_text: Optional[str] = None
    draft_id: Optional[str] = None
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
            "response_text": self.response_text,
            "draft_id": self.draft_id,
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


def _email_sender_address(msg: Dict[str, Any]) -> str:
    sender = msg.get("sender") or {}
    if isinstance(sender, dict):
        ea = sender.get("emailAddress") or {}
        return str(ea.get("address") or ea.get("name") or "").lower()
    return str(sender).lower()


def _email_body_text(msg: Dict[str, Any]) -> str:
    body = msg.get("body")
    if isinstance(body, dict):
        return str(body.get("content") or "")
    return str(msg.get("bodyPreview") or body or "")


def _matches_workflow_filter(
    msg: Dict[str, Any],
    workflow_filter: Optional[Dict[str, Any]],
) -> bool:
    if not workflow_filter:
        return True

    subject = str(msg.get("subject") or "")
    body = _email_body_text(msg)
    sender = _email_sender_address(msg)

    if workflow_filter.get("unread_only"):
        if msg.get("isRead") is not False:
            return False

    sender_allowlist = [str(x).strip().lower() for x in workflow_filter.get("sender_allowlist", []) if str(x).strip()]
    if sender_allowlist:
        if not any(
            (entry.startswith("@") and sender.endswith(entry))
            or sender == entry
            for entry in sender_allowlist
        ):
            return False

    sender_denylist = [str(x).strip().lower() for x in workflow_filter.get("sender_denylist", []) if str(x).strip()]
    if sender_denylist:
        if any(
            (entry.startswith("@") and sender.endswith(entry))
            or sender == entry
            for entry in sender_denylist
        ):
            return False

    subject_keywords = [str(x).strip().lower() for x in workflow_filter.get("subject_keywords", []) if str(x).strip()]
    if subject_keywords:
        mode = str(workflow_filter.get("subject_keyword_mode") or "any").lower()
        found = [kw in subject.lower() for kw in subject_keywords]
        if mode == "all" and not all(found):
            return False
        if mode != "all" and not any(found):
            return False

    body_keywords = [str(x).strip().lower() for x in workflow_filter.get("body_keywords", []) if str(x).strip()]
    if body_keywords:
        body_text = body.lower()
        if not all(kw in body_text for kw in body_keywords):
            return False

    importance_levels = [str(x).strip().lower() for x in workflow_filter.get("importance_levels", []) if str(x).strip()]
    if importance_levels:
        importance = str(msg.get("importance") or "").lower()
        if importance not in importance_levels:
            return False

    has_attachments = str(workflow_filter.get("has_attachments") or "any").lower()
    if has_attachments == "yes" and not msg.get("hasAttachments"):
        return False
    if has_attachments == "no" and msg.get("hasAttachments"):
        return False

    categories = [str(c).lower() for c in msg.get("categories") or [] if str(c).strip()]
    include_any = [str(x).strip().lower() for x in workflow_filter.get("category_include_any", []) if str(x).strip()]
    if include_any and not any(c in include_any for c in categories):
        return False

    exclude_any = [str(x).strip().lower() for x in workflow_filter.get("category_exclude_any", []) if str(x).strip()]
    if exclude_any and any(c in exclude_any for c in categories):
        return False

    return True


def _format_json_for_prompt(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except Exception:
        return str(value)


def _generate_response_text(
    response_prompt_body: str,
    msg: Dict[str, Any],
    extracted: Dict[str, Any],
    response_data: Dict[str, Any],
    mailbox_config: Any = None,
) -> str:
    if not response_prompt_body:
        return _format_json_for_prompt({
            "extracted": extracted,
            "response_data": response_data,
        })

    try:
        client, model_name = _make_genai_client(mailbox_config)
        subject = str(msg.get("subject") or "")
        body = body_text_for_classification(msg)
        user_message = (
            f"Original subject: {subject}\n\n"
            f"Original body:\n{body}\n\n"
            f"Extracted data:\n{_format_json_for_prompt(extracted)}\n\n"
            f"Agent API response:\n{_format_json_for_prompt(response_data)}"
        )
        response = client.models.generate_content(
            model=model_name,
            contents=[types.Content(role="user", parts=[types.Part(text=user_message)])],
            config=types.GenerateContentConfig(
                system_instruction=response_prompt_body,
                temperature=0.0,
                max_output_tokens=2048,
            ),
        )
        if response.candidates:
            text_parts: List[str] = []
            for part in response.candidates[0].content.parts:
                if getattr(part, "text", None) is not None:
                    text_parts.append(part.text)
                else:
                    text_parts.append(str(getattr(part, "content", "")))
            return "".join(text_parts).strip()
    except Exception as exc:
        logger.warning("Response generation failed for message %s: %s", msg.get("id"), exc)
    return _format_json_for_prompt({
        "extracted": extracted,
        "response_data": response_data,
    })


def _build_reply_body_html(response_text: str) -> str:
    escaped = html.escape(response_text or "")
    escaped = escaped.replace("\n", "<br>")
    return (
        "<div style='font-family:Arial,sans-serif;font-size:14px;'>"
        f"{escaped}"
        "<hr style='border:1px solid #ccc;margin:16px 0;'>"
        "<p style='font-size:12px;color:#888;'>"
        "This draft was auto-generated by the Email Tagging AI system. "
        "Review before sending."
        "</p>"
        "</div>"
    )


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
    graph_client: Any = None,
) -> List[AgentWorkflowResult]:
    """
    Execute a fully customizable agentic workflow:

    1. Filter predictions to only those in ``trigger_categories``.
    2. For each triggered message, call Gemini function calling with user-defined schemas.
    3. Call the primary configured Agent API and generate one response draft.
    4. Optionally auto-send the generated draft and/or POST all results to a webhook.

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
    api_names_to_call = list(agentic_config.get("agent_api_names", []))
    workflow_filter = agentic_config.get("workflow_filter")
    response_prompt_body = str(agentic_config.get("response_prompt_body") or "")
    auto_send = bool(agentic_config.get("auto_send"))
    webhook_url = (agentic_config.get("webhook_url") or "").strip()
    inbox_mailbox_id = agentic_config.get("inbox_mailbox_id", "")

    # Filter to only matching APIs, but use one primary API per workflow.
    selected_apis = [c for c in agent_api_configs if c.get("name") in api_names_to_call]
    if len(selected_apis) > 1:
        logger.warning(
            "Agentic workflow configured multiple matching agent APIs; only the first will be used."
        )
    selected_api = selected_apis[0] if selected_apis else None

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

        if not _matches_workflow_filter(msg, workflow_filter):
            logger.debug(
                "Agentic workflow skipped message %s because it did not match workflow filter.",
                email_id,
            )
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

        # Step 2: Call the primary Agent API and optionally build a reply draft.
        payload = _build_agent_payload(email_id, inbox_mailbox_id, category, msg, extracted)

        if not selected_api:
            results.append(AgentWorkflowResult(
                email_id=email_id,
                extracted=extracted,
                response_data={"note": "No primary agent API configured; extraction only."},
            ))
            continue

        result = _call_agent_api(selected_api, payload)
        result.extracted = extracted

        if result.response_data is not None:
            result.response_text = _generate_response_text(
                response_prompt_body,
                msg,
                extracted,
                result.response_data,
                mailbox_config,
            )
            if graph_client is not None:
                draft_id = create_reply_draft(
                    graph_client,
                    inbox_mailbox_id,
                    email_id,
                    _build_reply_body_html(result.response_text),
                )
                result.draft_id = draft_id
                if auto_send and draft_id:
                    sent = send_draft(graph_client, inbox_mailbox_id, draft_id)
                    if not sent:
                        logger.warning(
                            "Agentic workflow auto-send failed for draft %s",
                            draft_id,
                        )
                        result.error = (
                            result.error or ""
                        ) + " Draft send failed."

        results.append(result)

    # Step 3: Webhook callback
    if webhook_url and results:
        _post_webhook(webhook_url, [r.to_dict() for r in results])

    return results
