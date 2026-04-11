"""Assign mailbox category labels to Graph message dicts via Vertex Gemini."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from ..config.models import MailboxPipelineConfig
from ..preprocess.attachments import format_attachments_block
from ..preprocess.body import normalize_body_for_model
from .prompt import build_classification_system_and_user
from .schema_from_config import build_classification_json_schema
from .subject_rules import partition_messages_by_subject_rules, try_classify_by_subject_rules

logger = logging.getLogger(__name__)

# Default when ``GEMINI_MODEL`` is unset or empty (Vertex model id).
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"

# After first-word window (~1000 words, latest reply in top-posted bodies); char cap for prompts.
_CLASSIFICATION_BODY_MAX_CHARS = 65536

_GEMINI_MAX_RETRIES = 8
_CLASSIFICATION_POOL_WORKERS = 5


def _model_is_flash_lite(model_name: str) -> bool:
    m = (model_name or "").lower().replace("_", "-")
    return "flash-lite" in m


def _default_thinking_budget() -> int:
    return int(os.environ.get("GEMINI_THINKING_BUDGET", "24576"))


def _thinking_config_for_model(model_name: str) -> types.ThinkingConfig:
    if _model_is_flash_lite(model_name):
        return types.ThinkingConfig(thinking_budget=_default_thinking_budget())
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel.HIGH)


def _api_rejects_thinking_config(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if "not supported" not in msg:
        return False
    return (
        "thinking_level" in msg
        or "thinking_budget" in msg
        or "thinking_config" in msg
    )


def _retryable_genai_error(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return getattr(exc, "code", None) == 429
    return False


def effective_gemini_model_from_env() -> str:
    """Resolved model id when no per-inbox ``app_model`` overrides (see ``_make_genai_client``)."""
    raw = (os.environ.get("GEMINI_MODEL") or "").strip()
    return raw or DEFAULT_GEMINI_MODEL


def _make_genai_client(mailbox: Optional[MailboxPipelineConfig] = None) -> Tuple[Any, str]:
    project = os.environ.get("VERTEX_PROJECT")
    if not project:
        raise ValueError(
            "VERTEX_PROJECT is required for Gemini classification. Set it in .env."
        )
    location = os.environ.get("VERTEX_REGION")
    model_name = effective_gemini_model_from_env()
    if mailbox and mailbox.app_model and mailbox.app_model.name:
        model_name = mailbox.app_model.name

    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    api_key = os.environ.get("GOOGLE_CLOUD_API_KEY")
    client_kwargs: Dict[str, Any] = {
        "vertexai": True,
        "project": project,
        "location": location,
    }
    if creds_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(creds_path)
    if api_key and not creds_path:
        client_kwargs["api_key"] = api_key
    return genai.Client(**client_kwargs), model_name


def _sender_str(sender: Any) -> str:
    if isinstance(sender, dict):
        ea = sender.get("emailAddress") or {}
        return ea.get("address") or ea.get("name") or str(sender)
    return str(sender or "Unknown")


def _sanitize_for_prompt(
    text: str, limit: int = 1000, *, preserve_newlines: bool = False
) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    text = text.replace('"', "'")
    if not preserve_newlines:
        text = text.replace("\n", " ")
    return text[:limit]


def body_text_for_classification(email: Dict[str, Any]) -> str:
    """
    Body string exactly as used inside the Gemini prompt (normalize HTML/preview,
    first 1000 words, char cap, then prompt sanitization). Use for run logs / audits.
    """
    body_obj = email.get("body")
    body_html = body_obj.get("content") if isinstance(body_obj, dict) else None
    body = normalize_body_for_model(
        body_preview=str(email.get("bodyPreview", "") or ""),
        body_html=body_html,
        first_n_words=1000,
        max_chars=_CLASSIFICATION_BODY_MAX_CHARS,
    )
    return _sanitize_for_prompt(
        body, _CLASSIFICATION_BODY_MAX_CHARS, preserve_newlines=True
    )


def _prepare_classification_turns(
    email: Dict[str, Any], mailbox: MailboxPipelineConfig
) -> Tuple[str, str]:
    subj = _sanitize_for_prompt(str(email.get("subject", "No Subject")))
    sender = _sanitize_for_prompt(_sender_str(email.get("sender")))
    body = body_text_for_classification(email)
    recv = str(email.get("receivedDateTime", "") or "")
    return build_classification_system_and_user(
        mailbox.mailbox_id,
        mailbox.categories,
        subj,
        sender,
        recv,
        body,
        attachments_block=format_attachments_block(email),
        prompt_template=mailbox.prompt_template,
    )


def _parse_classification_response(
    raw: str,
) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Unexpected JSON shape from model")
    cat = data.get("category")
    if not isinstance(cat, str):
        raise ValueError("Missing or invalid category in model JSON")
    return cat


def _generate_classification_response_text(
    client: Any,
    model_name: str,
    mailbox: MailboxPipelineConfig,
    email: Dict[str, Any],
) -> Tuple[Optional[str], int, int]:
    """
    Single Gemini generate_content call (with retries). Returns ``(text, input_tokens,
    output_tokens)``; ``text`` is None if the call failed after retries.
    """
    schema = build_classification_json_schema(mailbox)
    system_instruction, user_message = _prepare_classification_turns(email, mailbox)
    contents = [types.Content(role="user", parts=[types.Part(text=user_message)])]
    use_thinking = True
    thinking_fallback_tried = False
    api_retry_count = 0
    response = None
    classify_failed = False
    while response is None:
        cfg_kwargs: Dict[str, Any] = {
            "system_instruction": system_instruction,
            "temperature": 0.2,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
            "response_json_schema": schema,
        }
        if use_thinking:
            cfg_kwargs["thinking_config"] = _thinking_config_for_model(model_name)
        config = types.GenerateContentConfig(**cfg_kwargs)
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
                        "Failed to classify message after %s retries: %s",
                        _GEMINI_MAX_RETRIES,
                        e,
                    )
                    classify_failed = True
                    break
                delay = min(2.0**api_retry_count + random.random(), 120.0)
                logger.warning(
                    "Gemini API error (retry %s/%s): %s; sleeping %.1fs",
                    api_retry_count,
                    _GEMINI_MAX_RETRIES,
                    e,
                    delay,
                )
                time.sleep(delay)
                continue
            raise

    if classify_failed:
        return None, 0, 0

    in_tok = out_tok = 0
    um = getattr(response, "usage_metadata", None)
    if um:
        in_tok = getattr(um, "prompt_token_count", None) or 0
        out_tok = getattr(um, "candidates_token_count", None) or 0

    text = getattr(response, "text", None)
    if not text and response.candidates:
        text = response.candidates[0].content.parts[0].text
    if not text:
        return "", in_tok, out_tok
    return text, in_tok, out_tok


def run_test_prompt_classification(
    mailbox: MailboxPipelineConfig,
    email: Dict[str, Any],
) -> Dict[str, Any]:
    """
    One-off classification for admin UI (test prompt). Returns model JSON, resolved
    category, token usage, and optional error/warning strings. Does not call Graph.
    """
    if not mailbox.categories:
        raise ValueError("At least one category is required.")

    allowed = {c.name for c in mailbox.categories}
    default_cat = mailbox.categories[0].name

    rule_cat = try_classify_by_subject_rules(mailbox, email)
    if rule_cat is not None:
        return {
            "model_json": {"category": rule_cat},
            "category_resolved": rule_cat,
            "usage": {"prompt_token_count": 0, "candidates_token_count": 0},
            "error": None,
            "warning": "Classified via subject rule (no model call).",
            "raw_text": None,
        }

    client, model_name = _make_genai_client(mailbox)
    text, in_tok, out_tok = _generate_classification_response_text(
        client, model_name, mailbox, email
    )
    usage = {"prompt_token_count": in_tok, "candidates_token_count": out_tok}

    if text is None:
        return {
            "model_json": None,
            "category_resolved": default_cat,
            "usage": usage,
            "error": "Gemini request failed after retries.",
            "warning": None,
            "raw_text": None,
        }

    if not text.strip():
        return {
            "model_json": None,
            "category_resolved": default_cat,
            "usage": usage,
            "error": "Empty model response (e.g. safety filters).",
            "warning": None,
            "raw_text": None,
        }

    raw = text.strip()
    if raw.startswith("```"):
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)

    try:
        model_json = json.loads(raw)
    except json.JSONDecodeError as e:
        return {
            "model_json": None,
            "category_resolved": default_cat,
            "usage": usage,
            "error": f"Model output is not valid JSON: {e}",
            "warning": None,
            "raw_text": text[:8000],
        }

    if not isinstance(model_json, dict):
        return {
            "model_json": None,
            "category_resolved": default_cat,
            "usage": usage,
            "error": "Model JSON root must be an object.",
            "warning": None,
            "raw_text": text[:8000],
        }

    cat_val = model_json.get("category")
    cat = cat_val if isinstance(cat_val, str) else None
    warning: Optional[str] = None
    if cat is None:
        warning = "Missing or non-string category in model JSON; using default category."
        resolved = default_cat
    elif cat not in allowed:
        warning = f"Category {cat!r} is not in the taxonomy; coerced to {default_cat!r}."
        resolved = default_cat
    else:
        resolved = cat

    return {
        "model_json": model_json,
        "category_resolved": resolved,
        "usage": usage,
        "error": None,
        "warning": warning,
        "raw_text": None,
    }


def classify_graph_messages(
    messages: List[Dict[str, Any]],
    mailbox: MailboxPipelineConfig,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Classify one message per model call. Returns dicts with ``email_id`` (set in
    Python) and ``category`` (from the model), plus token usage aggregates.
    """
    if not messages:
        return [], {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "llm_calls_with_usage_metadata": 0,
            "classifications_with_zero_usage": 0,
            "avg_input_tokens_per_email": 0.0,
            "avg_output_tokens_per_email": 0.0,
        }

    client, model_name = _make_genai_client(mailbox)
    allowed = {c.name for c in mailbox.categories}
    default_cat = mailbox.categories[0].name if mailbox.categories else "Information"

    to_classify = [m for m in messages if m.get("id")]
    if not to_classify:
        return [], {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "llm_calls_with_usage_metadata": 0,
            "classifications_with_zero_usage": 0,
            "avg_input_tokens_per_email": 0.0,
            "avg_output_tokens_per_email": 0.0,
        }

    def _classify_one(email: Dict[str, Any]) -> Tuple[Dict[str, Any], int, int]:
        """One isolated model call per email (prompt built only from this message)."""
        key = str(email["id"])
        text, in_tok, out_tok = _generate_classification_response_text(
            client, model_name, mailbox, email
        )
        if text is None:
            pred_fail: Dict[str, Any] = {"email_id": key, "category": default_cat}
            return pred_fail, 0, 0

        cat: str | None = None
        try:
            if not text.strip():
                raise ValueError(
                    "Empty model response (likely blocked by safety filters)"
                )
            cat = _parse_classification_response(text)
        except Exception as exc:
            logger.error("Failed to parse Gemini output: %s", exc, exc_info=True)
            cat = default_cat

        if cat not in allowed:
            cat = default_cat
        out = {"email_id": key, "category": cat}
        return out, in_tok, out_tok

    workers = max(1, min(_CLASSIFICATION_POOL_WORKERS, len(to_classify)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_classify_one, to_classify))

    all_preds: List[Dict[str, Any]] = []
    total_in = 0
    total_out = 0
    n_with_usage = 0
    for pred, in_tok, out_tok in rows:
        all_preds.append(pred)
        total_in += in_tok
        total_out += out_tok
        if in_tok or out_tok:
            n_with_usage += 1

    n = len(all_preds)
    usage = {
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "llm_calls_with_usage_metadata": n_with_usage,
        "classifications_with_zero_usage": n - n_with_usage,
        # Averages exclude 0/0 failure rows so retries and hard failures do not skew costs.
        "avg_input_tokens_per_email": (
            round(total_in / n_with_usage, 2) if n_with_usage else 0.0
        ),
        "avg_output_tokens_per_email": (
            round(total_out / n_with_usage, 2) if n_with_usage else 0.0
        ),
    }
    return all_preds, usage


def _zero_usage_batch() -> Dict[str, Any]:
    return {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "llm_calls_with_usage_metadata": 0,
        "classifications_with_zero_usage": 0,
        "avg_input_tokens_per_email": 0.0,
        "avg_output_tokens_per_email": 0.0,
    }


def classify_messages_subject_then_ai(
    messages: List[Dict[str, Any]],
    mailbox: MailboxPipelineConfig,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Subject LIKE rules first; non-matching messages use Gemini (same shape as classify_graph_messages)."""
    if not messages:
        return [], _zero_usage_batch()
    if not mailbox.subject_classify_enabled or not mailbox.subject_classify_rules:
        return classify_graph_messages(messages, mailbox)
    subject_preds, for_ai = partition_messages_by_subject_rules(messages, mailbox)
    if not for_ai:
        return list(subject_preds), _zero_usage_batch()
    ai_preds, usage = classify_graph_messages(for_ai, mailbox)
    return list(subject_preds) + list(ai_preds), usage
