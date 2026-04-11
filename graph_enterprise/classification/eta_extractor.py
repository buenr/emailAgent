"""Extract reference numbers (order, BOL, PRO, truck, trailer) from ETA emails using Gemini function calling."""

from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from ..config.models import MailboxPipelineConfig
from .gemini_category_batch import (
    _GEMINI_MAX_RETRIES,
    _api_rejects_thinking_config,
    _make_genai_client,
    _model_is_flash_lite,
    _sanitize_for_prompt,
    body_text_for_classification,
    effective_gemini_model_from_env,
)

logger = logging.getLogger(__name__)

# Function declaration for Gemini function calling.
EXTRACT_REF_NUMBERS_FUNCTION = {
    "name": "extract_reference_numbers",
    "description": (
        "Extract order, BOL, PRO, truck, and trailer numbers from an ETA or "
        "tracking email. Call this function with the numbers you find in the email."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "order_number": {
                "type": "string",
                "description": "Order number (e.g. ORD-12345, 12345678)",
            },
            "bol_number": {
                "type": "string",
                "description": "Bill of lading number (e.g. BOL-67890, 987654)",
            },
            "pro_number": {
                "type": "string",
                "description": "PRO number (e.g. PRO-11111, 111222333)",
            },
            "truck_number": {
                "type": "string",
                "description": "Truck/tractor unit number (e.g. T-2222, 5001)",
            },
            "trailer_number": {
                "type": "string",
                "description": "Trailer unit number (e.g. TL-3333, 6002)",
            },
        },
        "required": [],
    },
}

_EXTRACTOR_SYSTEM_INSTRUCTION = (
    "You are a logistics data extraction assistant. Your job is to find reference "
    "numbers in freight/trucking emails. When you find order numbers, BOL numbers, "
    "PRO numbers, truck unit numbers, or trailer unit numbers in the email, call the "
    "extract_reference_numbers function with the values you find. If a number type is "
    "not present, omit it. Do not guess or invent numbers."
)


@dataclass
class ExtractedReferenceNumbers:
    order_number: Optional[str] = None
    bol_number: Optional[str] = None
    pro_number: Optional[str] = None
    truck_number: Optional[str] = None
    trailer_number: Optional[str] = None

    def has_any(self) -> bool:
        return any(
            v is not None and v.strip()
            for v in (
                self.order_number,
                self.bol_number,
                self.pro_number,
                self.truck_number,
                self.trailer_number,
            )
        )

    def to_dict(self) -> Dict[str, str]:
        return {k: v for k, v in {
            "order_number": self.order_number,
            "bol_number": self.bol_number,
            "pro_number": self.pro_number,
            "truck_number": self.truck_number,
            "trailer_number": self.trailer_number,
        }.items() if v is not None and v.strip()}


def _default_thinking_budget() -> int:
    return int(os.environ.get("GEMINI_THINKING_BUDGET", "8192"))


def _thinking_config_for_model(model_name: str) -> types.ThinkingConfig:
    if _model_is_flash_lite(model_name):
        return types.ThinkingConfig(thinking_budget=_default_thinking_budget())
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)


def extract_reference_numbers(
    email: Dict[str, Any],
    mailbox: MailboxPipelineConfig,
) -> ExtractedReferenceNumbers:
    """
    Use Gemini function calling to extract reference numbers from an ETA email.

    Returns an ExtractedReferenceNumbers with whatever numbers the model found.
    If the model does not call the function (e.g. no numbers in the email),
    returns an empty ExtractedReferenceNumbers.
    """
    client, model_name = _make_genai_client(mailbox)

    subject = _sanitize_for_prompt(str(email.get("subject", "")))
    body = body_text_for_classification(email)
    user_message = (
        f"Subject: {subject}\n\n"
        f"Body:\n{body}"
    )

    contents = [types.Content(role="user", parts=[types.Part(text=user_message)])]

    tool = types.Tool(function_declarations=[EXTRACT_REF_NUMBERS_FUNCTION])
    config_kwargs: Dict[str, Any] = {
        "system_instruction": _EXTRACTOR_SYSTEM_INSTRUCTION,
        "temperature": 0.0,
        "max_output_tokens": 2048,
        "tools": [tool],
        "tool_config": types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY,
                allowed_function_names=["extract_reference_numbers"],
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
                        "ETA extractor failed after %s retries: %s",
                        _GEMINI_MAX_RETRIES,
                        e,
                    )
                    return ExtractedReferenceNumbers()
                delay = min(2.0 ** api_retry_count + random.random(), 60.0)
                logger.warning(
                    "ETA extractor API error (retry %s/%s): %s; sleeping %.1fs",
                    api_retry_count,
                    _GEMINI_MAX_RETRIES,
                    e,
                    delay,
                )
                time.sleep(delay)
                continue
            logger.error("ETA extractor non-retryable error: %s", e)
            return ExtractedReferenceNumbers()

    if not response.candidates:
        return ExtractedReferenceNumbers()

    parts = response.candidates[0].content.parts
    for part in parts:
        fc = getattr(part, "function_call", None) or getattr(part, "functionCall", None)
        if fc is None:
            continue
        name = getattr(fc, "name", None)
        if name != "extract_reference_numbers":
            continue
        args = dict(getattr(fc, "args", {}) or {})
        return ExtractedReferenceNumbers(
            order_number=args.get("order_number"),
            bol_number=args.get("bol_number"),
            pro_number=args.get("pro_number"),
            truck_number=args.get("truck_number"),
            trailer_number=args.get("trailer_number"),
        )

    return ExtractedReferenceNumbers()


def _retryable_genai_error(exc: BaseException) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return getattr(exc, "code", None) == 429
    return False
